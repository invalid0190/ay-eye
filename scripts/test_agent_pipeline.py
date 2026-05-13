"""
End-to-End Agent Pipeline Test Harness
=======================================

Simulates full LLM responses passing through the COMPLETE safety pipeline
WITHOUT triggering real desktop interactions (mouse, keyboard, subprocess).

Pipeline stages tested:
  1. ResponseSchemaValidator   -- normalize/sanitize LLM output
  2. PlanValidator             -- require plan for multi-action/high-risk
  3. ActionSafetyValidator     -- block dangerous/sensitive actions
  4. (Executor MOCKED)         -- no real clicks/commands
  5. (Verifier MOCKED)         -- no real screen checks

Usage:
  .venv\\Scripts\\python scripts/test_agent_pipeline.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.response_schema import response_schema
from core.engine.plan_validator import plan_validator
from core.engine.action_safety import action_safety
from core.config import sys_config

# Ensure all gates are enabled
sys_config.config["planner_mode_enabled"] = True
sys_config.config["require_plan_for_multi_action"] = True
sys_config.config["require_plan_for_high_risk"] = True
sys_config.config["require_expect_for_high_risk_actions"] = True
sys_config.config["post_action_verify_enabled"] = True
sys_config.config["rag_enabled"] = False  # Don't need RAG for pipeline tests


# =====================================================================
# Pipeline runner
# =====================================================================

class PipelineResult:
    def __init__(self):
        self.schema_valid = False
        self.schema_reason = ""
        self.schema_removed = 0
        self.plan_valid = False
        self.plan_reason = ""
        self.plan_warnings = []
        self.safety_results = []      # list of (action_type, allowed, reason)
        self.executed_count = 0
        self.blocked_count = 0
        self.normalized_response = {}

    @property
    def fully_passed(self):
        return (
            self.schema_valid
            and self.plan_valid
            and self.blocked_count == 0
            and self.executed_count > 0
        )

    @property
    def summary_line(self):
        parts = []
        if not self.schema_valid:
            parts.append(f"SCHEMA_FAIL({self.schema_reason[:40]})")
        if not self.plan_valid:
            parts.append(f"PLAN_FAIL({self.plan_reason[:40]})")
        if self.blocked_count:
            parts.append(f"BLOCKED({self.blocked_count})")
        if self.schema_removed:
            parts.append(f"REMOVED({self.schema_removed})")
        if self.executed_count:
            parts.append(f"EXEC({self.executed_count})")
        return " | ".join(parts) if parts else "PASS"


def run_pipeline(
    response: dict,
    active_window: str = "",
    active_app: str = "",
    confidence_override: float | None = None,
) -> PipelineResult:
    """Run a simulated LLM response through all pipeline stages."""
    result = PipelineResult()

    # -- Stage 1: Schema Validation --
    sv = response_schema.validate(response)
    result.schema_valid = sv["valid"]
    result.schema_reason = sv["reason"]
    result.schema_removed = sv["removed_actions"]

    if not sv["valid"]:
        return result

    normalized = sv["response"]
    result.normalized_response = normalized

    # -- Stage 2: Plan Validation --
    pv = plan_validator.validate(normalized)
    result.plan_valid = pv["valid"]
    result.plan_reason = pv["reason"]
    result.plan_warnings = pv.get("warnings", [])

    if not pv["valid"]:
        return result

    # -- Stage 3: Action Safety (per action) --
    actions = normalized.get("actions", [])
    conf = confidence_override if confidence_override is not None else normalized.get("confidence", 1.0)

    for action in actions:
        a_type = action.get("type", "?")
        verdict = action_safety.validate(
            action,
            confidence=conf,
            active_window=active_window,
            active_app=active_app,
        )
        result.safety_results.append((a_type, verdict["allowed"], verdict.get("reason", "")))
        if verdict["allowed"]:
            # Mock execution -- don't actually run anything
            result.executed_count += 1
        else:
            result.blocked_count += 1

    return result


# =====================================================================
# Test runner
# =====================================================================

_pass_count = 0
_fail_count = 0


def test(label: str, response: dict, expect: str, **kwargs):
    """Run a pipeline test case.
    
    expect: "PASS" | "SCHEMA_FAIL" | "PLAN_FAIL" | "SAFETY_BLOCK" | "PARTIAL" | "GUIDE_PASS"
    """
    global _pass_count, _fail_count

    r = run_pipeline(response, **kwargs)

    # Determine actual outcome
    if not r.schema_valid:
        actual = "SCHEMA_FAIL"
    elif not r.plan_valid:
        actual = "PLAN_FAIL"
    elif r.blocked_count > 0 and r.executed_count == 0:
        actual = "SAFETY_BLOCK"
    elif r.blocked_count > 0 and r.executed_count > 0:
        actual = "PARTIAL"
    elif r.executed_count == 0 and len(response.get("actions", [])) == 0:
        actual = "GUIDE_PASS"
    elif r.executed_count > 0:
        actual = "PASS"
    else:
        actual = "UNKNOWN"

    matched = actual == expect
    mark = "PASS" if matched else "FAIL"
    icon = "[+]" if matched else "[X]"

    if matched:
        _pass_count += 1
    else:
        _fail_count += 1

    print(f"  {icon} {mark:4s} | {label}")
    print(f"         expected={expect:14s} actual={actual:14s} | {r.summary_line}")
    if r.plan_warnings:
        for w in r.plan_warnings:
            print(f"         ** WARNING: {w[:80]}")
    return r


# =====================================================================
# Test cases
# =====================================================================

print("=" * 70)
print("  AY-EYE END-TO-END AGENT PIPELINE TEST HARNESS")
print("=" * 70)
print()

# ------------------------------------------------------------------
# 1. Valid simple click
# ------------------------------------------------------------------
print("[1] Valid simple click")
test("single click_text passes all gates", {
    "intent": "act",
    "status": "complete",
    "message": "Clicking Submit now.",
    "actions": [{"type": "click_text", "text": "Submit"}],
    "confidence": 0.9,
}, expect="PASS")

# ------------------------------------------------------------------
# 2. Invalid malformed response
# ------------------------------------------------------------------
print("\n[2] Malformed responses")
test("None response", None, expect="SCHEMA_FAIL")
test("empty dict", {}, expect="GUIDE_PASS")
test("actions are strings", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": ["click here", "type there"],
}, expect="SCHEMA_FAIL")
test("missing required action fields", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd"}, {"type": "write_file"}],
}, expect="SCHEMA_FAIL")

# ------------------------------------------------------------------
# 3. Multi-action without plan -> PlanValidator now auto-synthesises a
#    plan from the actions (was: hard-rejected, which dropped the user's
#    intent silently and caused the "kehta hai but karta nahi" bug).
#    High-risk actions without a plan are still blocked -- see [4] below.
# ------------------------------------------------------------------
print("\n[3] Multi-action without plan (auto-synthesised, executes)")
test("3 actions, no plan", {
    "intent": "act", "status": "in_progress", "message": "Doing stuff.",
    "actions": [
        {"type": "click_text", "text": "File"},
        {"type": "click_text", "text": "Save As"},
        {"type": "type", "text": "document.txt"},
    ],
    "confidence": 0.9,
}, expect="PASS")

# ------------------------------------------------------------------
# 4. Dangerous cmd -> blocked by ActionSafety
# ------------------------------------------------------------------
print("\n[4] Dangerous commands blocked")
test("rm -rf blocked", {
    "intent": "act", "status": "in_progress", "message": "Cleaning up.",
    "plan": ["Remove temporary files"],
    "actions": [{"type": "cmd", "command": "rm -rf /",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK")

test("shutdown blocked", {
    "intent": "act", "status": "in_progress", "message": "Shutting down.",
    "plan": ["Shutdown the computer"],
    "actions": [{"type": "cmd", "command": "shutdown /s /t 0",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK")

test("format disk blocked", {
    "intent": "act", "status": "in_progress", "message": "Formatting.",
    "plan": ["Format the drive"],
    "actions": [{"type": "cmd", "command": "format C:",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK")

# ------------------------------------------------------------------
# 5. High-risk with plan + expect -> accepted
# ------------------------------------------------------------------
print("\n[5] High-risk with plan + expect (should pass)")
test("cmd with plan + expect", {
    "intent": "act", "status": "in_progress",
    "message": "Creating the project folder.",
    "plan": ["Run mkdir command to create a project directory"],
    "actions": [{"type": "cmd", "command": "mkdir MyProject",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.95,
}, expect="PASS")

test("write_file with plan + expect", {
    "intent": "act", "status": "in_progress",
    "message": "Writing the main file.",
    "plan": ["Create main.py with hello world content"],
    "actions": [{"type": "write_file", "path": "main.py",
                 "content": "print('hello')",
                 "expect": {"type": "file_exists", "value": "main.py"}}],
    "confidence": 0.9,
}, expect="PASS")

test("blender_python with plan", {
    "intent": "act", "status": "in_progress",
    "message": "Selecting all objects in Blender.",
    "plan": ["Run Blender Python script to select all objects"],
    "actions": [{"type": "blender_python",
                 "script": "import bpy; bpy.ops.object.select_all(action='SELECT')",
                 "expect": {"type": "none"}}],
    "confidence": 0.85,
}, expect="PASS")

# ------------------------------------------------------------------
# 6. Sensitive app blocks typing
# ------------------------------------------------------------------
print("\n[6] Sensitive window detection")
test("type in bank window", {
    "intent": "act", "status": "complete", "message": "Typing.",
    "actions": [{"type": "type", "text": "password123"}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK", active_window="Chase Bank - Chrome")

test("open_url in PayPal window", {
    "intent": "act", "status": "complete", "message": "Opening URL.",
    "actions": [{"type": "open_url", "url": "https://evil.com"}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK", active_window="PayPal Checkout - Chrome")

test("scroll in bank window (ALLOWED - safe action)", {
    "intent": "act", "status": "complete", "message": "Scrolling.",
    "actions": [{"type": "scroll", "amount": -3}],
    "confidence": 0.9,
}, expect="PASS", active_window="Bank of America - Chrome")

# ------------------------------------------------------------------
# 7. Invalid expect stripped (action still runs)
# ------------------------------------------------------------------
print("\n[7] Invalid expect contracts stripped")
test("invalid expect type stripped, cmd still runs", {
    "intent": "act", "status": "in_progress", "message": "Running.",
    "plan": ["Execute echo command"],
    "actions": [{"type": "cmd", "command": "echo hello",
                 "expect": {"type": "magic_prediction"}}],
    "confidence": 0.9,
}, expect="PASS")

test("file_exists expect missing value stripped", {
    "intent": "act", "status": "in_progress", "message": "Writing.",
    "plan": ["Write the output file"],
    "actions": [{"type": "write_file", "path": "x.py", "content": "x=1",
                 "expect": {"type": "file_exists"}}],  # Missing value
    "confidence": 0.9,
}, expect="PASS")

# ------------------------------------------------------------------
# 8. Mixed valid/invalid actions sanitized
# ------------------------------------------------------------------
print("\n[8] Mixed valid/invalid actions")
test("2 valid + 1 invalid -> 1 removed, 2 execute", {
    "intent": "act", "status": "in_progress", "message": "Multiple actions.",
    "actions": [
        {"type": "click_text", "text": "OK"},       # valid
        {"type": "cmd"},                              # invalid: no command
        {"type": "scroll", "amount": -3},             # valid
    ],
    "confidence": 0.9,
}, expect="PASS")

# ------------------------------------------------------------------
# 9. Low confidence -> blocked
# ------------------------------------------------------------------
print("\n[9] Low confidence gate")
test("click at confidence 0.2", {
    "intent": "act", "status": "complete", "message": "Maybe clicking.",
    "actions": [{"type": "click_text", "text": "Submit"}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK", confidence_override=0.2)

test("cmd at confidence 0.1", {
    "intent": "act", "status": "in_progress", "message": "Maybe running.",
    "plan": ["Run a safe command"],
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.9,
}, expect="SAFETY_BLOCK", confidence_override=0.1)

# ------------------------------------------------------------------
# 10. Guide response passes without actions
# ------------------------------------------------------------------
print("\n[10] Guide / non-action responses")
test("guide intent, no actions", {
    "intent": "guide", "status": "complete",
    "message": "Quantum computing uses qubits that can exist in superposition.",
    "actions": [], "confidence": 0.95,
}, expect="GUIDE_PASS")

test("ask intent, no actions", {
    "intent": "ask", "status": "complete",
    "message": "Which file would you like me to open?",
    "actions": [], "confidence": 0.9,
}, expect="GUIDE_PASS")

test("ignore intent", {
    "intent": "ignore", "status": "complete",
    "message": "", "actions": [], "confidence": 0.1,
}, expect="GUIDE_PASS")

# ------------------------------------------------------------------
# 11. Complex multi-step with plan (full pass)
# ------------------------------------------------------------------
print("\n[11] Complex multi-step with full plan")
test("Discord message flow with plan", {
    "intent": "act", "status": "in_progress",
    "message": "Sending the message to Discord now.",
    "plan": [
        "Click the message input field",
        "Type the message content",
        "Press Enter to send",
    ],
    "actions": [
        {"type": "click", "x": 640, "y": 700, "target": "message input"},
        {"type": "type", "text": "Hello from Ay-Eye!"},
        {"type": "hotkey", "keys": ["enter"]},
    ],
    "confidence": 0.92,
}, expect="PASS")

test("Project creation with cmd + write_file", {
    "intent": "act", "status": "in_progress",
    "message": "Creating the project structure.",
    "plan": [
        "Create the project directory using mkdir",
        "Write the initial main.py file",
    ],
    "actions": [
        {"type": "cmd",
         "command": "mkdir 'C:\\Users\\LENOVO\\Desktop\\TestProject'",
         "expect": {"type": "cmd_success"}},
        {"type": "write_file",
         "path": "C:\\Users\\LENOVO\\Desktop\\TestProject\\main.py",
         "content": "print('hello world')",
         "expect": {"type": "file_exists",
                    "value": "C:\\Users\\LENOVO\\Desktop\\TestProject\\main.py"}},
    ],
    "confidence": 0.95,
}, expect="PASS")

# ------------------------------------------------------------------
# 12. Edge cases
# ------------------------------------------------------------------
print("\n[12] Edge cases")
test("plan says 'do not click' but has click -> contradiction", {
    "intent": "act", "status": "in_progress", "message": "Careful action.",
    "plan": ["Do not click any buttons", "Just read the screen"],
    "actions": [
        {"type": "click", "x": 100, "y": 200, "target": "button"},
        {"type": "read_file", "path": "x.py"},
    ],
    "confidence": 0.9,
}, expect="PLAN_FAIL")

test("too many actions for plan size", {
    "intent": "act", "status": "in_progress", "message": "Doing a lot.",
    "plan": ["Do one thing"],
    "actions": [{"type": "click", "x": i, "y": i, "target": f"t{i}"} for i in range(10)],
    "confidence": 0.9,
}, expect="PLAN_FAIL")


# =====================================================================
# Summary
# =====================================================================

print()
print("=" * 70)
total = _pass_count + _fail_count
print(f"  RESULTS: {_pass_count}/{total} passed, {_fail_count} failed")
if _fail_count == 0:
    print("  STATUS:  ALL TESTS PASSED")
else:
    print("  STATUS:  SOME TESTS FAILED")
print("=" * 70)
