import requests
import json
import time
import threading
from queue import Queue
from typing import Optional, Dict, Any
from core.utils.logger import logger
from core.utils.json_parser import json_parser

class LLMBridge:
    def __init__(self, model="llama3", url="http://localhost:11434/api/generate"):
        self.model = model
        self.url = url
        self.timeout = 5.0
        self.queue = Queue(maxsize=1) # Prevent concurrent calls
        self._lock = threading.Lock()

    def generate(self, prompt: str, retry=True) -> Optional[Dict[str, Any]]:
        # Handle queueing
        if self.queue.full():
            logger.logger.warning("LLM Bridge busy, dropping request")
            return None
        
        self.queue.put(True)
        try:
            start_time = time.time()
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False, # Setting False for simpler MVP, can switch to stream later
                "format": "json"
            }
            
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            raw_text = response.json().get("response", "")
            data = json_parser.extract_and_heal(raw_text)
            
            if not data and retry:
                logger.logger.warning("JSON failed, retrying with stricter prompt...")
                return self.generate(prompt + "\n\nIMPORTANT: Return ONLY valid JSON.", retry=False)
            
            duration = int((time.time() - start_time) * 1000)
            logger.log_performance("LLM_GENERATE", duration)
            logger.log_event("LLM_RESPONSE", data)
            
            return data
        except Exception as e:
            logger.logger.error(f"LLM Bridge error: {e}")
            return None
        finally:
            self.queue.get()

llm_bridge = LLMBridge()
