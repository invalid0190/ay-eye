import keyboard
import time
from core.engine.event_bus import bus
from core.engine.audio_state import audio_state
from core.utils.logger import logger

class HotkeyManager:
    def __init__(self):
        self.hotkey = "alt+z"
        self.is_pressed = False
        
    def start(self):
        keyboard.hook(self._on_event)
        logger.log_event("HOTKEY_MANAGER_STARTED")

    def _on_event(self, e):
        if e.name == "z" and keyboard.is_pressed("alt"):
            if not self.is_pressed:
                self.is_pressed = True
                if audio_state.start_listening():
                    bus.publish("HOTKEY_PRESSED")
                    logger.log_event("VOICE_RECORDING_START")
        elif self.is_pressed:
            if not (keyboard.is_pressed("z") and keyboard.is_pressed("alt")):
                self.is_pressed = False
                audio_state.stop_listening()
                bus.publish("HOTKEY_RELEASED")
                logger.log_event("VOICE_RECORDING_STOP")

hotkey_manager = HotkeyManager()
