import time
import subprocess
from core.state.manager import state_manager
from core.utils.logger import logger

class TargetResolver:
    # Common apps that can be launched directly
    LAUNCHABLE = {
        "discord": "discord",
        "notepad": "notepad",
        "chrome": "chrome",
        "firefox": "firefox",
        "code": "code",
        "terminal": "wt",
        "explorer": "explorer",
        "calculator": "calc",
        "spotify": "spotify",
    }
    
    @staticmethod
    def resolve(target_name, trigger_confidence=1.0):
        if not target_name:
            return None
            
        if trigger_confidence < 0.5:
            return None

        state = state_manager.get_state()
        matches = []

        # 1. Check UIAutomation elements
        for el in state.ui_elements:
            if target_name.lower() in el.name.lower():
                # Validate rect has 4 elements
                if el.rect and len(el.rect) >= 4 and el.rect[2] > 0 and el.rect[3] > 0:
                    matches.append(el)

        if len(matches) > 1:
            logger.logger.warning(f"Ambiguity detected for {target_name}")
            return "AMBIGUOUS"
        
        if len(matches) == 1:
            el = matches[0]
            return {
                "x": el.rect[0] + el.rect[2] // 2,
                "y": el.rect[1] + el.rect[3] // 2,
                "w": el.rect[2],
                "h": el.rect[3]
            }
        
        # 2. Fallback: check if it's a launchable app
        for app_name, cmd in TargetResolver.LAUNCHABLE.items():
            if app_name in target_name.lower():
                try:
                    subprocess.Popen(cmd, shell=True)
                    logger.log_event("APP_LAUNCHED", {"app": app_name})
                    return {"launched": True, "app": app_name}
                except Exception as e:
                    logger.logger.error(f"Failed to launch {app_name}: {e}")
                    return None
        
        return None

    @staticmethod
    def validate_before_action(target_name, original_pos):
        return True

resolver = TargetResolver()
