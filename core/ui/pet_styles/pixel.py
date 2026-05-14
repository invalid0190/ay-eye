"""
Pixel-art mascot — Tamagotchi-style bean creature.

Design notes
------------
* The pet is a 16×16 pixel sprite scaled 5× to ~80×80 inside a
  110×110 widget. Antialiasing is **off** for the sprite (each
  pixel is a hard ``QPainter.fillRect`` of size ``PIXEL_SIZE``) so
  the silhouette stays crisp at any monitor DPI.
* The body silhouette never changes — only eyes, mouth and small
  accents change with state. That's how Tamagotchi got away with
  500 bytes of ROM and you can still tell a pixel cat from a
  pixel duck: the *expression* carries the personality.
* The halo (smooth radial gradient) is drawn with antialiasing
  back **on**; it's a separate layer that sits behind the sprite.

State expressions
-----------------
* ``IDLE``      — small alert dot pupils, neutral mouth dot.
* ``LISTENING`` — wider eyes with whites, small open mouth.
* ``THINKING`` — half-lidded eyes (^^), flat mouth.
* ``SPEAKING`` — mouth animates open/close at ~5 Hz.
* ``ACTING``   — wider eyes, determined flat mouth.
* ``SUCCESS``  — happy ^_^ + open smile.
* ``FAILED``   — x_x + frown.
* ``SLEEPING`` — closed-eye lines + drifting "z"s above-right.
* ``HATCHING`` — wobbling pixel egg sprite that fades into the bean.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient

from core.ui.pet_painter import (
    PaintInput,
    PetState,
    _clamp,
    bob_offset_y,
    halo_color,
    halo_intensity,
)
from core.ui.pet_styles import PetStyle, register
from core.ui.theme import theme


# ── Geometry ────────────────────────────────────────────────────────


WIDTH = 110
HEIGHT = 110
SPRITE_GRID = 16                       # 16×16 logical pixels
PIXEL_SIZE = 5                         # each logical pixel = 5×5 widget pixels
SPRITE_PX = SPRITE_GRID * PIXEL_SIZE   # 80
SPRITE_X = (WIDTH - SPRITE_PX) // 2    # 15
SPRITE_Y = (HEIGHT - SPRITE_PX) // 2   # 15


# ── Sprite data ────────────────────────────────────────────────────


# Body silhouette — same for every awake state. Each row is 16 chars.
# 'X' = body main color, 'O' = highlight, 'B' = blush, '.' = transparent.
BODY = [
    "....XXXXXXXX....",
    "..XXOOXXXXXXXX..",
    ".XXOOXXXXXXXXXX.",
    ".XXOXXXXXXXXXXX.",
    "XXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXX",
    "XXXBBXXXXXXBBXXX",   # blush row
    "XXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXX",
    ".XXXXXXXXXXXXXX.",
    "..XXXXXXXXXXXX..",
    "...XXXXXXXXXX...",
    "....XXXXXXXX....",
]


def _eyes(*pixels: Tuple[int, int, str]) -> Dict[Tuple[int, int], str]:
    """Helper: build a sparse {(col, row): char} dict from triples.

    Using a dict keeps overlays compact and makes per-state diffs
    obvious — each state lists *only* the pixels it draws differently.
    """
    return {(c, r): ch for c, r, ch in pixels}


# Eye overlays per state — sparse {(col, row): char} dicts.
# 'P' = pupil (dark), 'W' = eye white.
EYES_IDLE = _eyes(
    (5, 6, 'P'), (10, 6, 'P'),
)

EYES_LISTENING = _eyes(
    (4, 5, 'W'), (5, 5, 'W'), (6, 5, 'W'),
    (5, 6, 'P'),
    (9, 5, 'W'), (10, 5, 'W'), (11, 5, 'W'),
    (10, 6, 'P'),
)

EYES_THINKING = _eyes(
    (4, 6, 'P'), (5, 5, 'P'), (6, 6, 'P'),
    (9, 6, 'P'), (10, 5, 'P'), (11, 6, 'P'),
)

EYES_SPEAKING = EYES_IDLE

EYES_ACTING = _eyes(
    (4, 6, 'P'), (5, 6, 'P'),
    (10, 6, 'P'), (11, 6, 'P'),
)

EYES_SUCCESS = _eyes(
    # Happy ^_^ — concave-up arcs
    (4, 6, 'P'), (5, 5, 'P'), (6, 6, 'P'),
    (9, 6, 'P'), (10, 5, 'P'), (11, 6, 'P'),
)

EYES_FAILED = _eyes(
    # x_x — diagonals at each eye
    (4, 5, 'P'), (5, 6, 'P'), (6, 5, 'P'),
    (4, 7, 'P'),               (6, 7, 'P'),
    (9, 5, 'P'), (10, 6, 'P'), (11, 5, 'P'),
    (9, 7, 'P'),               (11, 7, 'P'),
)

EYES_SLEEPING = _eyes(
    (4, 6, 'P'), (5, 6, 'P'), (6, 6, 'P'),
    (9, 6, 'P'), (10, 6, 'P'), (11, 6, 'P'),
)

# Blink uses the same closed-line shape as sleeping.
EYES_BLINK = EYES_SLEEPING


# Mouth overlays per state — 'M' = mouth dark.
MOUTH_IDLE = _eyes(
    (7, 10, 'M'), (8, 10, 'M'),
)

MOUTH_SMILE = _eyes(
    (6, 10, 'M'), (7, 11, 'M'), (8, 11, 'M'), (9, 10, 'M'),
)

MOUTH_FROWN = _eyes(
    (6, 11, 'M'), (7, 10, 'M'), (8, 10, 'M'), (9, 11, 'M'),
)

MOUTH_OPEN_SMALL = _eyes(
    (7, 10, 'M'), (8, 10, 'M'),
    (7, 11, 'M'), (8, 11, 'M'),
)

MOUTH_OPEN_LARGE = _eyes(
    (6, 10, 'M'), (7, 10, 'M'), (8, 10, 'M'), (9, 10, 'M'),
    (6, 11, 'M'), (7, 11, 'M'), (8, 11, 'M'), (9, 11, 'M'),
)

MOUTH_FLAT = _eyes(
    (6, 10, 'M'), (7, 10, 'M'), (8, 10, 'M'), (9, 10, 'M'),
)

MOUTH_NONE: Dict[Tuple[int, int], str] = {}


# ── Palette ────────────────────────────────────────────────────────


def _palette(ch: str, alpha: float = 1.0) -> QColor:
    """Map a sprite character to a QColor (with optional alpha multiply)."""
    if ch == 'X':         # body main color
        c = QColor(theme.ACCENT_COLOR)
    elif ch == 'O':       # highlight (lighter cyan)
        c = QColor(140, 220, 255)
    elif ch == 'B':       # blush (warm pink)
        c = QColor(255, 130, 180)
    elif ch == 'W':       # eye white
        c = QColor(245, 247, 252)
    elif ch == 'P':       # pupil (very dark)
        c = QColor(20, 22, 28)
    elif ch == 'M':       # mouth (very dark)
        c = QColor(20, 22, 28)
    else:
        return QColor(0, 0, 0, 0)
    if alpha < 1.0:
        c.setAlphaF(_clamp(alpha, 0, 1))
    return c


# ── Sub-renderers ──────────────────────────────────────────────────


def _draw_halo(painter: QPainter, cx: float, cy: float,
               state: PetState, time_ms: int) -> None:
    intensity = halo_intensity(state, time_ms)
    radius = 50 + 16 * intensity
    inner = halo_color(state)
    inner.setAlphaF(0.45 * intensity)
    outer = QColor(inner); outer.setAlphaF(0)
    grad = QRadialGradient(QPointF(cx, cy), radius)
    grad.setColorAt(0.45, inner)
    grad.setColorAt(1.0, outer)
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)


def _draw_sprite(painter: QPainter, sprite_x: int, sprite_y: int,
                 body, overlays, alpha: float = 1.0) -> None:
    """Blit the body sprite then each overlay on top.

    Antialiasing should be turned **off** before calling this — the
    pixel-art look depends on hard rectangle edges.
    """
    # 1. Body
    for row, line in enumerate(body):
        for col, ch in enumerate(line):
            if ch == '.':
                continue
            color = _palette(ch, alpha)
            painter.fillRect(
                sprite_x + col * PIXEL_SIZE,
                sprite_y + row * PIXEL_SIZE,
                PIXEL_SIZE, PIXEL_SIZE,
                color,
            )
    # 2. Overlays (eyes, mouth, accents)
    for overlay in overlays:
        for (col, row), ch in overlay.items():
            color = _palette(ch, alpha)
            painter.fillRect(
                sprite_x + col * PIXEL_SIZE,
                sprite_y + row * PIXEL_SIZE,
                PIXEL_SIZE, PIXEL_SIZE,
                color,
            )


def _eyes_for(state: PetState, blink: float) -> Dict[Tuple[int, int], str]:
    """Pick the right eye overlay, honouring the blink animation."""
    if blink > 0.5 and state not in (PetState.SLEEPING, PetState.HATCHING,
                                     PetState.SUCCESS, PetState.FAILED):
        return EYES_BLINK
    return {
        PetState.IDLE:      EYES_IDLE,
        PetState.LISTENING: EYES_LISTENING,
        PetState.THINKING:  EYES_THINKING,
        PetState.SPEAKING:  EYES_SPEAKING,
        PetState.ACTING:    EYES_ACTING,
        PetState.SUCCESS:   EYES_SUCCESS,
        PetState.FAILED:    EYES_FAILED,
        PetState.SLEEPING:  EYES_SLEEPING,
    }.get(state, EYES_IDLE)


def _mouth_for(state: PetState, time_ms: int) -> Dict[Tuple[int, int], str]:
    """Pick the right mouth overlay; SPEAKING animates between two frames."""
    if state == PetState.SUCCESS:
        return MOUTH_SMILE
    if state == PetState.FAILED:
        return MOUTH_FROWN
    if state == PetState.SLEEPING:
        return MOUTH_NONE
    if state == PetState.LISTENING:
        return MOUTH_OPEN_SMALL
    if state == PetState.SPEAKING:
        # Animate between large and small mouth at ~5Hz so it looks
        # like the pet is talking.
        return MOUTH_OPEN_LARGE if (time_ms // 100) % 2 == 0 else MOUTH_OPEN_SMALL
    if state in (PetState.THINKING, PetState.ACTING):
        return MOUTH_FLAT
    return MOUTH_IDLE


def _draw_zzz(painter: QPainter, cx: float, cy: float, time_ms: int) -> None:
    """Faint floating 'z' characters above-right of the sprite."""
    drift = (time_ms / 200.0) % 30
    pen = QPen(QColor(theme.TEXT_DIM))
    painter.setPen(pen)
    font = painter.font()
    for i, size in enumerate((10, 8, 6)):
        font.setPointSize(size)
        painter.setFont(font)
        x = cx + 24 + i * 5
        y = cy - 24 - i * 6 - drift * 0.3
        painter.drawText(QPointF(x, y), "z")


# Egg shape used during HATCHING — a smaller pixel sprite that wobbles.
EGG = [
    "....XXXX....",
    "..XXXXXXXX..",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    ".XXXXXXXXXX.",
    "..XXXXXXXX..",
    "....XXXX....",
]


def _draw_egg(painter: QPainter, cx: float, cy: float,
              wobble_radians: float, scale: float) -> None:
    """Draw the hatching egg with optional wobble + scale.

    Antialiasing should be off (called inside the same path that
    draws the sprite). The egg uses a beige palette so it visually
    contrasts with the cyan bean it cracks into.
    """
    if scale <= 0.0:
        return
    egg_px = 4
    grid_w = len(EGG[0])
    grid_h = len(EGG)
    painter.save()
    painter.translate(cx, cy)
    painter.rotate(math.degrees(wobble_radians))
    painter.scale(scale, scale)
    offset_x = -grid_w * egg_px // 2
    offset_y = -grid_h * egg_px // 2
    egg_color = QColor(245, 240, 220)
    for r, line in enumerate(EGG):
        for c, ch in enumerate(line):
            if ch == '.':
                continue
            painter.fillRect(
                offset_x + c * egg_px, offset_y + r * egg_px,
                egg_px, egg_px,
                egg_color,
            )
    painter.restore()


# ── Public draw entry point ────────────────────────────────────────


def draw(painter: QPainter, p: PaintInput) -> None:
    """Render one frame of the pixel mascot."""
    cx, cy = WIDTH / 2.0, HEIGHT / 2.0
    bob = bob_offset_y(p.state, p.time_ms)

    # 1. Halo — smooth gradient, AA on.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _draw_halo(painter, cx, cy + bob, p.state, p.time_ms)

    # 2. HATCHING is two phases: wobbling egg, then a fading-in bean.
    if p.state == PetState.HATCHING:
        progress = _clamp(p.hatch_progress, 0.0, 1.0)
        if progress < 0.55:
            wobble = 0.18 * math.sin(p.time_ms / 80.0) * progress
            scale = _clamp(progress / 0.10, 0.0, 1.0)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            _draw_egg(painter, cx, cy, wobble, scale)
            return
        # 55%+: fade in the bean character
        char_alpha = _clamp((progress - 0.55) / 0.45, 0.0, 1.0)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        _draw_sprite(
            painter,
            SPRITE_X, int(SPRITE_Y + bob),
            BODY,
            [_eyes_for(PetState.IDLE, 0.0), _mouth_for(PetState.IDLE, p.time_ms)],
            alpha=char_alpha * p.body_alpha,
        )
        return

    # 3. Awake states — blit body + overlays.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    _draw_sprite(
        painter,
        SPRITE_X, int(SPRITE_Y + bob),
        BODY,
        [_eyes_for(p.state, p.blink_progress), _mouth_for(p.state, p.time_ms)],
        alpha=p.body_alpha,
    )

    # 4. Sleeping accent — drifting Zs (text rendering wants AA back on).
    if p.state == PetState.SLEEPING:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_zzz(painter, cx, cy, p.time_ms)


# ── Style record ──────────────────────────────────────────────────


PIXEL_STYLE = PetStyle(
    name="pixel",
    description="Tamagotchi-style pixel mascot — friendly bean creature with retro 8-bit charm.",
    widget_size=(WIDTH, HEIGHT),
    draw=draw,
)
register(PIXEL_STYLE)
