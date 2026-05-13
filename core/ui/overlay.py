import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor, QRadialGradient, QFont, QBrush
from core.ui.theme import theme
from core.engine.event_bus import bus

class VisualOverlay(QWidget):
    """Transparent click-through overlay spanning the ENTIRE virtual desktop
    (every connected monitor). Renders:

      * A target highlight box around screen-locator hits.
      * A distinctive 'AI CURSOR' marker around the current mouse position
        whose size + colour + label change based on agent state, so the
        captured screenshot (which the LLM sees) clearly conveys where the
        agent's focus is and which monitor the cursor is on.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")
        self.target_rect = None
        self.cursor_pos = QPoint(0, 0)
        self._state = "idle"  # idle, recording, thinking, acting

        # Subscribe to state changes for visual feedback. The marker no longer
        # hides during capture because it is offset away from the actual click
        # target -- the LLM also receives the cursor position textually in the
        # vision prompt, so we don't need to embed it in the screenshot.
        bus.subscribe("VOICE_RECORDING_START", lambda d: self._set_state("recording"))
        bus.subscribe("VOICE_RECORDING_STOP", lambda d: self._set_state("thinking"))
        bus.subscribe("BRAIN_RESPONDED", lambda d: self._set_state("idle"))
        bus.subscribe("BRAIN_ERROR", lambda d: self._set_state("idle"))
        bus.subscribe("SAFE_NO_ACTION", lambda d: self._set_state("idle"))
        bus.subscribe("UI_ACTION_PREPARE", lambda d=None: self._set_state("acting"))

        # Cursor tracking timer (lower frequency to prevent crashes)
        self.track_timer = QTimer()
        self.track_timer.timeout.connect(self._track_mouse)
        self.track_timer.start(50)  # 20fps instead of 33fps

        # Pulse animation for ring
        self._pulse_phase = 0
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_timer.start(40)

        self._span_virtual_desktop()

    def _span_virtual_desktop(self):
        """Resize the overlay so it covers EVERY connected monitor.

        ``showFullScreen()`` only fullscreens the current display, which is
        why the cursor ring used to disappear on secondary monitors. We union
        every screen's geometry and call ``setGeometry`` directly so the
        widget physically spans the whole virtual desktop.
        """
        app = QApplication.instance()
        if app is None:
            self.showFullScreen()
            return
        screens = app.screens()
        if not screens:
            self.showFullScreen()
            return
        union = screens[0].geometry()
        for s in screens[1:]:
            union = union.united(s.geometry())
        self.setGeometry(union)
        self.show()

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.update()

    def _track_mouse(self):
        try:
            new_pos = self.mapFromGlobal(QCursor.pos())
            if new_pos != self.cursor_pos:
                self.cursor_pos = new_pos
                self.update()
        except Exception:
            pass  # Prevent crashes on minimize/Task View

    def _pulse_tick(self):
        self._pulse_phase = (self._pulse_phase + 1) % 60
        if self._state in ("recording", "thinking", "acting"):
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Draw Target Highlight
        if self.target_rect:
            # Glowing border
            pen = QPen(theme.ACCENT_COLOR, 2)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 180, 255, 15))
            painter.drawRoundedRect(self.target_rect, 4, 4)
            
            # Corner brackets
            r = self.target_rect
            bracket_len = min(12, r.width() // 4, r.height() // 4)
            pen = QPen(theme.ACCENT_COLOR, 3)
            painter.setPen(pen)
            
            # Top-left
            painter.drawLine(r.left(), r.top(), r.left() + bracket_len, r.top())
            painter.drawLine(r.left(), r.top(), r.left(), r.top() + bracket_len)
            # Top-right
            painter.drawLine(r.right(), r.top(), r.right() - bracket_len, r.top())
            painter.drawLine(r.right(), r.top(), r.right(), r.top() + bracket_len)
            # Bottom-left
            painter.drawLine(r.left(), r.bottom(), r.left() + bracket_len, r.bottom())
            painter.drawLine(r.left(), r.bottom(), r.left(), r.bottom() - bracket_len)
            # Bottom-right
            painter.drawLine(r.right(), r.bottom(), r.right() - bracket_len, r.bottom())
            painter.drawLine(r.right(), r.bottom(), r.right(), r.bottom() - bracket_len)
            
        # 2. Floating status pill above the cursor.
        # The pill sits ~26 px above the cursor with a leader line pointing
        # at it. This way the marker never covers the click target, so we
        # don't need to hide anything during capture or actions.
        import math

        state_styles = {
            "idle":      (QColor(0, 180, 255),  None),       # No pill when idle
            "recording": (QColor(255, 70, 70),  "REC"),
            "thinking":  (QColor(0, 200, 255),  "THINKING"),
            "acting":    (QColor(50, 220, 120), "ACTING"),
        }
        color, label_text = state_styles.get(self._state, (QColor(0, 180, 255), None))

        cx, cy = self.cursor_pos.x(), self.cursor_pos.y()

        # 2a. Always-on small status dot offset diagonally up-right of cursor.
        # Sized so the OS pointer itself remains the dominant visual.
        dot_offset_x, dot_offset_y = 14, -14
        dot_x = cx + dot_offset_x
        dot_y = cy + dot_offset_y

        # Soft glow under the dot (subtle when idle, brighter when active).
        glow_alpha = 70 if self._state == "idle" else 150
        gradient = QRadialGradient(dot_x, dot_y, 18)
        gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), glow_alpha))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(dot_x, dot_y), 18, 18)

        # Dot itself: 5 px coloured circle with white outline for contrast on
        # both light and dark backgrounds.
        pulse = 0
        if self._state in ("recording", "thinking", "acting"):
            pulse = int(math.sin(self._pulse_phase * 0.2) * 2)
        dot_r = 5 + pulse
        painter.setBrush(color)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        painter.drawEllipse(QPoint(dot_x, dot_y), dot_r, dot_r)

        # 2b. Active-state pill anchored above the dot (never on the cursor).
        if label_text is None:
            return

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(label_text)
        text_h = metrics.height()
        pad_x, pad_y = 7, 2
        pill_w = text_w + pad_x * 2
        pill_h = text_h + pad_y * 2

        pill_x = dot_x + 10
        pill_y = dot_y - pill_h - 6

        # Keep the pill inside the overlay bounds.
        if pill_x + pill_w > self.width():
            pill_x = dot_x - pill_w - 10
        if pill_y < 0:
            pill_y = dot_y + 10

        # Leader line from dot to pill edge.
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 180), 1.5))
        painter.drawLine(
            dot_x, dot_y,
            pill_x + (pill_w // 2 if pill_x > dot_x else pill_w // 2),
            pill_y + pill_h // 2,
        )

        # Pill background + outline.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 15, 20, 220))
        painter.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, pill_h // 2, pill_h // 2)
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, pill_h // 2, pill_h // 2)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            pill_x + pad_x,
            pill_y + pad_y + metrics.ascent(),
            label_text,
        )

    def highlight(self, x, y, w, h, duration=2000):
        self.target_rect = QRect(x, y, w, h)
        self.update()
        QTimer.singleShot(duration, self._clear)

    def _clear(self):
        self.target_rect = None
        self.update()

# Shared instance initialized by main
overlay_instance = None
