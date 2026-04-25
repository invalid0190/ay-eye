import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor

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
        
        # Cursor tracking timer
        self.track_timer = QTimer()
        self.track_timer.timeout.connect(self._track_mouse)
        self.track_timer.start(30) # 33fps
        
        self.showFullScreen()

    def _track_mouse(self):
        new_pos = self.mapFromGlobal(QCursor.pos())
        if new_pos != self.cursor_pos:
            self.cursor_pos = new_pos
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Draw Target Highlight
        if self.target_rect:
            pen = QPen(QColor(0, 180, 255, 200), 3) # ay-eye cyan
            painter.setPen(pen)
            painter.drawRect(self.target_rect)
            
        # 2. Draw AI Cursor (Subtle Ring)
        pen = QPen(QColor(0, 180, 255, 100), 1)
        painter.setPen(pen)
        painter.drawEllipse(self.cursor_pos, 8, 8)
        
        # Small dot in center
        painter.setBrush(QColor(0, 180, 255, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.cursor_pos, 2, 2)

    def highlight(self, x, y, w, h, duration=200):
        self.target_rect = QRect(x, y, w, h)
        self.update()
        QTimer.singleShot(duration, self._clear)

    def _clear(self):
        self.target_rect = None
        self.update()

# Shared instance initialized by main
overlay_instance = None

