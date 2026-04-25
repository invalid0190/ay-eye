import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor, QRadialGradient
from core.ui.theme import theme
from core.engine.event_bus import bus

class VisualOverlay(QWidget):
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
        self._ring_radius = 8
        self._state = "idle"  # idle, recording, thinking, acting
        
        # Subscribe to state changes for visual feedback
        bus.subscribe("VOICE_RECORDING_START", lambda d: self._set_state("recording"))
        bus.subscribe("VOICE_RECORDING_STOP", lambda d: self._set_state("thinking"))
        bus.subscribe("BRAIN_RESPONDED", lambda d: self._set_state("idle"))
        bus.subscribe("BRAIN_ERROR", lambda d: self._set_state("idle"))
        bus.subscribe("SAFE_NO_ACTION", lambda d: self._set_state("idle"))
        
        # Cursor tracking timer (lower frequency to prevent crashes)
        self.track_timer = QTimer()
        self.track_timer.timeout.connect(self._track_mouse)
        self.track_timer.start(50)  # 20fps instead of 33fps
        
        # Pulse animation for ring
        self._pulse_phase = 0
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_timer.start(40)
        
        self.showFullScreen()
    
    def _set_state(self, state):
        self._state = state
    
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
        if self._state in ("recording", "thinking"):
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
            
        # 2. Draw AI Cursor Ring
        state_colors = {
            "idle": QColor(0, 180, 255, 60),
            "recording": QColor(255, 60, 60, 180),
            "thinking": QColor(0, 180, 255, 150),
            "acting": QColor(50, 255, 120, 180),
        }
        ring_color = state_colors.get(self._state, QColor(0, 180, 255, 60))
        
        # Pulsing radius for active states
        pulse_offset = 0
        if self._state in ("recording", "thinking"):
            import math
            pulse_offset = int(math.sin(self._pulse_phase * 0.2) * 4)
        
        radius = self._ring_radius + pulse_offset
        
        # Outer glow
        if self._state != "idle":
            gradient = QRadialGradient(self.cursor_pos.x(), self.cursor_pos.y(), radius + 10)
            gradient.setColorAt(0, QColor(ring_color.red(), ring_color.green(), ring_color.blue(), 40))
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.cursor_pos, radius + 10, radius + 10)
        
        # Ring
        pen = QPen(ring_color, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.cursor_pos, radius, radius)
        
        # Center dot
        dot_color = QColor(ring_color.red(), ring_color.green(), ring_color.blue(), 220)
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.cursor_pos, 2, 2)

    def highlight(self, x, y, w, h, duration=2000):
        self.target_rect = QRect(x, y, w, h)
        self.update()
        QTimer.singleShot(duration, self._clear)

    def _clear(self):
        self.target_rect = None
        self.update()

# Shared instance initialized by main
overlay_instance = None
