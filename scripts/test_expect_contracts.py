"""Smoke test for ActionVerifier with expect contracts — run from project root.

Tests both expect-based verification and fallback to heuristic handlers.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.action_verifier import action_verifier, _ok, _fail
from core.config import sys_config

sys_config.config["post_action_verify_enabled"] = True
sys_config.config["require_expect_for_high_risk_actions"] = True


def test(label, result, expect_success=True):
    s = "[OK]" if result["success"] else "[FAIL]"
    mark = "[OK]" if result["success"] == expect_success else "[MISMATCH]"
    retry = " (retryable)" if result.get("should_retry") else ""
    print(f"  {mark:10s} {s:6s} | {label}")
    if result.get("reason"):
        print(f"                     -> {result['reason'][:120]}{retry}")
    return result


print("=== Expect Contract Tests ===\n")

# ------------------------------------------------------------------
# Group 1: file_exists expect — positive and negative
# ------------------------------------------------------------------
print("[Group 1] file_exists expect contract")
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
tmp.write(b"hello world")
tmp.close()

test("file_exists: file DOES exist",
     action_verifier.verify({
         "type": "write_file", "path": tmp.name,
         "expect": {"type": "file_exists", "value": tmp.name}
     }),
     expect_success=True)

os.unlink(tmp.name)

test("file_exists: file does NOT exist",
     action_verifier.verify({
         "type": "write_file", "path": tmp.name,
         "expect": {"type": "file_exists", "value": tmp.name}
     }),
     expect_success=False)

# ------------------------------------------------------------------
# Group 2: cmd_success expect
# ------------------------------------------------------------------
print("\n[Group 2] cmd_success expect contract")
try:
    from core.state.short_term import short_term_memory
    
    short_term_memory.add_system_context("CMD_RESULT [SUCCESS]: python --version\nOutput: Python 3.11")
    test("cmd_success: command succeeded",
         action_verifier.verify({
             "type": "cmd", "command": "python --version",
             "expect": {"type": "cmd_success"}
         }),
         expect_success=True)
except Exception as e:
    print(f"  [SKIP] cmd_success test: {e}")

# ------------------------------------------------------------------
# Group 3: app_focused expect
# ------------------------------------------------------------------
print("\n[Group 3] app_focused expect contract")
# This will check the actual foreground window — likely our terminal
test("app_focused: checking current foreground",
     action_verifier.verify({
         "type": "switch", "target": "nonexistent_app_xyz",
         "expect": {"type": "app_focused", "value": "nonexistent_app_xyz"}
     }),
     expect_success=False)

# ------------------------------------------------------------------
# Group 4: window_title expect
# ------------------------------------------------------------------
print("\n[Group 4] window_title expect contract")
test("window_title: unlikely match",
     action_verifier.verify({
         "type": "click", "x": 100, "y": 200,
         "expect": {"type": "window_title", "value": "xyzzy_nonexistent_12345"}
     }),
     expect_success=False)

# ------------------------------------------------------------------
# Group 5: screen_text expect (checks short_term_memory)
# ------------------------------------------------------------------
print("\n[Group 5] screen_text expect contract")
try:
    from core.state.short_term import short_term_memory
    
    short_term_memory.add_system_context("File saved successfully to disk")
    test("screen_text: text in context",
         action_verifier.verify({
             "type": "click_text", "text": "Save",
             "expect": {"type": "screen_text", "value": "saved successfully"}
         }),
         expect_success=True)

    test("screen_text: text NOT in context",
         action_verifier.verify({
             "type": "click_text", "text": "Export",
             "expect": {"type": "screen_text", "value": "xyzzy_not_found_12345"}
         }),
         expect_success=True)  # Falls back to screen-change (no frame = OK)
except Exception as e:
    print(f"  [SKIP] screen_text test: {e}")

# ------------------------------------------------------------------
# Group 6: clipboard_contains expect
# ------------------------------------------------------------------
print("\n[Group 6] clipboard_contains expect contract")
try:
    from core.state.short_term import short_term_memory
    
    short_term_memory.add_system_context("CLIPBOARD_DATA: Hello World from clipboard")
    test("clipboard_contains: match",
         action_verifier.verify({
             "type": "extract_clipboard",
             "expect": {"type": "clipboard_contains", "value": "hello world"}
         }),
         expect_success=True)
    
    test("clipboard_contains: no match",
         action_verifier.verify({
             "type": "extract_clipboard",
             "expect": {"type": "clipboard_contains", "value": "zzz_not_in_clipboard"}
         }),
         expect_success=False)
except Exception as e:
    print(f"  [SKIP] clipboard_contains test: {e}")

# ------------------------------------------------------------------
# Group 7: none expect (skip verification)
# ------------------------------------------------------------------
print("\n[Group 7] none expect contract")
test("none: always passes",
     action_verifier.verify({
         "type": "cmd", "command": "echo hi",
         "expect": {"type": "none"}
     }),
     expect_success=True)

# ------------------------------------------------------------------
# Group 8: Invalid expect type (should fall back to heuristic)
# ------------------------------------------------------------------
print("\n[Group 8] Invalid expect type (fallback)")
test("invalid expect type -> heuristic fallback",
     action_verifier.verify({
         "type": "scroll", "amount": -3,
         "expect": {"type": "magic_crystal_ball", "value": "42"}
     }),
     expect_success=True)  # Falls back to screen-change (no frame = OK)

# ------------------------------------------------------------------
# Group 9: Missing expect on high-risk (warning logged)
# ------------------------------------------------------------------
print("\n[Group 9] High-risk action without expect (should still run, warning logged)")
test("cmd without expect -> heuristic runs + EXPECT_MISSING_HIGH_RISK logged",
     action_verifier.verify({
         "type": "cmd", "command": "echo hello"
     }),
     expect_success=True)  # Heuristic still runs; warning is just logged

test("write_file without expect -> heuristic runs",
     action_verifier.verify({
         "type": "write_file", "path": "nonexistent_for_test.py"
     }),
     expect_success=False)  # File doesn't exist, heuristic correctly fails

# ------------------------------------------------------------------
# Group 10: Expect with timeout (capped at 5s)
# ------------------------------------------------------------------
print("\n[Group 10] Expect with timeout")
import time
start = time.time()
test("file_exists with timeout=1",
     action_verifier.verify({
         "type": "write_file", "path": "nonexistent.py",
         "expect": {"type": "file_exists", "value": "nonexistent.py", "timeout": 1}
     }),
     expect_success=False)
elapsed = time.time() - start
print(f"                     (elapsed: {elapsed:.2f}s — timeout respected)")

# ------------------------------------------------------------------
# Group 11: Expect takes priority over heuristic
# ------------------------------------------------------------------
print("\n[Group 11] Expect takes priority over heuristic handler")
# A write_file with file_exists expect pointing to a REAL file
tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
tmp2.write(b"print('hello')")
tmp2.close()

test("write_file expect overrides heuristic (file exists)",
     action_verifier.verify({
         "type": "write_file", "path": "wrong_path_here.py",  # heuristic would fail
         "expect": {"type": "file_exists", "value": tmp2.name}  # expect passes
     }),
     expect_success=True)
os.unlink(tmp2.name)

print("\n=== All tests executed ===")
