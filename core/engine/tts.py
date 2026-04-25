import pyttsx3
import threading
from core.engine.audio_state import audio_state
from core.utils.logger import logger

class TTSEngine:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 180) # ~1.2x speed
        self._stop_event = threading.Event()

    def speak(self, text):
        if not audio_state.start_speaking():
            return

        def _run():
            try:
                self._stop_event.clear()
                # pyttsx3 block-based speaking
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                logger.logger.error(f"TTS error: {e}")
            finally:
                audio_state.stop_speaking()

        threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        try:
            self.engine.stop()
            self._stop_event.set()
            audio_state.stop_speaking()
            logger.log_event("TTS_INTERRUPTED")
        except Exception as e:
            logger.logger.error(f"TTS stop error: {e}")

tts_engine = TTSEngine()
