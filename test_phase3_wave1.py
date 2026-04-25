import time
from core.engine.event_bus import bus
from core.engine.tts import tts_engine
from core.engine.voice_controller import voice_controller
from core.engine.audio_state import audio_state

# Test TTS
print("Testing TTS (Interruptible)...")
tts_engine.speak("This is a long sentence that should be interrupted when I call stop.")
time.sleep(0.5)
tts_engine.stop()
print(f"Speaking state after interrupt: {audio_state.is_speaking}")

# Test Gating
print("\nTesting Voice Gating...")
voice_controller.handle_response({"message": "Hello ay-eye", "confidence": 0.9, "mode": "UI_VOICE"})
time.sleep(1)
