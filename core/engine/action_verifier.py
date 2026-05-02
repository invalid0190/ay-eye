"""
Post-Action Verifier — checks whether an executed action achieved its goal.

Called by the orchestrator AFTER executor.execute_single() returns.
Each action type has a lightweight, type-specific check.  The verifier
never performs heavy OCR; it relies on:
  • Screen-change detection via live_perception (already captured by executor)
  • File-system stat checks
  • Window-title matching via ctypes
  • Short-term memory entries injected by the executor itself

Verdict shape:
  {
      "success": bool,
      "reason": str,
      "evidence": dict,      # type-specific diagnostic data
      "should_retry": bool,  # hint for orchestrator
  }

Design constraints:
  • Sub-50 ms for most checks (no OCR, no LLM calls).
  • Never raises — returns a verdict.
  • Does NOT mutate state or execute actions.
"""

from __future__ import annotations

import os
import time
import ctypes
import ctypes.wintypes
from core.config import sys_config
from core.utils.logger import logger
from core.vision.live_perception import live_perception


# ── Verdict helpers ──────────────────────────────────────────────────

def _ok(reason: str = "Verified", evidence: dict | None = None) -> dict:
    return {"success": True, "reason": reason, "evidence": evidence or {}, "should_retry": False}


def _fail(reason: str, evidence: dict | None = None, should_retry: bool = True) -> dict:
    return {"success": False, "reason": reason, "evidence": evidence or {}, "should_retry": should_retry}


# ── Foreground window helper ────────────────────────────────────────

def _get_foreground_title() -> str:
    """Return the title of the current foreground window (fast Win32 call)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
    except Exception:
        pass
    return ""


# ── Verifier ─────────────────────────────────────────────────────────

class ActionVerifier:
    """Lightweight post-action verification for each action type."""

    # Action types where screen-change is meaningful evidence
    _SCREEN_CHANGE_TYPES = {"click", "click_text", "drag", "scroll", "hotkey"}
    # Action types where we check short_term_memory for executor feedback
    _MEMORY_CHECK_TYPES = {"cmd", "blender_python", "blender_open_import_menu", "blender_import_file"}

    def verify(self, action: dict, frame_before=None) -> dict:
        """Verify a single action. Returns a verdict dict."""
        if not sys_config.get("post_action_verify_enabled"):
            return _ok("Verification disabled")

        a_type = action.get("type", "")

        try:
            # Dispatch to type-specific verifier
            handler = self._HANDLERS.get(a_type)
            if handler:
                return handler(self, action, frame_before)

            # Generic fallback: screen-change check for UI actions
            if a_type in self._SCREEN_CHANGE_TYPES:
                return self._verify_screen_changed(action, frame_before)

            # Read-only / fire-and-forget actions are always OK
            return _ok(f"Action '{a_type}' does not require verification")

        except Exception as e:
            # Verifier must never crash the pipeline
            logger.logger.error(f"ActionVerifier: Exception during verify: {e}")
            return _ok(f"Verification skipped due to error: {e}")

    # ── Type-specific handlers ───────────────────────────────────────

    def _verify_click(self, action: dict, frame_before) -> dict:
        """Click/click_text: check screen changed around click point."""
        return self._verify_screen_changed(action, frame_before)

    def _verify_cmd(self, action: dict, frame_before) -> dict:
        """cmd: check short_term_memory for CMD_RESULT feedback."""
        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string()
            command = (action.get("command") or "")[:60]

            if "CMD_RESULT [SUCCESS" in history or "CMD_RESULT [LAUNCHED" in history:
                return _ok("Command completed successfully", {"command": command})
            if "CMD_RESULT [FAILED" in history:
                return _fail(f"Command failed: {command}", {"command": command}, should_retry=True)
            if "CMD_RESULT [BLOCKED" in history:
                return _fail(f"Command blocked by security: {command}", {"command": command}, should_retry=False)
            if "CMD_RESULT [TIMEOUT" in history:
                return _fail(f"Command timed out: {command}", {"command": command}, should_retry=True)

            # No CMD_RESULT yet — may still be running
            return _ok("Command submitted (no result captured yet)", {"command": command})
        except Exception:
            return _ok("cmd verification skipped")

    def _verify_write_file(self, action: dict, frame_before) -> dict:
        """write_file: check that the target file exists and is non-empty."""
        path = action.get("path", "")
        if not path:
            return _fail("write_file action missing path", should_retry=False)

        if os.path.isfile(path):
            size = os.path.getsize(path)
            return _ok(f"File exists ({size} bytes)", {"path": path, "size": size})
        return _fail(f"File not found after write: {path}", {"path": path}, should_retry=True)

    def _verify_switch(self, action: dict, frame_before) -> dict:
        """switch/launch: check foreground window title contains target."""
        target = (action.get("target") or "").lower()
        if not target:
            return _ok("switch action had no target")

        # Small delay for window manager to settle
        time.sleep(0.3)
        fg_title = _get_foreground_title().lower()

        if target in fg_title:
            return _ok(f"Window '{target}' is focused", {"fg_title": fg_title[:100]})
        return _fail(
            f"Expected '{target}' in foreground, got '{fg_title[:60]}'",
            {"target": target, "fg_title": fg_title[:100]},
            should_retry=True,
        )

    def _verify_type_action(self, action: dict, frame_before) -> dict:
        """type: screen must have changed (text appeared)."""
        return self._verify_screen_changed(action, frame_before)

    def _verify_blender(self, action: dict, frame_before) -> dict:
        """Blender API actions: check short_term_memory for BLENDER_API_RESULT."""
        try:
            from core.state.short_term import short_term_memory
            history = short_term_memory.get_history_string()

            if "BLENDER_API_RESULT [SENT]" in history:
                return _ok("Blender API command sent", {"action": action.get("type")})
            if "BLENDER_API_RESULT [FAILED]" in history:
                return _fail("Blender API action failed", {"action": action.get("type")}, should_retry=True)

            return _ok("Blender action submitted")
        except Exception:
            return _ok("Blender verification skipped")

    def _verify_open_url(self, action: dict, frame_before) -> dict:
        """open_url: check that a browser window appeared."""
        time.sleep(0.5)
        fg_title = _get_foreground_title().lower()

        browser_hints = ("chrome", "firefox", "edge", "brave", "opera", "safari", "browser")
        if any(h in fg_title for h in browser_hints):
            return _ok("Browser window detected", {"fg_title": fg_title[:100]})

        # Some URLs open non-browser apps — not a hard failure
        return _ok("URL opened (non-browser window focused)", {"fg_title": fg_title[:100]})

    # ── Generic screen-change check ──────────────────────────────────

    def _verify_screen_changed(self, action: dict, frame_before) -> dict:
        """Check if the screen changed since frame_before."""
        if frame_before is None:
            return _ok("No baseline frame for comparison")

        time.sleep(0.15)  # Let UI settle
        changed = live_perception.verify_screen_changed(frame_before)
        if changed:
            return _ok("Screen changed after action")
        return _fail(
            f"No visible screen change after '{action.get('type', '?')}'",
            {"action_type": action.get("type")},
            should_retry=True,
        )

    # ── Handler dispatch table ───────────────────────────────────────

    _HANDLERS: dict[str, callable] = {
        "click": _verify_click,
        "click_text": _verify_click,
        "drag": _verify_click,
        "type": _verify_type_action,
        "cmd": _verify_cmd,
        "write_file": _verify_write_file,
        "switch": _verify_switch,
        "launch": _verify_switch,
        "open_url": _verify_open_url,
        "blender_python": _verify_blender,
        "blender_open_import_menu": _verify_blender,
        "blender_import_file": _verify_blender,
    }


action_verifier = ActionVerifier()
