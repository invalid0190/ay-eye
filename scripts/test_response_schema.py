"""Smoke test for ResponseSchemaValidator -- run from project root."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.response_schema import response_schema


def test(label, raw, expect_valid=True, show_resp=False):
    r = response_schema.validate(raw)
    status = "VALID" if r["valid"] else "INVALID"
    mark = "[OK]" if r["valid"] == expect_valid else "[MISMATCH]"
    removed = r.get("removed_actions", 0)
    extra = f" (removed {removed} actions)" if removed else ""
    print(f"  {mark:10s} {status:8s} | {label}{extra}")
    if r.get("reason"):
        print(f"                     -> {r['reason'][:120]}")
    if show_resp:
        resp = r.get("response", {})
        print(f"                     intent={resp.get('intent')} status={resp.get('status')} "
              f"conf={resp.get('confidence')} actions={len(resp.get('actions', []))}")
    return r


print("=== ResponseSchemaValidator Tests ===\n")

# ------------------------------------------------------------------
# Group 1: Completely valid responses
# ------------------------------------------------------------------
print("[Group 1] Valid responses")
test("perfect guide response", {
    "intent": "guide", "status": "complete",
    "message": "Here is the info you asked for.",
    "actions": [], "confidence": 0.95,
})

test("perfect act response with actions", {
    "intent": "act", "status": "in_progress",
    "message": "Clicking the button now.",
    "actions": [{"type": "click", "x": 100, "y": 200}],
    "confidence": 0.9,
})

test("act with plan + expect", {
    "intent": "act", "status": "in_progress",
    "message": "Creating the file.",
    "plan": ["Create main.py"],
    "actions": [
        {"type": "write_file", "path": "main.py", "content": "print(1)",
         "expect": {"type": "file_exists", "value": "main.py"}}
    ],
    "confidence": 0.85,
})

# ------------------------------------------------------------------
# Group 2: Missing / malformed fields (should normalize)
# ------------------------------------------------------------------
print("\n[Group 2] Missing/malformed fields (normalized)")

test("missing actions -> []", {
    "intent": "guide", "status": "complete", "message": "hi",
}, show_resp=True)

test("missing confidence -> 0.0", {
    "intent": "act", "status": "complete", "message": "hi", "actions": [],
}, show_resp=True)

test("confidence out of range -> clamped", {
    "intent": "act", "status": "complete", "message": "hi",
    "actions": [], "confidence": 5.0,
}, show_resp=True)

test("unknown intent -> ignore", {
    "intent": "banana", "status": "complete", "message": "hi", "actions": [],
}, show_resp=True)

test("unknown status -> failed", {
    "intent": "act", "status": "banana", "message": "hi", "actions": [],
}, show_resp=True)

test("multiline message -> single line", {
    "intent": "guide", "status": "complete",
    "message": "Line 1\nLine 2\n\nLine 3",
    "actions": [],
}, show_resp=True)

test("missing intent + status", {
    "message": "something", "actions": [],
}, show_resp=True)

# ------------------------------------------------------------------
# Group 3: Unknown top-level keys (stripped)
# ------------------------------------------------------------------
print("\n[Group 3] Unknown top-level keys stripped")
r = test("extra keys removed", {
    "intent": "guide", "status": "complete", "message": "hi",
    "actions": [], "confidence": 0.5,
    "evil_payload": "DROP TABLE", "nested_bomb": {"x": 1},
})
resp = r["response"]
assert "evil_payload" not in resp, "evil_payload should be stripped"
assert "nested_bomb" not in resp, "nested_bomb should be stripped"
print("                     (verified: extra keys gone)")

# ------------------------------------------------------------------
# Group 4: Invalid actions removed
# ------------------------------------------------------------------
print("\n[Group 4] Invalid actions removed")

test("action not a dict", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": ["click here", 42, None],
}, expect_valid=False)

test("action with invalid type", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "hack_system"}],
}, expect_valid=False)

test("click missing x/y AND target", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "click"}],
}, expect_valid=False)

test("click with target only (valid)", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "click", "target": "Submit Button"}],
    "confidence": 0.8,
})

test("cmd missing command field", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd"}],
}, expect_valid=False)

test("write_file missing content", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "write_file", "path": "x.py"}],
}, expect_valid=False)

test("click_text missing text", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "click_text"}],
}, expect_valid=False)

test("mixed valid + invalid (partial removal)", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [
        {"type": "click", "x": 1, "y": 1},    # valid
        {"type": "cmd"},                         # invalid - no command
        {"type": "scroll", "amount": -3},        # valid
    ],
    "confidence": 0.9,
})

# ------------------------------------------------------------------
# Group 5: Expect contract validation inside actions
# ------------------------------------------------------------------
print("\n[Group 5] Expect contract validation")

test("valid expect", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "cmd_success"}}],
    "confidence": 0.9,
})

test("valid blender_scene_objects expect", {
    "intent": "act", "status": "in_progress", "message": "creating",
    "actions": [{"type": "blender_create_scene", "description": "container cafe",
                 "expect": {"type": "blender_scene_objects"}}],
    "confidence": 0.9,
})

test("expect with invalid type -> stripped", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "crystal_ball"}}],
    "confidence": 0.9,
})

test("file_exists expect missing value -> stripped", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "file_exists"}}],
    "confidence": 0.9,
})

test("expect timeout capped at 5", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "cmd_success", "timeout": 999}}],
    "confidence": 0.9,
})
# Verify the timeout was actually capped
r2 = response_schema.validate({
    "intent": "act", "status": "in_progress", "message": "hi",
    "actions": [{"type": "cmd", "command": "echo hi",
                 "expect": {"type": "cmd_success", "timeout": 999}}],
    "confidence": 0.9,
})
capped_timeout = r2["response"]["actions"][0]["expect"]["timeout"]
assert capped_timeout == 5, f"Expected timeout=5, got {capped_timeout}"
print(f"                     (verified: timeout capped to {capped_timeout})")

# ------------------------------------------------------------------
# Group 6: None / non-dict input
# ------------------------------------------------------------------
print("\n[Group 6] Totally invalid input")
test("None input", None, expect_valid=False)
test("string input", "just a string", expect_valid=False)
test("list input", [1, 2, 3], expect_valid=False)
test("integer input", 42, expect_valid=False)

# ------------------------------------------------------------------
# Group 7: Plan normalization
# ------------------------------------------------------------------
print("\n[Group 7] Plan normalization")
test("valid plan", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "plan": ["Step 1", "Step 2"], "actions": [], "confidence": 0.5,
})

r_bad_plan = response_schema.validate({
    "intent": "act", "status": "in_progress", "message": "hi",
    "plan": "not a list", "actions": [], "confidence": 0.5,
})
test("plan as string -> dropped", {
    "intent": "act", "status": "in_progress", "message": "hi",
    "plan": "not a list", "actions": [], "confidence": 0.5,
})
assert "plan" not in r_bad_plan["response"], "String plan should be dropped"
print("                     (verified: string plan dropped)")

# ------------------------------------------------------------------
# Group 8: No-action valid types
# ------------------------------------------------------------------
print("\n[Group 8] Actions without required-field entries (always valid)")
test("scroll (no required fields)", {
    "intent": "act", "status": "complete", "message": "scrolling",
    "actions": [{"type": "scroll"}], "confidence": 0.9,
})
test("extract_clipboard (no required fields)", {
    "intent": "act", "status": "complete", "message": "copying",
    "actions": [{"type": "extract_clipboard"}], "confidence": 0.9,
})
test("blender_open_import_menu (no required fields)", {
    "intent": "act", "status": "complete", "message": "opening",
    "actions": [{"type": "blender_open_import_menu"}], "confidence": 0.9,
})
test("blender_bridge_status (no required fields)", {
    "intent": "act", "status": "in_progress", "message": "checking",
    "actions": [{"type": "blender_bridge_status"}], "confidence": 0.9,
})
test("blender_create_scene", {
    "intent": "act", "status": "in_progress", "message": "creating",
    "actions": [{"type": "blender_create_scene", "description": "container cafe reference"}],
    "confidence": 0.9,
})

print("\n=== All tests executed ===")
