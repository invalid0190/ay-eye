"""
ASCII / kaomoji face — Codex-CLI vibe.

A single line of monospace text that morphs by state, framed in a
glassy rounded card. Pure typographic personality — no sprite, no
gradient orb, just characters doing the work.

Why this style exists
---------------------
Some users (and the user who asked us to build this picker)
prefer the *terminal* aesthetic to a fluffy cartoon character.
Codex-CLI's small inline indicator is the obvious reference: a
calm, monospace, faintly-glowing widget that you almost forget is
there until the agent is doing something interesting.

State faces
-----------
* IDLE      — ``( o _ o )``
* LISTENING — ``( ◉ _ ◉ )``
* THINKING  — ``( · _ · )``  (animated dots above)
* SPEAKING  — ``( o ‿ o )``
* ACTING    — ``( > _ < )``
* SUCCESS   — ``( ^ ‿ ^ )``
* FAILED    — ``( x _ x )``
* SLEEPING  — ``( - _ - )``  + drifting Zs
* HATCHING  — face fades in over the rounded card.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient,
)

from core.ui.pet_painter import (
    PaintInput, PetState, _clamp,
    bob_offset_y, halo_color, halo_intensity,
)
from core.ui.pet_styles import PetStyle, register
from core.ui.theme import theme


# ── Geometry ────────────────────────────────────────────────────────


WIDTH = 140
HEIGHT = 70
CARD_PAD_X = 10
CARD_PAD_Y = 10


# ── Face strings per state ─────────────────────────────────────────


FACES = {
    PetState.IDLE:      "( o _ o )",
    PetState.LISTENING: "( ◉ _ ◉ )",
    PetState.THINKING:  "( · _ · )",
    PetState.SPEAKING:  "( o ‿ o )",
    PetState.ACTING:    "( > _ < )",
    PetState.SUCCESS:   "( ^ ‿ ^ )",
    PetState.FAILED:    "( x _ x )",
    PetState.SLEEPING:  "( - _ - )",
    PetState.HATCHING:  "( · _ · )",
}

BLINK_FACE = "( - _ - )"


# ── Sub-renderers ──────────────────────────────────────────────────


def _draw_halo(painter: QPainter, cx: float, cy: float,
               state: PetState, time_ms: int) -> None:
    intensity = halo_intensity(state, time_ms)
    radius = 64 + 22 * intensity
    inner = halo_color(state); inner.setAlphaF(0.40 * intensity)
    outer = QColor(inner); outer.setAlphaF(0)
    grad = QRadialGradient(QPointF(cx, cy), radius)
    grad.setColorAt(0.40, inner)
    grad.setColorAt(1.0, outer)
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)


def _draw_glass_card(painter: QPainter, x: float, y: float,
                     w: float, h: float, alpha: float) -> None:
    """Translucent rounded rect with a thin cyan border — the frame
    around the face. Reads as 'a small terminal panel'."""
    if alpha <= 0:
        return
    bg = QColor(20, 22, 28); bg.setAlphaF(0.85 * alpha)
    border = QColor(theme.ACCENT_COLOR); border.setAlphaF(0.40 * alpha)

    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), 10, 10)
    painter.fillPath(path, QBrush(bg))

    pen = QPen(border)
    pen.setWidthF(1.0)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _draw_thinking_dots(painter: QPainter, cx: float, top_y: float,
                        time_ms: int, alpha: float) -> None:
    """Three small dots above the face that cycle on while THINKING."""
    cycle = (time_ms // 250) % 3
    base = QColor(theme.THINKING)
    for i in range(3):
        c = QColor(base)
        c.setAlphaF(0.85 * alpha if i == cycle else 0.18 * alpha)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx - 14 + i * 14, top_y), 2.4, 2.4)


def _draw_zzz(painter: QPainter, x: float, y: float,
              time_ms: int, alpha: float) -> None:
    drift = (time_ms / 250.0) % 25
    c = QColor(theme.TEXT_DIM); c.setAlphaF(0.85 * alpha)
    painter.setPen(QPen(c))
    f = painter.font()
    for i, size in enumerate((10, 8, 6)):
        f.setPointSize(size)
        painter.setFont(f)
        painter.drawText(
            QPointF(x + i * 5, y - i * 6 - drift * 0.25),
            "z",
        )


# ── Public draw entry point ────────────────────────────────────────


def draw(painter: QPainter, p: PaintInput) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    cx, cy = WIDTH / 2.0, HEIGHT / 2.0
    bob = bob_offset_y(p.state, p.time_ms)

    _draw_halo(painter, cx, cy + bob, p.state, p.time_ms)

    # Hatching fades the card + face in together.
    alpha = p.body_alpha
    if p.state == PetState.HATCHING:
        alpha *= _clamp(p.hatch_progress, 0.0, 1.0)

    # Glass card behind the text.
    card_w = WIDTH - 2 * CARD_PAD_X
    card_h = HEIGHT - 2 * CARD_PAD_Y
    _draw_glass_card(painter, CARD_PAD_X, CARD_PAD_Y + bob,
                     card_w, card_h, alpha)

    # Pick the face.
    if (p.blink_progress > 0.5
            and p.state not in (PetState.SLEEPING, PetState.HATCHING,
                                PetState.SUCCESS, PetState.FAILED)):
        face = BLINK_FACE
    else:
        face = FACES.get(p.state, FACES[PetState.IDLE])

    # Render the face text centered.
    color = QColor(theme.ACCENT_COLOR); color.setAlphaF(alpha)
    painter.setPen(QPen(color))
    font = QFont(getattr(theme, "FONT_MONO", "Consolas"))
    font.setPointSize(13)
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    text_w = metrics.horizontalAdvance(face)
    text_x = (WIDTH - text_w) / 2
    # Anchor baseline a touch below the card's vertical center for
    # optical balance — descenders + parens settle nicely there.
    text_y = (HEIGHT + metrics.ascent()) / 2 + bob - 2
    painter.drawText(QPointF(text_x, text_y), face)

    # Per-state ornaments.
    if p.state == PetState.THINKING:
        _draw_thinking_dots(painter, cx, CARD_PAD_Y + bob - 6,
                            p.time_ms, alpha)
    elif p.state == PetState.SLEEPING:
        _draw_zzz(painter, WIDTH - 28, CARD_PAD_Y + bob + 4,
                  p.time_ms, alpha)


# ── Style record ──────────────────────────────────────────────────


ASCII_STYLE = PetStyle(
    name="ascii",
    description="Codex-CLI vibe — a monospace text face that morphs by state, framed in a glassy card.",
    widget_size=(WIDTH, HEIGHT),
    draw=draw,
)
register(ASCII_STYLE)
