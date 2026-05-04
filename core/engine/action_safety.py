"""
Action Safety Validator — gates ALL actions before they reach the executor.

Every action proposed by the LLM passes through `validate()` before
execution.  The validator assigns a risk level, checks the active window
for sensitive contexts, enforces the confidence threshold, and blocks
known-dangerous patterns.

Risk levels (ascending severity):
  SAFE     → read-only / harmless  (scroll, read_file, list_dir, ocr)
  LOW      → reversible UI actions (click, click_text, drag, hotkey, switch)
  MEDIUM   → data-input / external (type, open_url, launch, extract_clipboard)
  HIGH     → system-mutating        (cmd, write_file, blender_python, blender_create_scene, create_skill)
  BLOCKED  → never allowed          (destructive system commands)

Design constraints:
  • Zero-allocation hot path — no object creation for SAFE/LOW actions.
  • Never raises — returns a verdict dict so the caller decides.
  • Stateless — safe to call from any thread.
"""

from __future__ import annotations

import re
from core.config import sys_config
from core.utils.logger import logger

# ── Risk tiers ────────────────────────────────────────────────────────

SAFE = "SAFE"
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
BLOCKED = "BLOCKED"

_ACTION_RISK: dict[str, str] = {
    # SAFE — read-only / no-op
    "scroll": SAFE,
    "read_file": SAFE,
    "list_dir": SAFE,
    "ocr_screen": SAFE,
    "listen_audio": SAFE,
    "extract_clipboard": SAFE,
    "blender_bridge_status": SAFE,
    # LOW — reversible UI interaction
    "click": LOW,
    "click_text": LOW,
    "drag": LOW,
    "hotkey": LOW,
    "switch": LOW,
    # MEDIUM — data input / external navigation
    "type": MEDIUM,
    "open_url": MEDIUM,
    "launch": MEDIUM,
    # HIGH — system-mutating
    "cmd": HIGH,
    "write_file": HIGH,
    "blender_python": HIGH,
    "blender_create_scene": HIGH,
    "blender_enhance_scene": HIGH,
    "blender_open_import_menu": MEDIUM,
    "blender_import_file": MEDIUM,
    "create_skill": MEDIUM,
}

# ── Sensitive window patterns ────────────────────────────────────────

_SENSITIVE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"bank",
        r"paypal",
        r"stripe",
        r"password",
        r"vault",
        r"credentials",
        r"credit\s*card",
        r"payment",
        r"wallet",
        r"1password",
        r"lastpass",
        r"bitwarden",
        r"keepass",
        r"incognito",
        r"private\s+browsing",
    )
]

# ── Blocked command patterns (superset of executor's list) ───────────

_BLOCKED_CMD_PATTERNS: list[str] = [
    "format ", "format-volume",
    "remove-item -recurse -force /",
    "rm -rf", "del /s /q c:\\", "rd /s /q c:\\",
    "shutdown", "restart-computer", "stop-computer",
    "set-executionpolicy", "reg delete", "reg add",
    "invoke-webrequest", "invoke-restmethod",
    "wget ", "curl ", "iwr ",
    "new-service", "set-service",
    "disable-windowsoptionalfeature",
    "clear-disk", "initialize-disk",
    "net user", "net localgroup",
    # Additional patterns
    "remove-item -recurse",
    "stop-process -force",
    "taskkill /f /im",
    "bcdedit",
    "diskpart",
    "cipher /w",
]


# ── Verdict object ───────────────────────────────────────────────────

def _verdict(allowed: bool, risk: str, reason: str = "") -> dict:
    return {"allowed": allowed, "risk": risk, "reason": reason}


# ── Public API ───────────────────────────────────────────────────────

class ActionSafetyValidator:
    """Stateless gate that decides whether an action may execute."""

    def validate(
        self,
        action: dict,
        confidence: float = 1.0,
        active_window: str = "",
        active_app: str = "",
    ) -> dict:
        """Return a verdict dict: {allowed: bool, risk: str, reason: str}."""
        a_type = action.get("type", "")

        # 1. Unknown action type → block
        risk = _ACTION_RISK.get(a_type)
        if risk is None:
            return self._block(action, BLOCKED, f"Unknown action type '{a_type}'")

        # 2. Command-level blocklist for 'cmd' actions
        if a_type == "cmd":
            command = (action.get("command") or "").lower().strip()
            for pattern in _BLOCKED_CMD_PATTERNS:
                if pattern in command:
                    return self._block(
                        action, BLOCKED,
                        f"Destructive command pattern '{pattern}' in: {command[:100]}",
                    )

        # 3. Sensitive window detection (block MEDIUM+ in banking/password contexts)
        if risk in (MEDIUM, HIGH):
            window_lower = (active_window or "").lower()
            for pat in _SENSITIVE_PATTERNS:
                if pat.search(window_lower):
                    return self._block(
                        action, BLOCKED,
                        f"Sensitive window detected ('{pat.pattern}'). "
                        f"Action '{a_type}' blocked for safety.",
                    )

        # 4. Confidence gate
        threshold = sys_config.get("confidence_threshold") or 0.5
        if confidence < threshold:
            return self._block(
                action, risk,
                f"Confidence {confidence:.2f} below threshold {threshold:.2f}",
            )

        # 5. HIGH-risk actions require confirmation if enabled
        if risk == HIGH and sys_config.get("action_confirmation_required"):
            logger.log_event("ACTION_REQUIRES_CONFIRMATION", {
                "type": a_type,
                "risk": risk,
            })
            # We don't block here — the orchestrator's confirmation flow handles it.
            # But we log it so there's an audit trail.

        # ── Allowed ──────────────────────────────────────────────
        logger.log_event("ACTION_ALLOWED", {"type": a_type, "risk": risk})
        return _verdict(True, risk)

    # ── Internal ─────────────────────────────────────────────────

    def _block(self, action: dict, risk: str, reason: str) -> dict:
        a_type = action.get("type", "?")
        logger.log_event("ACTION_BLOCKED", {
            "type": a_type,
            "risk": risk,
            "reason": reason[:300],
        })
        logger.logger.warning(f"ActionSafety: BLOCKED [{risk}] {a_type} — {reason[:200]}")
        return _verdict(False, risk, reason)


action_safety = ActionSafetyValidator()
