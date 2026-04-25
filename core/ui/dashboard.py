import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from core.ui.theme import theme
from core.ui.models import ui_state_manager
from core.ui.components import StatusBar, ActionPanel
from core.engine.event_bus import bus
from core.utils.health import health_checker
from core.config import sys_config

class AyEyeDashboard(QWidget):
    def __init__(self, overlay=None):
        super().__init__()
        self.overlay = overlay
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Status Area
        self.status_bar = StatusBar()
        self.layout.addWidget(self.status_bar)
        
        # 2. Action Area (Suggestions)
        self.action_panel = ActionPanel()
        self.layout.addWidget(self.action_panel)
        
        # 3. Dev Area (Debug Console)
        self.dev_panel = QWidget()
        self.dev_layout = QVBoxLayout(self.dev_panel)
        self.dev_text = QTextEdit()
        self.dev_text.setReadOnly(True)
        self.dev_text.setFixedHeight(120)
        self.dev_text.setStyleSheet(f"background: black; color: {theme.ACCENT_COLOR.name()}; font-family: Consolas; font-size: 8pt; border: none;")
        self.dev_layout.addWidget(QLabel("DEBUG CONSOLE"))
        self.dev_layout.addWidget(self.dev_text)
        self.dev_panel.setVisible(False)
        self.layout.addWidget(self.dev_panel)
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.BG_COLOR.name()}; 
                border: 1px solid {theme.GRAY_COLOR.name()}; 
                border-radius: 8px;
            }}
            QLabel {{ border: none; background: transparent; color: {theme.TEXT_COLOR.name()}; font-size: 8pt; }}
        """)
        
        self.setFixedWidth(280)
        self.adjust_position()
        self.show()
        
        # Subscribers
        bus.subscribe("BRAIN_RESPONDED", self.on_suggestion)
        bus.subscribe("BRAIN_THINKING", lambda d: self.log_debug("BRAIN: Thinking..."))
        bus.subscribe("BRAIN_THINKING", lambda d: ui_state_manager.update(status="thinking"))
        bus.subscribe("HIGHLIGHT_REQUESTED", self.on_highlight_request)
        bus.subscribe("HEARTBEAT", self.log_debug)
        bus.subscribe("VOICE_TRANSCRIBED", lambda d: self.log_debug(f"VOICE: {d.get('text')}"))
        bus.subscribe("VOICE_RECORDING_START", lambda d: self.log_debug("VOICE: Recording..."))
        
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
        mode_label = "OBS" if sys_config.is_observation_only else "ACT"
        
        self.status_bar.label.setText(f"ay-eye: {state.status} [{health_status}] | {mode_label}")
        self.status_bar.label.setToolTip(health["details"])
        
        color = theme.ACCENT_COLOR if state.status != "idle" else theme.GRAY_COLOR
        self.status_bar.icon.setStyleSheet(f"color: {color.name()};")
        
        # Auto-show dev panel in debug mode
        if sys_config.get("debug_mode") and not self.dev_panel.isVisible():
            self.dev_panel.setVisible(True)
            self.adjust_height()

    def log_debug(self, data):
        msg = f"> {data}\n"
        self.dev_text.append(msg)
        self.dev_text.verticalScrollBar().setValue(self.dev_text.verticalScrollBar().maximum())

    def on_suggestion(self, data):
        ui_state_manager.update(status="thinking", confidence=data.get("confidence", 0))
        self.action_panel.show_suggestion(data.get("message", ""), data.get("confidence", 0))
        self.log_debug(f"BRAIN: {data.get('intent')} | Conf: {data.get('confidence')}")
        self.adjust_height()

    def on_highlight_request(self, coords):
        if self.overlay:
            x = coords["x"] - coords["w"] // 2
            y = coords["y"] - coords["h"] // 2
            self.overlay.highlight(x, y, coords["w"], coords["h"])

    def adjust_height(self):
        h = 100
        if self.action_panel.isVisible(): h += 80
        if self.dev_panel.isVisible(): h += 150
        self.setFixedHeight(h)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
