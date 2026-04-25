from typing import Dict, Any, List
from core.state.models import SystemState
from core.utils.logger import logger

class ContextDistiller:
    TOKEN_LIMIT = 1000

    @staticmethod
    def distill(state: SystemState) -> Dict[str, Any]:
        distilled = {
            "app": state.app,
            "window": state.window,
            "ui_elements": [],
            "important_text": ""
        }
        elements = sorted(state.ui_elements, key=lambda x: x.role == "Button", reverse=True)[:10]
        distilled["ui_elements"] = [
            {"name": e.name, "role": e.role} for e in elements
        ]
        text = state.ocr_text.strip()
        if len(text) > 500:
            distilled["important_text"] = text[:250] + "..." + text[-250:]
        else:
            distilled["important_text"] = text
        return distilled

class PromptBuilder:
    SYSTEM_PROMPT = """You are ay-eye, a technical dev copilot. 
Analyze the screen context and suggest the next step. 
Be calm, precise, and minimal. Use noun-verb phrasing. 
Avoid theatricality. 
Return ONLY JSON:
{
  "intent": "guide|ask|act|ignore",
  "message": "Short actionable message",
  "actions": [{"type": "click|type", "target": "element name"}],
  "confidence": 0.0-1.0
}"""

    @staticmethod
    def build(distilled_context: Dict[str, Any], trigger_type: str) -> str:
        context_block = f"CONTEXT:\n{distilled_context}"
        task_block = f"TRIGGER: {trigger_type}. Action required?"
        return f"{PromptBuilder.SYSTEM_PROMPT}\n\n{context_block}\n\n{task_block}"

context_distiller = ContextDistiller()
prompt_builder = PromptBuilder()
