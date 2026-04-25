from core.engine.event_bus import bus
from core.engine.tts import tts_engine
from core.utils.logger import logger
import hashlib

class VoiceController:
    def __init__(self):
        self.last_message_hash = ""
        self.cooldown = 2.0
        self.last_speech_time = 0
        
        bus.subscribe("BRAIN_RESPONDED", self.handle_response)
        bus.subscribe("AI_GREETING", lambda d: tts_engine.speak(d.get("text")))
        bus.subscribe("KEY_PRESSED", self.interrupt)
        bus.subscribe("MOUSE_CLICKED", self.interrupt)

    def handle_response(self, data):
        message = data.get("message", "")
        confidence = data.get("confidence", 0)
        mode = data.get("mode", "IGNORE")

        if not message or confidence < 0.3:
            return

        # Prevent repetition
        m_hash = hashlib.md5(message.encode()).hexdigest()
        if m_hash == self.last_message_hash:
            return
            
        self.last_message_hash = m_hash
        tts_engine.speak(message)
        logger.log_event("VOICE_CONTROLLER_SPEAKING", {"message": message})

    def interrupt(self, data=None):
        tts_engine.stop()

voice_controller = VoiceController()

