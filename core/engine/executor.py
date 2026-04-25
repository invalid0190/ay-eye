import pyautogui
import time
import random
import threading
from core.engine.event_bus import bus
from core.engine.action_state import action_state
from core.utils.logger import logger

class ActionExecutor:
    def __init__(self):
        pyautogui.FAILSAFE = True # Move mouse to corner to kill
        self._stop_event = threading.Event()
        bus.subscribe("EMERGENCY_STOP", self.stop)

    def stop(self, data=None):
        self._stop_event.set()
        action_state.stop_action()
        logger.log_event("EXECUTOR_FORCE_STOPPED")

    def execute_sequence(self, actions):
        self._stop_event.clear()
        for action in actions:
            if self._stop_event.is_set():
                break
            
            # Human-like delay
            time.sleep(random.uniform(0.1, 0.3))
            self.execute_single(action)

    def execute_single(self, action):
        if self._stop_event.is_set():
            return

        a_type = action.get("type")
        logger.log_event("ACTION_STARTED", action)
        
        try:
            if a_type == "click":
                x, y = action.get("x"), action.get("y")
                # Add tiny random jitter to target
                jx = x + random.randint(-2, 2)
                jy = y + random.randint(-2, 2)
                
                # Human-like smooth movement
                duration = random.uniform(0.2, 0.4)
                pyautogui.moveTo(jx, jy, duration=duration, tween=pyautogui.easeOutQuad)
                
                time.sleep(random.uniform(0.05, 0.15)) # Micro-hesitation
                pyautogui.click()
            elif a_type == "type":
                text = action.get("text")
                pyautogui.write(text, interval=0.05)
            elif a_type == "hotkey":
                keys = action.get("keys", [])
                pyautogui.hotkey(*keys)
                
            time.sleep(random.uniform(0.15, 0.3)) # Delay after click
            bus.publish("ACTION_COMPLETED", action)
        except Exception as e:
            logger.logger.error(f"Execution error: {e}")
            bus.publish("ACTION_ABORTED", {"action": action, "error": str(e)})

executor = ActionExecutor()
