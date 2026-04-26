import time
import threading
from core.engine.event_bus import bus
from core.config import sys_config
from core.engine.executor import executor
from core.engine.action_state import action_state
from core.utils.logger import logger

class ActionOrchestrator:
    def __init__(self):
        bus.subscribe("ACTION_REQUESTED", self.on_action_requested)
        self.confirm_event = threading.Event()
        bus.subscribe("CONFIRM_HOTKEY", lambda d: self.confirm_event.set())

    def on_action_requested(self, data):
        if not action_state.start_action("orchestration"):
            return

        def _run():
            try:
                self.confirm_event.clear()
                
                if sys_config.is_observation_only:
                    logger.log_event("OBSERVATION_MODE_BLOCK", data)
                    return

                # Wait for confirmation if required
                if sys_config.get("action_confirmation_required"):
                    logger.log_event("WAITING_FOR_CONFIRMATION", data)
                    if not self.confirm_event.wait(timeout=15.0):
                        logger.log_event("ACTION_ABORTED", {"reason": "Timeout"})
                        bus.publish("ACTION_ABORTED", {"reason": "Confirmation timeout"})
                        return

                actions = data.get("actions", [])
                for action in actions:
                    a_type = action.get("type")
                    
                    if a_type == "click" and "x" in action and "y" in action:
                        bus.publish("HIGHLIGHT_REQUESTED", {
                            "x": action["x"], "y": action["y"], 
                            "w": 40, "h": 40
                        })
                        time.sleep(0.3)
                        executor.execute_single(action)
                        
                    elif a_type in ("type", "hotkey", "scroll", "switch", "cmd", "create_skill"):
                        executor.execute_single(action)
                        
                    elif a_type == "launch":
                        executor.execute_single(action)
                        
                    else:
                        logger.logger.warning(f"Unknown action type: {a_type}")
                    
            finally:
                action_state.stop_action()

        threading.Thread(target=_run, daemon=True).start()

action_orchestrator = ActionOrchestrator()
