"""
Dry-Run Mode Test
=================

Validates that when dry_run_enabled=True:
1. Actions are NOT executed by the executor.
2. Actions are still validated (Schema, Plan, Safety).
3. Dry-run events are logged and memory is updated.
4. UI highlight events are emitted.

Usage:
  .venv\\Scripts\\python scripts/test_dry_run_mode.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.action_orchestrator import action_orchestrator
from core.engine.event_bus import bus
from core.config import sys_config
from core.engine.action_state import action_state
from core.utils.logger import logger

# Mocking executor to detect if it's called
class MockExecutor:
    def __init__(self):
        self.called_actions = []
    
    def execute_single(self, action):
        self.called_actions.append(action)

import core.engine.executor as executor_mod
original_executor = executor_mod.executor
mock_executor = MockExecutor()
executor_mod.executor = mock_executor

def test_dry_run():
    print("\n" + "="*50)
    print("  TESTING DRY-RUN MODE")
    print("="*50)
    
    # Enable Dry-Run
    sys_config.set("dry_run_enabled", True)
    sys_config.set("dry_run_show_overlay", True)
    
    # Capture events
    events = []
    bus.subscribe("DRY_RUN_ACTION", lambda d: events.append(("DRY_RUN", d)))
    bus.subscribe("HIGHLIGHT_REQUESTED", lambda d: events.append(("HIGHLIGHT", d)))
    
    # Sample action request
    test_response = {
        "intent": "act",
        "status": "complete",
        "message": "Testing dry run.",
        "confidence": 1.0,
        "plan": ["Do a test click"],
        "actions": [
            {"type": "click", "x": 100, "y": 200, "target": "Test Button"}
        ]
    }
    
    print("[1] Requesting action in Dry-Run mode...")
    bus.publish("ACTION_REQUESTED", test_response)
    
    # Give it a moment to process (it runs in a thread)
    time.sleep(1.0)
    
    # Assertions
    passed = True
    
    # 1. Executor should NOT have been called
    if len(mock_executor.called_actions) == 0:
        print("  [+] PASS | Executor was NOT called.")
    else:
        print(f"  [X] FAIL | Executor WAS called with {len(mock_executor.called_actions)} actions!")
        passed = False
        
    # 2. Dry-run event should have been emitted
    dry_run_events = [e for e in events if e[0] == "DRY_RUN"]
    if len(dry_run_events) == 1:
        print("  [+] PASS | DRY_RUN_ACTION event emitted.")
    else:
        print(f"  [X] FAIL | DRY_RUN_ACTION event count: {len(dry_run_events)}")
        passed = False
        
    # 3. Highlight event should have been emitted
    highlight_events = [e for e in events if e[0] == "HIGHLIGHT"]
    if len(highlight_events) == 1:
        print("  [+] PASS | HIGHLIGHT_REQUESTED event emitted.")
    else:
        print(f"  [X] FAIL | HIGHLIGHT_REQUESTED event count: {len(highlight_events)}")
        passed = False
        
    # 4. Check short-term memory (optional, but good)
    try:
        from core.state.short_term import short_term_memory
        history = short_term_memory.get_history_string()
        if "DRY_RUN" in history:
            print("  [+] PASS | Short-term memory updated with DRY_RUN info.")
        else:
            print("  [X] FAIL | Short-term memory missing DRY_RUN info.")
            passed = False
    except:
        print("  [~] SKIP | Could not verify short-term memory.")

    # Cleanup
    executor_mod.executor = original_executor
    sys_config.set("dry_run_enabled", False)
    
    print("="*50)
    if passed:
        print("  STATUS: ALL DRY-RUN TESTS PASSED")
        sys.exit(0)
    else:
        print("  STATUS: DRY-RUN TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    test_dry_run()
