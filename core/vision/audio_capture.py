import pyaudio
import threading
import time
from core.engine.event_bus import bus
from core.vision.audio_processor import audio_processor
from core.utils.logger import logger

class AudioCapture:
    def __init__(self):
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.recording = False
        self.buffer = []
        self.max_recording_time = 10.0
        
        bus.subscribe("HOTKEY_PRESSED", self.start_recording)
        bus.subscribe("HOTKEY_RELEASED", self.stop_recording)

    def start_recording(self, data=None):
        self.recording = True
        self.buffer = []
        threading.Thread(target=self._record_loop, daemon=True).start()

    def stop_recording(self, data=None):
        self.recording = False

    def _record_loop(self):
        try:
            self.stream = self.p.open(format=self.format, channels=self.channels,
                                    rate=self.rate, input=True,
                                    frames_per_buffer=self.chunk)
            
            start_time = time.time()
            silence_start = None
            
            while self.recording and (time.time() - start_time < self.max_recording_time):
                data = self.stream.read(self.chunk)
                self.buffer.append(data)
                
                # Silence detection (0.6s)
                if audio_processor.is_silent(data):
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > 1.5:
                        break
                else:
                    silence_start = None
            
            if self.buffer:
                full_audio = b"".join(self.buffer)
                normalized = audio_processor.normalize(full_audio)
                bus.publish("AUDIO_SEGMENT_COMPLETED", normalized)
                logger.log_event("AUDIO_CAPTURED", {"duration_sec": time.time() - start_time})
                
        except Exception as e:
            logger.logger.error(f"Audio capture error: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            self.recording = False

audio_capture = AudioCapture()
