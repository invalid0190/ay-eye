from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class UIElement(BaseModel):
    name: str
    role: str
    rect: List[int]  # [x, y, w, h]
    text: Optional[str] = None

class SystemState(BaseModel):
    app: str = ""
    window: str = ""
    monitor: int = 0
    ui_elements: List[UIElement] = []
    ocr_text: str = ""
    last_frame_hash: str = ""
    last_update_time: datetime = Field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True
