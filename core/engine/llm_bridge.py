import requests
import json
import time
import os
import threading
from queue import Queue
from typing import Optional, Dict, Any
from core.utils.logger import logger
from core.utils.json_parser import json_parser
from dotenv import load_dotenv

load_dotenv()

class LLMBridge:
    def __init__(self, model="gemma3:4b"):
        self.model = model
        self.api_key = os.getenv("OLLAMA_API_KEY")
        
        # Use cloud API if key exists, else fallback to local
        if self.api_key:
            self.url = "https://ollama.com/api/generate"
            logger.logger.info("LLM Bridge: Using Ollama Cloud API")
        else:
            self.url = "http://localhost:11434/api/generate"
            logger.logger.info("LLM Bridge: Using local Ollama")
        
        self.timeout = 120.0
        self.queue = Queue(maxsize=1)
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
                "stream": False,
                "format": "json"
            }
            
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            raw_text = response.json().get("response", "")
            data = json_parser.extract_and_heal(raw_text)
            
            if not data and retry:
                logger.logger.warning("JSON parse failed, retrying...")
                payload["prompt"] = prompt + "\n\nIMPORTANT: Return ONLY valid JSON, no markdown."
                response2 = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response2.raise_for_status()
                raw_text2 = response2.json().get("response", "")
                data = json_parser.extract_and_heal(raw_text2)
            
            duration = int((time.time() - start_time) * 1000)
            logger.log_performance("LLM_GENERATE", duration)
            logger.log_event("LLM_RESPONSE", data)
            
            return data
        except Exception as e:
            logger.logger.error(f"LLM Bridge error: {e}")
            from core.engine.event_bus import bus
            bus.publish("BRAIN_ERROR", {"reason": str(e)})
            return None
        finally:
            self.queue.get()

llm_bridge = LLMBridge()
