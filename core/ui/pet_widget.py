"""
The actual desktop pet QWidget.

Owns the window, the animation timer, and the user input (drag /
single-click / double-click / right-click menu). All visual
rendering is delegated to ``pet_painter``; all state transitions are
delegated to ``pet_controller``. This file is just glue:

* sets up a frameless transparent always-on-top window,
* drives the paint loop with a QTimer,
* converts mouse events into clicks / drags / context menus,
* persists position + hatched flag through ``pet_settings``.
"""

from __future__ import annotations

import math
import random
import time
from typing import Callable, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
)
from PyQt6.QtWidgets import QMenu, QWidget

from core.engine.event_bus import bus
from core.state import pet_settings as pet_settings_module
from core.ui import pet_styles
from core.ui.pet_controller import PetController
from core.ui.pet_painter import (
    PaintInput,
    PetState,
)
from core.utils.logger import logger


# ── Tunables ────────────────────────────────────────────────────────


# How long the hatch animation runs. Matches the painter's progress 0→1
# mapping so visuals + timer stay in sync.
HATCH_DURATION_MS = 2200

# Minimum mouse displacement (px) before a press → release counts as a
# drag rather than a click.
DRAG_THRESHOLD_PX = 4

# Animation cadence. 60Hz is overkill for the visuals we draw and adds
# CPU pressure on weaker laptops, so we paint at 30Hz which still
# looks silky for our slow sine-bobs and pulses.
FRAME_INTERVAL_MS = 33

# Default corner offset on first ever launch (bottom-right of the
# primary screen, with a comfy gap from the taskbar).
DEFAULT_CORNER_GAP_PX = 24


class AyEyePet(QWidget):
    """Frameless, always-on-top desktop companion.

    Connects to the existing ``bus`` so engine events automatically
    drive the pet's visible state. A single click on the pet toggles
    the dashboard via the ``dashboard_toggle_requested`` signal,
    which ``main.py`` wires to the actual show/hide logic.
    """

    dashboard_toggle_requested = pyqtSignal()
    ghost_typing_requested = pyqtSignal()

    def __init__(
        self,
        bus_obj=None,
        settings_module=None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._bus = bus_obj or bus
        self._settings_mod = settings_module or pet_settings_module
        self._settings = self._settings_mod.pet_settings

        # ── Window flags ─────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)

        # ── Active visual style ───────────────────────────────
        # Looked up from the registry by name. ``pet_styles.get`` falls
        # back to the default style if the saved name is unknown
        # (e.g. user downgraded to a build that no longer ships a style).
        self._style = pet_styles.get(self._settings.style)
        self.setFixedSize(*self._style.widget_size)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # ── Controller ────────────────────────────────────────────
        self.controller = PetController(bus=self._bus, muted=self._settings.muted)
        if self.controller.state_changed is not None:
            self.controller.state_changed.connect(lambda _s: self.update())
        self.controller.attach_bus()

        # ── Show / hide command subscriptions ────────────────────
        # Typed commands ("pet", "hide pet", etc.) are intercepted in
        # the command panel and republished as these synthetic events
        # so the brain never sees them.
        try:
            self._bus.subscribe("PET_SHOW_REQUESTED", lambda _d=None: self.show_pet())
            self._bus.subscribe("PET_HIDE_REQUESTED", lambda _d=None: self._hide_pet())
            self._bus.subscribe(
                "PET_STYLE_REQUESTED",
                lambda d=None: self.set_style(
                    d.get("name", "") if isinstance(d, dict) else str(d or "")
                ),
            )
        except Exception:
            pass

        # ── Paint state ───────────────────────────────────────────
        self._start_ts_ms = self._now_ms()
        self._hatch_start_ms: Optional[int] = None
        self._next_blink_ms = self._start_ts_ms + random.randint(2500, 6000)
        self._blink_anim_start_ms: Optional[int] = None

        # ── Drag state ────────────────────────────────────────────
        self._drag_start_global: Optional[QPoint] = None
        self._drag_origin_pos: Optional[QPoint] = None
        self._is_dragging: bool = False

        # ── Position ──────────────────────────────────────────────
        self._restore_position()

        # ── Animation timer ──────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(FRAME_INTERVAL_MS)

        # ── Hatch decision ───────────────────────────────────────
        if self._settings.hatched:
            # Skip straight to idle / sleeping; the painter never
            # renders the egg in this branch.
            self.controller.hatch_complete()
        else:
            self._hatch_start_ms = self._start_ts_ms

    # ── Lifecycle helpers ─────────────────────────────────────────

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _restore_position(self) -> None:
        s = self._settings
        if s.position_x is not None and s.position_y is not None:
            self.move(int(s.position_x), int(s.position_y))
            return
        # First-ever placement: bottom-right of the primary screen.
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.move(100, 100)
            return
        geo = screen.availableGeometry()
        w, h = self._style.widget_size
        x = geo.right() - w - DEFAULT_CORNER_GAP_PX
        y = geo.bottom() - h - DEFAULT_CORNER_GAP_PX
        self.move(x, y)

    def _persist_settings(self) -> None:
        try:
            self._settings.position_x = self.x()
            self._settings.position_y = self.y()
            self._settings_mod.save(self._settings)
        except Exception as e:
            logger.logger.warning(f"AyEyePet: failed to save settings - {e}")

    # ── Paint pipeline ────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        try:
            self._style.draw(painter, self._build_paint_input())
        finally:
            painter.end()

    def _build_paint_input(self) -> PaintInput:
        now = self._now_ms()
        time_ms = now - self._start_ts_ms

        # Hatch progress: 0..1 over HATCH_DURATION_MS, else fixed at 1.
        if self._hatch_start_ms is not None:
            hatch_t = (now - self._hatch_start_ms) / float(HATCH_DURATION_MS)
            if hatch_t >= 1.0:
                hatch_t = 1.0
                self._hatch_start_ms = None
                self._settings.hatched = True
                self._persist_settings()
                self.controller.hatch_complete()
        else:
            hatch_t = 1.0

        # Eye-blink: a quick 200ms triangle wave around 0..1..0.
        blink_progress = self._compute_blink_progress(now)

        # Cursor proximity → pupil offset.
        self._update_cursor_target()

        state = (
            PetState.HATCHING
            if self._hatch_start_ms is not None and hatch_t < 1.0
            else self.controller.state
        )

        eye_dx, eye_dy = self.controller.eye_target

        return PaintInput(
            state=state,
            time_ms=time_ms,
            blink_progress=blink_progress,
            eye_target_dx=eye_dx,
            eye_target_dy=eye_dy,
            hatch_progress=hatch_t,
            body_alpha=1.0,
        )

    def _compute_blink_progress(self, now_ms: int) -> float:
        """Returns 0..1 where 1 means fully closed.

        We schedule the *next* blink time when the previous one ends,
        with a randomised interval so the pet doesn't blink in
        lockstep — small detail, big personality boost.
        """
        if self._blink_anim_start_ms is None:
            if now_ms >= self._next_blink_ms:
                self._blink_anim_start_ms = now_ms
            return 0.0
        elapsed = now_ms - self._blink_anim_start_ms
        duration = 220  # total blink duration (close + open)
        if elapsed >= duration:
            self._blink_anim_start_ms = None
            self._next_blink_ms = now_ms + random.randint(2500, 6000)
            return 0.0
        # Triangle wave: ramps up to 1 at the midpoint, ramps back to 0.
        half = duration / 2
        if elapsed <= half:
            return elapsed / half
        return 1.0 - (elapsed - half) / half

    def _update_cursor_target(self) -> None:
        try:
            cursor = QCursor.pos()
            w, h = self._style.widget_size
            pet_center_global_x = self.x() + w / 2
            pet_center_global_y = self.y() + h / 2
            self.controller.update_cursor(
                dx_pixels=cursor.x() - pet_center_global_x,
                dy_pixels=cursor.y() - pet_center_global_y,
            )
        except Exception:
            # If the screen probe fails (multi-monitor edge cases) just
            # re-center the eyes — don't crash the paint loop.
            self.controller.update_cursor(0, 0)

    # ── Tick ─────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        # Let the controller handle scheduled transient reverts.
        self.controller.tick()
        # Force a repaint (animations are time-driven, not state-driven).
        self.update()

    # ── Mouse handling ───────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = e.globalPosition().toPoint()
            self._drag_origin_pos = self.pos()
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start_global is None or self._drag_origin_pos is None:
            return super().mouseMoveEvent(e)
        delta = e.globalPosition().toPoint() - self._drag_start_global
        if not self._is_dragging:
            if abs(delta.x()) + abs(delta.y()) > DRAG_THRESHOLD_PX:
                self._is_dragging = True
        if self._is_dragging:
            self.move(self._drag_origin_pos + delta)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(e)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        was_drag = self._is_dragging
        self._drag_start_global = None
        self._drag_origin_pos = None
        self._is_dragging = False
        if was_drag:
            self._persist_settings()
            return
        # No drag → treat as a click. Toggle the dashboard.
        try:
            self.dashboard_toggle_requested.emit()
        except Exception as ex:
            logger.logger.warning(f"AyEyePet: toggle signal failed - {ex}")

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(e)
        # Cancel any pending single-click action by clearing drag state.
        self._drag_start_global = None
        self._is_dragging = False
        try:
            self.ghost_typing_requested.emit()
        except Exception as ex:
            logger.logger.warning(f"AyEyePet: ghost-type signal failed - {ex}")

    # ── Context menu ─────────────────────────────────────────────

    def _show_context_menu(self, point: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: rgba(18, 18, 22, 245); "
            "color: rgb(235,235,240); border: 1px solid rgba(255,255,255,30); "
            "padding: 4px; border-radius: 8px; }"
            "QMenu::item:selected { background-color: rgba(0,186,255,80); }"
        )

        toggle_dash = QAction("Open dashboard", menu)
        toggle_dash.triggered.connect(self.dashboard_toggle_requested.emit)
        menu.addAction(toggle_dash)

        ghost = QAction("Dictate (Ghost typing)", menu)
        ghost.triggered.connect(self.ghost_typing_requested.emit)
        menu.addAction(ghost)

        menu.addSeparator()

        mute_label = "Wake up" if self._settings.muted else "Sleep (mute)"
        mute_action = QAction(mute_label, menu)
        mute_action.triggered.connect(self._toggle_muted)
        menu.addAction(mute_action)

        rehatch = QAction("Re-hatch", menu)
        rehatch.triggered.connect(self._rehatch)
        menu.addAction(rehatch)

        menu.addSeparator()

        hide_action = QAction("Hide pet", menu)
        hide_action.triggered.connect(self._hide_pet)
        menu.addAction(hide_action)

        menu.exec(self.mapToGlobal(point))

    def _toggle_muted(self) -> None:
        new_val = not self._settings.muted
        self._settings.muted = new_val
        self.controller.set_muted(new_val)
        self._persist_settings()

    def _rehatch(self) -> None:
        self._settings.hatched = False
        self._hatch_start_ms = self._now_ms()
        self._persist_settings()
        # Return to HATCHING visually until the timer wraps the sequence.
        self.controller._set_state(PetState.HATCHING)
        self.update()

    def _hide_pet(self) -> None:
        self._settings.visible = False
        self._persist_settings()
        self.hide()
        # Tell the dashboard it can put its status pill bar back.
        try:
            self._bus.publish("PET_VISIBILITY_CHANGED", {"visible": False})
        except Exception:
            pass

    # ── External commands ───────────────────────────────────────

    def set_style(self, name: str) -> None:
        """Switch to a different registered visual style at runtime.

        Triggered by the ``/pet style <name>`` command. Resizes the
        widget to whatever the new style declares, persists the choice,
        and immediately repaints. Unknown style names are silently
        rejected (the dashboard log will already have shown a hint).
        """
        if not name or not pet_styles.has(name):
            return
        self._style = pet_styles.get(name)
        self._settings.style = name
        self.setFixedSize(*self._style.widget_size)
        self._persist_settings()
        self.update()

    def show_pet(self) -> None:
        """Make the pet visible. Idempotent.

        Triggered when the user types "pet" in the dashboard command
        input (or programmatically). On the very first show, restarts
        the hatch animation so the user gets the egg-cracking reveal
        instead of the pet just popping in.
        """
        was_hidden = not self.isVisible()
        self._settings.visible = True

        # First-ever show → play the hatch animation.
        if not self._settings.hatched and self._hatch_start_ms is None:
            self._hatch_start_ms = self._now_ms()
            self.controller._set_state(PetState.HATCHING)

        self._persist_settings()
        self.show()
        self.raise_()
        # Tell the dashboard to hide its status pill bar — the pet
        # has taken over that role.
        if was_hidden:
            try:
                self._bus.publish("PET_VISIBILITY_CHANGED", {"visible": True})
            except Exception:
                pass

    def closeEvent(self, e) -> None:  # noqa: N802 (Qt signature)
        self._persist_settings()
        super().closeEvent(e)
