import threading
from .models import SystemState
from core.engine.event_bus import bus
from datetime import datetime

class CurrentState:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(CurrentState, cls).__new__(cls)
                    cls._instance._state = SystemState()
        return cls._instance

    def update(self, **kwargs):
        with self._lock:
            kwargs['last_update_time'] = datetime.now()
            # Update only provided fields
            current_dict = self._state.dict()
            current_dict.update(kwargs)
            self._state = SystemState(**current_dict)
            
        bus.publish("STATE_UPDATED", self._state)

    def get_state(self) -> SystemState:
        with self._lock:
            return self._state

state_manager = CurrentState()
