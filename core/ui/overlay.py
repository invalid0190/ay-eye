import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPen
import threading

class VisualOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")
        self.target_rect = None
        self.showFullScreen()

    def paintEvent(self, event):
        if self.target_rect:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(255, 0, 0, 200), 3) # Semi-transparent red
            painter.setPen(pen)
            painter.drawRect(self.target_rect)

    def highlight(self, x, y, w, h, duration=200):
        self.target_rect = QRect(x, y, w, h)
        self.update()
        QTimer.singleShot(duration, self._clear)

    def _clear(self):
        self.target_rect = None
        self.update()

overlay_app = None
overlay_window = None

def start_overlay():
    global overlay_app, overlay_window
    overlay_app = QApplication.instance() or QApplication(sys.argv)
    overlay_window = VisualOverlay()
    overlay_app.exec()

# Start in a separate thread
threading.Thread(target=start_overlay, daemon=True).start()
