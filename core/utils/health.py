import requests
import shutil
import time
from core.utils.logger import logger

class HealthChecker:
    def __init__(self):
        self.last_check = 0
        self.cached_result = {"ok": False, "details": "Initializing..."}

    def check_ollama(self, model="llama3"):
        try:
            # Increased timeout to 2s for cold starts
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                models = [m['name'] for m in response.json().get('models', [])]
                if any(model in m for m in models):
                    return True, f"Ollama OK ({model})"
                return False, f"Ollama OK (Model {model} missing)"
            return False, f"Ollama error (status {response.status_code})"
        except requests.exceptions.Timeout:
            return False, "Ollama timeout"
        except Exception as e:
            return False, f"Ollama offline: {str(e)[:30]}"

    def check_tesseract(self):
        # We now use Node-based tesseract.js, so we check for node instead
        if shutil.which("node"):
            return True, "OCR Engine OK (Node)"
        return False, "Node.js missing (required for OCR)"

    def run_all(self, force=False):
        # Only check every 10 seconds unless forced
        if not force and time.time() - self.last_check < 10:
            return self.cached_result

        o_ok, o_msg = self.check_ollama()
        t_ok, t_msg = self.check_tesseract()
        
        self.cached_result = {
            "ok": o_ok and t_ok,
            "details": f"{o_msg} | {t_msg}"
        }
        self.last_check = time.time()
        return self.cached_result

health_checker = HealthChecker()
