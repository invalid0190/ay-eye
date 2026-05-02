import requests
import os
import tempfile
import threading
import subprocess
from core.engine.audio_state import audio_state
from core.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

def _looks_hindi(text: str) -> bool:
    # Devanagari block: U+0900–U+097F
    for ch in text or "":
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            return True
    return False


class TTSEngine:
    """Text-to-Speech engine. Uses OpenAI TTS if available, falls back to Murf AI."""

    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.murf_key = os.getenv("MURF_API_KEY")
        self._stop_event = threading.Event()
        self._player_process = None
        self._last_input_lang = "en"
        from core.engine.event_bus import bus
        bus.subscribe("EMERGENCY_STOP", lambda d: self.stop())
        bus.subscribe("VOICE_INPUT_RECEIVED", self._on_user_text)

        if self.openai_key:
            self.provider = "openai"
            self.voice = "nova"  # Options: alloy, echo, fable, onyx, nova, shimmer
            logger.logger.info(f"TTS Engine: Using OpenAI TTS (voice: {self.voice})")
        elif self.murf_key:
            self.provider = "murf"
            # Default English + Hindi voices (override in .env)
            self.voice_en = (os.getenv("MURF_VOICE_EN") or "Natalie").strip() or "Natalie"
            self.voice_hi = (os.getenv("MURF_VOICE_HI") or "Ruby").strip() or "Ruby"
            self.style_hi = (os.getenv("MURF_STYLE_HI") or "Conversational").strip() or "Conversational"
            self.locale_hi = (os.getenv("MURF_LOCALE_HI") or "hi-IN").strip() or "hi-IN"
            self.voice = self.voice_en
            logger.logger.info(f"TTS Engine: Using Murf AI (voice: {self.voice})")
        else:
            self.provider = None
            logger.logger.warning("TTS Engine: No API key found, TTS disabled")

    def _on_user_text(self, text):
        if isinstance(text, str) and _looks_hindi(text):
            self._last_input_lang = "hi"
        else:
            self._last_input_lang = "en"

    def speak(self, text):
        if not self.provider:
            logger.logger.warning("TTS skipped: no provider")
            from core.engine.event_bus import bus
            bus.publish("TTS_FINISHED", {})
            return

        if not audio_state.start_speaking():
            from core.engine.event_bus import bus
            bus.publish("TTS_FINISHED", {})
            return

        def _run():
            try:
                self._stop_event.clear()

                if self.provider == "openai":
                    self._speak_openai(text)
                else:
                    self._speak_murf(text)

            except Exception as e:
                logger.logger.error(f"TTS error: {e}")
            finally:
                audio_state.stop_speaking()
                from core.engine.event_bus import bus
                bus.publish("TTS_FINISHED", {})

        threading.Thread(target=_run, daemon=True).start()

    def _speak_openai(self, text):
        """Use OpenAI TTS API — fast, high quality."""
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "tts-1",
            "input": text[:4096],  # OpenAI limit
            "voice": self.voice,
            "response_format": "mp3"
        }

        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            self._play_audio(response.content)
        else:
            logger.logger.error(f"OpenAI TTS error: {response.status_code} - {response.text[:200]}")

    def _speak_murf(self, text):
        """Use Murf AI TTS as fallback."""
        headers = {
            "Content-Type": "application/json",
            "api-key": self.murf_key
        }
        is_hi = self._last_input_lang == "hi" and _looks_hindi(text)
        voice_id = self.voice_hi if is_hi else self.voice_en
        payload = {"text": text, "voiceId": voice_id, "modelVersion": "GEN2"}
        # Hindi tuning (per user request / Murf docs); safe if server ignores unknown fields.
        if is_hi:
            payload["style"] = self.style_hi
            payload["locale"] = self.locale_hi

        response = requests.post(
            "https://api.murf.ai/v1/speech/generate",
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            audio_url = data.get("audioFile")
            if audio_url:
                audio_response = requests.get(audio_url, timeout=15)
                if audio_response.status_code == 200:
                    self._play_audio(audio_response.content)
        else:
            logger.logger.error(f"Murf TTS error: {response.status_code} - {response.text[:200]}")

    def _play_audio(self, audio_bytes):
        """Play audio bytes as MP3 using PowerShell MediaPlayer."""
        import uuid
        tmp_path = os.path.join(tempfile.gettempdir(), f"ayeye_tts_{uuid.uuid4().hex[:8]}.mp3")
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)

        ps_cmd = f"""
Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([uri]'{tmp_path}')
$player.Play()
Start-Sleep -Milliseconds 500
while ($player.Position -lt $player.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100 }}
$player.Close()
Remove-Item -Path '{tmp_path}' -Force -ErrorAction SilentlyContinue
"""
        self._player_process = subprocess.Popen(
            ["powershell", "-NoProfile", "-c", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self._player_process.wait()
        self._player_process = None

    def stop(self):
        self._stop_event.set()
        # Kill the player process if running
        if self._player_process:
            try:
                self._player_process.terminate()
            except Exception:
                pass
        audio_state.stop_speaking()
        logger.log_event("TTS_INTERRUPTED")
        from core.engine.event_bus import bus
        bus.publish("TTS_FINISHED", {})


tts_engine = TTSEngine()
