"""
Pet state controller.

Translates engine bus events (``BRAIN_THINKING``, ``ACTION_COMPLETED``,
etc.) into ``PetState`` transitions, with three responsibilities:

1. **Mute gate.** When the user has set ``muted=True`` the pet stays
   in ``SLEEPING`` regardless of what's happening underneath.
2. **Transient state auto-revert.** ``SUCCESS`` and ``FAILED`` are
   short-lived "punctuation" states — they should pop for ~1.5 s and
   then return to whatever ambient state is appropriate. The
   controller schedules that revert so the widget never has to.
3. **Cursor proximity tracking.** Computes a clamped pupil offset
   based on the cursor's screen position relative to the pet, so the
   eyes can follow the cursor in ``IDLE`` / ``LISTENING``.

The controller is **headless** — it does not touch QPainter or
QWidget. It exposes a Qt signal the widget connects to, plus a tick
method for the widget's animation timer to call. That means tests
drive every transition without any window ever being shown.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except Exception:  # pragma: no cover - Qt should always be available
    _HAS_QT = False
    class QObject:  # type: ignore[no-redef]
        pass
    def pyqtSignal(*_a, **_kw):  # type: ignore[no-redef]
        return None

from core.ui.pet_painter import (
    PetState,
    PUPIL_TRACK_RANGE,
    TRANSIENT_DURATION_MS,
    TRANSIENT_STATES,
    clamp_eye_target,
)


# ── Bus-event → state mapping ────────────────────────────────────────


# Map each subscribed bus event to a ``(state, transient)`` pair.
# ``transient=True`` means "show this for ~TRANSIENT_DURATION_MS, then
# revert to IDLE". Order matters only for documentation; lookup is
# by exact event name.
_EVENT_MAP: dict[str, Tuple[PetState, bool]] = {
    "VOICE_RECORDING_START":      (PetState.LISTENING, False),
    "VOICE_RECORDING_STOP":       (PetState.THINKING,  False),
    "BRAIN_THINKING":             (PetState.THINKING,  False),
    "BRAIN_RESPONDED":            (PetState.IDLE,      False),
    "BRAIN_ERROR":                (PetState.FAILED,    True),
    "ACTION_STARTED":             (PetState.ACTING,    False),
    "ACTION_COMPLETED":           (PetState.SUCCESS,   True),
    "ACTION_ABORTED":             (PetState.FAILED,    True),
    "EMERGENCY_STOP":             (PetState.FAILED,    True),
    "AI_GREETING":                (PetState.SPEAKING,  False),
    "SAFE_NO_ACTION":             (PetState.IDLE,      False),
    "VOICE_IGNORED":              (PetState.IDLE,      False),
}


# ── Controller ──────────────────────────────────────────────────────


@dataclass
class _ControllerState:
    """Mutable internal state — kept as a dataclass so tests can read
    every field without poking around private attributes."""

    state: PetState = PetState.HATCHING
    last_event_ts_ms: int = 0
    transient_until_ms: int = 0  # 0 = no transient pending
    eye_target_dx: float = 0.0
    eye_target_dy: float = 0.0
    muted: bool = False


class PetController(QObject):
    """Bus subscriber + transient/cursor scheduler.

    Emits ``state_changed(PetState)`` whenever the visible state
    transitions. The widget connects this signal to its repaint hook.
    """

    state_changed = pyqtSignal(object) if _HAS_QT else None  # PetState

    def __init__(
        self,
        bus=None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        muted: bool = False,
    ):
        super().__init__()
        self._bus = bus
        self._clock_ms = clock_ms
        self._st = _ControllerState(muted=muted)
        self._subscribed = False

    # ── Public surface ─────────────────────────────────────────────

    @property
    def state(self) -> PetState:
        return self._st.state

    @property
    def eye_target(self) -> Tuple[float, float]:
        return (self._st.eye_target_dx, self._st.eye_target_dy)

    def set_muted(self, muted: bool) -> None:
        self._st.muted = bool(muted)
        if muted:
            self._set_state(PetState.SLEEPING)
        else:
            # Wake up; controller will resume normal mapping on next event.
            self._set_state(PetState.IDLE)

    def attach_bus(self) -> None:
        """Subscribe to the engine bus. Idempotent."""
        if self._subscribed or self._bus is None:
            return
        for evt, (target, _) in _EVENT_MAP.items():
            self._bus.subscribe(evt, lambda data, e=evt: self.on_event(e, data))
        self._subscribed = True

    def on_event(self, event: str, _data=None) -> None:
        """Drive a state transition from a bus event.

        This is also the test hook — unit tests fire ``on_event`` directly
        rather than going through the bus.
        """
        mapping = _EVENT_MAP.get(event)
        if mapping is None:
            return
        target, transient = mapping

        # While muted, the only state we ever show is SLEEPING. Engine
        # events still arrive; we just ignore their visual impact.
        if self._st.muted:
            self._set_state(PetState.SLEEPING)
            return

        self._st.last_event_ts_ms = self._clock_ms()
        if transient:
            self._st.transient_until_ms = self._st.last_event_ts_ms + TRANSIENT_DURATION_MS

        self._set_state(target)

    def hatch_complete(self) -> None:
        """Called by the widget when the hatch animation finishes."""
        if self._st.state == PetState.HATCHING:
            self._set_state(
                PetState.SLEEPING if self._st.muted else PetState.IDLE
            )

    def update_cursor(self, dx_pixels: float, dy_pixels: float,
                      proximity_radius: float = 250.0) -> None:
        """Update where the pupil should look.

        ``dx``/``dy`` are the cursor's screen offset from the pet's
        body center. We scale that into the pupil's tiny tracking
        range, then clamp. When the cursor is far from the pet (more
        than ``proximity_radius`` px), we recentre the pupils so the
        pet "loses interest" and looks straight ahead.
        """
        distance = (dx_pixels * dx_pixels + dy_pixels * dy_pixels) ** 0.5
        if distance > proximity_radius:
            tx = ty = 0.0
        else:
            # Map the cursor position onto the pupil's tracking range.
            # Distance ratio drops smoothly from 1 (close) to 0 (at radius).
            ratio = 1.0 - (distance / proximity_radius)
            scale = (PUPIL_TRACK_RANGE * ratio) / max(distance, 1e-3)
            tx = dx_pixels * scale
            ty = dy_pixels * scale
        self._st.eye_target_dx, self._st.eye_target_dy = clamp_eye_target(tx, ty)

    def tick(self) -> None:
        """Drive scheduled transitions. Widget calls this at ~60fps.

        Currently the only thing that needs ticking is the transient
        revert: when ``transient_until_ms`` has passed, fall back to
        ``IDLE`` (or ``SLEEPING`` if muted).
        """
        if self._st.transient_until_ms == 0:
            return
        now = self._clock_ms()
        if now >= self._st.transient_until_ms:
            self._st.transient_until_ms = 0
            self._set_state(
                PetState.SLEEPING if self._st.muted else PetState.IDLE
            )

    # ── Internal ───────────────────────────────────────────────────

    def _set_state(self, new_state: PetState) -> None:
        if new_state == self._st.state:
            return
        self._st.state = new_state
        if _HAS_QT and self.state_changed is not None:
            try:
                self.state_changed.emit(new_state)
            except Exception:
                pass
