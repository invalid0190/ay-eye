from pydantic import BaseModel
from typing import Optional

class UIState(BaseModel):
    status: str = "idle" # idle, listening, thinking, acting
    active_app: str = ""
    confidence: float = 0.0
    last_action: str = ""
    visible: bool = True

class UIStateManager:
    def __init__(self):
        self.state = UIState()
    
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.state, k):
                setattr(self.state, k, v)

ui_state_manager = UIStateManager()
