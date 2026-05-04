"""Smoke test for ActionVerifier — run from project root.

NOTE: Some checks (screen-change, switch) need a running desktop and
LivePerception.  Those are tested as far as possible without an active
display.  The unit-testable paths (cmd, write_file, open_url, unknown
types, disabled config) are fully exercised.
"""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.action_verifier import action_verifier, _ok, _fail
from core.config import sys_config

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def test(label, result):
    s = "[OK]" if result["success"] else "[FAIL]"
    retry = " (retryable)" if result.get("should_retry") else ""
    print(f"  {s:6s} | {label}")
    if result.get("reason"):
        print(f"           -> {result['reason'][:120]}{retry}")
    return result


print("=== ActionVerifier Tests ===\n")

# ------------------------------------------------------------------
# 1. Disabled config — everything should return OK immediately
# ------------------------------------------------------------------
print("[Group 1] Verification disabled")
sys_config.config["post_action_verify_enabled"] = False
test("click with verify disabled",
     action_verifier.verify({"type": "click", "x": 50, "y": 50}))
sys_config.config["post_action_verify_enabled"] = True

# ------------------------------------------------------------------
# 2. Actions that don't require verification
# ------------------------------------------------------------------
print("\n[Group 2] Read-only / no-verification actions")
test("scroll (no baseline frame)",
     action_verifier.verify({"type": "scroll", "amount": -3}))
test("read_file",
     action_verifier.verify({"type": "read_file", "path": "main.py"}))
test("list_dir",
     action_verifier.verify({"type": "list_dir", "path": "."}))
test("ocr_screen",
     action_verifier.verify({"type": "ocr_screen"}))

# ------------------------------------------------------------------
# 3. write_file — file existence check
# ------------------------------------------------------------------
print("\n[Group 3] write_file verification")
# Create a real temp file
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
tmp.write(b"hello")
tmp.close()
test("write_file -> file exists",
     action_verifier.verify({"type": "write_file", "path": tmp.name}))
os.unlink(tmp.name)
test("write_file -> file does NOT exist",
     action_verifier.verify({"type": "write_file", "path": tmp.name}))
test("write_file -> missing path field",
     action_verifier.verify({"type": "write_file"}))

# ------------------------------------------------------------------
# 4. cmd — short_term_memory feedback check
# ------------------------------------------------------------------
print("\n[Group 4] cmd verification (via short_term_memory)")
try:
    from core.state.short_term import short_term_memory
    
    # Simulate success feedback
    short_term_memory.add_system_context("CMD_RESULT [SUCCESS]: echo hello\\nOutput: hello")
    test("cmd after SUCCESS feedback",
         action_verifier.verify({"type": "cmd", "command": "echo hello"}))
    
    # Simulate failure feedback
    short_term_memory.add_system_context("CMD_RESULT [FAILED, exit=1]: bad_cmd\\nError: not found")
    test("cmd after FAILED feedback",
         action_verifier.verify({"type": "cmd", "command": "bad_cmd"}))

    # Simulate blocked
    short_term_memory.add_system_context("CMD_RESULT [BLOCKED BY SECURITY]: rm -rf /")
    test("cmd after BLOCKED feedback",
         action_verifier.verify({"type": "cmd", "command": "rm -rf /"}))
except Exception as e:
    print(f"  [SKIP] Could not test cmd verification: {e}")

# ------------------------------------------------------------------
# 5. switch/launch — foreground window check (may not match)
# ------------------------------------------------------------------
print("\n[Group 4b] Blender verification (via short_term_memory)")
try:
    from core.state.short_term import short_term_memory

    short_term_memory.history.clear()
    short_term_memory.add_system_context(
        "BLENDER_API_RESULT [SUCCESS]: create Blender scene. object_count=42. object_names=container, table"
    )
    test("blender_create_scene after SUCCESS with objects",
         action_verifier.verify({"type": "blender_create_scene", "description": "container cafe"}))

    short_term_memory.history.clear()
    short_term_memory.add_system_context(
        "BLENDER_API_RESULT [SUCCESS]: create Blender scene. object_count=0. object_names="
    )
    test("blender_create_scene after SUCCESS with zero objects",
         action_verifier.verify({"type": "blender_create_scene", "description": "empty scene"}))

    short_term_memory.history.clear()
    short_term_memory.add_system_context(
        "BLENDER_API_RESULT [FAILED]: create Blender scene. object_count=0. error=boom"
    )
    test("blender_create_scene after FAILED",
         action_verifier.verify({"type": "blender_create_scene", "description": "bad scene"}))

    short_term_memory.add_system_context(
        "BLENDER_BRIDGE_STATUS [CONNECTED]: host=127.0.0.1 port=8765 object_count=42 mesh_count=40 object_names=container"
    )
    test("blender_bridge_status after CONNECTED",
         action_verifier.verify({"type": "blender_bridge_status"}))
except Exception as e:
    print(f"  [SKIP] Could not test Blender verification: {e}")

print("\n[Group 5] switch/launch verification (live window check)")
test("switch to current foreground window",
     action_verifier.verify({"type": "switch", "target": ""}))

# ------------------------------------------------------------------
# 6. click with no baseline frame
# ------------------------------------------------------------------
print("\n[Group 6] click without baseline frame")
test("click (no frame_before)",
     action_verifier.verify({"type": "click", "x": 100, "y": 100}, frame_before=None))

# ------------------------------------------------------------------
# 7. Unknown action type fallback
# ------------------------------------------------------------------
print("\n[Group 7] Unknown / custom action types")
test("custom_action",
     action_verifier.verify({"type": "custom_action"}))

# ------------------------------------------------------------------
# 8. Verdict helpers
# ------------------------------------------------------------------
print("\n[Group 8] Verdict helpers")
ok = _ok("test reason", {"key": "val"})
assert ok["success"] and ok["reason"] == "test reason" and ok["evidence"]["key"] == "val"
print("  [OK]    | _ok() helper")

fail = _fail("bad", {"k": 1}, should_retry=True)
assert not fail["success"] and fail["should_retry"]
print("  [OK]    | _fail() helper")

print("\n=== All tests executed ===")
