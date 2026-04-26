import requests
import os
import tempfile
import threading
import subprocess
from core.engine.audio_state import audio_state
from core.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()


class TTSEngine:
    """Text-to-Speech engine. Uses OpenAI TTS if available, falls back to Murf AI."""

    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.murf_key = os.getenv("MURF_API_KEY")
        self._stop_event = threading.Event()
        self._player_process = None

        if self.openai_key:
            self.provider = "openai"
            self.voice = "nova"  # Options: alloy, echo, fable, onyx, nova, shimmer
            logger.logger.info(f"TTS Engine: Using OpenAI TTS (voice: {self.voice})")
        elif self.murf_key:
            self.provider = "murf"
            self.voice = "Natalie"
            logger.logger.info(f"TTS Engine: Using Murf AI (voice: {self.voice})")
        else:
            self.provider = None
            logger.logger.warning("TTS Engine: No API key found, TTS disabled")

    def speak(self, text):
        if not self.provider:
            logger.logger.warning("TTS skipped: no provider")
            return

        if not audio_state.start_speaking():
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
        payload = {
            "text": text,
            "voiceId": self.voice,
            "modelVersion": "GEN2"
        }

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
        tmp_path = os.path.join(tempfile.gettempdir(), "ayeye_tts.mp3")
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


tts_engine = TTSEngine()
