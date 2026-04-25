import logging
import json
import time
from datetime import datetime

class StructuredLogger:
    def __init__(self, name="ay-eye"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

    def log_event(self, event_type, data=None):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "EVENT",
            "event": event_type,
            "data": data
        }
        self.logger.info(json.dumps(log_entry))

    def log_performance(self, module, duration_ms):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "PERF",
            "module": module,
            "duration_ms": duration_ms
        }
        self.logger.info(json.dumps(log_entry))

logger = StructuredLogger()
