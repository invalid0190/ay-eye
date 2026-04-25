import time
from typing import Dict, Any, Optional
from core.utils.logger import logger

class DecisionEngine:
    def __init__(self):
        self.last_call_time = 0
        self.cooldown = 10.0

    def should_call_ai(self, trigger_data: Dict[str, Any], state: Any) -> bool:
        # Layer 1: Trigger check (Already handled by Trigger Engine but validated here)
        if not trigger_data:
            return False
            
        # Layer 2: Context importance
        # If no window title or no text/ui, it's not meaningful
        if not state.window or (not state.ocr_text and not state.ui_elements):
            logger.logger.info("Decision: Context not meaningful, skipping AI")
            return False
            
        # Layer 3: Confidence threshold
        # (Assuming trigger confidence is passed in data)
        confidence = trigger_data.get("confidence", 1.0)
        if confidence < 0.7:
            logger.logger.info(f"Decision: Confidence {confidence} too low")
            return False
            
        # Cooldown check
        if time.time() - self.last_call_time < self.cooldown:
            logger.logger.info("Decision: Cooldown active")
            return False
            
        self.last_call_time = time.time()
        return True

    def get_response_mode(self, confidence: float) -> str:
        if confidence < 0.5:
            return "IGNORE"
        elif confidence < 0.7:
            return "UI_ONLY"
        else:
            return "UI_VOICE"

decision_engine = DecisionEngine()
