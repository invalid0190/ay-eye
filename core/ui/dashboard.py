import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint
from core.ui.theme import theme
from core.ui.models import ui_state_manager
from core.ui.components import PillStatusBar, ActionPanel
from core.engine.event_bus import bus
from core.utils.health import health_checker
from core.config import sys_config
from core.state.manager import state_manager

class AyEyeDashboard:
    def __init__(self, overlay=None):
        self.overlay = overlay
        
        # 1. Persistent Status Bar
        self.status_bar = PillStatusBar()
        self.status_bar.show()
        
        # 2. Expandable Suggestion Panel
        self.action_panel = ActionPanel()
        self.action_panel.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.action_panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.action_panel.setFixedWidth(300)
        
        self.adjust_positions()
        
        # Subscribers
        bus.subscribe("BRAIN_RESPONDED", self.on_suggestion)
        bus.subscribe("BRAIN_THINKING", lambda d: self.update_status("thinking"))
        bus.subscribe("VOICE_RECORDING_START", lambda d: self.update_status("recording"))
        bus.subscribe("VOICE_RECORDING_STOP", lambda d: self.update_status("thinking"))
        bus.subscribe("BRAIN_ERROR", lambda d: self.update_status("idle"))
        bus.subscribe("HIGHLIGHT_REQUESTED", self.on_highlight_request)
        bus.subscribe("STATE_UPDATED", self.on_state_update)
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.sync_state)
        self.update_timer.start(100)

    def adjust_positions(self):
        screen = QApplication.primaryScreen().geometry()
        # Status bar at top right
        self.status_bar.move(screen.width() - self.status_bar.width() - 20, 20)
        
        # Action panel below status bar
        self.action_panel.move(screen.width() - self.action_panel.width() - 20, 60)

    def sync_state(self):
        state = ui_state_manager.state
        sys_state = state_manager.get_state()
        self.status_bar.update_status(state.status, sys_state.window)
        
        # If no suggestion for a while, hide action panel
        # (Implementation of auto-hide could go here)

    def update_status(self, status):
        ui_state_manager.update(status=status)

    def on_state_update(self, state):
        # Triggered when system state changes (active app, etc)
        pass

    def on_suggestion(self, data):
        self.update_status("idle")
        self.action_panel.show_suggestion(data.get("message", ""), data.get("confidence", 0))
        
        # Animation
        self.anim = QPropertyAnimation(self.action_panel, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def on_highlight_request(self, coords):
        if self.overlay:
            x = coords["x"] - coords["w"] // 2
            y = coords["y"] - coords["h"] // 2
            self.overlay.highlight(x, y, coords["w"], coords["h"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
