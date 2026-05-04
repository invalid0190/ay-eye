"""Smoke test for ActionSafetyValidator — run from project root."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.action_safety import action_safety

def test(label, action, **kwargs):
    v = action_safety.validate(action, **kwargs)
    status = "ALLOWED" if v["allowed"] else "BLOCKED"
    risk = v["risk"]
    reason = v.get("reason", "")
    print(f"  [{status}] {risk:8s} | {label}")
    if reason:
        print(f"           -> {reason[:120]}")
    return v

print("=== Action Safety Validator Tests ===\n")

# --- SAFE actions ---
print("[Group 1] SAFE actions (always allowed)")
test("scroll down",          {"type": "scroll", "amount": -3})
test("read a file",          {"type": "read_file", "path": "main.py"})
test("list directory",       {"type": "list_dir", "path": "."})

# --- LOW actions ---
print("\n[Group 2] LOW actions (allowed unless confidence too low)")
test("click button",         {"type": "click", "x": 100, "y": 200})
test("click_text 'Submit'",  {"type": "click_text", "text": "Submit"})
test("hotkey Ctrl+S",        {"type": "hotkey", "keys": ["ctrl", "s"]})

# --- MEDIUM actions ---
print("\n[Group 3] MEDIUM actions (blocked in sensitive windows)")
test("type text",            {"type": "type", "text": "hello"})
test("open URL",             {"type": "open_url", "url": "https://example.com"})
test("type in bank window",  {"type": "type", "text": "hello"}, active_window="Chase Bank - Chrome")
test("open_url in PayPal",   {"type": "open_url", "url": "x"}, active_window="PayPal Checkout")

# --- HIGH actions ---
print("\n[Group 4] HIGH actions (allowed in normal context)")
test("cmd mkdir",            {"type": "cmd", "command": "mkdir test_folder"})
test("write_file",           {"type": "write_file", "path": "x.py", "content": "print(1)"})
test("blender python",       {"type": "blender_python", "script": "import bpy"})
test("blender create scene", {"type": "blender_create_scene", "description": "container cafe"})
test("blender bridge status", {"type": "blender_bridge_status"})

# --- BLOCKED commands ---
print("\n[Group 5] BLOCKED commands (always refused)")
test("cmd rm -rf /",         {"type": "cmd", "command": "rm -rf /"})
test("cmd format C:",        {"type": "cmd", "command": "format C:"})
test("cmd shutdown",         {"type": "cmd", "command": "shutdown /s /t 0"})
test("cmd reg delete",       {"type": "cmd", "command": "reg delete HKCU\\Software"})
test("cmd diskpart",         {"type": "cmd", "command": "diskpart"})
test("cmd net user",         {"type": "cmd", "command": "net user admin /add"})

# --- Confidence gate ---
print("\n[Group 6] Low confidence (blocked regardless of risk)")
test("click, conf=0.3",      {"type": "click", "x": 1, "y": 1}, confidence=0.3)
test("cmd, conf=0.2",        {"type": "cmd", "command": "echo hi"}, confidence=0.2)

# --- Unknown type ---
print("\n[Group 7] Unknown action types")
test("delete_everything",    {"type": "delete_everything"})

# --- Sensitive windows + LOW (should pass) ---
print("\n[Group 8] LOW action in sensitive window (should PASS)")
test("scroll in bank window", {"type": "scroll"}, active_window="Bank of America - Chrome")

print("\n=== All tests executed ===")
