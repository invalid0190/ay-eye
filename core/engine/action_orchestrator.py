import time
import threading
from core.engine.event_bus import bus
from core.config import sys_config
from core.engine.executor import executor
from core.engine.action_state import action_state
from core.utils.logger import logger

class ActionOrchestrator:
    # All known action types — add new ones here, they route to executor automatically
    KNOWN_ACTIONS = {
        "click", "click_text", "drag", "type", "hotkey", "scroll", "switch", "launch",
        "open_url", "cmd", "create_skill", "read_file", "list_dir",
        "write_file", "extract_clipboard", "listen_audio", "ocr_screen"
    }

    def __init__(self):
        bus.subscribe("ACTION_REQUESTED", self.on_action_requested)
        self.confirm_event = threading.Event()
        bus.subscribe("CONFIRM_HOTKEY", lambda d: self.confirm_event.set())

    def on_action_requested(self, data):
        logger.log_event("ACTION_REQUESTED", {
            "status": data.get("status"),
            "actions": data.get("actions", [])
        })

        if not action_state.start_action("orchestration"):
            logger.log_event("ACTION_SKIPPED_BUSY", {
                "current_action": action_state.current_action,
                "requested_actions": data.get("actions", [])
            })
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
                    
                    if a_type not in self.KNOWN_ACTIONS:
                        logger.logger.warning(f"Unknown action type: {a_type}")
                        continue
                    
                    # Click gets special visual highlight before execution
                    if a_type == "click" and "x" in action and "y" in action:
                        bus.publish("HIGHLIGHT_REQUESTED", {
                            "x": action["x"], "y": action["y"], 
                            "w": 40, "h": 40
                        })
                        time.sleep(0.3)
                    
                    executor.execute_single(action)

                logger.log_event("ACTION_SEQUENCE_COMPLETED", {
                    "count": len(actions),
                    "status": data.get("status")
                })
                    
            finally:
                action_state.stop_action()
                
            # Trigger the agentic verification loop if the AI indicated it's still in progress
            if data.get("status") == "in_progress":
                logger.logger.info("Actions complete, triggering verification loop...")
                time.sleep(1.0) # Wait for UI to settle
                bus.publish("AUTONOMOUS_LOOP_TRIGGER", data)

        threading.Thread(target=_run, daemon=True).start()

action_orchestrator = ActionOrchestrator()
