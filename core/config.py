import json
import os

class SystemConfig:
    def __init__(self):
        self.config_path = "config.json"
        self.defaults = {
            "mode": "ACTIVE", # Setting to ACTIVE for better feedback
            "confidence_threshold": 0.5,
            "trigger_sensitivity": 0.5,
            "voice_enabled": True,
            "action_confirmation_required": False, # Faster testing
            "cooldown_seconds": 5.0,
            "debug_mode": True
        }
        self.config = self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    # Merge with defaults for safety
                    return {**self.defaults, **data}
            except:
                return self.defaults
        return self.defaults

    def save(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key):
        return self.config.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()

    @property
    def is_observation_only(self):
        return self.get("mode") == "OBSERVATION"

sys_config = SystemConfig()
