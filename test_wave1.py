from core.utils.json_parser import json_parser
from core.engine.context_builder import ContextDistiller
from core.state.models import SystemState

# Test JSON Healing
raw = 'Model says: { "intent": "guide", "message": "Hello", "actions": [], "confidence": 0.8 }'
healed = json_parser.extract_and_heal(raw)
print(f"Healed JSON: {healed}")

# Test Distillation
s = SystemState(ocr_text='A'*1000)
distilled = ContextDistiller.distill(s)
print(f"Distilled Length: {len(distilled['important_text'])}")
