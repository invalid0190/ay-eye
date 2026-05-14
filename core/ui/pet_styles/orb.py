"""
Neon energy orb — a glowing sphere with internal particles.

Pure abstract aesthetic. No face, no character — just light, color
and motion. Designed for users who want the pet to feel like a
*power core* / *magic gem* rather than a creature.

What changes per state
----------------------
* Orb **color**     — cyan / red / green / etc. via ``halo_color``.
* Orb **radius**    — pulses harder during high-energy states.
* Particle **speed** — multiplied by an excitement factor.
* Particle **count** — same; visual density carried by speed.
* Halo intensity    — same shared helper everyone uses.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient

from core.ui.pet_painter import (
    PaintInput, PetState, _clamp,
    bob_offset_y, halo_color, halo_intensity,
)
from core.ui.pet_styles import PetStyle, register
from core.ui.theme import theme


# ── Geometry ────────────────────────────────────────────────────────


WIDTH = 110
HEIGHT = 110
CX = WIDTH / 2.0
CY = HEIGHT / 2.0
ORB_RADIUS = 26.0
PARTICLE_COUNT = 7


# ── Sub-renderers ──────────────────────────────────────────────────


def _draw_halo(painter: QPainter, cx: float, cy: float,
               state: PetState, time_ms: int) -> None:
    intensity = halo_intensity(state, time_ms)
    radius = ORB_RADIUS + 12 + 18 * intensity
    inner = halo_color(state); inner.setAlphaF(0.55 * intensity)
    outer = QColor(inner); outer.setAlphaF(0)
    grad = QRadialGradient(QPointF(cx, cy), radius)
    grad.setColorAt(0.40, inner)
    grad.setColorAt(1.0, outer)
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)


def _orb_radius(state: PetState, time_ms: int) -> float:
    """State-dependent radius pulse. Higher energy → bigger / faster."""
    if state == PetState.LISTENING:
        return ORB_RADIUS + 2.5 + 1.5 * math.sin(time_ms / 200.0)
    if state == PetState.SPEAKING:
        return ORB_RADIUS + 2.0 * math.sin(time_ms / 80.0)
    if state == PetState.ACTING:
        return ORB_RADIUS + 1.5 + 1.5 * math.sin(time_ms / 150.0)
    if state == PetState.IDLE:
        return ORB_RADIUS + 1.0 * math.sin(time_ms / 700.0)
    if state == PetState.SLEEPING:
        return ORB_RADIUS - 4.0
    if state == PetState.THINKING:
        return ORB_RADIUS - 1.5
    if state == PetState.FAILED:
        return ORB_RADIUS - 2.0
    return ORB_RADIUS


def _orb_core_color(state: PetState) -> QColor:
    """Inner brightest color of the orb sphere — biased a bit warmer
    for warning/error/success states than the matching halo color."""
    if state == PetState.FAILED:
        return QColor(255, 80, 80)
    if state == PetState.SUCCESS:
        return QColor(80, 230, 130)
    if state == PetState.LISTENING:
        return QColor(255, 100, 90)
    if state in (PetState.ACTING, PetState.SPEAKING):
        return QColor(80, 230, 140)
    if state == PetState.SLEEPING:
        return QColor(140, 145, 160)
    if state == PetState.THINKING:
        return QColor(theme.THINKING)
    return QColor(theme.ACCENT_COLOR)


def _draw_orb(painter: QPainter, cx: float, cy: float, radius: float,
              state: PetState, alpha: float) -> None:
    if alpha <= 0.0 or radius <= 0.0:
        return

    core = _orb_core_color(state)
    bright = QColor(255, 255, 255); bright.setAlphaF(0.95 * alpha)
    mid = QColor(core);              mid.setAlphaF(0.95 * alpha)
    dark = QColor(core.darker(180)); dark.setAlphaF(0.90 * alpha)

    # Off-center bright spot gives a 3D sphere read.
    grad = QRadialGradient(
        QPointF(cx - radius * 0.25, cy - radius * 0.25),
        radius * 1.4,
    )
    grad.setColorAt(0.00, bright)
    grad.setColorAt(0.35, mid)
    grad.setColorAt(1.00, dark)
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)

    # Rim highlight.
    rim = QColor(255, 255, 255); rim.setAlphaF(0.30 * alpha)
    pen = QPen(rim); pen.setWidthF(1.0)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), max(0.0, radius - 0.5),
                        max(0.0, radius - 0.5))


def _particle_speed_mult(state: PetState) -> float:
    return {
        PetState.LISTENING: 2.0,
        PetState.THINKING:  1.6,
        PetState.SPEAKING:  1.8,
        PetState.ACTING:    2.2,
        PetState.SUCCESS:   1.3,
        PetState.FAILED:    2.5,
        PetState.SLEEPING:  0.3,
        PetState.IDLE:      1.0,
        PetState.HATCHING:  0.8,
    }.get(state, 1.0)


def _draw_particles(painter: QPainter, cx: float, cy: float, radius: float,
                    state: PetState, time_ms: int, alpha: float) -> None:
    """Small white particles orbiting inside the orb at varied radii."""
    speed = _particle_speed_mult(state)
    pcolor = QColor(255, 255, 255); pcolor.setAlphaF(0.85 * alpha)
    painter.setBrush(QBrush(pcolor))
    painter.setPen(Qt.PenStyle.NoPen)

    for i in range(PARTICLE_COUNT):
        # Distribute particles across orbit radii for parallax depth.
        orbit_r = radius * (0.30 + 0.55 * (i / max(1, PARTICLE_COUNT - 1)))
        # Slight per-particle speed jitter so they don't stay collinear.
        jitter = 0.4 + 0.6 * ((i * 7) % 5) / 5.0
        angle = (time_ms / 1000.0) * speed * jitter \
                + i * (2 * math.pi / PARTICLE_COUNT)
        x = cx + orbit_r * math.cos(angle)
        y = cy + orbit_r * math.sin(angle)
        # Outer particles are a touch smaller — sells depth.
        psize = 1.6 + 0.8 * (1.0 - i / max(1, PARTICLE_COUNT - 1))
        painter.drawEllipse(QPointF(x, y), psize, psize)


def _draw_zzz(painter: QPainter, cx: float, cy: float,
              time_ms: int, alpha: float) -> None:
    drift = (time_ms / 250.0) % 25
    c = QColor(theme.TEXT_DIM); c.setAlphaF(0.85 * alpha)
    painter.setPen(QPen(c))
    f = painter.font()
    for i, size in enumerate((10, 8, 6)):
        f.setPointSize(size)
        painter.setFont(f)
        painter.drawText(
            QPointF(cx + 22 + i * 5, cy - 22 - i * 6 - drift * 0.3),
            "z",
        )


# ── Public draw entry point ────────────────────────────────────────


def draw(painter: QPainter, p: PaintInput) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    cx = CX
    cy = CY + bob_offset_y(p.state, p.time_ms)

    _draw_halo(painter, cx, cy, p.state, p.time_ms)

    # HATCHING grows the orb from 0 → full radius while alpha ramps.
    alpha = p.body_alpha
    radius = _orb_radius(p.state, p.time_ms)
    if p.state == PetState.HATCHING:
        progress = _clamp(p.hatch_progress, 0.0, 1.0)
        alpha *= progress
        radius *= progress

    _draw_orb(painter, cx, cy, radius, p.state, alpha)
    if alpha > 0.5:
        _draw_particles(painter, cx, cy, radius, p.state, p.time_ms, alpha)

    if p.state == PetState.SLEEPING:
        _draw_zzz(painter, cx, cy, p.time_ms, alpha)


# ── Style record ──────────────────────────────────────────────────


ORB_STYLE = PetStyle(
    name="orb",
    description="Neon energy sphere — a glowing core with internal particles, pure abstract aesthetic.",
    widget_size=(WIDTH, HEIGHT),
    draw=draw,
)
register(ORB_STYLE)
