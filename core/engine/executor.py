import pyautogui
import subprocess
import time
import random
import threading
from core.engine.event_bus import bus
from core.engine.action_state import action_state
from core.utils.logger import logger

class ActionExecutor:
    def __init__(self):
        # We keep FAILSAFE=True for user safety, but we will clamp coords to prevent accidental triggers
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self._stop_event = threading.Event()
        bus.subscribe("EMERGENCY_STOP", self.stop)
        
        # Get screen size for clamping
        self.screen_w, self.screen_h = pyautogui.size()

    def stop(self, data=None):
        self._stop_event.set()
        action_state.stop_action()
        logger.log_event("EXECUTOR_FORCE_STOPPED")

    def execute_sequence(self, actions):
        self._stop_event.clear()
        for action in actions:
            if self._stop_event.is_set():
                break
            time.sleep(random.uniform(0.1, 0.3))
            self.execute_single(action)

    def execute_single(self, action):
        if self._stop_event.is_set():
            return

        a_type = action.get("type")
        bus.publish("ACTION_STARTED", action)
        logger.log_event("ACTION_STARTED", action)
        
        try:
            if a_type == "click":
                x = action.get("x")
                y = action.get("y")
                
                if x is not None and y is not None:
                    # Clamp to safe zone (10px from edges) to avoid fail-safe corners
                    jx = max(10, min(self.screen_w - 10, x + random.randint(-2, 2)))
                    jy = max(10, min(self.screen_h - 10, y + random.randint(-2, 2)))
                    
                    duration = random.uniform(0.8, 1.2)
                    pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                    time.sleep(random.uniform(0.05, 0.15))
                    pyautogui.click()
                else:
                    logger.logger.warning(f"Click action missing coordinates: {action}")
                    
            elif a_type == "type":
                text = action.get("text", "")
                if text:
                    for char in text:
                        if self._stop_event.is_set():
                            break
                        pyautogui.press(char) if len(char) > 1 else pyautogui.write(char, interval=0)
                        time.sleep(random.uniform(0.03, 0.08))
                        
            elif a_type == "hotkey":
                keys = action.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    
            elif a_type == "launch":
                target = action.get("target", "")
                if target:
                    try:
                        # Try 'start' command for Windows apps/links
                        subprocess.Popen(f"start {target}", shell=True)
                        logger.log_event("APP_LAUNCHED", {"app": target})
                        logger.logger.info(f"Executor: Launched {target}")
                    except Exception as e:
                        logger.logger.error(f"Launch failed for {target}: {e}")
                else:
                    logger.logger.warning("Launch action missing target")
                        
            elif a_type == "scroll":
                amount = action.get("amount", -3)
                pyautogui.scroll(amount)
                
            time.sleep(random.uniform(0.1, 0.2))
            bus.publish("ACTION_COMPLETED", action)
            
        except pyautogui.FailSafeException:
            logger.logger.error("PyAutoGUI Fail-safe triggered (mouse in corner). Action aborted.")
            bus.publish("ACTION_ABORTED", {"reason": "Fail-safe triggered (User intervention)"})
        except Exception as e:
            logger.logger.error(f"Execution error: {e}")
            bus.publish("ACTION_ABORTED", {"reason": str(e)})

executor = ActionExecutor()
