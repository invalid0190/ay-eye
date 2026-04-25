import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from core.ui.theme import theme
from core.ui.models import ui_state_manager
from core.ui.components import StatusBar, ActionPanel
from core.engine.event_bus import bus
from core.utils.health import health_checker

class AyEyeDashboard(QWidget):
    def __init__(self, overlay=None):
        super().__init__()
        self.overlay = overlay
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        self.status_bar = StatusBar()
        self.action_panel = ActionPanel()
        
        self.layout.addWidget(self.status_bar)
        self.layout.addWidget(self.action_panel)
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.BG_COLOR.name()}; 
                border: 1px solid {theme.GRAY_COLOR.name()}; 
                border-radius: 8px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        
        self.setFixedWidth(250)
        self.adjust_position()
        self.show()
        
        # Subscribe to events for UI updates
        bus.subscribe("BRAIN_RESPONDED", self.on_suggestion)
        bus.subscribe("ACTION_COMPLETED", self.on_action_end)
        bus.subscribe("ACTION_ABORTED", self.on_action_end)
        bus.subscribe("HIGHLIGHT_REQUESTED", self.on_highlight_request)
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.sync_state)
        self.update_timer.start(100)

    def adjust_position(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, 40)

    def sync_state(self):
        state = ui_state_manager.state
        health = health_checker.run_all()
        health_status = "✓" if health["ok"] else "⚠"
        
        self.status_bar.label.setText(f"ay-eye: {state.status} [{health_status}]")
        self.status_bar.label.setToolTip(health["details"])
        
        color = theme.ACCENT_COLOR if state.status != "idle" else theme.GRAY_COLOR
        self.status_bar.icon.setStyleSheet(f"color: {color.name()};")

    def on_suggestion(self, data):
        ui_state_manager.update(status="thinking", confidence=data.get("confidence", 0))
        self.action_panel.show_suggestion(data.get("message", ""), data.get("confidence", 0))
        self.animate_expand()

    def on_action_end(self, data=None):
        ui_state_manager.update(status="idle")
        QTimer.singleShot(3000, lambda: self.action_panel.setVisible(False))

    def on_highlight_request(self, coords):
        if self.overlay:
            # coords are {x, y, w, h} - resolver returns center for x,y
            # overlay.highlight expects top-left for rect
            x = coords["x"] - coords["w"] // 2
            y = coords["y"] - coords["h"] // 2
            self.overlay.highlight(x, y, coords["w"], coords["h"])

    def animate_expand(self):
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(200)
        self.anim.setStartValue(self.geometry())
        new_height = 150 # Estimated expanded height
        self.anim.setEndValue(QRect(self.x(), self.y(), self.width(), new_height))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
