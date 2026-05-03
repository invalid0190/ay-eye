import keyboard
import time
import threading
from core.engine.event_bus import bus
from core.engine.audio_state import audio_state
from core.utils.logger import logger

class HotkeyManager:
    def __init__(self):
        self.hotkey = "alt+z"
        self.is_pressed = False
        self._lock = threading.Lock()
        self._watchdog_running = False
        self._pressed_at = 0.0
        self._max_hold_seconds = 12.0
        
    def start(self):
        keyboard.hook(self._on_event)
        self._watchdog_running = True
        threading.Thread(target=self._watchdog_loop, daemon=True).start()
        logger.log_event("HOTKEY_MANAGER_STARTED")

    def _on_event(self, e):
        if e.name == "z" and e.event_type == "down" and keyboard.is_pressed("alt"):
            self._start_listening(e.name)
        elif e.name == 'x' and keyboard.is_pressed('ctrl') and keyboard.is_pressed('shift'):
            bus.publish('EMERGENCY_STOP')
            logger.log_event('EMERGENCY_STOP_TRIGGERED')
        elif e.name == 'enter' and keyboard.is_pressed('alt'):
            bus.publish('CONFIRM_HOTKEY')
        elif self.is_pressed and e.event_type == "up":
            # Stop as soon as either key in Alt+Z is released.
            if e.name in ("z", "alt", "left alt", "right alt") or not self._is_hotkey_down():
                self._stop_listening(e.name)

    def _is_hotkey_down(self):
        try:
            return keyboard.is_pressed("z") and (
                keyboard.is_pressed("alt")
                or keyboard.is_pressed("left alt")
                or keyboard.is_pressed("right alt")
            )
        except Exception:
            return False

    def _start_listening(self, key_name="z"):
        with self._lock:
            if self.is_pressed:
                return
            self.is_pressed = True
            self._pressed_at = time.time()

        logger.log_event("DEBUG_HOTKEY_DOWN", {"key": key_name})
        if audio_state.start_listening():
            bus.publish("HOTKEY_PRESSED")
            bus.publish("VOICE_RECORDING_START", {})
            logger.log_event("VOICE_RECORDING_START")
        else:
            logger.logger.warning("Could not start listening (busy?)")
            self._stop_listening("start_failed")

    def _stop_listening(self, key_name="release"):
        with self._lock:
            if not self.is_pressed:
                return
            self.is_pressed = False
            self._pressed_at = 0.0

        logger.log_event("DEBUG_HOTKEY_UP", {"key": key_name})
        audio_state.stop_listening()
        bus.publish("HOTKEY_RELEASED")
        bus.publish("VOICE_RECORDING_STOP", {})
        logger.log_event("VOICE_RECORDING_STOP")

    def _watchdog_loop(self):
        while self._watchdog_running:
            time.sleep(0.15)
            if not self.is_pressed:
                continue

            held_too_long = self._pressed_at and (time.time() - self._pressed_at > self._max_hold_seconds)
            if held_too_long or not self._is_hotkey_down():
                reason = "watchdog_timeout" if held_too_long else "watchdog_release"
                logger.logger.warning(f"HotkeyManager: forcing listen stop ({reason})")
                self._stop_listening(reason)

hotkey_manager = HotkeyManager()
