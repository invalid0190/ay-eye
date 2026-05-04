import requests
import time
import os
import threading
from queue import Queue, Full
from typing import Optional, Dict, Any, List
from core.utils.logger import logger
from core.utils.json_parser import json_parser
from dotenv import load_dotenv

load_dotenv()


def _safe_log_snippet(text: str, limit: int = 800) -> str:
    """ASCII-safe for Windows consoles (cp1252); avoids UnicodeEncodeError in logging."""
    if not text:
        return ""
    return text[:limit].encode("ascii", errors="replace").decode("ascii")


class LLMBridge:
    _VISION_UNSUPPORTED_HINT = (
        "\n\n[System: This model cannot see your screen. Answer using the voice "
        "command text and general knowledge only — no screenshot.]"
    )

    def __init__(self):
        preferred_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.moonshot_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        self.agent_router_key = os.getenv("AGENT_ROUTER_API_KEY")
        self.ollama_key = os.getenv("OLLAMA_API_KEY")

        use_openai = self.openai_key and (
            preferred_provider in ("", "openai")
            or (preferred_provider not in ("moonshot", "kimi", "agentrouter", "ollama"))
        )
        use_moonshot = self.moonshot_key and preferred_provider in ("moonshot", "kimi")
        use_agentrouter = self.agent_router_key and preferred_provider == "agentrouter"
        use_ollama_cloud = self.ollama_key and preferred_provider == "ollama"

        if not any((use_openai, use_moonshot, use_agentrouter, use_ollama_cloud)):
            use_openai = bool(self.openai_key)
            use_moonshot = bool(self.moonshot_key) and not use_openai
            use_agentrouter = bool(self.agent_router_key) and not (use_openai or use_moonshot)
            use_ollama_cloud = bool(self.ollama_key) and not (use_openai or use_moonshot or use_agentrouter)

        # Priority: explicit LLM_PROVIDER > OpenAI > Moonshot/Kimi > AgentRouter > Ollama Cloud > Local Ollama
        if use_openai:
            self.provider = "openai"
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
            self.url = "https://api.openai.com/v1/chat/completions"
            logger.logger.info(f"LLM Bridge: Using OpenAI {self.model}")
        elif use_moonshot:
            self.provider = "moonshot"
            self.model = os.getenv("MOONSHOT_MODEL") or os.getenv("KIMI_MODEL") or "kimi-k2.6"
            base_url = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
            self.url = f"{base_url.rstrip('/')}/chat/completions"
            logger.logger.info(f"LLM Bridge: Using Moonshot/Kimi {self.model}")
        elif use_agentrouter:
            self.provider = "agentrouter"
            # Dashboard IDs: deepseek-r1-0528, deepseek-v3.1, deepseek-v3.2, glm-4.5, glm-4.6, glm-5.1
            self.primary_model = os.getenv(
                "AGENT_ROUTER_PRIMARY_MODEL", "deepseek-r1-0528"
            )
            _sec_env = os.getenv("AGENT_ROUTER_SECONDARY_MODEL")
            if _sec_env is None:
                self.secondary_model = "glm-5.1"
            else:
                self.secondary_model = _sec_env.strip() or None

            self.model = self.primary_model
            base_url = os.getenv("AGENT_ROUTER_BASE_URL", "https://agentrouter.org/v1")
            self.url = f"{base_url.rstrip('/')}/chat/completions"
            sec_log = self.secondary_model or "(none)"
            logger.logger.info(
                f"LLM Bridge: Using AgentRouter {self.model} (Secondary: {sec_log})"
            )
        elif use_ollama_cloud:
            self.provider = "ollama"
            self.model = "gemma4:e2b"
            self.url = "https://ollama.com/api/generate"
            logger.logger.info(f"LLM Bridge: Using Ollama Cloud {self.model}")
        else:
            self.provider = "ollama"
            self.model = "gemma4:e2b"
            self.url = "http://localhost:11434/api/generate"
            logger.logger.info("LLM Bridge: Using local Ollama")

        self.timeout = 60.0
        self.queue = Queue(maxsize=1)
        self.busy_wait_timeout = 20.0
        self._agent_router_retries = max(1, int(os.getenv("AGENT_ROUTER_HTTP_RETRIES", "3")))

    def _post_openai_chat(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        tag: str = "LLM",
        raise_for_status: bool = True,
    ):
        """POST to chat/completions; Agent Router gets retries on transient upstream errors."""
        if self.provider != "agentrouter":
            response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            if response.status_code != 200:
                logger.logger.error(
                    f"{tag}: {self.provider} error {response.status_code}: "
                    f"{_safe_log_snippet(response.text)}"
                )
            if raise_for_status:
                response.raise_for_status()
            return response

        delay = float(os.getenv("AGENT_ROUTER_HTTP_RETRY_DELAY_SEC", "1.0"))
        last = None
        for attempt in range(self._agent_router_retries):
            last = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            if last.status_code == 200:
                return last
            transient = last.status_code in (502, 503, 504, 429)
            if transient and attempt < self._agent_router_retries - 1:
                logger.logger.warning(
                    f"{tag}: AgentRouter HTTP {last.status_code}, retry {attempt + 1}/{self._agent_router_retries}"
                )
                time.sleep(delay * (2**attempt))
                continue
            break
        
        if last is not None and last.status_code != 200:
            msg = f"{tag}: AgentRouter error {last.status_code}: {_safe_log_snippet(last.text)}"
            if raise_for_status:
                logger.logger.error(msg)
            else:
                logger.logger.warning(msg)

        if raise_for_status:
            last.raise_for_status()
        return last

    @staticmethod
    def _response_indicates_no_vision(response: requests.Response) -> bool:
        if response.status_code != 400:
            return False
        t = response.text
        return (
            "image_url" in t
            or "Invalid content" in t
            or "only supported by certain models" in t
        )

    def _build_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.provider == "openai":
            headers["Authorization"] = f"Bearer {self.openai_key}"
        elif self.provider == "moonshot":
            headers["Authorization"] = f"Bearer {self.moonshot_key}"
        elif self.provider == "agentrouter":
            headers["Authorization"] = f"Bearer {self.agent_router_key}"
            headers["Originator"] = "codex_cli_rs"
            headers["User-Agent"] = "codex_cli_rs/0.101.0 (Mac OS 26.0.1; arm64) Apple_Terminal/464"
            headers["Version"] = "0.101.0"
        elif self.ollama_key:
            headers["Authorization"] = f"Bearer {self.ollama_key}"
        return headers

    def generate(self, prompt: str, retry=True) -> Optional[Dict[str, Any]]:
        try:
            self.queue.put(True, timeout=self.busy_wait_timeout)
        except Full:
            logger.logger.warning("LLM Bridge busy, dropping request")
            return None

        try:
            return self._generate_internal(prompt, retry)
        finally:
            self.queue.get()

    def _complete_prompt_text(self, prompt: str, retry=True) -> Optional[Dict[str, Any]]:
        """Single text completion (no queue). Used by generate and vision→text fallback."""
        start_time = time.time()
        headers = self._build_headers()

        if self.provider in ["openai", "moonshot", "agentrouter"]:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            }
            if self.provider == "openai":
                payload["response_format"] = {"type": "json_object"}

            response = self._post_openai_chat(payload, headers, tag="LLM Bridge")
            raw_text = response.json()["choices"][0]["message"]["content"]
        else:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            raw_text = response.json().get("response", "")

        data = json_parser.extract_and_heal(raw_text)

        if not data and retry:
            logger.logger.warning("JSON parse failed, retrying...")
            return self._complete_prompt_text(
                prompt + "\n\nIMPORTANT: Return ONLY valid JSON.", retry=False
            )

        duration = int((time.time() - start_time) * 1000)
        logger.log_performance("LLM_GENERATE", duration)
        logger.log_event("LLM_RESPONSE", data)
        return data

    def _generate_internal(self, prompt: str, retry=True) -> Optional[Dict[str, Any]]:
        try:
            return self._complete_prompt_text(prompt, retry)
        except Exception as e:
            logger.logger.error(f"LLM Bridge error: {e}")
            if (
                self.provider == "agentrouter"
                and self.model == self.primary_model
                and self.secondary_model
            ):
                logger.logger.info(
                    f"Primary model {self.primary_model} failed, retrying with secondary {self.secondary_model}"
                )
                old_model = self.model
                self.model = self.secondary_model
                try:
                    return self._complete_prompt_text(prompt, retry=retry)
                finally:
                    self.model = old_model
            
            from core.engine.event_bus import bus
            bus.publish("BRAIN_ERROR", {"reason": str(e)})
            return None

    def generate_with_vision(self, prompt: str, images_b64: List[str], retry=True) -> Optional[Dict[str, Any]]:
        """Send a prompt with screenshot images to the vision-capable LLM."""
        try:
            self.queue.put(True, timeout=self.busy_wait_timeout)
        except Full:
            logger.logger.warning("LLM Bridge busy, dropping request")
            return None

        try:
            return self._generate_with_vision_internal(prompt, images_b64, retry)
        finally:
            self.queue.get()

    def _generate_with_vision_internal(self, prompt: str, images_b64: List[str], retry=True) -> Optional[Dict[str, Any]]:
        try:
            start_time = time.time()
            headers = self._build_headers()

            if self.provider in ["openai", "moonshot", "agentrouter"]:
                content = [{"type": "text", "text": prompt}]
                for img_b64 in images_b64:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                            "detail": "high",
                        },
                    })

                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 2000,
                }
                if self.provider == "openai":
                    payload["response_format"] = {"type": "json_object"}

                response = self._post_openai_chat(
                    payload, headers, tag="LLM Bridge Vision", raise_for_status=False
                )

                if response.status_code == 200:
                    raw_text = response.json()["choices"][0]["message"]["content"]
                elif self._response_indicates_no_vision(response):
                    logger.logger.info(
                        "LLM Bridge: Model does not support vision; falling back to text-only."
                    )
                    fb_prompt = prompt + self._VISION_UNSUPPORTED_HINT
                    return self._generate_internal(fb_prompt, retry)
                else:
                    response.raise_for_status()
                    raw_text = response.json()["choices"][0]["message"]["content"]
            else:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "images": images_b64,
                    "stream": False,
                    "format": "json",
                }
                response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                raw_text = response.json().get("response", "")

            data = json_parser.extract_and_heal(raw_text)

            if not data and retry:
                logger.logger.warning("Vision JSON parse failed, retrying...")
                return self._generate_with_vision_internal(
                    prompt + "\n\nReturn ONLY valid JSON.", images_b64, retry=False
                )

            duration = int((time.time() - start_time) * 1000)
            logger.log_performance("LLM_VISION", duration)
            logger.log_event("LLM_VISION_RESPONSE", data)
            return data
        except Exception as e:
            logger.logger.error(f"LLM Vision error: {e}")
            if (
                self.provider == "agentrouter"
                and self.model == self.primary_model
                and self.secondary_model
            ):
                logger.logger.info(
                    f"Primary vision model {self.primary_model} failed, retrying with secondary {self.secondary_model}"
                )
                old_model = self.model
                self.model = self.secondary_model
                try:
                    return self._generate_with_vision_internal(prompt, images_b64, retry=retry)
                finally:
                    self.model = old_model
            
            from core.engine.event_bus import bus
            bus.publish("BRAIN_ERROR", {"reason": str(e)})
            return None


llm_bridge = LLMBridge()
