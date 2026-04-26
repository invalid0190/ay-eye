import time
import threading

class AudioState:
    def __init__(self):
        self.is_listening = False
        self.is_speaking = False
        self.last_interaction_time = time.time()
        self._lock = threading.Lock()

    def start_listening(self):
        with self._lock:
            # Always allow listening — if speaking, the user is interrupting
            if self.is_speaking:
                self.is_speaking = False  # Force stop speaking state
            self.is_listening = True
            return True

    def stop_listening(self):
        with self._lock:
            self.is_listening = False

    def start_speaking(self):
        with self._lock:
            if not self.is_listening:
                self.is_speaking = True
                return True
            return False

    def stop_speaking(self):
        with self._lock:
            self.is_speaking = False

audio_state = AudioState()
