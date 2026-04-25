import numpy as np

class AudioProcessor:
    @staticmethod
    def is_silent(data, threshold=0.01):
        # Convert to float array and check RMS
        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(audio_data**2))
        return rms < threshold

    @staticmethod
    def normalize(data):
        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
        return (audio_data * 32767).astype(np.int16).tobytes()

audio_processor = AudioProcessor()
