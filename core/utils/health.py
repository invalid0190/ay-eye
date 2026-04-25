import requests
import shutil
import subprocess
from core.utils.logger import logger

class HealthChecker:
    @staticmethod
    def check_ollama(model="llama3"):
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=1)
            if response.status_code == 200:
                models = [m['name'] for m in response.json().get('models', [])]
                if any(model in m for m in models):
                    return True, f"Ollama OK ({model})"
                return False, f"Ollama OK (Model {model} missing)"
            return False, "Ollama error (status != 200)"
        except:
            return False, "Ollama offline"

    @staticmethod
    def check_tesseract():
        if shutil.which("tesseract"):
            return True, "Tesseract OK"
        return False, "Tesseract missing from PATH"

    @staticmethod
    def run_all():
        o_ok, o_msg = HealthChecker.check_ollama()
        t_ok, t_msg = HealthChecker.check_tesseract()
        return {
            "ok": o_ok and t_ok,
            "details": f"{o_msg} | {t_msg}"
        }

health_checker = HealthChecker()
