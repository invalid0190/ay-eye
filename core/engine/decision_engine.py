import time
from typing import Dict, Any, Optional
from core.utils.logger import logger
from core.config import sys_config

class DecisionEngine:
    def __init__(self):
        self.last_call_time = 0
        self.cooldown = 10.0

    def should_call_ai(self, trigger_data: Dict[str, Any], state: Any) -> bool:
        # Layer 1: Trigger check (Already handled by Trigger Engine but validated here)
        if not trigger_data:
            return False
            
        # Layer 2: Context importance
        # If no window title or no text/ui, it's not meaningful (unless it's a direct voice command)
        is_voice = trigger_data.get("type") == "VOICE_COMMAND"
        if not is_voice:
            if not state.window or (not state.ocr_text and not state.ui_elements):
                logger.logger.info("Decision: Context not meaningful, skipping AI")
                return False
            
        # Layer 3: Confidence threshold
        confidence = trigger_data.get("confidence", 1.0)
        threshold = sys_config.get("trigger_sensitivity")
        if confidence < threshold:
            logger.logger.info(f"Decision: Confidence {confidence} below threshold {threshold}")
            return False
            
        # Cooldown check (skip for voice commands - always process immediately)
        if not is_voice:
            cooldown = sys_config.get("cooldown_seconds")
            if time.time() - self.last_call_time < cooldown:
                logger.logger.info("Decision: Cooldown active")
                return False
            
        self.last_call_time = time.time()
        return True

    def get_response_mode(self, confidence: float) -> str:
        # Low threshold to ensure voice responses get through
        if confidence < 0.3:
            return "IGNORE"
        return "UI_VOICE"

decision_engine = DecisionEngine()
