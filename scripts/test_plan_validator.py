"""Smoke test for PlanValidator — run from project root."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.plan_validator import plan_validator
from core.config import sys_config

# Ensure planner mode is on
sys_config.config["planner_mode_enabled"] = True
sys_config.config["require_plan_for_multi_action"] = True
sys_config.config["require_plan_for_high_risk"] = True


def test(label, response, expect_valid):
    v = plan_validator.validate(response)
    status = "VALID" if v["valid"] else "INVALID"
    mark = "[OK]" if v["valid"] == expect_valid else "[MISMATCH]"
    print(f"  {mark:10s} {status:8s} | {label}")
    if v.get("reason"):
        print(f"                     -> {v['reason'][:120]}")
    if v.get("warnings"):
        for w in v["warnings"]:
            print(f"                     ** WARNING: {w[:100]}")
    return v


print("=== PlanValidator Tests ===\n")

# ------------------------------------------------------------------
# Group 1: Non-action intents (always valid, no plan needed)
# ------------------------------------------------------------------
print("[Group 1] Non-action intents")
test("guide intent",
     {"intent": "guide", "actions": [], "message": "Here's info"},
     expect_valid=True)
test("ask intent",
     {"intent": "ask", "actions": [], "message": "What do you mean?"},
     expect_valid=True)

# ------------------------------------------------------------------
# Group 2: Simple responses (1-2 actions, no plan needed)
# ------------------------------------------------------------------
print("\n[Group 2] Simple responses (no plan needed)")
test("single click",
     {"intent": "act", "actions": [{"type": "click", "x": 100, "y": 200}], "confidence": 0.9},
     expect_valid=True)
test("click + type (2 actions)",
     {"intent": "act", "actions": [
         {"type": "click", "x": 100, "y": 200},
         {"type": "type", "text": "hello"}
     ], "confidence": 0.9},
     expect_valid=True)

# ------------------------------------------------------------------
# Group 3: Multi-action WITHOUT plan -- now auto-synthesises a plan
# from the actions and passes (was: hard-rejected, which silently
# dropped the user's task whenever the LLM forgot the 'plan' field).
# High-risk actions are still hard-gated separately in Group 4.
# ------------------------------------------------------------------
print("\n[Group 3] Multi-action without plan (auto-synthesised)")

def test_with_plan_synthesis(label, response):
    """Run the validator and assert it passed AND that a plan was synthesised
    in place onto the response dict."""
    verdict = plan_validator.validate(response)
    ok = (
        verdict["valid"] is True
        and isinstance(response.get("plan"), list)
        and len(response["plan"]) >= 1
        and any("auto-synth" in w.lower() for w in verdict.get("warnings", []))
    )
    print(f"  {'[PASS]' if ok else '[FAIL]'} {label}: synthesised plan = {response.get('plan')}")
    if not ok:
        sys.exit(1)


test_with_plan_synthesis("3 clicks, no plan",
     {"intent": "act", "actions": [
         {"type": "click", "x": 1, "y": 1},
         {"type": "click_text", "text": "OK"},
         {"type": "type", "text": "hello"},
     ]})
test_with_plan_synthesis("5 actions, no plan",
     {"intent": "act", "actions": [
         {"type": "click", "x": 1, "y": 1},
         {"type": "type", "text": "hello"},
         {"type": "hotkey", "keys": ["enter"]},
         {"type": "click_text", "text": "Send"},
         {"type": "switch", "target": "discord"},
     ]})

# ------------------------------------------------------------------
# Group 4: High-risk action WITHOUT plan (should FAIL)
# ------------------------------------------------------------------
print("\n[Group 4] High-risk without plan (should fail)")
test("cmd without plan",
     {"intent": "act", "actions": [
         {"type": "cmd", "command": "mkdir test"},
     ]},
     expect_valid=False)
test("write_file without plan",
     {"intent": "act", "actions": [
         {"type": "write_file", "path": "x.py", "content": "print(1)"},
     ]},
     expect_valid=False)
test("blender_python without plan",
     {"intent": "act", "actions": [
         {"type": "blender_python", "script": "import bpy"},
     ]},
     expect_valid=False)
test("blender_create_scene without plan",
     {"intent": "act", "actions": [
         {"type": "blender_create_scene", "description": "container cafe"},
     ]},
     expect_valid=False)
test("blender_enhance_scene without plan",
     {"intent": "act", "actions": [
         {"type": "blender_enhance_scene", "description": "add professional MLO details"},
     ]},
     expect_valid=False)

# ------------------------------------------------------------------
# Group 5: Valid plans (should PASS)
# ------------------------------------------------------------------
print("\n[Group 5] Valid plans")
test("cmd with plan",
     {"intent": "act",
      "plan": ["Create a new project folder using mkdir"],
      "actions": [{"type": "cmd", "command": "mkdir test"}]},
     expect_valid=True)
test("multi-action with plan",
     {"intent": "act",
      "plan": [
          "Click the input field",
          "Type the message",
          "Press Enter to send",
      ],
      "actions": [
          {"type": "click", "x": 100, "y": 700},
          {"type": "type", "text": "hello"},
          {"type": "hotkey", "keys": ["enter"]},
      ]},
     expect_valid=True)
test("write_file with plan",
     {"intent": "act",
      "plan": ["Write a Python hello-world file to disk"],
      "actions": [{"type": "write_file", "path": "hello.py", "content": "print('hi')"}]},
     expect_valid=True)
test("blender_create_scene with plan",
     {"intent": "act",
      "plan": ["Create a Blender reference scene from the image"],
      "actions": [{"type": "blender_create_scene", "description": "container cafe"}]},
     expect_valid=True)
test("blender_enhance_scene with plan",
     {"intent": "act",
      "plan": ["Enhance the Blender MLO scene with professional details"],
      "actions": [{"type": "blender_enhance_scene", "description": "make this MLO professional"}]},
     expect_valid=True)

# ------------------------------------------------------------------
# Group 6: Too many actions for plan size (should FAIL)
# ------------------------------------------------------------------
print("\n[Group 6] Too many actions vs plan steps")
test("1-step plan, 10 actions",
     {"intent": "act",
      "plan": ["Do everything"],
      "actions": [{"type": "click", "x": i, "y": i} for i in range(10)]},
     expect_valid=False)

# ------------------------------------------------------------------
# Group 7: Contradictory plan + actions (should FAIL)
# ------------------------------------------------------------------
print("\n[Group 7] Contradictory plan + actions")
test("plan says 'do not click' but has click",
     {"intent": "act",
      "plan": ["Do not click any buttons", "Type the text instead"],
      "actions": [
          {"type": "click", "x": 100, "y": 200},
          {"type": "type", "text": "hi"},
      ]},
     expect_valid=False)
test("plan says 'don't type' but has type",
     {"intent": "act",
      "plan": ["Don't type anything", "Just scroll down"],
      "actions": [
          {"type": "type", "text": "oops"},
          {"type": "scroll", "amount": -3},
      ]},
     expect_valid=False)

# ------------------------------------------------------------------
# Group 8: High-risk not mentioned in plan (warning only)
# ------------------------------------------------------------------
print("\n[Group 8] High-risk not mentioned in plan (should pass with warning)")
test("cmd present but plan doesn't mention it",
     {"intent": "act",
      "plan": ["Open the project folder", "Check the files"],
      "actions": [
          {"type": "cmd", "command": "ls"},
          {"type": "list_dir", "path": "."},
      ]},
     expect_valid=True)  # Warning but not failure

# ------------------------------------------------------------------
# Group 9: Malformed plans
# ------------------------------------------------------------------
print("\n[Group 9] Malformed plans")
test("plan is a string (not list)",
     {"intent": "act",
      "plan": "just do stuff",
      "actions": [{"type": "cmd", "command": "echo hi"}]},
     expect_valid=False)
test("plan is empty list",
     {"intent": "act",
      "plan": [],
      "actions": [{"type": "cmd", "command": "echo hi"}]},
     expect_valid=False)

# ------------------------------------------------------------------
# Group 10: Planner mode disabled (always pass)
# ------------------------------------------------------------------
print("\n[Group 10] Planner mode disabled")
sys_config.config["planner_mode_enabled"] = False
test("dangerous response, planner off",
     {"intent": "act", "actions": [
         {"type": "cmd", "command": "rm -rf /"},
         {"type": "write_file", "path": "/etc/passwd", "content": "pwned"},
     ]},
     expect_valid=True)
sys_config.config["planner_mode_enabled"] = True

# ------------------------------------------------------------------
# Group 11: Trivial actions don't count (scroll/read_file)
# ------------------------------------------------------------------
print("\n[Group 11] Trivial actions are excluded from plan requirement")
test("5 scrolls + 2 read_files, no plan",
     {"intent": "act", "actions": [
         {"type": "scroll", "amount": -3},
         {"type": "scroll", "amount": -3},
         {"type": "scroll", "amount": -3},
         {"type": "read_file", "path": "a.py"},
         {"type": "read_file", "path": "b.py"},
         {"type": "scroll", "amount": -3},
         {"type": "scroll", "amount": -3},
     ]},
     expect_valid=True)

print("\n=== All tests executed ===")
