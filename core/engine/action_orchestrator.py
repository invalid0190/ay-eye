import time
import threading
from core.engine.event_bus import bus
from core.config import sys_config
from core.engine.resolver import resolver
from core.engine.executor import executor
from core.state.trust import trust_manager
from core.engine.action_state import action_state
from core.utils.logger import logger

class ActionOrchestrator:
    def __init__(self):
        bus.subscribe("ACTION_REQUESTED", self.on_action_requested)
        self.confirm_event = threading.Event()
        bus.subscribe("CONFIRM_HOTKEY", lambda d: self.confirm_event.set())

    def on_action_requested(self, data):
        # 1. Start State
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
                    # The UI should be showing the suggestion via BRAIN_RESPONDED
                    # We wait up to 10 seconds
                    if not self.confirm_event.wait(timeout=10.0):
                        logger.log_event("ACTION_ABORTED", {"reason": "Timeout"})
                        bus.publish("ACTION_ABORTED", {"reason": "Timeout"})
                        return

                actions = data.get("actions", [])
                for action in actions:
                    a_type = action.get("type")
                    target = action.get("target")
                    
                    # 2. Resolve
                    coords = resolver.resolve(target)
                    if coords == "AMBIGUOUS" or not coords:
                        bus.publish("ACTION_ABORTED", {"reason": "Target mismatch"})
                        break
                    
                    # If app was launched directly, skip UI interaction
                    if isinstance(coords, dict) and coords.get("launched"):
                        bus.publish("ACTION_COMPLETED", {"type": "launch", "app": coords.get("app")})
                        continue
                    
                    # 3. Trust Check
                    if not trust_manager.is_trusted(a_type):
                        logger.log_event("CONFIRMATION_REQUIRED", action)
                        pass
                    
                    # 4. Highlight
                    bus.publish("HIGHLIGHT_REQUESTED", coords)
                    time.sleep(0.5)
                    
                    # 5. Execute
                    action.update(coords)
                    executor.execute_single(action)
                    trust_manager.update_trust(a_type, success=True)
                    
            finally:
                action_state.stop_action()

        threading.Thread(target=_run, daemon=True).start()

action_orchestrator = ActionOrchestrator()
