"""
Skill Synthesizer — turn raw recorded events into a replayable Skill.

The recorder gives us a flat ``list[MimicEvent]`` of clicks, key presses,
key releases, and scrolls. Replaying that stream verbatim through
``pyautogui`` would technically work, but every keystroke would fire its
own action call (slow + visually jittery + bypasses our existing
``type``/``hotkey`` schemas).

This module compresses the event log into the same action JSON shape the
brain already emits, so the executor can replay it through the standard
pipeline (safety, plan validation, verification, telemetry — everything).

Compression rules
-----------------

1. **Consecutive printable key presses** with no modifiers held collapse
   into one ``type`` action whose ``text`` is the concatenation of the
   characters. We also flush a ``type`` whenever we hit a non-printable
   key, a click, or a modifier combo.

2. **Modifier + key combos** (``ctrl+s``, ``alt+tab``, ``ctrl+shift+p``)
   become a single ``hotkey`` action. We track which modifier keys are
   currently held using key-press / key-release events.

3. **Special keys pressed alone** (``enter``, ``tab``, ``backspace``,
   ``escape``, arrow keys) become ``hotkey`` actions with a single key.

4. **Mouse clicks** become ``click`` actions with absolute screen
   coordinates. Right-clicks include ``"button": "right"``. Double-clicks
   are merged when the same coords fire twice within 350 ms.

5. **Scrolls** become ``scroll`` actions with the dy direction collapsed
   to ±3 (matching pyautogui's typical scroll amount).

The output is a dict with::

    {
        "name": str,
        "description": str,        # filled in by the caller (LLM-written)
        "instruction": str,        # human-readable steps, also caller-filled
        "recorded_actions": [...]  # the compressed action list
    }

Pure-data, deterministic, no LLM call lives in this module — that lets
the unit tests run in milliseconds without any API access.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.mimic_recorder import MimicEvent
from core.utils.logger import logger


# ── Key classification ───────────────────────────────────────────────


# pynput key names we treat as "modifier keys" (they shouldn't appear in
# their own action; they only colour the *next* key press).
_MODIFIER_KEYS = {
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "shift", "shift_l", "shift_r",
    "cmd", "cmd_l", "cmd_r",  # Windows / Super
}

# pynput key names that should fire a single-key ``hotkey`` action.
_NAMED_KEYS = {
    "enter", "return", "tab", "backspace", "delete", "escape", "esc",
    "up", "down", "left", "right",
    "home", "end", "page_up", "page_down", "pageup", "pagedown",
    "space", "insert",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
    "f11", "f12",
}

# Maximum gap between two clicks at the same coords for them to merge into
# a double-click action.
_DOUBLE_CLICK_WINDOW_S = 0.35


# ── Helpers ──────────────────────────────────────────────────────────


def _normalize_key(name: str) -> str:
    """Return a canonical, lowercase key name with the ``Key.`` prefix
    stripped. Pynput sometimes hands us strings like ``"Key.shift_l"``
    or ``"'a'"``; we want bare ``"shift_l"`` / ``"a"``."""
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    if n.startswith("key."):
        n = n[4:]
    if n.startswith("'") and n.endswith("'") and len(n) >= 2:
        n = n[1:-1]
    return n


def _modifier_root(name: str) -> str:
    """Return the modifier family for a key name (so ``ctrl_l`` and
    ``ctrl_r`` both map to ``ctrl``). Returns an empty string for
    non-modifier keys."""
    n = _normalize_key(name)
    if n in _MODIFIER_KEYS:
        # Strip the trailing _l / _r / _gr
        for suffix in ("_l", "_r", "_gr"):
            if n.endswith(suffix):
                return n[: -len(suffix)]
        return n
    return ""


# ── Compressor ───────────────────────────────────────────────────────


@dataclass
class _TypeBuffer:
    """Mutable accumulator used while compressing consecutive characters."""

    chars: list[str]

    def __init__(self):
        self.chars = []

    def append(self, ch: str) -> None:
        self.chars.append(ch)

    def flush(self) -> dict | None:
        if not self.chars:
            return None
        text = "".join(self.chars)
        self.chars = []
        return {"type": "type", "text": text}


def compress_events(events: list[MimicEvent]) -> list[dict]:
    """Convert a raw event list into our action JSON list.

    The compressor is *side-effect free* and *order-preserving*; events
    are emitted in the same chronological order they were recorded.
    """
    out: list[dict] = []
    held_modifiers: set[str] = set()
    type_buf = _TypeBuffer()

    def _flush_type():
        action = type_buf.flush()
        if action is not None:
            out.append(action)

    last_click_at: float | None = None
    last_click_coords: tuple[int, int] | None = None
    last_click_button: str | None = None

    for ev in events:
        if ev.kind == "key_press":
            key = _normalize_key(ev.data.get("key", ""))
            ch = ev.data.get("char")
            mod_root = _modifier_root(key)

            # Track modifier hold state but never emit a standalone action
            # for a modifier press — wait for the partner key.
            if mod_root:
                held_modifiers.add(mod_root)
                continue

            # Modifier + key combo → hotkey action
            if held_modifiers:
                _flush_type()
                combo_key = ch if (ch is not None and len(ch) == 1) else key
                # Sort modifiers for stable output (ctrl before shift before alt
                # is a common UI convention, but alphabetical is good enough).
                keys = sorted(held_modifiers) + [combo_key]
                out.append({"type": "hotkey", "keys": keys})
                continue

            # Plain printable character → buffer for a future ``type`` action
            if ch is not None and len(ch) == 1 and ch.isprintable():
                type_buf.append(ch)
                continue

            # Named key without modifiers (enter, tab, esc, …) → hotkey
            if key in _NAMED_KEYS:
                _flush_type()
                out.append({"type": "hotkey", "keys": [key]})
                continue

            # Anything else (e.g. media keys) — just record as best-effort
            _flush_type()
            out.append({"type": "hotkey", "keys": [key]})

        elif ev.kind == "key_release":
            key = _normalize_key(ev.data.get("key", ""))
            mod_root = _modifier_root(key)
            if mod_root and mod_root in held_modifiers:
                held_modifiers.discard(mod_root)
            # Releases of non-modifier keys are intentionally ignored

        elif ev.kind == "click":
            _flush_type()
            x = int(ev.data.get("x", 0))
            y = int(ev.data.get("y", 0))
            button = ev.data.get("button", "left")
            ts = ev.timestamp

            # Double-click merge: same coords + same button + within window
            if (
                last_click_coords == (x, y)
                and last_click_button == button
                and last_click_at is not None
                and (ts - last_click_at) <= _DOUBLE_CLICK_WINDOW_S
                and out
                and out[-1].get("type") == "click"
                and out[-1].get("x") == x
                and out[-1].get("y") == y
            ):
                prev = out[-1]
                prev["clicks"] = int(prev.get("clicks", 1)) + 1
                last_click_at = ts
                continue

            click_action: dict = {"type": "click", "x": x, "y": y}
            if button and button != "left":
                click_action["button"] = button
            out.append(click_action)
            last_click_at = ts
            last_click_coords = (x, y)
            last_click_button = button

        elif ev.kind == "scroll":
            _flush_type()
            dy = int(ev.data.get("dy", 0))
            if dy == 0:
                continue
            # Normalize: pyautogui scrolls in units of "clicks" not pixels.
            amount = 3 if dy > 0 else -3
            out.append({"type": "scroll", "amount": amount})

    # Flush any trailing buffered text
    _flush_type()
    return out


# ── Skill assembly ───────────────────────────────────────────────────


def synthesize_skill(
    events: list[MimicEvent],
    name: str,
    description: str | None = None,
    instruction: str | None = None,
) -> dict:
    """Assemble a complete skill dict from a recording.

    *description* and *instruction* are caller-supplied so the LLM (or
    the user) can write friendly text. We don't make an LLM call from
    here — keeping this function pure makes the unit tests trivial and
    means the synthesizer also works offline.
    """
    actions = compress_events(events)
    if not name:
        name = "untitled_skill"

    # Default instruction is a coarse, user-readable summary built from
    # the action list. Callers usually override this with an LLM-written
    # one-line description, but having a deterministic fallback means we
    # never ship an empty skill.
    fallback_instruction = _summarize_actions(actions)

    skill = {
        "name": name,
        "description": description or fallback_instruction,
        "instruction": instruction or fallback_instruction,
        "recorded_actions": actions,
        "raw_event_count": len(events),
    }
    logger.logger.info(
        f"SkillSynthesizer: '{name}' compressed "
        f"{len(events)} events -> {len(actions)} actions"
    )
    return skill


def _summarize_actions(actions: list[dict]) -> str:
    """Generate a one-line, deterministic, human-readable summary."""
    if not actions:
        return "Empty workflow"
    parts: list[str] = []
    for a in actions[:10]:
        t = a.get("type")
        if t == "click":
            x = a.get("x")
            y = a.get("y")
            clicks = a.get("clicks", 1)
            parts.append(f"click({x},{y})" if clicks == 1 else f"double-click({x},{y})")
        elif t == "type":
            text = a.get("text", "")
            preview = text[:20] + ("…" if len(text) > 20 else "")
            parts.append(f"type({preview!r})")
        elif t == "hotkey":
            keys = a.get("keys", [])
            parts.append("+".join(keys))
        elif t == "scroll":
            parts.append(f"scroll({a.get('amount', 0)})")
        else:
            parts.append(str(t))
    suffix = " …" if len(actions) > 10 else ""
    return " → ".join(parts) + suffix
