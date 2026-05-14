"""
Tests for the desktop pet.

Covers three layers without ever opening a real window:

* ``core.state.pet_settings`` — JSON round-trip + atomic save behaviour
* ``core.ui.pet_painter``    — geometry helpers, halo intensity, eye
                                  clamping, hatch progress bounds
* ``core.ui.pet_controller`` — bus event → state mapping, transient
                                  auto-revert, mute gate, cursor tracking

Run:
    .venv\\Scripts\\python scripts\\test_pet.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure a QApplication exists *before* we import anything that
# touches QWidget. QApplication (rather than the lighter
# QGuiApplication / QCoreApplication) is required because the
# show_pet() regression test below instantiates the real AyEyePet
# QWidget — and QWidget.show() needs the full QApplication
# event-loop machinery to attach to the platform's offscreen
# rendering pipeline. Headless on Windows works fine.
from PyQt6.QtCore import QCoreApplication  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
_app = QApplication.instance() or QApplication(sys.argv)

from core.state import pet_settings as pet_settings_module  # noqa: E402
from core.state.pet_settings import PetSettings, load, save  # noqa: E402
from core.ui.pet_painter import (  # noqa: E402
    PUPIL_TRACK_RANGE,
    TRANSIENT_DURATION_MS,
    PaintInput,
    PetState,
    bob_offset_y,
    clamp_eye_target,
    halo_color,
    halo_intensity,
)
from core.ui import pet_styles  # noqa: E402
from core.ui.pet_controller import PetController, _EVENT_MAP  # noqa: E402


PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── pet_settings ──────────────────────────────────────────────────


def test_settings_defaults_match_design():
    s = PetSettings()
    check(s.hatched is False, "default hatched=False (hatch animation plays on first show)")
    check(s.position_x is None and s.position_y is None,
          "default position=None means 'snap to default corner'")
    check(s.muted is False, "default muted=False (pet reacts to events)")
    check(s.visible is False,
          "default visible=False (pet hidden until user types 'pet')")
    check(s.name == "Ay", "default pet name is 'Ay'")
    check(s.style == "pixel",
          "default style is 'pixel' (Tamagotchi mascot)")


def test_settings_round_trip_through_json():
    s = PetSettings(hatched=True, position_x=42, position_y=99,
                    muted=True, name="Spark", visible=False, style="orb")
    revived = PetSettings.from_json(s.to_json())
    check(revived == s, "settings survive JSON round-trip unchanged")
    check(revived.style == "orb", "non-default style persists through JSON")


def test_settings_from_json_ignores_unknown_keys():
    raw = '{"hatched":true,"position_x":1,"future_field":"ignore me"}'
    s = PetSettings.from_json(raw)
    check(s.hatched is True and s.position_x == 1,
          "known keys parsed through despite stray future_field")


def test_settings_from_json_handles_garbage():
    check(PetSettings.from_json("not valid json").hatched is False,
          "garbage JSON falls back to defaults without raising")
    check(PetSettings.from_json("").hatched is False,
          "empty string falls back to defaults")


def test_settings_save_then_load_roundtrip_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "pet_settings.json")
        original = PetSettings(hatched=True, position_x=120, position_y=240)
        ok = save(original, path=path)
        check(ok is True, "save() reports success")
        revived = load(path=path)
        check(revived == original,
              "settings written then read from disk are identical")


def test_settings_load_returns_defaults_for_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "no_such_file.json")
        s = load(path=path)
        check(s == PetSettings(),
              "missing file -> defaults (no exception)")


def test_settings_save_atomic_does_not_leave_tmp_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "pet_settings.json")
        save(PetSettings(name="Atomic"), path=path)
        siblings = os.listdir(tmp)
        leftover = [n for n in siblings if n.endswith(".tmp")]
        check(leftover == [],
              f"no .tmp file left after save (got {leftover})")


# ── pet_painter geometry ─────────────────────────────────────────


def test_clamp_eye_target_within_range():
    dx, dy = clamp_eye_target(0.5, -1.0)
    check(dx == 0.5 and dy == -1.0,
          "values inside the tracking range pass through unchanged")


def test_clamp_eye_target_clamps_extreme_values():
    dx, dy = clamp_eye_target(50.0, -50.0)
    check(dx == PUPIL_TRACK_RANGE and dy == -PUPIL_TRACK_RANGE,
          "out-of-range pupil offsets clamped to +/-PUPIL_TRACK_RANGE")


# ── Style registry & per-style smoke tests ────────────────────


def test_style_registry_has_all_expected_styles():
    names = pet_styles.list_styles()
    # The three procedural styles plus the two hand-encoded pixel-art
    # pets (shiba + cat) that we crafted from the Codex Pets reference.
    expected = {"pixel", "ascii", "orb", "shiba", "cat"}
    missing = expected - set(names)
    check(not missing,
          f"all expected styles registered (missing: {missing})")


def test_style_default_is_pixel():
    check(pet_styles.DEFAULT_STYLE == "pixel",
          "default style is 'pixel'")
    check(pet_styles.has(pet_styles.DEFAULT_STYLE),
          "DEFAULT_STYLE references a real registered style")


def test_style_get_falls_back_to_default_for_unknown_name():
    style = pet_styles.get("this-style-will-never-exist")
    check(style.name == pet_styles.DEFAULT_STYLE,
          "unknown style name falls back to default")


def test_each_style_has_valid_metadata():
    for name in pet_styles.list_styles():
        s = pet_styles.get(name)
        check(s.name == name, f"{name}: PetStyle.name matches registry key")
        check(isinstance(s.description, str) and len(s.description) > 10,
              f"{name}: has a non-trivial description")
        w, h = s.widget_size
        check(40 <= w <= 400 and 40 <= h <= 400,
              f"{name}: widget_size {s.widget_size} is in a sane range")
        check(callable(s.draw), f"{name}: draw is callable")


def test_each_style_has_descriptive_pairs():
    pairs = pet_styles.list_descriptions()
    check(len(pairs) == len(pet_styles.list_styles()),
          "list_descriptions() returns one entry per registered style")
    for name, desc in pairs:
        check(isinstance(desc, str) and len(desc) > 0,
              f"{name}: description is a non-empty string")


def test_each_style_draws_every_state_without_raising():
    """Smoke-test: every registered style must successfully render
    every PetState onto an offscreen QImage. Catches uninitialised
    palettes, KeyErrors in lookup tables, geometry off-by-ones, etc.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter

    for name in pet_styles.list_styles():
        style = pet_styles.get(name)
        w, h = style.widget_size
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        for state in PetState:
            for hatch in (0.0, 0.5, 1.0):
                p = PaintInput(state=state, time_ms=1234,
                               hatch_progress=hatch)
                painter = QPainter(img)
                try:
                    style.draw(painter, p)
                finally:
                    painter.end()
        check(True, f"{name}: draws every PetState without raising")


# ── Sprite engine + hand-encoded pixel-art pets ────────────────


def test_sprite_engine_validates_bitmap_geometry():
    """A bitmap with mismatched row widths must fail fast (at import
    time, not silently mid-paint).
    """
    from core.ui.pet_styles import _sprite_engine as se
    bad = ("xxxx", "xxx", "xxxx")
    raised = False
    try:
        se.validate_bitmap(bad, name="bad")
    except ValueError as exc:
        raised = "width" in str(exc).lower() or "row" in str(exc).lower()
    check(raised, "validate_bitmap() raises on ragged rows with a useful message")


def test_sprite_engine_validates_palette_coverage():
    """Every non-``.`` char in a bitmap must have a palette entry."""
    from PyQt6.QtGui import QColor

    from core.ui.pet_styles import _sprite_engine as se
    bitmap = ("xz", ".x")
    palette = {"x": QColor(0, 0, 0)}        # missing 'z' on purpose
    raised = False
    try:
        se.validate_palette_keys(bitmap, palette, name="b")
    except ValueError as exc:
        raised = "z" in str(exc)
    check(raised, "validate_palette_keys() reports the missing key")


def test_sprite_engine_palette_keys_used_excludes_transparent():
    from core.ui.pet_styles import _sprite_engine as se
    keys = se.palette_keys_used(("a.b", "..a", "ccc"))
    check(keys == ["a", "b", "c"],
          f"palette_keys_used() returns sorted non-'.' chars (got {keys})")


def test_shiba_body_is_28x28_grid():
    from core.ui.pet_styles import shiba
    check(len(shiba.BODY) == 28 and all(len(row) == 28 for row in shiba.BODY),
          "shiba body bitmap is a perfectly square 28x28 grid")


def test_cat_body_is_28x28_grid():
    from core.ui.pet_styles import cat
    check(len(cat.BODY) == 28 and all(len(row) == 28 for row in cat.BODY),
          "cat body bitmap is a perfectly square 28x28 grid")


def test_shiba_palette_covers_every_pixel_in_body():
    """No silent fallback colors — every body pixel must resolve."""
    from core.ui.pet_styles import _sprite_engine as se
    from core.ui.pet_styles import shiba
    used = set(se.palette_keys_used(shiba.BODY))
    missing = used - set(shiba.PALETTE.keys())
    check(not missing,
          f"every shiba body pixel has a palette entry (missing: {missing})")


def test_cat_palette_covers_every_pixel_in_body():
    from core.ui.pet_styles import _sprite_engine as se
    from core.ui.pet_styles import cat
    used = set(se.palette_keys_used(cat.BODY))
    missing = used - set(cat.PALETTE.keys())
    check(not missing,
          f"every cat body pixel has a palette entry (missing: {missing})")


def test_shiba_state_overlays_use_only_palette_keys():
    """Every overlay cell's character must exist in the palette too —
    otherwise the engine silently skips painting it, which would
    leave the pet missing an eye or a nose at runtime.
    """
    from core.ui.pet_styles import shiba
    overlays = [
        shiba.NOSE, shiba.EYES_OPEN, shiba.EYES_WIDE, shiba.EYES_THINK,
        shiba.EYES_NARROW, shiba.EYES_HAPPY, shiba.EYES_DEAD, shiba.EYES_CLOSED,
        shiba.MOUTH_SMILE, shiba.MOUTH_BIG_SMILE, shiba.MOUTH_FROWN,
        shiba.MOUTH_FLAT, shiba.MOUTH_OPEN_O,
        shiba.SPARKLE, shiba.SWEAT_DROP,
    ]
    palette_keys = set(shiba.PALETTE.keys())
    for i, overlay in enumerate(overlays):
        bad = {ch for ch in overlay.values() if ch not in palette_keys}
        check(not bad,
              f"shiba overlay #{i} uses unknown palette keys: {bad}")


def test_cat_state_overlays_use_only_palette_keys():
    from core.ui.pet_styles import cat
    overlays = [
        cat.NOSE, cat.WHISKERS,
        cat.EYES_OPEN, cat.EYES_WIDE, cat.EYES_THINK,
        cat.EYES_NARROW, cat.EYES_HAPPY, cat.EYES_DEAD, cat.EYES_CLOSED,
        cat.MOUTH_SMILE, cat.MOUTH_BIG_SMILE, cat.MOUTH_FROWN,
        cat.MOUTH_FLAT, cat.MOUTH_OPEN_O,
        cat.SPARKLE, cat.SWEAT_DROP,
    ]
    palette_keys = set(cat.PALETTE.keys())
    for i, overlay in enumerate(overlays):
        bad = {ch for ch in overlay.values() if ch not in palette_keys}
        check(not bad,
              f"cat overlay #{i} uses unknown palette keys: {bad}")


def test_shiba_overlay_coordinates_stay_inside_grid():
    """An overlay cell at (col, row) outside the 28x28 grid would be
    blitted off-canvas. Cheap to verify, prevents head-scratching
    'why is half my pet missing on a tiny widget' bugs later.
    """
    from core.ui.pet_styles import shiba
    overlays = [
        shiba.NOSE, shiba.EYES_OPEN, shiba.EYES_WIDE, shiba.EYES_THINK,
        shiba.EYES_NARROW, shiba.EYES_HAPPY, shiba.EYES_DEAD, shiba.EYES_CLOSED,
        shiba.MOUTH_SMILE, shiba.MOUTH_BIG_SMILE, shiba.MOUTH_FROWN,
        shiba.MOUTH_FLAT, shiba.MOUTH_OPEN_O,
        shiba.SPARKLE, shiba.SWEAT_DROP,
    ]
    for i, overlay in enumerate(overlays):
        bad = [(c, r) for (c, r) in overlay.keys()
               if not (0 <= c < 28 and 0 <= r < 28)]
        check(not bad,
              f"shiba overlay #{i} has out-of-grid cells: {bad[:3]}")


def test_cat_overlay_coordinates_stay_inside_grid():
    from core.ui.pet_styles import cat
    overlays = [
        cat.NOSE, cat.WHISKERS,
        cat.EYES_OPEN, cat.EYES_WIDE, cat.EYES_THINK,
        cat.EYES_NARROW, cat.EYES_HAPPY, cat.EYES_DEAD, cat.EYES_CLOSED,
        cat.MOUTH_SMILE, cat.MOUTH_BIG_SMILE, cat.MOUTH_FROWN,
        cat.MOUTH_FLAT, cat.MOUTH_OPEN_O,
        cat.SPARKLE, cat.SWEAT_DROP,
    ]
    for i, overlay in enumerate(overlays):
        bad = [(c, r) for (c, r) in overlay.keys()
               if not (0 <= c < 28 and 0 <= r < 28)]
        check(not bad,
              f"cat overlay #{i} has out-of-grid cells: {bad[:3]}")


def test_shiba_and_cat_share_identical_widget_geometry():
    """The two pixel-art pets share the same widget footprint so
    switching between them at runtime doesn't reshuffle the desktop
    pet's position or size.
    """
    s = pet_styles.get("shiba")
    c = pet_styles.get("cat")
    check(s.widget_size == c.widget_size,
          f"shiba and cat have matching widget_size "
          f"(shiba={s.widget_size}, cat={c.widget_size})")


def test_bob_offset_zero_during_hatching():
    check(bob_offset_y(PetState.HATCHING, 0) == 0.0,
          "no vertical bob while hatching (egg sits still)")
    check(bob_offset_y(PetState.HATCHING, 12345) == 0.0,
          "bob remains 0 across all hatch frames")


def test_bob_offset_oscillates_for_idle():
    samples = [bob_offset_y(PetState.IDLE, t) for t in range(0, 4000, 50)]
    check(min(samples) <= -1.0 and max(samples) >= 1.0,
          "idle bob produces a meaningful sine oscillation")
    check(all(-3.0 <= v <= 3.0 for v in samples),
          "idle bob amplitude bounded by +/-3 px (gentler than v1)")




def test_halo_intensity_within_unit_interval_for_every_state():
    for state in PetState:
        for t in (0, 100, 1000, 5000, 10000):
            v = halo_intensity(state, t)
            assert 0.0 <= v <= 1.0, f"{state} at {t}ms gave {v}"
    check(True, "halo_intensity() stays in [0, 1] for every state across time")


def test_halo_intensity_idle_is_lower_than_acting():
    # Average over a representative window so we don't compare two
    # cherry-picked sine peaks.
    avg_idle   = sum(halo_intensity(PetState.IDLE,   t) for t in range(0, 4000, 50)) / 80
    avg_acting = sum(halo_intensity(PetState.ACTING, t) for t in range(0, 4000, 50)) / 80
    check(avg_idle < avg_acting,
          f"acting halo is brighter on average than idle ({avg_idle:.2f} < {avg_acting:.2f})")


def test_halo_color_distinct_per_primary_mood():
    # The theme intentionally reuses colors for paired moods:
    #   ACTING == SUCCESS (both green, "good things happening")
    #   LISTENING == FAILED (both red, "alarm")
    # We only assert that the three *primary* mood families are visually
    # distinct, which is what the user actually perceives.
    listening = halo_color(PetState.LISTENING).rgb()
    thinking  = halo_color(PetState.THINKING).rgb()
    acting    = halo_color(PetState.ACTING).rgb()
    distinct = {listening, thinking, acting}
    check(len(distinct) == 3,
          f"the three primary mood halos are distinct (got {len(distinct)})")
    # IDLE and THINKING intentionally share the cyan brand color; the
    # painter distinguishes them via intensity + sparkles, validated by
    # ``test_halo_intensity_idle_is_lower_than_acting``. We just need
    # the SLEEPING halo to be visibly different from IDLE so muting is
    # legible.
    idle = halo_color(PetState.IDLE).rgb()
    sleeping = halo_color(PetState.SLEEPING).rgb()
    check(sleeping != idle,
          "sleeping halo is dimmer/different from idle so muting is visible")


def test_paint_input_defaults_are_safe():
    p = PaintInput()
    check(p.state == PetState.IDLE, "default PaintInput state is IDLE")
    check(p.body_alpha == 1.0 and p.hatch_progress == 0.0,
          "default body_alpha=1, hatch_progress=0 (no animations in flight)")


# ── pet_controller ─────────────────────────────────────────────


class _FakeBus:
    """Records subscriptions; lets tests fire events synchronously."""

    def __init__(self):
        self.subs: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        self.subs.setdefault(event_type, []).append(callback)

    def publish(self, event_type: str, data=None):
        for cb in self.subs.get(event_type, []):
            cb(data)


class _ManualClock:
    def __init__(self, start: int = 0):
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


def _make_controller(muted: bool = False, start_ms: int = 0):
    bus = _FakeBus()
    clock = _ManualClock(start_ms)
    ctl = PetController(bus=bus, clock_ms=clock, muted=muted)
    ctl.attach_bus()
    return ctl, bus, clock


def test_controller_starts_in_hatching():
    ctl, _, _ = _make_controller()
    check(ctl.state == PetState.HATCHING,
          "freshly built controller starts in HATCHING")


def test_controller_hatch_complete_transitions_to_idle():
    ctl, _, _ = _make_controller()
    ctl.hatch_complete()
    check(ctl.state == PetState.IDLE,
          "hatch_complete() transitions HATCHING -> IDLE")


def test_controller_hatch_complete_respects_muted():
    ctl, _, _ = _make_controller(muted=True)
    ctl.hatch_complete()
    check(ctl.state == PetState.SLEEPING,
          "muted pet wakes from hatch into SLEEPING, not IDLE")


def test_controller_event_map_covers_all_critical_events():
    expected = {
        "VOICE_RECORDING_START", "VOICE_RECORDING_STOP",
        "BRAIN_THINKING", "BRAIN_RESPONDED", "BRAIN_ERROR",
        "ACTION_STARTED", "ACTION_COMPLETED", "ACTION_ABORTED",
        "EMERGENCY_STOP", "AI_GREETING", "SAFE_NO_ACTION",
    }
    missing = expected - set(_EVENT_MAP.keys())
    check(not missing, f"controller maps every critical bus event (missing: {missing})")


def test_controller_listening_on_voice_recording_start():
    ctl, bus, _ = _make_controller()
    ctl.hatch_complete()
    bus.publish("VOICE_RECORDING_START")
    check(ctl.state == PetState.LISTENING,
          "VOICE_RECORDING_START -> LISTENING")


def test_controller_thinking_on_voice_recording_stop():
    ctl, bus, _ = _make_controller()
    ctl.hatch_complete()
    bus.publish("VOICE_RECORDING_STOP")
    check(ctl.state == PetState.THINKING,
          "VOICE_RECORDING_STOP -> THINKING")


def test_controller_acting_on_action_started():
    ctl, bus, _ = _make_controller()
    ctl.hatch_complete()
    bus.publish("ACTION_STARTED", {"type": "click"})
    check(ctl.state == PetState.ACTING,
          "ACTION_STARTED -> ACTING")


def test_controller_success_then_idle_transient_revert():
    ctl, bus, clock = _make_controller(start_ms=1000)
    ctl.hatch_complete()
    bus.publish("ACTION_COMPLETED", {"type": "click"})
    check(ctl.state == PetState.SUCCESS,
          "ACTION_COMPLETED -> SUCCESS (transient)")
    # Still inside the transient window.
    clock.advance(TRANSIENT_DURATION_MS - 100)
    ctl.tick()
    check(ctl.state == PetState.SUCCESS,
          "before transient window expires, state stays SUCCESS")
    # Past the transient window.
    clock.advance(200)
    ctl.tick()
    check(ctl.state == PetState.IDLE,
          "after transient window, controller reverts to IDLE")


def test_controller_failed_transient_revert():
    ctl, bus, clock = _make_controller(start_ms=2000)
    ctl.hatch_complete()
    bus.publish("BRAIN_ERROR", {"reason": "boom"})
    check(ctl.state == PetState.FAILED,
          "BRAIN_ERROR -> FAILED (transient)")
    clock.advance(TRANSIENT_DURATION_MS + 100)
    ctl.tick()
    check(ctl.state == PetState.IDLE,
          "FAILED reverts to IDLE after transient window")


def test_controller_mute_gate_overrides_events():
    ctl, bus, _ = _make_controller(muted=True)
    ctl.hatch_complete()
    bus.publish("VOICE_RECORDING_START")
    bus.publish("ACTION_STARTED")
    bus.publish("ACTION_COMPLETED")
    check(ctl.state == PetState.SLEEPING,
          "muted pet stays in SLEEPING regardless of incoming events")


def test_controller_unmuting_returns_to_idle():
    ctl, _, _ = _make_controller(muted=True)
    ctl.hatch_complete()
    ctl.set_muted(False)
    check(ctl.state == PetState.IDLE,
          "set_muted(False) wakes the pet to IDLE")


def test_controller_set_muted_true_sleeps_immediately():
    ctl, _, _ = _make_controller()
    ctl.hatch_complete()
    ctl.set_muted(True)
    check(ctl.state == PetState.SLEEPING,
          "set_muted(True) sleeps the pet immediately")


def test_controller_unknown_event_is_ignored():
    ctl, bus, _ = _make_controller()
    ctl.hatch_complete()
    state_before = ctl.state
    ctl.on_event("SOME_RANDOM_UNKNOWN_EVENT")
    check(ctl.state == state_before,
          "unknown events do not change state")


def test_controller_cursor_tracking_clamps_to_pupil_range():
    ctl, _, _ = _make_controller()
    # A cursor very close to the pet, far to the right, should produce
    # a small positive dx and dy that respects the pupil range.
    ctl.update_cursor(dx_pixels=50, dy_pixels=20, proximity_radius=200)
    dx, dy = ctl.eye_target
    check(abs(dx) <= PUPIL_TRACK_RANGE and abs(dy) <= PUPIL_TRACK_RANGE,
          f"pupil offset clamped to PUPIL_TRACK_RANGE (got dx={dx:.2f}, dy={dy:.2f})")


def test_controller_cursor_far_away_recenters_eyes():
    ctl, _, _ = _make_controller()
    ctl.update_cursor(dx_pixels=0, dy_pixels=0)
    ctl.update_cursor(dx_pixels=2000, dy_pixels=2000, proximity_radius=200)
    dx, dy = ctl.eye_target
    check(dx == 0.0 and dy == 0.0,
          "cursor outside proximity radius re-centers eyes (lose interest)")


def test_controller_cursor_direction_signs_match_movement():
    ctl, _, _ = _make_controller()
    ctl.update_cursor(dx_pixels=100, dy_pixels=-50, proximity_radius=300)
    dx, dy = ctl.eye_target
    check(dx > 0 and dy < 0,
          f"cursor right-and-up -> pupils right-and-up (got {dx:.2f}, {dy:.2f})")


# ── Pet widget visibility events ───────────────────────────────


class _RecordingBus:
    """Captures every published event for assertion. Subscribe is a no-op
    because the show/hide regression tests below only care about publishes.

    Distinct from the controller-tests' ``_FakeBus`` (which actually
    dispatches events to subscribers) — these widget tests only need to
    verify that ``publish()`` was called with the right payload, so a
    pure recorder is simpler and safer.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def subscribe(self, *_a, **_kw) -> None:
        pass

    def publish(self, name: str, data=None) -> None:
        self.events.append((name, data))

    def event_names(self) -> list[str]:
        return [n for n, _ in self.events]


class _FakeSettingsModule:
    """Stand-in for ``core.state.pet_settings`` that never writes to disk."""

    def __init__(self, settings: PetSettings) -> None:
        self.pet_settings = settings
        self.save_count = 0

    def save(self, _s) -> bool:
        self.save_count += 1
        return True


def _make_pet(visible_initially: bool = False) -> tuple[object, _RecordingBus, _FakeSettingsModule]:
    """Spin up a real AyEyePet wired to a recording bus + fake settings module.

    The widget is created but never actually shown on screen during the
    test (we keep it as a freshly-constructed widget and call .show_pet()
    explicitly to exercise the visibility event). Returns the trio so the
    caller can clean up via ``pet.deleteLater()``.
    """
    from core.ui.pet_widget import AyEyePet
    settings = PetSettings(hatched=True, visible=visible_initially)
    settings_mod = _FakeSettingsModule(settings)
    fake_bus = _RecordingBus()
    pet = AyEyePet(bus_obj=fake_bus, settings_module=settings_mod)
    return pet, fake_bus, settings_mod


def test_show_pet_publishes_visibility_event():
    """Regression: pet.show_pet() must publish PET_VISIBILITY_CHANGED.

    The bug this guards against: ``main.py`` was previously calling raw
    ``QWidget.show()`` on a pet whose persisted ``visible`` flag was True.
    That bypassed ``show_pet()`` and skipped the bus publish, so the
    dashboard never learned the pet had taken over the status role and
    the IDLE/SYSTEM pill bar stayed floating on top of the visible pet.
    """
    pet, fake_bus, _ = _make_pet(visible_initially=False)
    try:
        pet.show_pet()
        names = fake_bus.event_names()
        check("PET_VISIBILITY_CHANGED" in names,
              "show_pet() publishes PET_VISIBILITY_CHANGED")
        payloads = [d for n, d in fake_bus.events
                    if n == "PET_VISIBILITY_CHANGED"]
        check(bool(payloads) and payloads[0].get("visible") is True,
              "the published event reports visible=True")
    finally:
        pet.hide()
        pet.deleteLater()


def test_hide_pet_publishes_visibility_false_event():
    """Symmetric: dismissing the pet must publish visible=False so the
    dashboard can put its pill bar back."""
    pet, fake_bus, _ = _make_pet(visible_initially=False)
    try:
        pet.show_pet()
        fake_bus.events.clear()
        pet._hide_pet()
        payloads = [d for n, d in fake_bus.events
                    if n == "PET_VISIBILITY_CHANGED"]
        check(bool(payloads) and payloads[0].get("visible") is False,
              "hide path publishes PET_VISIBILITY_CHANGED with visible=False")
    finally:
        pet.deleteLater()


def test_show_pet_is_idempotent_for_visibility_events():
    """Calling show_pet() twice in a row should only publish *one*
    visibility event — the second call should be a no-op for downstream
    listeners since the pet is already visible.
    """
    pet, fake_bus, _ = _make_pet(visible_initially=False)
    try:
        pet.show_pet()
        first_count = fake_bus.event_names().count("PET_VISIBILITY_CHANGED")
        pet.show_pet()
        second_count = fake_bus.event_names().count("PET_VISIBILITY_CHANGED")
        check(first_count == 1 and second_count == 1,
              "show_pet() publishes exactly once even when called twice")
    finally:
        pet.hide()
        pet.deleteLater()


# ── Command panel interception ─────────────────────────────────


def _build_pet_command_filter():
    """Reproduce the filter logic from components.py without importing
    Qt widgets (which would require a QApplication for QLineEdit). The
    *behaviour* under test is the lookup-set + the .rstrip(".!?") trim
    + the ``/pet style <name>`` prefix matching.
    """
    show_triggers = {
        "pet", "/pet", "show pet", "spawn pet", "hatch pet",
        "wake pet", "wake up pet",
    }
    hide_triggers = {
        "hide pet", "kill pet", "remove pet", "bye pet",
        "sleep pet", "stop pet",
    }
    style_list_triggers = {
        "/pet styles", "pet styles", "/pet style", "pet style",
    }

    def classify(text: str) -> str:
        lower = text.strip().lower().rstrip(".!?")
        if lower in style_list_triggers:
            return "style_list"
        for prefix in ("/pet style ", "pet style "):
            if lower.startswith(prefix):
                name = lower[len(prefix):].strip()
                if not name:
                    return "style_list"
                return f"style:{name}"
        if lower in show_triggers:
            return "show"
        if lower in hide_triggers:
            return "hide"
        return "brain"

    return classify


def test_command_filter_recognises_pet_show_phrases():
    classify = _build_pet_command_filter()
    for phrase in ("pet", "PET", "  pet  ", "pet!", "/pet",
                   "show pet", "Spawn pet", "hatch pet"):
        check(classify(phrase) == "show",
              f"'{phrase}' classified as a pet-show command")


def test_command_filter_recognises_pet_hide_phrases():
    classify = _build_pet_command_filter()
    for phrase in ("hide pet", "Hide Pet.", "kill pet", "bye pet",
                   "stop pet", "sleep pet"):
        check(classify(phrase) == "hide",
              f"'{phrase}' classified as a pet-hide command")


def test_command_filter_does_not_swallow_legitimate_input():
    classify = _build_pet_command_filter()
    # The brain must still get sentences that *contain* the word "pet"
    # but aren't direct pet-summon commands.
    for phrase in (
        "pet the cat in this game",
        "open my pet store webpage",
        "what does pet stand for",
        "click the pet button",
        "a pet shop owner walked in",
    ):
        check(classify(phrase) == "brain",
              f"'{phrase}' is a real instruction; should reach the brain")


def test_command_filter_handles_empty_and_whitespace():
    classify = _build_pet_command_filter()
    check(classify("") == "brain",
          "empty input doesn't match any pet trigger")
    check(classify("   ") == "brain",
          "whitespace-only input doesn't match any pet trigger")


def test_command_filter_recognises_pet_style_list():
    classify = _build_pet_command_filter()
    for phrase in ("/pet styles", "pet styles", "/pet style",
                   "pet style", "  PET Styles  ", "/pet style."):
        check(classify(phrase) == "style_list",
              f"'{phrase}' classified as a style-list command")


def test_command_filter_extracts_pet_style_name():
    classify = _build_pet_command_filter()
    check(classify("/pet style pixel") == "style:pixel",
          "'/pet style pixel' extracts 'pixel' as the target style")
    check(classify("pet style ascii") == "style:ascii",
          "'pet style ascii' extracts 'ascii' as the target style")
    check(classify("PET STYLE Orb") == "style:orb",
          "case-insensitive style name extraction")


def test_command_filter_does_not_treat_style_as_brain():
    classify = _build_pet_command_filter()
    # The style-set commands must short-circuit before falling through
    # to "brain" — otherwise the LLM would see them.
    check(classify("/pet style pixel") != "brain",
          "'/pet style pixel' never reaches the brain")
    check(classify("pet style nonexistent") != "brain",
          "even unknown style names are consumed locally (with a warning)")


# ── Run ────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            check(False, f"{t.__name__} raised AssertionError: {e}")
        except Exception as e:
            check(False, f"{t.__name__} crashed: {e!r}")
    print()
    print(f"=== Pet: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
