import time
import threading
from core.engine.event_bus import bus
from core.state.manager import state_manager
from core.state.models import UIElement
from core.engine.action_orchestrator import action_orchestrator
from core.utils.logger import logger

# 1. Setup Mock State with a 'Submit' button
mock_button = UIElement(name="Submit", role="Button", rect=[100, 100, 50, 20])
state_manager.update(app="TestApp", window="Main", ui_elements=[mock_button])

# 2. Subscribe to feedback
events = []
bus.subscribe("ACTION_COMPLETED", lambda a: events.append("COMPLETED"))
bus.subscribe("ACTION_ABORTED", lambda a: events.append("ABORTED"))

# 3. Simulate Brain Request
action_req = {
    "intent": "act",
    "actions": [{"type": "click", "target": "Submit"}],
    "confidence": 0.9
}

print("Simulating Action Request...")
bus.publish("ACTION_REQUESTED", action_req)

# Wait for thread to process
time.sleep(2)

if "COMPLETED" in events:
    print("VERIFICATION SUCCESS: Action executed successfully.")
else:
    print(f"VERIFICATION FAILED: Events: {events}")
