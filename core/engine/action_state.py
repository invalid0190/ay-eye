import time
import threading

class ActionState:
    def __init__(self):
        self.is_executing = False
        self.current_action = None
        self.started_at = None
        self.last_action_time = time.time()
        self.max_action_seconds = 90
        self._lock = threading.Lock()

    def start_action(self, action_name):
        with self._lock:
            now = time.time()
            if self.is_executing and self.started_at:
                age = now - self.started_at
                if age > self.max_action_seconds:
                    try:
                        from core.utils.logger import logger
                        logger.logger.warning(
                            f"ActionState: stale action '{self.current_action}' held for {age:.1f}s; recovering"
                        )
                    except Exception:
                        pass
                    self.is_executing = False
                    self.current_action = None
                    self.started_at = None

            if not self.is_executing:
                self.is_executing = True
                self.current_action = action_name
                self.started_at = now
                return True
            return False

    def stop_action(self):
        with self._lock:
            self.is_executing = False
            self.current_action = None
            self.started_at = None
            self.last_action_time = time.time()

action_state = ActionState()
