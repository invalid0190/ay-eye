import time
import threading

class ActionState:
    def __init__(self):
        self.is_executing = False
        self.current_action = None
        self.last_action_time = time.time()
        self._lock = threading.Lock()

    def start_action(self, action_name):
        with self._lock:
            if not self.is_executing:
                self.is_executing = True
                self.current_action = action_name
                return True
            return False

    def stop_action(self):
        with self._lock:
            self.is_executing = False
            self.current_action = None
            self.last_action_time = time.time()

action_state = ActionState()
