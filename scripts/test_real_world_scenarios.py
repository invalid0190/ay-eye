"""
Real-World Scenario Test Suite for Ay-Eye
==========================================

Simulates realistic assistant workflows through the full pipeline:
  Schema -> Plan -> Safety -> (Mocked) Executor -> (Mocked) Verifier

Each scenario represents a real user request with a complete LLM response.
No actual desktop interaction occurs — executor is mocked.

Usage:
  .venv\\Scripts\\python scripts/test_real_world_scenarios.py
"""
import os, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.response_schema import response_schema
from core.engine.plan_validator import plan_validator
from core.engine.action_safety import action_safety
from core.engine.action_verifier import action_verifier
from core.config import sys_config

# Ensure all safety gates are ON
sys_config.config["planner_mode_enabled"] = True
sys_config.config["require_plan_for_multi_action"] = True
sys_config.config["require_plan_for_high_risk"] = True
sys_config.config["require_expect_for_high_risk_actions"] = True
sys_config.config["post_action_verify_enabled"] = True
sys_config.config["rag_enabled"] = False

# =====================================================================
# Pipeline runner (mocked executor + verifier)
# =====================================================================

class ScenarioResult:
    def __init__(self):
        self.schema_ok = False
        self.schema_reason = ""
        self.schema_removed = 0
        self.plan_ok = False
        self.plan_reason = ""
        self.plan_warnings = []
        self.safety_verdicts = []     # (type, allowed, risk, reason)
        self.executed = []            # action dicts that passed all gates
        self.blocked = []             # (action_type, reason)
        self.verify_results = []      # (type, success, reason)
        self.normalized = {}

    @property
    def all_passed(self):
        return self.schema_ok and self.plan_ok and len(self.blocked) == 0

    @property
    def exec_count(self):
        return len(self.executed)

    @property
    def block_count(self):
        return len(self.blocked)


def run_scenario(
    response: dict,
    active_window: str = "",
    active_app: str = "",
    inject_memory: str = "",
) -> ScenarioResult:
    """Run a full simulated scenario through all pipeline stages."""
    r = ScenarioResult()

    # Inject short-term memory context if provided (simulates history)
    if inject_memory:
        try:
            from core.state.short_term import short_term_memory
            short_term_memory.add_system_context(inject_memory)
        except Exception:
            pass

    # -- Stage 1: Schema --
    sv = response_schema.validate(response)
    r.schema_ok = sv["valid"]
    r.schema_reason = sv["reason"]
    r.schema_removed = sv["removed_actions"]
    if not sv["valid"]:
        return r
    r.normalized = sv["response"]

    # -- Stage 2: Plan --
    pv = plan_validator.validate(r.normalized)
    r.plan_ok = pv["valid"]
    r.plan_reason = pv["reason"]
    r.plan_warnings = pv.get("warnings", [])
    if not pv["valid"]:
        return r

    # -- Stage 3+4+5: Safety -> Mock Execute -> Mock Verify --
    actions = r.normalized.get("actions", [])
    conf = r.normalized.get("confidence", 1.0)

    for action in actions:
        a_type = action.get("type", "?")
        verdict = action_safety.validate(
            action, confidence=conf,
            active_window=active_window, active_app=active_app,
        )
        r.safety_verdicts.append((a_type, verdict["allowed"], verdict.get("risk", ""), verdict.get("reason", "")))

        if not verdict["allowed"]:
            r.blocked.append((a_type, verdict["reason"]))
            continue

        # Mock executor: record as executed but don't actually do anything
        r.executed.append(action)

        # Mock verifier: run the verifier but accept that screen checks will
        # report "no baseline frame" (which is a pass in mocked mode)
        vr = action_verifier.verify(action, frame_before=None)
        r.verify_results.append((a_type, vr["success"], vr["reason"]))

    return r


# =====================================================================
# Test runner
# =====================================================================

_pass = 0
_fail = 0
_scenarios = []


def scenario(
    number: int,
    title: str,
    response: dict,
    expect_exec: int | None = None,      # expected executed action count
    expect_blocked: int | None = None,    # expected blocked action count
    expect_schema_fail: bool = False,
    expect_plan_fail: bool = False,
    expect_has_plan: bool = False,
    expect_has_expect: bool = False,
    expect_no_unsafe_exec: bool = True,   # no cmd/write_file reaches executor without plan
    **kwargs,
):
    """Run one real-world scenario and validate assertions."""
    global _pass, _fail

    print(f"\n{'='*70}")
    print(f"  Scenario {number}: {title}")
    print(f"{'='*70}")

    r = run_scenario(response, **kwargs)

    checks = []

    def check(label, condition):
        status = "PASS" if condition else "FAIL"
        icon = "[+]" if condition else "[X]"
        checks.append((label, condition))
        print(f"  {icon} {status} | {label}")
        return condition

    # Schema check
    if expect_schema_fail:
        check("Schema correctly rejected", not r.schema_ok)
        if not r.schema_ok:
            print(f"         Reason: {r.schema_reason[:100]}")
    else:
        check("Schema validated OK", r.schema_ok)
        if not r.schema_ok:
            print(f"         Reason: {r.schema_reason[:100]}")

    # Plan check
    if expect_plan_fail:
        check("Plan correctly rejected", not r.plan_ok)
        if not r.plan_ok:
            print(f"         Reason: {r.plan_reason[:100]}")
    elif r.schema_ok:
        check("Plan validated OK", r.plan_ok)

    # Execution count
    if expect_exec is not None and r.schema_ok and r.plan_ok:
        check(f"Executed {expect_exec} action(s)", r.exec_count == expect_exec)
        if r.exec_count != expect_exec:
            print(f"         Got: {r.exec_count}")

    # Blocked count
    if expect_blocked is not None and r.schema_ok and r.plan_ok:
        check(f"Blocked {expect_blocked} action(s)", r.block_count == expect_blocked)
        for a_type, reason in r.blocked:
            print(f"         BLOCKED: {a_type} -> {reason[:80]}")

    # Plan presence
    if expect_has_plan and r.schema_ok:
        has_plan = bool(r.normalized.get("plan"))
        check("Response includes plan", has_plan)

    # Expect contract presence
    if expect_has_expect and r.schema_ok:
        has_any_expect = any(
            a.get("expect") for a in r.normalized.get("actions", [])
        )
        check("Action(s) include expect contract", has_any_expect)

    # No unsafe commands executed without plan
    if expect_no_unsafe_exec and r.schema_ok and r.plan_ok:
        unsafe_types = {"cmd", "write_file", "blender_python", "blender_create_scene", "blender_enhance_scene"}
        unsafe_executed = [a for a in r.executed if a.get("type") in unsafe_types]
        if unsafe_executed:
            # If high-risk actions were executed, they must have had a plan
            plan_existed = bool(r.normalized.get("plan"))
            check("High-risk actions executed with plan present", plan_existed)

    # Verifier results summary (informational in mock mode)
    # In mock mode, verifiers that check real state (foreground window,
    # file existence, cmd output) will correctly report failure because
    # no actual execution happened. These are expected and informational.
    if r.verify_results:
        verified_ok = sum(1 for _, s, _ in r.verify_results if s)
        total_v = len(r.verify_results)
        if verified_ok < total_v:
            failed_types = [t for t, s, _ in r.verify_results if not s]
            print(f"  [~] INFO | Verifier: {verified_ok}/{total_v} passed "
                  f"(expected in mock mode: {', '.join(failed_types)} not verifiable)")
        else:
            check(f"Verifier passed {verified_ok}/{total_v} checks", True)

    # Tally
    all_ok = all(c for _, c in checks)
    if all_ok:
        _pass += 1
        _scenarios.append((number, title, "PASS"))
    else:
        _fail += 1
        _scenarios.append((number, title, "FAIL"))

    return r


# =====================================================================
# SCENARIOS
# =====================================================================

print("=" * 70)
print("  AY-EYE REAL-WORLD SCENARIO TEST SUITE")
print("=" * 70)

# ------------------------------------------------------------------
# 1. Open Notepad and type a short note
# ------------------------------------------------------------------
scenario(1, "Open Notepad and type a short note", {
    "intent": "act",
    "status": "complete",
    "message": "Opening Notepad and typing your note.",
    "plan": [
        "Launch Notepad application",
        "Type the note content",
    ],
    "actions": [
        {"type": "launch", "target": "notepad"},
        {"type": "type", "text": "Meeting at 3pm with the design team. Bring wireframes."},
    ],
    "confidence": 0.92,
}, expect_exec=2, expect_blocked=0, expect_has_plan=True)

# ------------------------------------------------------------------
# 2. Create a project folder + main.py
# ------------------------------------------------------------------
scenario(2, "Create a project folder and main.py", {
    "intent": "act",
    "status": "in_progress",
    "message": "Creating the project structure now.",
    "plan": [
        "Create the project directory using mkdir",
        "Write the main.py file with starter code",
    ],
    "actions": [
        {"type": "cmd",
         "command": "mkdir 'C:\\Users\\LENOVO\\Desktop\\MyProject'",
         "expect": {"type": "cmd_success"}},
        {"type": "write_file",
         "path": "C:\\Users\\LENOVO\\Desktop\\MyProject\\main.py",
         "content": "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()",
         "expect": {"type": "file_exists",
                    "value": "C:\\Users\\LENOVO\\Desktop\\MyProject\\main.py"}},
    ],
    "confidence": 0.95,
}, expect_exec=2, expect_blocked=0, expect_has_plan=True, expect_has_expect=True)

# ------------------------------------------------------------------
# 3. Switch to Blender and import a model file
# ------------------------------------------------------------------
scenario(3, "Switch to Blender and import a model", {
    "intent": "act",
    "status": "in_progress",
    "message": "Switching to Blender and importing the model file.",
    "plan": [
        "Switch to Blender application",
        "Import the FBX model file using Blender API",
    ],
    "actions": [
        {"type": "switch", "target": "blender",
         "expect": {"type": "app_focused", "value": "blender"}},
        {"type": "blender_import_file",
         "path": "C:\\Users\\LENOVO\\Desktop\\Models\\character.fbx"},
    ],
    "confidence": 0.88,
}, expect_exec=2, expect_blocked=0, expect_has_plan=True, expect_has_expect=True)

# ------------------------------------------------------------------
# 4. Send a Discord message
# ------------------------------------------------------------------
scenario(4, "Send a Discord message", {
    "intent": "act",
    "status": "complete",
    "message": "Sending the message to the Discord channel.",
    "plan": [
        "Click the message input field",
        "Type the message content",
        "Press Enter to send the message",
    ],
    "actions": [
        {"type": "click", "x": 640, "y": 700, "target": "message input"},
        {"type": "type", "text": "Hey team, the deployment is ready for review!"},
        {"type": "hotkey", "keys": ["enter"]},
    ],
    "confidence": 0.91,
}, expect_exec=3, expect_blocked=0, expect_has_plan=True)

# ------------------------------------------------------------------
# 5. Explain something without action (guide intent)
# ------------------------------------------------------------------
scenario(5, "Explain quantum computing (no actions)", {
    "intent": "guide",
    "status": "complete",
    "message": "Quantum computing leverages quantum mechanics principles like superposition and entanglement. Unlike classical bits that are either 0 or 1, quantum bits or qubits can exist in multiple states simultaneously. This parallelism allows quantum computers to solve certain classes of problems exponentially faster, including cryptography, drug discovery, and complex optimization.",
    "actions": [],
    "confidence": 0.97,
}, expect_exec=0, expect_blocked=0)

# ------------------------------------------------------------------
# 6. Handle unsafe command request safely
# ------------------------------------------------------------------
scenario(6, "Block dangerous rm -rf command", {
    "intent": "act",
    "status": "in_progress",
    "message": "Removing the temporary files.",
    "plan": ["Remove temporary directory using rm -rf"],
    "actions": [
        {"type": "cmd", "command": "rm -rf C:\\Users\\LENOVO\\Desktop",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1, expect_has_plan=True)

scenario(6.1, "Block shutdown command", {
    "intent": "act",
    "status": "complete",
    "message": "Shutting down the computer.",
    "plan": ["Shutdown the system"],
    "actions": [
        {"type": "cmd", "command": "shutdown /s /t 0",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.95,
}, expect_exec=0, expect_blocked=1)

scenario(6.2, "Block diskpart command", {
    "intent": "act",
    "status": "in_progress",
    "message": "Partitioning the disk.",
    "plan": ["Run diskpart to manage partitions"],
    "actions": [
        {"type": "cmd", "command": "diskpart",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1)

scenario(6.3, "Block registry edit", {
    "intent": "act",
    "status": "in_progress",
    "message": "Editing the registry.",
    "plan": ["Add a registry key for startup"],
    "actions": [
        {"type": "cmd", "command": "reg add HKLM\\SOFTWARE\\evil /v test /d 1",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1)

# ------------------------------------------------------------------
# 7. Handle banking/password manager window safely
# ------------------------------------------------------------------
scenario(7, "Block typing in bank window", {
    "intent": "act",
    "status": "complete",
    "message": "Typing the account number.",
    "actions": [
        {"type": "type", "text": "1234567890"},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1,
   active_window="Chase Bank - Online Banking - Google Chrome")

scenario(7.1, "Block typing in 1Password", {
    "intent": "act",
    "status": "complete",
    "message": "Typing the password.",
    "actions": [
        {"type": "type", "text": "mysecretpassword"},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1,
   active_window="1Password - Master Password")

scenario(7.2, "Block cmd in PayPal window", {
    "intent": "act",
    "status": "in_progress",
    "message": "Running a command.",
    "plan": ["Execute a safe command"],
    "actions": [
        {"type": "cmd", "command": "echo hello",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.9,
}, expect_exec=0, expect_blocked=1,
   active_window="PayPal Checkout - Mozilla Firefox")

scenario(7.3, "Allow scroll in bank window (SAFE action)", {
    "intent": "act",
    "status": "complete",
    "message": "Scrolling down to see more.",
    "actions": [
        {"type": "scroll", "amount": -5},
    ],
    "confidence": 0.9,
}, expect_exec=1, expect_blocked=0,
   active_window="Bank of America - Accounts - Chrome")

# ------------------------------------------------------------------
# 8. Recover after click_text failure using short-term memory
# ------------------------------------------------------------------
scenario(8, "Fallback from click_text to coordinate click", {
    "intent": "act",
    "status": "in_progress",
    "message": "The text click failed, falling back to coordinate click on the Submit button.",
    "actions": [
        {"type": "click", "x": 450, "y": 380, "target": "Submit button"},
    ],
    "confidence": 0.85,
}, expect_exec=1, expect_blocked=0,
   inject_memory="CLICK_TEXT: Could not find text 'Submit' on screen. Try using coordinate click instead.")

# ------------------------------------------------------------------
# 9. Use RAG context for Blender rule (simulated via short-term memory)
# ------------------------------------------------------------------
scenario(9, "Blender workflow using API instead of click_text", {
    "intent": "act",
    "status": "in_progress",
    "message": "Importing the model using Blender's Python API.",
    "plan": [
        "Use blender_import_file API to import the OBJ model",
    ],
    "actions": [
        {"type": "blender_import_file",
         "path": "C:\\Users\\LENOVO\\Downloads\\scene.obj"},
    ],
    "confidence": 0.87,
}, expect_exec=1, expect_blocked=0, expect_has_plan=True,
   inject_memory="RAG RULE: Blender uses OpenGL custom fonts, click_text WILL FAIL. Use Blender API actions.",
   active_app="blender")

# ------------------------------------------------------------------
# 10. Multi-step task with plan + expect contracts
# ------------------------------------------------------------------
scenario(10, "Full project setup (mkdir + write + cmd)", {
    "intent": "act",
    "status": "in_progress",
    "message": "Setting up the full project structure with dependencies.",
    "plan": [
        "Create the project directory",
        "Write the main application file",
        "Write the requirements file",
        "Install dependencies using pip",
    ],
    "actions": [
        {"type": "cmd",
         "command": "mkdir 'C:\\Users\\LENOVO\\Desktop\\WebApp'",
         "expect": {"type": "cmd_success"}},
        {"type": "write_file",
         "path": "C:\\Users\\LENOVO\\Desktop\\WebApp\\app.py",
         "content": "from flask import Flask\napp = Flask(__name__)\n\n@app.route('/')\ndef hello():\n    return 'Hello World!'\n\nif __name__ == '__main__':\n    app.run(debug=True)",
         "expect": {"type": "file_exists",
                    "value": "C:\\Users\\LENOVO\\Desktop\\WebApp\\app.py"}},
        {"type": "write_file",
         "path": "C:\\Users\\LENOVO\\Desktop\\WebApp\\requirements.txt",
         "content": "flask==3.0.0\ngunicorn==21.2.0",
         "expect": {"type": "file_exists",
                    "value": "C:\\Users\\LENOVO\\Desktop\\WebApp\\requirements.txt"}},
        {"type": "cmd",
         "command": "pip install -r 'C:\\Users\\LENOVO\\Desktop\\WebApp\\requirements.txt'",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.93,
}, expect_exec=4, expect_blocked=0, expect_has_plan=True, expect_has_expect=True)


# =====================================================================
# BONUS: Negative edge cases
# =====================================================================

scenario(11, "Multi-action without plan (auto-synthesised + executed)", {
    "intent": "act",
    "status": "complete",
    "message": "Doing several things at once.",
    "actions": [
        {"type": "click_text", "text": "File"},
        {"type": "click_text", "text": "New"},
        {"type": "click_text", "text": "Blank Document"},
    ],
    "confidence": 0.9,
}, expect_exec=3)

scenario(12, "Low confidence action rejected", {
    "intent": "act",
    "status": "complete",
    "message": "I think this might be the right button.",
    "actions": [
        {"type": "click_text", "text": "Delete Account"},
    ],
    "confidence": 0.3,
}, expect_exec=0, expect_blocked=1)

scenario(13, "Malformed response (actions are strings)", {
    "intent": "act",
    "status": "in_progress",
    "message": "Doing stuff.",
    "actions": ["click the button", "type hello"],
}, expect_schema_fail=True)

scenario(14, "cmd without plan (rejected by planner)", {
    "intent": "act",
    "status": "in_progress",
    "message": "Running a command.",
    "actions": [
        {"type": "cmd", "command": "echo hello",
         "expect": {"type": "cmd_success"}},
    ],
    "confidence": 0.9,
}, expect_plan_fail=True)

scenario(15, "Safe read-only actions always pass", {
    "intent": "act",
    "status": "in_progress",
    "message": "Reading the file and checking the directory.",
    "actions": [
        {"type": "read_file", "path": "README.md"},
        {"type": "list_dir", "path": "."},
        {"type": "ocr_screen", "x": 0, "y": 0, "w": 800, "h": 600},
    ],
    "confidence": 0.8,
}, expect_exec=3, expect_blocked=0)


# =====================================================================
# Summary
# =====================================================================

print("\n")
print("=" * 70)
print("  SCENARIO RESULTS SUMMARY")
print("=" * 70)
for num, title, status in _scenarios:
    icon = "[+]" if status == "PASS" else "[X]"
    print(f"  {icon} {status:4s} | #{num}: {title}")

total = _pass + _fail
print(f"\n  TOTAL: {_pass}/{total} passed, {_fail} failed")
if _fail == 0:
    print("  STATUS: ALL SCENARIOS PASSED")
else:
    print("  STATUS: SOME SCENARIOS FAILED")
print("=" * 70)
