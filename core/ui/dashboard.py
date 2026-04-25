import sys
import os
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from core.ui.theme import theme
from core.ui.models import ui_state_manager
from core.ui.components import PillStatusBar, CommandPanel, ChatBubble, HealthBar, AudioLevelBar
from core.engine.event_bus import bus
from core.config import sys_config
from core.state.manager import state_manager

class AyEyeDashboard:
    def __init__(self, overlay=None):
        self.overlay = overlay
        
        # 1. Persistent Status Bar
        self.status_bar = PillStatusBar()
        self.status_bar.show()
        
        # 2. Rich Command Panel
        self.command_panel = CommandPanel()
        self.command_panel.setFixedWidth(360)
        
        # 3. Add Health Bar to command panel
        self.health_bar = HealthBar()
        self.command_panel.layout().insertWidget(1, self.health_bar)
        
        # 4. Add Audio Level Bar (visible during recording)
        self.audio_level = AudioLevelBar()
        self.audio_level.setVisible(False)
        self.command_panel.layout().insertWidget(2, self.audio_level)
        
        self.adjust_positions()
        
        # ── Conversation State ──
        self._chat_history = []
        
        # ── Event Subscribers ──
        bus.subscribe("BRAIN_RESPONDED", self.on_suggestion)
        bus.subscribe("BRAIN_THINKING", self._on_thinking)
        bus.subscribe("VOICE_RECORDING_START", self._on_recording_start)
        bus.subscribe("VOICE_RECORDING_STOP", self._on_recording_stop)
        bus.subscribe("BRAIN_ERROR", self._on_error)
        bus.subscribe("HIGHLIGHT_REQUESTED", self.on_highlight_request)
        bus.subscribe("STATE_UPDATED", self.on_state_update)
        bus.subscribe("AI_GREETING", self._on_greeting)
        bus.subscribe("VOICE_INPUT_RECEIVED", self._on_voice_input)
        bus.subscribe("SAFE_NO_ACTION", lambda d: self.update_status("idle"))
        bus.subscribe("ACTION_COMPLETED", self._on_action_completed)
        bus.subscribe("ACTION_ABORTED", self._on_action_aborted)
        bus.subscribe("EMERGENCY_STOP", self._on_emergency_stop)
        bus.subscribe("STT_MODEL_LOADED", lambda d: self.health_bar.set_status("STT", True))
        bus.subscribe("LLM_RESPONSE", lambda d: self.health_bar.set_status("LLM", True))
        
        # Sync timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.sync_state)
        self.update_timer.start(200)
        
        # Auto-hide timer for the command panel
        self._auto_hide_timer = QTimer()
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(lambda: self.command_panel.setVisible(False))
        
        # Health check timer (every 30s)
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._check_health)
        self._health_timer.start(30000)
        QTimer.singleShot(5000, self._check_health)  # Initial check after 5s

    def adjust_positions(self):
        screen = QApplication.primaryScreen().geometry()
        self.status_bar.move(screen.width() - self.status_bar.width() - 20, 20)
        self.command_panel.move(screen.width() - self.command_panel.width() - 20, 65)

    def sync_state(self):
        state = ui_state_manager.state
        sys_state = state_manager.get_state()
        self.status_bar.update_status(state.status, sys_state.window)

    def update_status(self, status):
        ui_state_manager.update(status=status)

    # ── Health Check ──
    
    def _check_health(self):
        """Check service connectivity in background."""
        def _run():
            import requests
            from dotenv import load_dotenv
            load_dotenv()
            
            # LLM Check
            try:
                api_key = os.getenv("OLLAMA_API_KEY")
                if api_key:
                    r = requests.get("https://ollama.com/api/tags", 
                                     headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
                    self.health_bar.set_status("LLM", r.status_code == 200)
                else:
                    r = requests.get("http://localhost:11434/api/tags", timeout=3)
                    self.health_bar.set_status("LLM", r.status_code == 200)
            except Exception:
                self.health_bar.set_status("LLM", False)
            
            # TTS Check
            murf_key = os.getenv("MURF_API_KEY")
            self.health_bar.set_status("TTS", bool(murf_key))
            
            # STT is always local
            self.health_bar.set_status("STT", True)
        
        threading.Thread(target=_run, daemon=True).start()

    # ── Event Handlers ──
    
    def _on_thinking(self, data):
        self.update_status("thinking")
        self.command_panel.add_log("🧠", "Processing...", theme.THINKING.name())
        self.audio_level.setVisible(False)
    
    def _on_recording_start(self, data):
        self.update_status("recording")
        self.command_panel.add_log("🎙️", "Listening...", theme.RECORDING.name())
        self.audio_level.setVisible(True)
        self.command_panel.setVisible(True)
        self._auto_hide_timer.stop()
    
    def _on_recording_stop(self, data):
        self.update_status("thinking")
        self.audio_level.setVisible(False)
    
    def _on_error(self, data):
        self.update_status("idle")
        reason = data.get("reason", "Unknown error") if data else "Unknown error"
        self.command_panel.add_log("⚠️", reason[:60], theme.ERROR.name())
    
    def _on_greeting(self, data):
        text = data.get("text", "") if data else ""
        self.command_panel.add_log("👋", "System online", theme.SUCCESS.name())
        self._add_chat_bubble(text, is_user=False)
    
    def _on_voice_input(self, text):
        display = text if isinstance(text, str) else str(text)
        self.command_panel.add_log("🗣️", f'"{display[:50]}"', theme.ACCENT_COLOR.name())
        self._add_chat_bubble(display, is_user=True)

    def _on_action_completed(self, data):
        a_type = data.get("type", "action") if data else "action"
        self.command_panel.add_log("✅", f"{a_type} completed", theme.SUCCESS.name())
    
    def _on_action_aborted(self, data):
        reason = data.get("reason", "aborted") if data else "aborted"
        self.command_panel.add_log("🚫", reason[:40], theme.WARNING.name())
    
    def _on_emergency_stop(self, data=None):
        self.update_status("idle")
        self.command_panel.add_log("🛑", "EMERGENCY STOP", theme.ERROR.name())

    def on_state_update(self, state):
        pass

    def on_suggestion(self, data):
        self.update_status("idle")
        
        message = data.get("message", "")
        confidence = data.get("confidence", 0)
        intent = data.get("intent", "guide")
        
        self.command_panel.show_suggestion(message, confidence, intent)
        self.command_panel.add_log("💡", message[:50], theme.SUCCESS.name())
        self._add_chat_bubble(message, is_user=False)
        
        # Fade-in animation
        self.anim = QPropertyAnimation(self.command_panel, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        
        # Auto-hide after 20 seconds
        self._auto_hide_timer.start(20000)

    def on_highlight_request(self, coords):
        if self.overlay:
            x = coords["x"] - coords["w"] // 2
            y = coords["y"] - coords["h"] // 2
            self.overlay.highlight(x, y, coords["w"], coords["h"])
    
    # ── Chat Bubbles ──
    
    def _add_chat_bubble(self, text, is_user=True):
        """Add a conversation bubble to the activity log area."""
        bubble = ChatBubble(text, is_user=is_user, parent=self.command_panel.log_container)
        self.command_panel.log_layout.insertWidget(
            self.command_panel.log_layout.count() - 1, bubble
        )
        self.command_panel._log_count += 1
        
        # Keep max 30 items
        if self.command_panel._log_count > 30:
            item = self.command_panel.log_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                self.command_panel._log_count -= 1
        
        # Auto-scroll
        QTimer.singleShot(50, lambda: self.command_panel.log_scroll.verticalScrollBar().setValue(
            self.command_panel.log_scroll.verticalScrollBar().maximum()
        ))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
