import sys
import os
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QObject, pyqtSignal
from core.ui.theme import theme
from core.ui.models import ui_state_manager
from core.ui.components import PillStatusBar, CommandPanel, ChatBubble, HealthBar, AudioLevelBar
from core.engine.event_bus import bus
from core.config import sys_config
from core.state.manager import state_manager


class ThreadBridge(QObject):
    """Bridges background thread events to the Qt main thread via signals."""
    thinking = pyqtSignal()
    recording_start = pyqtSignal()
    recording_stop = pyqtSignal()
    error = pyqtSignal(str)
    greeting = pyqtSignal(str)
    voice_input = pyqtSignal(str)
    voice_ignored = pyqtSignal(str)
    toggle_panel = pyqtSignal()
    suggestion = pyqtSignal(dict)
    action_done = pyqtSignal(str)
    action_start = pyqtSignal(str)
    action_abort = pyqtSignal(str)
    emergency = pyqtSignal()
    idle = pyqtSignal()
    health_llm = pyqtSignal(bool)
    health_tts = pyqtSignal(bool)
    health_stt = pyqtSignal(bool)
    web_search = pyqtSignal(str)


class AyEyeDashboard:
    def __init__(self, overlay=None):
        self.overlay = overlay
        
        # Thread-safe signal bridge
        self.bridge = ThreadBridge()
        
        # 1. Persistent Status Bar
        self.status_bar = PillStatusBar()
        self.status_bar.show()
        
        # 2. Rich Command Panel
        self.command_panel = CommandPanel()
        self.command_panel.setFixedWidth(360)
        
        # 3. Health Bar
        self.health_bar = HealthBar()
        self.command_panel.layout().insertWidget(1, self.health_bar)
        
        # 4. Audio Level Bar
        self.audio_level = AudioLevelBar()
        self.audio_level.setVisible(False)
        self.command_panel.layout().insertWidget(2, self.audio_level)
        
        self.adjust_positions()
        
        # ── Connect signals to main-thread slots ──
        self.bridge.thinking.connect(self._on_thinking)
        self.bridge.recording_start.connect(self._on_recording_start)
        self.bridge.recording_stop.connect(self._on_recording_stop)
        self.bridge.error.connect(self._on_error)
        self.bridge.greeting.connect(self._on_greeting)
        self.bridge.voice_input.connect(self._on_voice_input)
        self.bridge.voice_ignored.connect(self._on_voice_ignored)
        self.bridge.toggle_panel.connect(self._on_toggle_panel)
        self.bridge.suggestion.connect(self._on_suggestion)
        self.bridge.action_start.connect(self._on_action_start)
        self.bridge.action_done.connect(self._on_action_done)
        self.bridge.action_abort.connect(self._on_action_abort)
        self.bridge.emergency.connect(self._on_emergency)
        self.bridge.idle.connect(lambda: self.update_status("idle"))
        self.bridge.health_llm.connect(lambda ok: self.health_bar.set_status("LLM", ok))
        self.bridge.health_tts.connect(lambda ok: self.health_bar.set_status("TTS", ok))
        self.bridge.health_stt.connect(lambda ok: self.health_bar.set_status("STT", ok))
        self.bridge.web_search.connect(self._on_web_search)
        
        # ── Subscribe event bus → emit signals (thread-safe) ──
        bus.subscribe("BRAIN_THINKING", lambda d: self.bridge.thinking.emit())
        bus.subscribe("VOICE_RECORDING_START", lambda d: self.bridge.recording_start.emit())
        bus.subscribe("VOICE_RECORDING_STOP", lambda d: self.bridge.recording_stop.emit())
        bus.subscribe("BRAIN_ERROR", lambda d: self.bridge.error.emit(
            d.get("reason", "Unknown") if isinstance(d, dict) else "Unknown"
        ))
        bus.subscribe("AI_GREETING", lambda d: self.bridge.greeting.emit(
            d.get("text", "") if isinstance(d, dict) else ""
        ))
        bus.subscribe("VOICE_INPUT_RECEIVED", lambda text: self.bridge.voice_input.emit(
            text if isinstance(text, str) else str(text)
        ))
        bus.subscribe("BRAIN_RESPONDED", lambda d: self.bridge.suggestion.emit(d if isinstance(d, dict) else {}))
        bus.subscribe("SAFE_NO_ACTION", lambda d: self.bridge.idle.emit())
        bus.subscribe("ACTION_STARTED", lambda d: self.bridge.action_start.emit(
            d.get("type", "action") if isinstance(d, dict) else "action"
        ))
        bus.subscribe("ACTION_COMPLETED", lambda d: self.bridge.action_done.emit(
            d.get("type", "action") if isinstance(d, dict) else "action"
        ))
        bus.subscribe("ACTION_ABORTED", lambda d: self.bridge.action_abort.emit(
            d.get("reason", "aborted") if isinstance(d, dict) else "aborted"
        ))
        bus.subscribe("EMERGENCY_STOP", lambda d: self.bridge.emergency.emit())
        bus.subscribe("STT_MODEL_LOADED", lambda d: self.bridge.health_stt.emit(True))
        bus.subscribe("WEB_SEARCH_COMPLETED", lambda d: self.bridge.web_search.emit(
            d.get("query", "search") if isinstance(d, dict) else "search"
        ))
        bus.subscribe("VOICE_IGNORED", self._on_voice_ignored_bus)
        bus.subscribe("TOGGLE_COMMAND_PANEL", lambda d=None: self.bridge.toggle_panel.emit())
        bus.subscribe("HIGHLIGHT_REQUESTED", self.on_highlight_request)
        
        # Sync timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.sync_state)
        self.update_timer.start(200)
        
        # Auto-hide timer
        self._auto_hide_timer = QTimer()
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(lambda: self.command_panel.setVisible(False))
        
        # Health check (every 30s)
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._check_health)
        self._health_timer.start(30000)
        QTimer.singleShot(5000, self._check_health)

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

    # ── Health Check (runs in background) ──
    def _check_health(self):
        def _run():
            import requests
            from dotenv import load_dotenv
            load_dotenv()
            try:
                openai_key = os.getenv("OPENAI_API_KEY")
                ollama_key = os.getenv("OLLAMA_API_KEY")
                if openai_key:
                    r = requests.get("https://api.openai.com/v1/models",
                                     headers={"Authorization": f"Bearer {openai_key}"}, timeout=5)
                    self.bridge.health_llm.emit(r.status_code == 200)
                elif ollama_key:
                    r = requests.get("https://ollama.com/api/tags",
                                     headers={"Authorization": f"Bearer {ollama_key}"}, timeout=5)
                    self.bridge.health_llm.emit(r.status_code == 200)
                else:
                    r = requests.get("http://localhost:11434/api/tags", timeout=3)
                    self.bridge.health_llm.emit(r.status_code == 200)
            except Exception:
                self.bridge.health_llm.emit(False)
            self.bridge.health_tts.emit(bool(os.getenv("OPENAI_API_KEY") or os.getenv("MURF_API_KEY")))
            self.bridge.health_stt.emit(True)
        threading.Thread(target=_run, daemon=True).start()

    # ── Main-Thread Slot Handlers ──
    
    def _on_thinking(self):
        self.update_status("thinking")
        self.command_panel.add_log("🧠", "Processing...", theme.THINKING.name())
        self.audio_level.setVisible(False)
    
    def _on_recording_start(self):
        self.update_status("recording")
        self.command_panel.add_log("🎙️", "Listening...", theme.RECORDING.name())
        self.audio_level.setVisible(True)
        self.command_panel.setVisible(True)
        self._auto_hide_timer.stop()
    
    def _on_recording_stop(self):
        self.update_status("thinking")
        self.audio_level.setVisible(False)
        # STT runs before BRAIN_THINKING — without this line the last activity stays "Listening..."
        self.command_panel.add_log("✨", "Transcribing...", theme.THINKING.name())

    def _on_voice_ignored_bus(self, data):
        reason = ""
        if isinstance(data, dict):
            reason = data.get("reason") or ""
        self.bridge.voice_ignored.emit(reason)

    def _on_voice_ignored(self, reason: str):
        self.update_status("idle")
        hints = {
            "no_audio": "No audio captured — hold Alt+Z while you speak.",
            "empty_transcript": "No speech detected — speak louder or check the mic.",
            "transcription_error": "Speech recognition failed — check logs.",
        }
        msg = hints.get(reason, "Voice input skipped.")
        self.command_panel.add_log("💬", msg, theme.WARNING.name())
    
    def _on_error(self, reason):
        self.update_status("idle")
        self.command_panel.add_log("⚠️", reason[:60], theme.ERROR.name())
    
    def _on_greeting(self, text):
        self.command_panel.add_log("👋", "System online", theme.SUCCESS.name())
        if text:
            self._add_chat_bubble(text, is_user=False)
    
    def _on_voice_input(self, text):
        self.command_panel.add_log("🗣️", f'"{text[:50]}"', theme.ACCENT_COLOR.name())
        self._add_chat_bubble(text, is_user=True)

    def _on_suggestion(self, data):
        self.update_status("idle")
        message = data.get("message", "")
        confidence = data.get("confidence", 0)
        intent = data.get("intent", "guide")
        
        self.command_panel.show_suggestion(message, confidence, intent)
        self.command_panel.add_log("💡", message[:50], theme.SUCCESS.name())
        if message:
            self._add_chat_bubble(message, is_user=False)
        
        self.anim = QPropertyAnimation(self.command_panel, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        self._auto_hide_timer.start(20000)

    def _on_action_start(self, a_type):
        self.update_status("acting")
        self.command_panel.add_log("⚡", f"Executing {a_type}...", theme.ACTING.name())

    def _on_action_done(self, a_type):
        self.update_status("idle")
        self.command_panel.add_log("✅", f"{a_type} completed", theme.SUCCESS.name())
    
    def _on_action_abort(self, reason):
        self.command_panel.add_log("🚫", reason[:40], theme.WARNING.name())
    
    def _on_emergency(self):
        self.update_status("idle")
        self.command_panel.add_log("🛑", "EMERGENCY STOP", theme.ERROR.name())

    def _on_toggle_panel(self):
        now_visible = not self.command_panel.isVisible()
        self.command_panel.setVisible(now_visible)
        if now_visible:
            self._auto_hide_timer.stop()
            self.command_panel.add_log("☰", "Panel opened", theme.ACCENT_COLOR.name())
        else:
            self.command_panel.add_log("☰", "Panel hidden", theme.TEXT_DIM.name())
    
    def _on_web_search(self, query):
        self.command_panel.add_log("🔍", f"Searching: {query[:35]}", theme.ACCENT_COLOR.name())

    def on_highlight_request(self, coords):
        if self.overlay and isinstance(coords, dict):
            x = coords.get("x", 0) - coords.get("w", 0) // 2
            y = coords.get("y", 0) - coords.get("h", 0) // 2
            self.overlay.highlight(x, y, coords.get("w", 0), coords.get("h", 0))
    
    def _add_chat_bubble(self, text, is_user=True):
        bubble = ChatBubble(text, is_user=is_user, parent=self.command_panel.log_container)
        self.command_panel.log_layout.insertWidget(
            self.command_panel.log_layout.count() - 1, bubble
        )
        self.command_panel._log_count += 1
        if self.command_panel._log_count > 30:
            item = self.command_panel.log_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                self.command_panel._log_count -= 1
        QTimer.singleShot(50, lambda: self.command_panel.log_scroll.verticalScrollBar().setValue(
            self.command_panel.log_scroll.verticalScrollBar().maximum()
        ))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AyEyeDashboard()
    sys.exit(app.exec())
