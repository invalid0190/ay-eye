import json
import os
from core.utils.logger import logger

class TrustManager:
    def __init__(self, file_path=".gsd/trust_scores.json"):
        self.file_path = file_path
        self.scores = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                return json.load(f)
        return {"click": 0, "type": 0, "open_app": 0}

    def _save(self):
        with open(self.file_path, "w") as f:
            json.dump(self.scores, f)

    def is_trusted(self, action_type):
        return self.scores.get(action_type, 0) >= 5

    def update_trust(self, action_type, success=True):
        if success:
            self.scores[action_type] = self.scores.get(action_type, 0) + 1
        else:
            self.scores[action_type] = 0 # Reset on failure
        self._save()

trust_manager = TrustManager()
