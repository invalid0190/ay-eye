"""
Tests for Mimic Mode — recorder, event compressor, skill persistence,
schema integration, and structured-output enum exposure.

Every test runs without ``pynput`` so the suite passes on a fresh checkout.
We swap a ``FakeHook`` into ``MimicRecorder`` so we can drive synthetic
events through the full pipeline.

Run:
    .venv\\Scripts\\python scripts\\test_mimic_mode.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

# Make the project root importable when run directly.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.engine.mimic_recorder import (
    MimicEvent,
    MimicRecorder,
    HookBackend,
    _NullHook,
)
from core.engine.skill_synthesizer import (
    compress_events,
    synthesize_skill,
    _normalize_key,
    _modifier_root,
)


# ── Tiny test runner ────────────────────────────────────────────────

PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Fake hook backend ───────────────────────────────────────────────


class FakeHook(HookBackend):
    """Hook that lets tests push synthetic events on demand.

    The recorder's contract is that *start* installs a callback we can
    invoke; *stop* releases it. We mirror that exactly so swapping the
    real Pynput hook for this fake is a drop-in change.
    """

    def __init__(self):
        self._on_event = None
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_start = False

    def start(self, on_event):
        self.start_calls += 1
        if self.fail_start:
            return False
        self._on_event = on_event
        return True

    def stop(self) -> None:
        self.stop_calls += 1
        self._on_event = None

    def emit(self, ev: MimicEvent) -> None:
        if self._on_event is not None:
            self._on_event(ev)


def _click(x: int, y: int, button: str = "left", t: float = 0.0) -> MimicEvent:
    return MimicEvent(
        kind="click",
        timestamp=t,
        data={"x": x, "y": y, "button": button},
    )


def _press(key: str, char: str | None = None, t: float = 0.0) -> MimicEvent:
    data: dict = {"key": key}
    if char is not None:
        data["char"] = char
    return MimicEvent(kind="key_press", timestamp=t, data=data)


def _release(key: str, t: float = 0.0) -> MimicEvent:
    return MimicEvent(kind="key_release", timestamp=t, data={"key": key})


def _scroll(dy: int, t: float = 0.0) -> MimicEvent:
    return MimicEvent(kind="scroll", timestamp=t, data={"x": 0, "y": 0, "dx": 0, "dy": dy})


# ── Helpers ─────────────────────────────────────────────────────────


def test_helpers_normalize_key_strips_prefixes_and_quotes():
    check(_normalize_key("Key.shift_l") == "shift_l",
          "Key. prefix stripped and lowercased")
    check(_normalize_key("'A'") == "a",
          "single-quoted character is unwrapped and lowercased")
    check(_normalize_key("") == "",
          "empty input -> empty output")


def test_helpers_modifier_root_collapses_left_right_variants():
    check(_modifier_root("ctrl_l") == "ctrl",
          "ctrl_l -> ctrl")
    check(_modifier_root("alt_r") == "alt",
          "alt_r -> alt")
    check(_modifier_root("shift") == "shift",
          "bare shift stays shift")
    check(_modifier_root("a") == "",
          "non-modifier key -> empty modifier root")


# ── Recorder lifecycle ──────────────────────────────────────────────


def test_recorder_starts_and_reports_active_name():
    rec = MimicRecorder(hook=FakeHook())
    ok = rec.start("morning_routine")
    check(ok is True, "start() returns True with a working backend")
    check(rec.is_recording is True, "is_recording flips to True after start()")
    check(rec.active_name == "morning_routine",
          "active_name reports the in-flight session name")
    rec.stop()


def test_recorder_refuses_double_start():
    hook = FakeHook()
    rec = MimicRecorder(hook=hook)
    rec.start("first")
    ok = rec.start("second")
    check(ok is False,
          "second start() while already recording returns False")
    check(rec.active_name == "first",
          "active_name remains the original session")
    rec.stop()


def test_recorder_returns_false_when_backend_unavailable():
    hook = FakeHook()
    hook.fail_start = True
    rec = MimicRecorder(hook=hook)
    ok = rec.start("anything")
    check(ok is False,
          "start() returns False when backend is unavailable")
    check(rec.is_recording is False,
          "recorder stays inactive when backend fails to attach")


def test_recorder_stop_returns_captured_events_and_clears_state():
    hook = FakeHook()
    rec = MimicRecorder(hook=hook)
    rec.start("demo")
    hook.emit(_click(100, 100))
    hook.emit(_press("a", char="a"))
    captured = rec.stop()
    check(len(captured) == 2,
          "stop() returns the buffered events")
    check(rec.is_recording is False,
          "recorder is no longer active after stop()")
    check(rec.event_count == 0,
          "buffer is cleared after stop()")


def test_recorder_cancel_releases_hook_and_drops_events():
    hook = FakeHook()
    rec = MimicRecorder(hook=hook)
    rec.start("trash")
    hook.emit(_click(50, 50))
    rec.cancel()
    check(rec.is_recording is False,
          "cancel() leaves the recorder idle")
    check(hook.stop_calls >= 1,
          "cancel() calls hook.stop() exactly like stop()")


def test_recorder_ignores_events_after_stop():
    hook = FakeHook()
    rec = MimicRecorder(hook=hook)
    rec.start("demo")
    hook.emit(_click(1, 1))
    rec.stop()
    # Simulate a stale event that arrived on a listener thread after stop.
    # Our FakeHook clears its callback on stop(), so emit() is a no-op,
    # but the recorder must also be defensively safe.
    check(rec.event_count == 0,
          "stale events after stop don't accidentally re-arm the buffer")


def test_null_hook_signals_unavailable_backend():
    null = _NullHook()
    started = null.start(lambda ev: None)
    check(started is False,
          "_NullHook.start always returns False")
    null.stop()  # must not raise
    check(True, "_NullHook.stop is a safe no-op")


# ── compress_events ─────────────────────────────────────────────────


def test_compress_empty_returns_empty():
    check(compress_events([]) == [],
          "no events -> no actions")


def test_compress_consecutive_chars_become_one_type_action():
    events = [
        _press("h", char="h"), _release("h"),
        _press("e", char="e"), _release("e"),
        _press("l", char="l"), _release("l"),
        _press("l", char="l"), _release("l"),
        _press("o", char="o"), _release("o"),
    ]
    actions = compress_events(events)
    check(actions == [{"type": "type", "text": "hello"}],
          "five chars collapsed to a single type action with text='hello'")


def test_compress_modifier_combo_becomes_hotkey():
    events = [
        _press("ctrl_l"),
        _press("s", char="s"),
        _release("s"),
        _release("ctrl_l"),
    ]
    actions = compress_events(events)
    check(len(actions) == 1 and actions[0]["type"] == "hotkey",
          "ctrl+s recorded as a single hotkey action")
    keys = actions[0]["keys"]
    check("ctrl" in keys and "s" in keys,
          f"hotkey keys list contains ctrl + s (got {keys})")


def test_compress_three_modifier_combo_includes_all_modifiers():
    events = [
        _press("ctrl_l"),
        _press("shift"),
        _press("p", char="p"),
        _release("p"),
        _release("shift"),
        _release("ctrl_l"),
    ]
    actions = compress_events(events)
    check(len(actions) == 1, "ctrl+shift+p emits exactly one action")
    keys = set(actions[0]["keys"])
    check(keys == {"ctrl", "shift", "p"},
          f"all three modifiers + key present (got {keys})")


def test_compress_typing_then_hotkey_flushes_type_first():
    events = [
        _press("h", char="h"), _release("h"),
        _press("i", char="i"), _release("i"),
        _press("ctrl_l"),
        _press("s", char="s"), _release("s"),
        _release("ctrl_l"),
    ]
    actions = compress_events(events)
    check(len(actions) == 2,
          "two actions emitted: type then hotkey")
    check(actions[0] == {"type": "type", "text": "hi"},
          "buffered text is flushed before the hotkey")
    check(actions[1]["type"] == "hotkey",
          "hotkey follows the type action")


def test_compress_named_key_alone_is_hotkey():
    events = [
        _press("enter"),
        _release("enter"),
    ]
    actions = compress_events(events)
    check(actions == [{"type": "hotkey", "keys": ["enter"]}],
          "lone enter key becomes a hotkey action")


def test_compress_click_event_emits_click_action():
    actions = compress_events([_click(640, 480)])
    check(actions == [{"type": "click", "x": 640, "y": 480}],
          "click event becomes a click action")


def test_compress_right_click_includes_button_field():
    actions = compress_events([_click(100, 100, button="right")])
    check(actions[0].get("button") == "right",
          "non-default button is preserved on the click action")


def test_compress_double_click_merges_into_one_action():
    events = [
        _click(200, 200, t=0.0),
        _click(200, 200, t=0.10),  # well within 350ms window
    ]
    actions = compress_events(events)
    check(len(actions) == 1,
          "two rapid same-coord clicks merge into one action")
    check(actions[0].get("clicks") == 2,
          "merged action has clicks=2")


def test_compress_two_clicks_far_apart_stay_separate():
    events = [
        _click(200, 200, t=0.0),
        _click(200, 200, t=1.5),  # far outside the double-click window
    ]
    actions = compress_events(events)
    check(len(actions) == 2,
          "clicks separated by >350ms remain two distinct actions")


def test_compress_click_flushes_pending_type_buffer():
    events = [
        _press("h", char="h"), _release("h"),
        _press("i", char="i"), _release("i"),
        _click(50, 50),
    ]
    actions = compress_events(events)
    check(len(actions) == 2,
          "a click after typing flushes the type buffer first")
    check(actions[0]["type"] == "type",
          "type action emitted before the click")
    check(actions[1]["type"] == "click",
          "click action follows")


def test_compress_scroll_emits_normalized_amount():
    actions = compress_events([_scroll(dy=5), _scroll(dy=-2)])
    check(actions == [
        {"type": "scroll", "amount": 3},
        {"type": "scroll", "amount": -3},
    ],
          "scroll events normalized to ±3 amount")


def test_compress_zero_scroll_is_dropped():
    actions = compress_events([_scroll(dy=0)])
    check(actions == [],
          "scroll with dy=0 produces no action (avoid pyautogui no-op spam)")


def test_compress_modifier_key_alone_emits_no_action():
    events = [
        _press("ctrl_l"),
        _release("ctrl_l"),
    ]
    actions = compress_events(events)
    check(actions == [],
          "lone modifier press/release produces no action")


# ── synthesize_skill ────────────────────────────────────────────────


def test_synthesize_returns_complete_skill_dict():
    events = [
        _click(100, 100),
        _press("h", char="h"), _release("h"),
        _press("i", char="i"), _release("i"),
        _press("enter"), _release("enter"),
    ]
    skill = synthesize_skill(events, name="say hi")
    check(skill["name"] == "say hi",
          "skill name preserved")
    check(skill["raw_event_count"] == len(events),
          "raw_event_count reflects the input event count")
    check(len(skill["recorded_actions"]) == 3,
          "recorded_actions has the compressed action list")
    check(isinstance(skill["instruction"], str) and skill["instruction"] != "",
          "fallback instruction is a non-empty string")


def test_synthesize_uses_caller_description_when_provided():
    skill = synthesize_skill(
        [_click(0, 0)],
        name="x",
        description="Custom blurb",
        instruction="Custom step list",
    )
    check(skill["description"] == "Custom blurb",
          "explicit description wins over fallback")
    check(skill["instruction"] == "Custom step list",
          "explicit instruction wins over fallback")


def test_synthesize_empty_events_still_produces_valid_skill_shell():
    skill = synthesize_skill([], name="empty")
    check(skill["name"] == "empty",
          "name preserved even with no events")
    check(skill["recorded_actions"] == [],
          "recorded_actions is an empty list, not None")
    check(isinstance(skill["instruction"], str),
          "instruction is always a string")


def test_synthesize_blank_name_falls_back_to_untitled():
    skill = synthesize_skill([_click(0, 0)], name="")
    check(skill["name"] == "untitled_skill",
          "blank name coerced to 'untitled_skill'")


# ── SkillManager (with a temp skills dir) ───────────────────────────


def _temp_skill_manager():
    """Build a SkillManager pointed at a fresh temp directory."""
    from core.engine.skill_manager import SkillManager
    sm = SkillManager()
    sm.skills_dir = tempfile.mkdtemp(prefix="ay-eye-skills-")
    return sm


def test_save_recorded_skill_writes_json_with_actions():
    sm = _temp_skill_manager()
    skill = {
        "name": "morning routine",
        "description": "Open Discord then VS Code",
        "instruction": "click(100,100) -> type('hi')",
        "recorded_actions": [
            {"type": "click", "x": 100, "y": 100},
            {"type": "type", "text": "hi"},
        ],
        "raw_event_count": 5,
    }
    ok = sm.save_recorded_skill(skill)
    check(ok is True, "save_recorded_skill returns True on success")
    files = os.listdir(sm.skills_dir)
    check(any(f.startswith("morning_routine") for f in files),
          "skill saved with safe filename derived from the human-readable name")
    payload = json.load(open(os.path.join(sm.skills_dir, files[0]), "r", encoding="utf-8"))
    check(payload.get("kind") == "recorded",
          "saved skill carries kind='recorded' marker")
    check(payload["recorded_actions"] == skill["recorded_actions"],
          "recorded_actions persisted byte-for-byte")


def test_save_recorded_skill_rejects_missing_actions():
    sm = _temp_skill_manager()
    ok = sm.save_recorded_skill({"name": "broken", "recorded_actions": []})
    check(ok is False,
          "skill with no recorded_actions is refused")


def test_save_recorded_skill_rejects_blank_name():
    sm = _temp_skill_manager()
    ok = sm.save_recorded_skill({
        "name": "    ",
        "recorded_actions": [{"type": "click", "x": 0, "y": 0}],
    })
    check(ok is False,
          "skill with whitespace-only name is refused")


def test_safe_filename_normalizes_punctuation_and_case():
    from core.engine.skill_manager import SkillManager
    f = SkillManager._safe_filename
    check(f("Morning Routine!") == "morning_routine",
          "spaces converted, punctuation stripped, lowercased")
    check(f("a-b-c") == "a_b_c",
          "hyphens become underscores")
    check(f("__weird__") == "weird",
          "leading/trailing underscores trimmed and collapsed")
    check(f("") == "",
          "empty string -> empty")
    check(f("###") == "",
          "all-punctuation -> empty (refused upstream)")


def test_skills_context_inlines_recorded_actions_for_brain():
    sm = _temp_skill_manager()
    sm.save_recorded_skill({
        "name": "demo",
        "description": "open chrome",
        "instruction": "step list",
        "recorded_actions": [{"type": "launch", "target": "chrome"}],
        "raw_event_count": 1,
    })
    ctx = sm.get_all_skills_context()
    check("Skill [demo]" in ctx,
          "skill name appears in the prompt context")
    check("RECORDED_ACTIONS:" in ctx,
          "RECORDED_ACTIONS marker is emitted for recorded skills")
    check('"type": "launch"' in ctx and '"target": "chrome"' in ctx,
          "actions are inlined as JSON the brain can copy verbatim")


def test_skills_context_omits_recorded_marker_for_freetext_skills():
    sm = _temp_skill_manager()
    sm.learn_skill("freeform", "do the thing")
    ctx = sm.get_all_skills_context()
    check("Skill [freeform]: do the thing" in ctx,
          "free-text skills render in the original simple format")
    check("RECORDED_ACTIONS:" not in ctx,
          "free-text skills do not get the recorded marker")


# ── Schema integration ─────────────────────────────────────────────


def test_schema_accepts_start_mimic_with_optional_name():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "in_progress",
        "message": "Watching now.",
        "actions": [{"type": "start_mimic", "name": "morning"}],
        "confidence": 0.8,
    })
    check(out["valid"] is True,
          "start_mimic with name is accepted")
    check(out["response"]["actions"][0]["name"] == "morning",
          "name field round-trips through validation")


def test_schema_accepts_start_mimic_without_name():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "in_progress",
        "message": "Watching.",
        "actions": [{"type": "start_mimic"}],
        "confidence": 0.7,
    })
    check(out["valid"] is True and len(out["response"]["actions"]) == 1,
          "start_mimic without name is also accepted")


def test_schema_rejects_stop_mimic_and_save_without_name():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Saving.",
        "actions": [{"type": "stop_mimic_and_save"}],
        "confidence": 0.9,
    })
    actions = out["response"]["actions"]
    check(actions == [],
          "stop_mimic_and_save with no name is stripped (saving anonymously is unsafe)")


def test_schema_accepts_stop_mimic_and_save_with_name_and_description():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Saving as morning_routine.",
        "actions": [{
            "type": "stop_mimic_and_save",
            "name": "morning_routine",
            "description": "Opens Discord then VS Code",
        }],
        "confidence": 0.9,
    })
    check(out["valid"] is True,
          "stop_mimic_and_save with name + description is valid")
    a = out["response"]["actions"][0]
    check(a["name"] == "morning_routine" and a["description"].startswith("Opens"),
          "name + description survive validation")


def test_schema_accepts_cancel_mimic_with_no_fields():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Forgetting it.",
        "actions": [{"type": "cancel_mimic"}],
        "confidence": 0.9,
    })
    check(out["valid"] is True and out["response"]["actions"][0]["type"] == "cancel_mimic",
          "cancel_mimic action passes validation")


def test_response_format_enum_lists_all_three_mimic_actions():
    from core.engine.response_format import build_action_schema
    enum = set(build_action_schema()["properties"]["type"]["enum"])
    check({"start_mimic", "stop_mimic_and_save", "cancel_mimic"} <= enum,
          "structured-output JSON Schema enum lists all three Mimic actions")


# ── End-to-end: recorder -> synthesizer -> skill_manager ────────────


def test_end_to_end_record_compress_save_roundtrip():
    hook = FakeHook()
    rec = MimicRecorder(hook=hook)
    rec.start("demo_e2e")

    # Simulate the user clicking, typing 'hi', pressing Enter, hitting Ctrl+S.
    hook.emit(_click(640, 480))
    hook.emit(_press("h", char="h")); hook.emit(_release("h"))
    hook.emit(_press("i", char="i")); hook.emit(_release("i"))
    hook.emit(_press("enter")); hook.emit(_release("enter"))
    hook.emit(_press("ctrl_l"))
    hook.emit(_press("s", char="s")); hook.emit(_release("s"))
    hook.emit(_release("ctrl_l"))

    captured = rec.stop()
    check(len(captured) >= 9,
          "recorder buffered every emitted event")

    skill = synthesize_skill(captured, name="demo_e2e")
    actions = skill["recorded_actions"]
    types = [a["type"] for a in actions]
    check(types == ["click", "type", "hotkey", "hotkey"],
          f"E2E sequence compressed to expected action types (got {types})")
    check(actions[1]["text"] == "hi",
          "typed 'hi' captured exactly")

    sm = _temp_skill_manager()
    ok = sm.save_recorded_skill(skill)
    check(ok is True,
          "synthesised skill saves cleanly")
    ctx = sm.get_all_skills_context()
    check("demo_e2e" in ctx and "RECORDED_ACTIONS:" in ctx,
          "saved skill appears in brain prompt context with recorded marker")


# ── Run ─────────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Mimic Mode: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
