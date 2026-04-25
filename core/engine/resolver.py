import time
from core.state.manager import state_manager
from core.utils.logger import logger

class TargetResolver:
    @staticmethod
    def resolve(target_name, trigger_confidence=1.0):
        if trigger_confidence < 0.8:
            return None

        state = state_manager.get_state()
        matches = []

        # 1. Check UIAutomation
        for el in state.ui_elements:
            if target_name.lower() in el.name.lower():
                matches.append(el)

        # 2. Check OCR (simple fallback)
        # In a real scenario, we'd find the text box in OCR results
        # For now, we prioritize UI Elements
        
        if len(matches) > 1:
            logger.logger.warning(f"Ambiguity detected for {target_name}")
            return "AMBIGUOUS"
        
        if len(matches) == 1:
            el = matches[0]
            # Convert center from rect [x, y, w, h]
            return {
                "x": el.rect[0] + el.rect[2] // 2,
                "y": el.rect[1] + el.rect[3] // 2,
                "w": el.rect[2],
                "h": el.rect[3]
            }
        
        return None

    @staticmethod
    def validate_before_action(target_name, original_pos):
        # Re-scan UI and confirm target still at pos
        # (This is a simplified mock for Phase 4)
        return True

resolver = TargetResolver()
