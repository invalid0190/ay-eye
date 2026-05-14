"""
Shiba Inu — a hand-encoded pixel-art pet style.

Inspired by the Codex Pets shiba/samoyed sprites. The body is a 28×28
grid scaled 4× to a 112×112 sprite sitting inside a 128×128 widget.
Every pixel is hand-placed; the engine just blits the matrix at the
right scale (see ``_sprite_engine.draw_bitmap``).

Design notes
------------
* The silhouette is **head-dominant chibi** — a big round head on a
  small triangular sitting body. This is the same proportion the
  Codex Pets reference uses, and it's also the easiest proportion to
  recognize at 28×28 because the eyes/ears/snout (the parts you
  actually identify a shiba by) get the most pixels.
* The body silhouette is constant. Only **eyes + mouth + accents**
  change per state — exactly the Tamagotchi trick.
* Outlines are hard black (``K``) rather than dark-orange so the
  shape stays crisp against any wallpaper.
* Cream snout + cream paws + cream chest = the shiba "urajiro" mask
  that distinguishes them from generic orange dogs.

State expressions
-----------------
* ``IDLE``       — alert open eyes, tiny smile.
* ``LISTENING``  — wide-open eyes with whites showing, neutral mouth
                   (pet is *paying attention*).
* ``THINKING``   — half-lidded eyes (looking up), flat mouth.
* ``SPEAKING``   — alert eyes, mouth opens & closes every ~100 ms.
* ``ACTING``     — determined narrow eyes, flat mouth.
* ``SUCCESS``    — happy ``^_^`` eyes + open smile + sparkle accent.
* ``FAILED``     — ``x_x`` eyes + frown + sweat-drop accent.
* ``SLEEPING``   — closed-eye lines + drifting ``z`` chars above.
* ``HATCHING``   — handled by the widget's egg overlay (style-agnostic).
"""

from __future__ import annotations

from typing import Dict, Tuple

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPen

from core.ui.pet_painter import (
    PaintInput,
    PetState,
    _clamp,
    bob_offset_y,
)
from core.ui.pet_styles import PetStyle, register
from core.ui.pet_styles._sprite_engine import (
    draw_bitmap,
    draw_overlays,
    validate_bitmap,
    validate_palette_keys,
)
from core.ui.theme import theme


# ── Geometry ────────────────────────────────────────────────────────


# Smaller, halo-free footprint. Going from 128×128 → 96×96 with a
# 3× pixel scale (28 × 3 = 84 px sprite) gives the dog a discreet
# presence on the desktop instead of the previous "big square card"
# look. Padding of 6 px around the sprite is just enough room for
# the success/failed sparkle/sweat accents to live above the head.
WIDTH = 96
HEIGHT = 96
GRID = 28
PIXEL_SIZE = 3                              # 28 * 3 = 84
SPRITE_PX = GRID * PIXEL_SIZE
SPRITE_X = (WIDTH - SPRITE_PX) // 2         # 6
SPRITE_Y = (HEIGHT - SPRITE_PX) // 2        # 6


# ── Palette ────────────────────────────────────────────────────────
#
# Keep this small (≤8 entries) so the sprite reads as cohesive pixel-
# art rather than a noisy gradient. The shading entries (``O``, ``W``)
# carry depth; the rest are flat fills.


PALETTE: Dict[str, QColor] = {
    "K": QColor(0x12, 0x0C, 0x08),     # outline / nose / pupil — near-black
    "o": QColor(0xE4, 0x92, 0x2E),     # main orange (saturated, slightly warm)
    "O": QColor(0xA8, 0x60, 0x1B),     # shadow orange (face/body edges)
    "w": QColor(0xF6, 0xE6, 0xC4),     # cream — snout, chest, paws
    "W": QColor(0xFF, 0xF5, 0xDC),     # cream highlight (top of snout)
    "p": QColor(0xE5, 0x9F, 0x9F),     # pink inner ear / tongue
    "e": QColor(0xFF, 0xFF, 0xFF),     # eye-white sparkle pixel
    "a": QColor(0xC8, 0x7A, 0x2A),     # amber iris (warm dog-eye brown)
    "A": QColor(0x8E, 0x4F, 0x14),     # darker amber rim
    "r": QColor(0xC8, 0x4A, 0x4A),     # red — sweat-drop / sparkle accent
}


# ── Base body sprite (28 × 28) ─────────────────────────────────────
#
# Every row MUST be exactly 28 characters. ``validate_bitmap()`` below
# raises on any mismatch at import time, so a typo here can't sneak
# into a corrupted paint frame.
#
# Coordinates (mental model):
#   col →  0 1 2 3 ... 27
#   row ↓  0  ┌── head ──┐
#         …   │          │
#         18  └── chest ─┘
#         …   ╱ legs ╲
#         27


BODY = (
    "............................",  # 00
    "....KK..............KK......",  # 01  ear outline tops
    "...KooK............KooK.....",  # 02  ear orange
    "...KooK............KooK.....",  # 03
    "...KopK............KopK.....",  # 04  pink inner-ear stripe
    "..KooooK..........KooooK....",  # 05  ears flare
    "..KooooOKK......KKOooooK....",  # 06  ear base shadow
    ".KOooooooKKKKKKKKooooooOK...",  # 07  head crown begins
    ".KooooooooooooooooooooooK...",  # 08
    ".KoooooowwwwwwwwwwwwoooooK..",  # 09  cream face mask line
    ".KOooowwwwwwwwwwwwwwwwooOK..",  # 10
    ".KOooowwwwwwwwwwwwwwwwooOK..",  # 11
    ".KOooowwwwwwwwwwwwwwwwwooK..",  # 12  (eyes painted as overlay)
    ".KOooowwwwwwwwwwwwwwwwwoOK..",  # 13
    ".KOoooowwwwwwwwwwwwwwwooOK..",  # 14
    ".KOoooowwwwwwwwwwwwwwwooOK..",  # 15  (nose painted as overlay)
    "..KOoooowwwwwwwwwwwwwoooOK..",  # 16
    "..KOoooooowwwwwwwwwwooooOK..",  # 17  (mouth painted as overlay)
    "...KOoooooowwwwwwwwooooooK..",  # 18  chin
    "....KOoooooooooooooooooooK..",  # 19  neck
    ".....KKOOOoooooooooooOOOK...",  # 20  chest cream begins
    "......KOoowwwwwwwwwwooooK...",  # 21  white chest
    "......KOoowwwwwwwwwwooooK...",  # 22
    "......KOoooowwwwwwwooooOK...",  # 23
    "......KOoooooooooooooooOK...",  # 24
    "......KKKOOOooOOOoOOOKKK....",  # 25  legs hinted
    "........K.KwwK.KwwK.K.......",  # 26  white paws
    "........KKKKKKKKKKKKK.......",  # 27  ground line
)


# ── Overlays (eyes / nose / mouth / accents) ───────────────────────
#
# Sparse {(col, row): char} dicts overlay onto BODY. Coordinates are
# in **grid cells**, not widget pixels. Keep these tiny and localized
# so per-state diffs are easy to read.


def _overlay(*pixels: Tuple[int, int, str]) -> Dict[Tuple[int, int], str]:
    return {(c, r): ch for c, r, ch in pixels}


# Nose — a small dark triangle at the tip of the snout. Always-on.
NOSE = _overlay(
    (13, 13, "K"), (14, 13, "K"),
    (12, 14, "K"), (13, 14, "K"), (14, 14, "K"), (15, 14, "K"),
    (13, 15, "K"), (14, 15, "K"),
)


# Open alert eyes (default for IDLE, LISTENING, ACTING, SPEAKING).
#
# Each eye is a 4×3 block centered on the cream face mask:
#   row 11: . K K K K .     (top eyelid)
#   row 12: K A a a K       (amber iris with sparkle 'e' on the inside)
#   row 13: . K K K K .     (bottom eyelid)
#
# This gives ~12 dark pixels per eye at 4× scale = a 16×12 eye on
# screen, big enough to read instantly. The sparkle is placed on the
# *inside* corner of each iris (left-eye sparkle on the right side,
# right-eye sparkle on the left side) so the pet looks like both eyes
# are reflecting the same light source.
EYES_OPEN = _overlay(
    # Left eye — cols 5..8, rows 11..13.
    (5, 11, "K"), (6, 11, "K"), (7, 11, "K"), (8, 11, "K"),
    (5, 12, "K"), (6, 12, "A"), (7, 12, "a"), (8, 12, "K"),
    (5, 13, "K"), (6, 13, "K"), (7, 13, "K"), (8, 13, "K"),
    (7, 12, "e"),               # sparkle replaces the inner-iris cell
    # Right eye — cols 19..22, rows 11..13 (mirror of the left eye).
    (19, 11, "K"), (20, 11, "K"), (21, 11, "K"), (22, 11, "K"),
    (19, 12, "K"), (20, 12, "a"), (21, 12, "A"), (22, 12, "K"),
    (19, 13, "K"), (20, 13, "K"), (21, 13, "K"), (22, 13, "K"),
    (20, 12, "e"),
)


# Wide eyes (LISTENING) — same shape but with an eye-white row above
# the iris and a slightly larger sparkle so the pet reads as alert /
# paying attention rather than just "looking forward".
EYES_WIDE = _overlay(
    (5, 10, "K"), (6, 10, "K"), (7, 10, "K"), (8, 10, "K"),
    (5, 11, "K"), (6, 11, "w"), (7, 11, "w"), (8, 11, "K"),
    (5, 12, "K"), (6, 12, "A"), (7, 12, "a"), (8, 12, "K"),
    (5, 13, "K"), (6, 13, "K"), (7, 13, "K"), (8, 13, "K"),
    (7, 12, "e"),
    (19, 10, "K"), (20, 10, "K"), (21, 10, "K"), (22, 10, "K"),
    (19, 11, "K"), (20, 11, "w"), (21, 11, "w"), (22, 11, "K"),
    (19, 12, "K"), (20, 12, "a"), (21, 12, "A"), (22, 12, "K"),
    (19, 13, "K"), (20, 13, "K"), (21, 13, "K"), (22, 13, "K"),
    (20, 12, "e"),
)


# Half-lidded thinking eyes — top eyelid drops, only the bottom edge
# of the iris peeks out (the classic "looking up while thinking" pose).
EYES_THINK = _overlay(
    (5, 12, "K"), (6, 12, "K"), (7, 12, "K"), (8, 12, "K"),
    (6, 13, "a"), (7, 13, "a"),
    (19, 12, "K"), (20, 12, "K"), (21, 12, "K"), (22, 12, "K"),
    (20, 13, "a"), (21, 13, "a"),
)


# Narrow determined eyes (ACTING) — a single thick horizontal slit
# per eye, no iris. Reads as "focused, all business".
EYES_NARROW = _overlay(
    (5, 12, "K"), (6, 12, "K"), (7, 12, "K"), (8, 12, "K"),
    (19, 12, "K"), (20, 12, "K"), (21, 12, "K"), (22, 12, "K"),
)


# Happy ^_^ eyes (SUCCESS) — concave-up arcs, no iris. The arc
# anchors at the iris corners so it lines up visually with the
# default EYES_OPEN slots.
EYES_HAPPY = _overlay(
    (5, 13, "K"), (6, 12, "K"), (7, 11, "K"), (8, 12, "K"),
    (19, 12, "K"), (20, 11, "K"), (21, 12, "K"), (22, 13, "K"),
)


# x_x dazed eyes (FAILED) — diagonal crosses in the iris area.
EYES_DEAD = _overlay(
    (5, 11, "K"), (8, 11, "K"),
    (6, 12, "K"), (7, 12, "K"),
    (5, 13, "K"), (8, 13, "K"),
    (19, 11, "K"), (22, 11, "K"),
    (20, 12, "K"), (21, 12, "K"),
    (19, 13, "K"), (22, 13, "K"),
)


# Closed eyelid (SLEEPING + mid-blink) — a flat 4-pixel line per eye
# at the middle row of the eye slot.
EYES_CLOSED = _overlay(
    (5, 12, "K"), (6, 12, "K"), (7, 12, "K"), (8, 12, "K"),
    (19, 12, "K"), (20, 12, "K"), (21, 12, "K"), (22, 12, "K"),
)


# Mouth overlays. The snout is at cols 11..16, rows 17..18. All
# mouths here are 6+ pixels wide so they read clearly at the 4×
# rendering scale (the previous 4-pixel mouths were nearly invisible).
MOUTH_SMILE = _overlay(
    # Classic shiba smug smile: corners curl up, middle goes flat.
    #   .K....K.
    #   ..KKKK..
    (11, 17, "K"),                                 (16, 17, "K"),
    (12, 18, "K"), (13, 18, "K"), (14, 18, "K"), (15, 18, "K"),
)
MOUTH_BIG_SMILE = _overlay(
    # Open mouth with pink tongue — happy panting dog.
    (11, 17, "K"),                                 (16, 17, "K"),
    (12, 18, "K"), (15, 18, "K"),
    (13, 18, "p"), (14, 18, "p"),                  # tongue
)
MOUTH_FROWN = _overlay(
    (11, 18, "K"),                                 (16, 18, "K"),
    (12, 17, "K"), (13, 17, "K"), (14, 17, "K"), (15, 17, "K"),
)
MOUTH_FLAT = _overlay(
    (12, 17, "K"), (13, 17, "K"), (14, 17, "K"), (15, 17, "K"),
    (11, 17, "K"),                                 (16, 17, "K"),
)
MOUTH_OPEN_O = _overlay(
    (12, 17, "K"), (13, 17, "K"), (14, 17, "K"), (15, 17, "K"),
    (12, 18, "K"), (13, 18, "K"), (14, 18, "K"), (15, 18, "K"),
)
MOUTH_NONE: Dict[Tuple[int, int], str] = {}


# Decorations placed *outside* the body silhouette to communicate
# emotion. They paint over the transparent border padding so they
# never clash with the dog itself.

# Sparkle (SUCCESS) — a 4-arm star at top-right above the head.
SPARKLE = _overlay(
    (24, 3, "r"),
    (23, 4, "r"), (24, 4, "W"), (25, 4, "r"),
    (24, 5, "r"),
)

# Sweat-drop (FAILED) — a pixel teardrop above the head on the right.
SWEAT_DROP = _overlay(
    (23, 5, "e"),
    (22, 6, "e"), (23, 6, "e"), (24, 6, "e"),
    (23, 7, "e"),
)


# ── Validate at import time ────────────────────────────────────────


_BODY_W, _BODY_H = validate_bitmap(BODY, name="shiba.BODY")
assert _BODY_W == GRID and _BODY_H == GRID, (
    f"shiba.BODY must be {GRID}×{GRID}, got {_BODY_W}×{_BODY_H}"
)
validate_palette_keys(BODY, PALETTE, name="shiba.BODY")


# ── Per-state lookups ─────────────────────────────────────────────


def _eyes_for(state: PetState, blink: float) -> Dict[Tuple[int, int], str]:
    """Pick the right eye overlay. A mid-blink fades through the
    closed-eye line regardless of base expression (except for already-
    closed states where blinking would be a no-op).
    """
    if blink > 0.5 and state not in (
        PetState.SLEEPING, PetState.HATCHING,
        PetState.SUCCESS, PetState.FAILED,
    ):
        return EYES_CLOSED
    return {
        PetState.IDLE:      EYES_OPEN,
        PetState.LISTENING: EYES_WIDE,
        PetState.THINKING:  EYES_THINK,
        PetState.SPEAKING:  EYES_OPEN,
        PetState.ACTING:    EYES_NARROW,
        PetState.SUCCESS:   EYES_HAPPY,
        PetState.FAILED:    EYES_DEAD,
        PetState.SLEEPING:  EYES_CLOSED,
    }.get(state, EYES_OPEN)


def _mouth_for(state: PetState, time_ms: int) -> Dict[Tuple[int, int], str]:
    if state == PetState.SUCCESS:
        return MOUTH_BIG_SMILE
    if state == PetState.FAILED:
        return MOUTH_FROWN
    if state == PetState.SLEEPING:
        return MOUTH_NONE
    if state == PetState.LISTENING:
        return MOUTH_OPEN_O
    if state == PetState.SPEAKING:
        # Animate jaw at ~5 Hz so the pet "talks".
        return MOUTH_OPEN_O if (time_ms // 100) % 2 == 0 else MOUTH_FLAT
    if state in (PetState.THINKING, PetState.ACTING):
        return MOUTH_FLAT
    return MOUTH_SMILE


def _accents_for(state: PetState) -> Dict[Tuple[int, int], str]:
    if state == PetState.SUCCESS:
        return SPARKLE
    if state == PetState.FAILED:
        return SWEAT_DROP
    return {}


# ── Sub-renderers ──────────────────────────────────────────────────


# Intentionally no halo. The pixel-art sprite is high-contrast on its
# own (hard black outlines + bold colors), and the previous halo
# gradient filled most of the 128×128 widget which made the pet read
# as a "square card on the desktop" rather than a free-standing
# companion. Mood is still legible via the eye/mouth state overlays.


def _draw_zzz(painter: QPainter, cx: float, cy: float, time_ms: int) -> None:
    """Floating ``z`` chars above the head while sleeping.

    Positioned closer to the head now that the widget is 96×96 — the
    old 128 px geometry let the Zs drift well outside the silhouette,
    which looked weirdly disconnected at the smaller size.
    """
    drift = (time_ms / 200.0) % 22
    pen = QPen(QColor(theme.TEXT_DIM))
    painter.setPen(pen)
    font = painter.font()
    for i, size in enumerate((10, 8, 6)):
        font.setPointSize(size)
        painter.setFont(font)
        x = cx + 20 + i * 5
        y = cy - 22 - i * 5 - drift * 0.3
        painter.drawText(QPointF(x, y), "z")


# ── Public draw entry point ────────────────────────────────────────


def draw(painter: QPainter, p: PaintInput) -> None:
    """Render one frame of the shiba inu.

    No background, no halo — the widget is set to translucent in
    :class:`AyEyePet`, so anything we don't explicitly paint stays
    fully transparent on the desktop. The sprite floats freely.
    """
    cx, cy = WIDTH / 2.0, HEIGHT / 2.0
    bob = bob_offset_y(p.state, p.time_ms)

    # Body + overlays. Antialiasing OFF so pixel edges stay hard.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    sprite_y = int(SPRITE_Y + bob)
    alpha = _clamp(p.body_alpha, 0.0, 1.0)

    draw_bitmap(
        painter, BODY, PALETTE,
        origin_x=SPRITE_X, origin_y=sprite_y,
        pixel_size=PIXEL_SIZE, alpha=alpha,
    )
    draw_overlays(
        painter,
        [NOSE,
         _eyes_for(p.state, p.blink_progress),
         _mouth_for(p.state, p.time_ms),
         _accents_for(p.state)],
        PALETTE,
        origin_x=SPRITE_X, origin_y=sprite_y,
        pixel_size=PIXEL_SIZE, alpha=alpha,
    )

    # Sleeping Z's — text rendering wants AA back on.
    if p.state == PetState.SLEEPING:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_zzz(painter, cx, cy, p.time_ms)


# ── Style record ──────────────────────────────────────────────────


SHIBA_STYLE = PetStyle(
    name="shiba",
    description="Shiba Inu — hand-pixel-arted orange chibi dog with cream mask and curly ears.",
    widget_size=(WIDTH, HEIGHT),
    draw=draw,
)
register(SHIBA_STYLE)
