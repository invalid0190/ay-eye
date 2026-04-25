from faster_whisper import WhisperModel
import threading
import io
import wave
import numpy as np
from core.engine.event_bus import bus
from core.utils.logger import logger

class STTEngine:
    def __init__(self):
        # Using 'base' for speed, can be 'small' for better accuracy
        self.model = None
        self._load_lock = threading.Lock()
        bus.subscribe("AUDIO_SEGMENT_COMPLETED", self.transcribe)

    def _lazy_load(self):
        if self.model is None:
            with self._load_lock:
                if self.model is None:
                    logger.log_event("STT_MODEL_LOADING")
                    self.model = WhisperModel("base", device="cpu", compute_type="int8")
                    logger.log_event("STT_MODEL_LOADED")

    def transcribe(self, audio_data):
        self._lazy_load()
        
        def _run():
            try:
                # Convert bytes to numpy float array
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                segments, info = self.model.transcribe(audio_np, beam_size=5)
                text = " ".join([s.text for s in segments]).strip()
                
                if text:
                    bus.publish("VOICE_INPUT_RECEIVED", text)
                    logger.log_event("VOICE_TRANSCRIBED", {"text": text, "prob": info.language_probability})
                else:
                    bus.publish("VOICE_IGNORED")
            except Exception as e:
                logger.logger.error(f"Transcription error: {e}")
                bus.publish("VOICE_IGNORED")

        threading.Thread(target=_run, daemon=True).start()

stt_engine = STTEngine()
