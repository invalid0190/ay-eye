from typing import Dict, Any, List
from core.state.models import SystemState
from core.utils.logger import logger

class ContextDistiller:
    TOKEN_LIMIT = 1000 # Strict limit

    @staticmethod
    def distill(state: SystemState) -> Dict[str, Any]:
        # Priority order: Errors > Buttons/Inputs > Titles > Text
        distilled = {
            "app": state.app,
            "window": state.window,
            "ui_elements": [],
            "important_text": ""
        }
        
        # 1. Distill UI Elements
        # Max 10 elements
        elements = sorted(state.ui_elements, key=lambda x: x.role == "Button", reverse=True)[:10]
        distilled["ui_elements"] = [
            {"name": e.name, "role": e.role} for e in elements
        ]
        
        # 2. Distill OCR Text
        # Find error-like text or just take the start
        text = state.ocr_text.strip()
        if len(text) > 500:
            # Simple truncation: keep start and end
            distilled["important_text"] = text[:250] + "..." + text[-250:]
        else:
            distilled["important_text"] = text
            
        return distilled

class PromptBuilder:
    SYSTEM_PROMPT = """You are ay-eye, a Jarvis-like Windows copilot. 
Analyze the screen context and suggest the next step. 
Return ONLY JSON in this format:
{
  "intent": "guide|ask|act|ignore",
  "message": "Direct message to user",
  "actions": [{"type": "click|type", "target": "element name"}],
  "confidence": 0.0-1.0
}"""

    @staticmethod
    def build(distilled_context: Dict[str, Any], trigger_type: str) -> str:
        context_block = f"SCREEN CONTEXT:\n{distilled_context}"
        task_block = f"SITUATION: Triggered by {trigger_type}. What should I do?"
        
        return f"{PromptBuilder.SYSTEM_PROMPT}\n\n{context_block}\n\n{task_block}"

context_distiller = ContextDistiller()
prompt_builder = PromptBuilder()
