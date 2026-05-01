import requests
import json
import time
import os
import base64
import threading
from queue import Queue
from typing import Optional, Dict, Any, List
from core.utils.logger import logger
from core.utils.json_parser import json_parser
from dotenv import load_dotenv

load_dotenv()


class LLMBridge:
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.ollama_key = os.getenv("OLLAMA_API_KEY")
        
        # Prefer OpenAI GPT-4o if available, fallback to Ollama
        if self.openai_key:
            self.provider = "openai"
            self.model = "gpt-4o"
            self.url = "https://api.openai.com/v1/chat/completions"
            logger.logger.info(f"LLM Bridge: Using OpenAI {self.model}")
        elif self.ollama_key:
            self.provider = "ollama"
            self.model = "gemma3:4b"
            self.url = "https://ollama.com/api/generate"
            logger.logger.info(f"LLM Bridge: Using Ollama Cloud {self.model}")
        else:
            self.provider = "ollama"
            self.model = "gemma3:4b"
            self.url = "http://localhost:11434/api/generate"
            logger.logger.info("LLM Bridge: Using local Ollama")
        
        self.timeout = 60.0
        self.queue = Queue(maxsize=1)
        self._lock = threading.Lock()

    def _build_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.provider == "openai":
            headers["Authorization"] = f"Bearer {self.openai_key}"
        elif self.ollama_key:
            headers["Authorization"] = f"Bearer {self.ollama_key}"
        return headers

    def generate(self, prompt: str, retry=True) -> Optional[Dict[str, Any]]:
        if self.queue.full():
            logger.logger.warning("LLM Bridge busy, dropping request")
            return None
        
        self.queue.put(True)
        queued = True
        try:
            start_time = time.time()
            headers = self._build_headers()
            
            if self.provider == "openai":
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2000
                }
                response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                raw_text = response.json()["choices"][0]["message"]["content"]
            else:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }
                response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                raw_text = response.json().get("response", "")
            
            data = json_parser.extract_and_heal(raw_text)
            
            if not data and retry:
                logger.logger.warning("JSON parse failed, retrying...")
                self.queue.get()
                queued = False
                return self.generate(prompt + "\n\nIMPORTANT: Return ONLY valid JSON.", retry=False)
            
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
            if queued:
                self.queue.get()

    def generate_with_vision(self, prompt: str, images_b64: List[str], retry=True) -> Optional[Dict[str, Any]]:
        """Send a prompt with screenshot images to the vision-capable LLM."""
        if self.queue.full():
            logger.logger.warning("LLM Bridge busy, dropping request")
            return None
        
        self.queue.put(True)
        queued = True
        try:
            start_time = time.time()
            headers = self._build_headers()
            
            if self.provider == "openai":
                # Build multi-modal content with images
                content = [{"type": "text", "text": prompt}]
                for img_b64 in images_b64:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                            "detail": "high"
                        }
                    })
                
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2000
                }
                response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                raw_text = response.json()["choices"][0]["message"]["content"]
            else:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "images": images_b64,
                    "stream": False,
                    "format": "json"
                }
                response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                raw_text = response.json().get("response", "")
            
            data = json_parser.extract_and_heal(raw_text)
            
            if not data and retry:
                logger.logger.warning("Vision JSON parse failed, retrying...")
                self.queue.get()
                queued = False
                return self.generate_with_vision(
                    prompt + "\n\nReturn ONLY valid JSON.", images_b64, retry=False
                )
            
            duration = int((time.time() - start_time) * 1000)
            logger.log_performance("LLM_VISION", duration)
            logger.log_event("LLM_VISION_RESPONSE", data)
            return data
        except Exception as e:
            logger.logger.error(f"LLM Vision error: {e}")
            from core.engine.event_bus import bus
            bus.publish("BRAIN_ERROR", {"reason": str(e)})
            return None
        finally:
            if queued:
                self.queue.get()


llm_bridge = LLMBridge()
