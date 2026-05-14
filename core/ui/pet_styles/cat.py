"""
Cat — a hand-encoded pixel-art pet style.

A chibi white kitten with oversized anime eyes, pink inner ears, and
a tiny stitched smile. Same engine and proportions as ``shiba`` — a
28×28 grid scaled 4× to a 112×112 sprite in a 128×128 widget — so
switching styles at runtime feels seamless (same widget footprint,
same animation curves, only the pixels change).

Design intent
-------------
The cat is intentionally rounder and more "blob-shaped" than the
shiba so the two pets read as visually distinct at a glance.
Where the shiba is angular (pointy ears, sharp snout, urajiro mask),
the kitten is soft: triangular but rounded-tip ears, no protruding
snout, big circular eyes that occupy nearly half the face.

State expressions
-----------------
The cat's state language matches the shiba's so the user gets
consistent emotional read-outs across styles:

* ``IDLE``       — alert green eyes, tiny stitched ``ω`` smile.
* ``LISTENING``  — wide eyes, mouth slightly open.
* ``THINKING``   — half-lidded eyes, flat mouth.
* ``SPEAKING``   — open eyes, mouth animates 5 Hz.
* ``ACTING``     — narrow determined eyes, flat mouth.
* ``SUCCESS``    — happy ``>_<`` eyes + smile + sparkle.
* ``FAILED``     — ``x_x`` eyes + frown + sweat-drop.
* ``SLEEPING``   — closed eyes + drifting ``z`` chars.
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


# Matching the shiba's smaller halo-free footprint: 96×96 widget,
# 3× pixel scale (28 × 3 = 84 px sprite, 6 px breathing room).
WIDTH = 96
HEIGHT = 96
GRID = 28
PIXEL_SIZE = 3
SPRITE_PX = GRID * PIXEL_SIZE       # 84
SPRITE_X = (WIDTH - SPRITE_PX) // 2  # 6
SPRITE_Y = (HEIGHT - SPRITE_PX) // 2  # 6


# ── Palette ────────────────────────────────────────────────────────


PALETTE: Dict[str, QColor] = {
    "K": QColor(0x1A, 0x14, 0x10),    # outline + pupil — near-black
    "w": QColor(0xF8, 0xF4, 0xEE),    # main white fur (warm, not pure white)
    "W": QColor(0xFF, 0xFF, 0xFF),    # pure white highlight
    "g": QColor(0xC8, 0xC4, 0xCC),    # grey shadow (body underside)
    "p": QColor(0xF0, 0xA8, 0xB8),    # pink — nose, inner ear, paw pad
    "P": QColor(0xC4, 0x7A, 0x90),    # darker pink shadow
    "y": QColor(0x7C, 0xC6, 0x4E),    # bright green eye iris
    "Y": QColor(0x52, 0x9A, 0x32),    # darker green eye edge
    "e": QColor(0xFF, 0xFF, 0xFF),    # eye sparkle
    "r": QColor(0xE8, 0x4A, 0x4A),    # red accent (sparkle/sweat)
    "b": QColor(0xA0, 0xD8, 0xFF),    # blue tear / sweat drop
}


# ── Base body sprite (28 × 28) ─────────────────────────────────────


BODY = (
    "............................",  # 00
    "....KK..............KK......",  # 01  ear tip outlines
    "...KwwK............KwwK.....",  # 02  ears
    "...KwpK............KwpK.....",  # 03  pink inner ear
    "..KwwwpK..........KpwwwK....",  # 04
    "..KwwwwKK........KKwwwwK....",  # 05
    "..KwwwwwwKK....KKwwwwwwK....",  # 06  ears flare
    ".KwwwwwwwwKKKKKKwwwwwwwwK...",  # 07  head crown
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 08
    ".KwwwWWwwwwwwwwwwwwwwWWwK...",  # 09  forehead highlights
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 10
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 11  (eyes painted by overlay)
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 12
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 13
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 14
    ".KwwwwwwwwwwwwwwwwwwwwwwK...",  # 15  (nose painted by overlay)
    "..KwwwwwwwwwwwwwwwwwwwwK....",  # 16
    "..KwwwwwwwwwwwwwwwwwwwwK....",  # 17  (mouth painted by overlay)
    "...KwwwwwwwwwwwwwwwwwwK.....",  # 18
    "....KwwwwwwwwwwwwwwwwK......",  # 19  chin
    ".....KwwwwwwwwwwwwwwwK......",  # 20  neck
    ".....KgwwwwwwwwwwwwwwK......",  # 21  body shadow starts left
    ".....KgwwwwwwwwwwwwwwK......",  # 22
    "......KgwwwwwwwwwwwwK.......",  # 23
    "......KKgggwwwwwgggK........",  # 24  body narrows
    ".......KgKpwKwpwKgK.........",  # 25  legs + pink paw pads
    ".......K.K..K..K.K..........",  # 26  paw spacing
    ".......KKKKKKKKKKK..........",  # 27  ground line
)


# ── Overlays ───────────────────────────────────────────────────────


def _overlay(*pixels: Tuple[int, int, str]) -> Dict[Tuple[int, int], str]:
    return {(c, r): ch for c, r, ch in pixels}


# Pink triangular nose at the snout center.
NOSE = _overlay(
    (13, 14, "p"), (14, 14, "p"),
    (13, 15, "P"), (14, 15, "P"),
)


# Big round anime eyes — 3×3 dark block with green iris + white sparkle.
# These are oversized intentionally; chibi cats are eye-driven.
EYES_OPEN = _overlay(
    # Left eye (cols 6-9, rows 11-13)
    (6, 11, "K"), (7, 11, "K"), (8, 11, "K"), (9, 11, "K"),
    (6, 12, "K"), (7, 12, "Y"), (8, 12, "y"), (9, 12, "K"),
    (6, 13, "K"), (7, 13, "K"), (8, 13, "K"), (9, 13, "K"),
    (7, 12, "e"),                       # sparkle (top-left of iris)
    # Right eye (cols 18-21, rows 11-13)
    (18, 11, "K"), (19, 11, "K"), (20, 11, "K"), (21, 11, "K"),
    (18, 12, "K"), (19, 12, "y"), (20, 12, "Y"), (21, 12, "K"),
    (18, 13, "K"), (19, 13, "K"), (20, 13, "K"), (21, 13, "K"),
    (19, 12, "e"),
)


# Wide eyes for LISTENING — same as open but with eye-white above
# the pupil, giving a "ears-up + alert" read.
EYES_WIDE = _overlay(
    (6, 10, "w"), (7, 10, "w"), (8, 10, "w"), (9, 10, "w"),
    (6, 11, "K"), (7, 11, "K"), (8, 11, "K"), (9, 11, "K"),
    (6, 12, "K"), (7, 12, "Y"), (8, 12, "y"), (9, 12, "K"),
    (6, 13, "K"), (7, 13, "K"), (8, 13, "K"), (9, 13, "K"),
    (7, 12, "e"),
    (18, 10, "w"), (19, 10, "w"), (20, 10, "w"), (21, 10, "w"),
    (18, 11, "K"), (19, 11, "K"), (20, 11, "K"), (21, 11, "K"),
    (18, 12, "K"), (19, 12, "y"), (20, 12, "Y"), (21, 12, "K"),
    (18, 13, "K"), (19, 13, "K"), (20, 13, "K"), (21, 13, "K"),
    (19, 12, "e"),
)


# Half-lidded thinking eyes — just the bottom half of the iris peeks
# out, top is covered by a "lid" line.
EYES_THINK = _overlay(
    (6, 12, "K"), (7, 12, "K"), (8, 12, "K"), (9, 12, "K"),
    (7, 13, "y"), (8, 13, "y"),
    (18, 12, "K"), (19, 12, "K"), (20, 12, "K"), (21, 12, "K"),
    (19, 13, "y"), (20, 13, "y"),
)


# Narrow determined eyes (ACTING).
EYES_NARROW = _overlay(
    (5, 12, "K"), (6, 12, "K"), (7, 12, "K"), (8, 12, "K"), (9, 12, "K"),
    (18, 12, "K"), (19, 12, "K"), (20, 12, "K"), (21, 12, "K"), (22, 12, "K"),
)


# Happy >_< style closed-up eyes (SUCCESS).
EYES_HAPPY = _overlay(
    (5, 11, "K"), (6, 12, "K"), (7, 13, "K"), (8, 12, "K"), (9, 11, "K"),
    (18, 11, "K"), (19, 12, "K"), (20, 13, "K"), (21, 12, "K"), (22, 11, "K"),
)


# x_x dazed eyes (FAILED).
EYES_DEAD = _overlay(
    (6, 11, "K"), (8, 11, "K"),
    (7, 12, "K"),
    (6, 13, "K"), (8, 13, "K"),
    (19, 11, "K"), (21, 11, "K"),
    (20, 12, "K"),
    (19, 13, "K"), (21, 13, "K"),
)


# Closed eye line (SLEEPING + blink).
EYES_CLOSED = _overlay(
    (6, 12, "K"), (7, 12, "K"), (8, 12, "K"), (9, 12, "K"),
    (18, 12, "K"), (19, 12, "K"), (20, 12, "K"), (21, 12, "K"),
)


# Mouth — for the cat, the classic ``ω`` two-bumps smile reads great.
MOUTH_SMILE = _overlay(
    (12, 16, "K"), (13, 17, "K"), (14, 17, "K"), (15, 16, "K"),
)
MOUTH_BIG_SMILE = _overlay(
    (11, 16, "K"), (12, 17, "K"), (13, 17, "p"),
    (14, 17, "p"), (15, 17, "K"), (16, 16, "K"),
)
MOUTH_FROWN = _overlay(
    (12, 17, "K"), (13, 16, "K"), (14, 16, "K"), (15, 17, "K"),
)
MOUTH_FLAT = _overlay(
    (12, 17, "K"), (13, 17, "K"), (14, 17, "K"), (15, 17, "K"),
)
MOUTH_OPEN_O = _overlay(
    (13, 16, "K"), (14, 16, "K"),
    (13, 17, "K"), (14, 17, "K"),
)
MOUTH_NONE: Dict[Tuple[int, int], str] = {}


# Whiskers — three thin lines on each cheek. Always-on (defining
# feature of a cat; the silhouette alone could read as a fox without
# them).
WHISKERS = _overlay(
    # Left cheek
    (2, 14, "g"), (3, 14, "g"), (4, 14, "g"),
    (2, 15, "g"), (3, 15, "g"), (4, 15, "g"),
    # Right cheek
    (23, 14, "g"), (24, 14, "g"), (25, 14, "g"),
    (23, 15, "g"), (24, 15, "g"), (25, 15, "g"),
)


# Accents (above the head).
SPARKLE = _overlay(
    (24, 3, "r"),
    (23, 4, "r"), (24, 4, "W"), (25, 4, "r"),
    (24, 5, "r"),
)
SWEAT_DROP = _overlay(
    (23, 5, "b"),
    (22, 6, "b"), (23, 6, "e"), (24, 6, "b"),
    (23, 7, "b"),
)


# ── Validate at import time ────────────────────────────────────────


_BODY_W, _BODY_H = validate_bitmap(BODY, name="cat.BODY")
assert _BODY_W == GRID and _BODY_H == GRID, (
    f"cat.BODY must be {GRID}×{GRID}, got {_BODY_W}×{_BODY_H}"
)
validate_palette_keys(BODY, PALETTE, name="cat.BODY")


# ── Per-state lookups ─────────────────────────────────────────────


def _eyes_for(state: PetState, blink: float) -> Dict[Tuple[int, int], str]:
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


# No halo — same reasoning as shiba.py: the pixel-art silhouette
# carries enough visual weight on its own, and the halo gradient
# at this widget size made the pet read as a "square card".


def _draw_zzz(painter: QPainter, cx: float, cy: float, time_ms: int) -> None:
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
    """Render one frame of the chibi kitten.

    No background, no halo — the widget is translucent so we only
    paint the sprite and its overlays; everything else stays a
    fully-transparent hole in the desktop.
    """
    cx, cy = WIDTH / 2.0, HEIGHT / 2.0
    bob = bob_offset_y(p.state, p.time_ms)

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
        [WHISKERS, NOSE,
         _eyes_for(p.state, p.blink_progress),
         _mouth_for(p.state, p.time_ms),
         _accents_for(p.state)],
        PALETTE,
        origin_x=SPRITE_X, origin_y=sprite_y,
        pixel_size=PIXEL_SIZE, alpha=alpha,
    )

    if p.state == PetState.SLEEPING:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_zzz(painter, cx, cy, p.time_ms)


# ── Style record ──────────────────────────────────────────────────


CAT_STYLE = PetStyle(
    name="cat",
    description="Chibi white kitten — big green anime eyes, pink nose, stitched ω smile.",
    widget_size=(WIDTH, HEIGHT),
    draw=draw,
)
register(CAT_STYLE)
