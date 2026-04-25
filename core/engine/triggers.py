import time
from core.engine.event_bus import bus
from core.utils.logger import logger

class TriggerEngine:
    def __init__(self):
        self.last_triggers = {}
        self.cooldowns = {
            "ERROR": 30.0,
            "IDLE": 60.0,
            "CONTEXT": 10.0
        }
        self.last_input_time = time.time()

    def check_error(self, text):
        error_keywords = ["traceback", "exception", "crash"]
        if any(kw in text.lower() for kw in error_keywords):
            self._emit("ERROR_TRIGGER", {"reason": "Error keyword detected"})

    def check_idle(self):
        if time.time() - self.last_input_time > 30.0:
            self._emit("IDLE_TRIGGER", {"idle_sec": time.time() - self.last_input_time})

    def _emit(self, trigger_type, data):
        last_time = self.last_triggers.get(trigger_type, 0)
        cooldown = self.cooldowns.get(trigger_type.split("_")[0], 5.0)
        
        if time.time() - last_time > cooldown:
            self.last_triggers[trigger_type] = time.time()
            bus.publish("AI_TRIGGERED", {"type": trigger_type, "data": data})
            logger.log_event("TRIGGER_ACTIVATED", {"type": trigger_type})

trigger_engine = TriggerEngine()
