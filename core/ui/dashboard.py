import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from core.ui.theme import theme
from core.ui.models import ui_state_manager

class AyEyeDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Status Bar (Minimal)
        self.status_bar = QWidget()
        self.status_layout = QHBoxLayout(self.status_bar)
        self.status_icon = QLabel("●") # Activity indicator
        self.status_label = QLabel("ay-eye: idle")
        self.status_label.setStyleSheet(f"color: {theme.TEXT_COLOR.name()}; font-family: {theme.FONT_FAMILY}; font-size: {theme.FONT_SIZE_SMALL}pt;")
        
        self.status_layout.addWidget(self.status_icon)
        self.status_layout.addWidget(self.status_label)
        self.layout.addWidget(self.status_bar)
        
        self.setStyleSheet(f"background-color: {theme.BG_COLOR.name()}; border: 1px solid {theme.GRAY_COLOR.name()}; border-radius: 5px;")
        
        self.adjust_position()
        self.show()

    def adjust_position(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, 40) # Top right corner

    def update_ui(self):
        state = ui_state_manager.state
        self.status_label.setText(f"ay-eye: {state.status} | {state.active_app}")
        # Pulse/Glow logic
        color = theme.ACCENT_COLOR if state.status != "idle" else theme.GRAY_COLOR
        self.status_icon.setStyleSheet(f"color: {color.name()};")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
