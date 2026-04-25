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
        
        # File handler for analytics
        self.log_file = "ay-eye-analytics.jsonl"
        fh = logging.FileHandler(self.log_file)
        self.logger.addHandler(fh)

    def _write_json(self, entry):
        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                import numpy as np
                if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                                    np.int16, np.int32, np.int64, np.uint8,
                                    np.uint16, np.uint32, np.uint64)):
                    return int(obj)
                elif isinstance(obj, (np.float16, np.float32, np.float64)):
                    return float(obj)
                elif isinstance(obj, (np.ndarray,)):
                    return obj.tolist()
                return json.JSONEncoder.default(self, obj)
        
        self.logger.info(json.dumps(entry, cls=NumpyEncoder))

    def log_event(self, event_type, data=None):
        entry = {
            "ts": datetime.now().isoformat(),
            "type": "EVENT",
            "event": event_type,
            "data": data
        }
        self._write_json(entry)

    def log_failure(self, failure_type, details):
        entry = {
            "ts": datetime.now().isoformat(),
            "type": "FAILURE",
            "fail": failure_type,
            "details": details
        }
        self._write_json(entry)

    def log_performance(self, module, duration_ms):
        entry = {
            "ts": datetime.now().isoformat(),
            "type": "PERF",
            "module": module,
            "ms": duration_ms
        }
        self._write_json(entry)

logger = StructuredLogger()
