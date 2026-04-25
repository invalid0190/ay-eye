import requests
import os
import tempfile
import threading
from core.engine.audio_state import audio_state
from core.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

class MurfTTSEngine:
    def __init__(self):
        self.api_key = os.getenv("MURF_API_KEY")
        self.url = "https://api.murf.ai/v1/speech/generate"
        self.voice_id = "Natalie"
        self._stop_event = threading.Event()
        
        if not self.api_key:
            logger.logger.warning("MURF_API_KEY not found in .env, TTS will be disabled")

    def speak(self, text):
        if not self.api_key:
            logger.logger.warning("TTS skipped: no API key")
            return
            
        if not audio_state.start_speaking():
            return

        def _run():
            try:
                self._stop_event.clear()
                
                headers = {
                    "Content-Type": "application/json",
                    "api-key": self.api_key
                }
                
                payload = {
                    "text": text,
                    "voiceId": self.voice_id,
                    "modelVersion": "GEN2"
                }
                
                response = requests.post(self.url, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    audio_url = data.get("audioFile")
                    
                    if audio_url:
                        # Download and play the audio
                        audio_response = requests.get(audio_url, timeout=15)
                        if audio_response.status_code == 200:
                            tmp_path = os.path.join(tempfile.gettempdir(), "ayeye_tts.mp3")
                            with open(tmp_path, "wb") as f:
                                f.write(audio_response.content)
                            
                            # Play MP3 using PowerShell MediaPlayer
                            import subprocess
                            ps_cmd = f"""
Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([uri]'{tmp_path}')
$player.Play()
Start-Sleep -Milliseconds 500
while ($player.Position -lt $player.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100 }}
$player.Close()
"""
                            subprocess.run(
                                ["powershell", "-NoProfile", "-c", ps_cmd],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                    else:
                        logger.logger.error(f"Murf TTS: No audio URL in response")
                else:
                    logger.logger.error(f"Murf TTS error: {response.status_code} - {response.text[:200]}")
                    
            except Exception as e:
                logger.logger.error(f"TTS error: {e}")
            finally:
                audio_state.stop_speaking()

        threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        audio_state.stop_speaking()
        logger.log_event("TTS_INTERRUPTED")

tts_engine = MurfTTSEngine()
