"""
Shared types and helpers for the desktop pet's pluggable visual system.

The actual rendering lives in ``core.ui.pet_styles.*``. This module
defines:

* ``PetState`` — the agent-state enum the pet animates through.
* ``PaintInput`` — the bundle of transient parameters every style's
  ``draw()`` function consumes.
* A handful of pure helpers (``bob_offset_y``, ``halo_color``, …)
  that every style is free to reuse so the visual language stays
  consistent across styles.

Keeping these helpers in one module also means the unit tests in
``test_pet.py`` can validate the *shared* visual contract once
(e.g., halo intensity stays in [0,1] for every state) without
duplicating the same assertions per style.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from PyQt6.QtGui import QColor

from core.ui.theme import theme


# ── Public state enum ────────────────────────────────────────────────


class PetState(str, Enum):
    """Every visual mode the pet can be in."""

    HATCHING   = "hatching"
    SLEEPING   = "sleeping"
    IDLE       = "idle"
    LISTENING  = "listening"
    THINKING   = "thinking"
    SPEAKING   = "speaking"
    ACTING     = "acting"
    SUCCESS    = "success"
    FAILED     = "failed"


# Pet states that auto-revert to IDLE after a short window.
TRANSIENT_STATES: frozenset[PetState] = frozenset({
    PetState.SUCCESS, PetState.FAILED,
})

# How long transient states linger before the controller flips back.
TRANSIENT_DURATION_MS = 1500

# Pupil tracking — how far the pupil can drift to follow the cursor.
PUPIL_TRACK_RANGE = 3.0


# ── Paint input bundle ──────────────────────────────────────────────


@dataclass
class PaintInput:
    """Transient paint-time parameters. Bundled into a struct so
    callers don't have to thread a dozen arguments through every call."""

    state: PetState = PetState.IDLE
    time_ms: int = 0
    blink_progress: float = 0.0        # 0 = fully open, 1 = fully closed
    eye_target_dx: float = 0.0          # cursor offset, already clamped
    eye_target_dy: float = 0.0
    hatch_progress: float = 0.0         # 0 → 1 over the hatch sequence
    body_alpha: float = 1.0             # 0 = invisible, 1 = fully visible


# ── Shared helpers (used by every style) ───────────────────────────


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_eye_target(dx: float, dy: float) -> Tuple[float, float]:
    """Clamp the cursor-tracking pupil offset to the safe range."""
    return (
        _clamp(dx, -PUPIL_TRACK_RANGE, PUPIL_TRACK_RANGE),
        _clamp(dy, -PUPIL_TRACK_RANGE, PUPIL_TRACK_RANGE),
    )


def bob_offset_y(state: PetState, time_ms: int) -> float:
    """Subtle vertical sine bob applied to the whole pet.

    Hatching is *not* bobbed (the egg/reveal should sit still).
    Sleeping uses a slower, smaller wave for a "breathing in sleep" feel.
    Other states share a single calm period so styles look consistent.
    """
    if state == PetState.HATCHING:
        return 0.0
    if state == PetState.SLEEPING:
        return 1.0 * math.sin(time_ms / 1500.0)
    period_ms = 2200.0 if state in (
        PetState.IDLE, PetState.LISTENING, PetState.THINKING, PetState.SPEAKING
    ) else 1400.0
    return 2.5 * math.sin(time_ms / (period_ms / (2 * math.pi)))


def halo_color(state: PetState) -> QColor:
    """Pick the inner halo color for a given state.

    The hue carries the *mood* — red for alarm/listening, cyan for
    thought, green for action/success — and styles are encouraged to
    surface this color somewhere in their composition.
    """
    if state == PetState.LISTENING:
        return QColor(theme.RECORDING)
    if state == PetState.THINKING:
        return QColor(theme.THINKING)
    if state in (PetState.ACTING, PetState.SPEAKING):
        return QColor(theme.ACTING)
    if state == PetState.SUCCESS:
        return QColor(theme.SUCCESS)
    if state == PetState.FAILED:
        return QColor(theme.ERROR)
    if state == PetState.SLEEPING:
        c = QColor(theme.GRAY_COLOR); c.setAlpha(120)
        return c
    if state == PetState.HATCHING:
        return QColor(theme.WARNING)
    return QColor(theme.ACCENT_COLOR)


def halo_intensity(state: PetState, time_ms: int) -> float:
    """Returns 0..1 for the halo strength right now (state-dependent pulse).

    Higher-energy states pulse harder and faster. Sleeping is dim
    and slow. Transient states stay bright with a small flicker.
    """
    base, amp, period_ms = {
        PetState.IDLE:      (0.30, 0.10, 2200.0),
        PetState.SLEEPING:  (0.18, 0.05, 2400.0),
        PetState.LISTENING: (0.55, 0.25, 600.0),
        PetState.THINKING:  (0.50, 0.18, 1000.0),
        PetState.SPEAKING:  (0.55, 0.25, 350.0),
        PetState.ACTING:    (0.65, 0.20, 700.0),
        PetState.SUCCESS:   (0.80, 0.10, 500.0),
        PetState.FAILED:    (0.70, 0.15, 400.0),
        PetState.HATCHING:  (0.45, 0.30, 700.0),
    }.get(state, (0.30, 0.10, 2200.0))
    pulse = math.sin(time_ms / (period_ms / (2 * math.pi)))
    return _clamp(base + amp * pulse, 0.0, 1.0)
