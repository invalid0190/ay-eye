import time
from core.engine.event_bus import bus
from core.engine.brain import brain
from core.state.manager import state_manager
from core.engine.llm_bridge import llm_bridge
from core.utils.logger import logger

# Mock LLM to return valid JSON
def mock_generate(prompt, retry=True):
    return {
        "intent": "guide",
        "message": "I see you are in Discord. Need help?",
        "actions": [],
        "confidence": 0.85
    }

llm_bridge.generate = mock_generate

# Subscribe to result
results = []
bus.subscribe("BRAIN_RESPONDED", lambda r: results.append(r))

# Setup State
state_manager.update(app="Discord", window="General Channel", ocr_text="Hello world")

# Simulate Trigger
logger.log_event("TEST_TRIGGER_START")
bus.publish("AI_TRIGGERED", {"type": "IDLE_TRIGGER", "confidence": 0.9})

# Wait for async (though this is sync in our test mock)
time.sleep(1)

if results:
    print(f"VERIFICATION SUCCESS: Brain responded with {results[0]['intent']}")
else:
    print("VERIFICATION FAILED: No brain response")
