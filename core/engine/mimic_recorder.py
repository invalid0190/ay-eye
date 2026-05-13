"""
Mimic Mode Recorder
===================

Captures the user's actual mouse + keyboard input so Ay-Eye can later
replay the same workflow on voice command. The recorder runs entirely
in-memory; nothing is written to disk until the user explicitly says
"save this as <name>".

Architecture
------------
The recorder is split into three pieces so we can unit-test it without
needing real OS hooks:

* ``MimicEvent`` — typed event records (click, key press, key release,
  scroll). Pure data, no behaviour.
* ``HookBackend`` — abstract protocol that emits ``MimicEvent`` callbacks.
  We ship two implementations:

    - ``_PynputHook`` — real backend, lazy-imports ``pynput`` so the
      project keeps loading even when the user hasn't installed it.
    - ``_NullHook`` — no-op fallback; the recorder reports
      ``start()`` failure cleanly instead of crashing.

  Tests inject their own fake backend.

* ``MimicRecorder`` — orchestrator. Holds the hook, the event buffer,
  and the active "skill name". Singleton ``mimic_recorder`` mirrors
  every other engine module's pattern.

The recorder intentionally does NOT capture screenshots on every event
(too heavy + privacy-sensitive). Replay relies on the deterministic
event log alone, plus an optional one-shot LLM call for a human-readable
description in ``skill_synthesizer``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.utils.logger import logger


# ── Event model ──────────────────────────────────────────────────────


@dataclass
class MimicEvent:
    """Single captured input event."""

    kind: str  # "click" | "key_press" | "key_release" | "scroll"
    timestamp: float  # seconds since start of the recording
    data: dict = field(default_factory=dict)
    window_title: str = ""
    window_class: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "timestamp": round(self.timestamp, 3),
            "data": dict(self.data),
            "window_title": self.window_title,
            "window_class": self.window_class,
        }


# ── Hook protocol ────────────────────────────────────────────────────


class HookBackend:
    """Abstract base for OS-input hooks. Subclasses must implement
    ``start`` (begin emitting events) and ``stop`` (release the hook)."""

    def start(self, on_event: Callable[[MimicEvent], None]) -> bool:
        """Attach the hook. Return True if the backend is now live."""
        raise NotImplementedError

    def stop(self) -> None:
        """Detach the hook. Idempotent."""
        raise NotImplementedError


class _NullHook(HookBackend):
    """No-op fallback used when the real backend is unavailable."""

    def start(self, on_event: Callable[[MimicEvent], None]) -> bool:
        return False

    def stop(self) -> None:
        return None


class _PynputHook(HookBackend):
    """Real Win32 / X11 / macOS hook backed by the ``pynput`` package.

    Lazy-imports ``pynput`` inside ``start`` so a missing dependency
    surfaces as a friendly recorder error rather than a project-wide
    import failure.
    """

    def __init__(self, get_window_context: Callable[[], tuple[str, str]] | None = None):
        self._get_window = get_window_context or (lambda: ("", ""))
        self._mouse_listener = None
        self._kb_listener = None
        self._on_event: Optional[Callable[[MimicEvent], None]] = None
        self._t0 = 0.0

    def start(self, on_event: Callable[[MimicEvent], None]) -> bool:
        try:
            from pynput import mouse, keyboard  # type: ignore
        except ImportError:
            logger.logger.warning(
                "MimicRecorder: pynput is not installed. "
                "Install with: pip install pynput  (then restart Ay-Eye)"
            )
            return False
        except Exception as e:
            logger.logger.error(f"MimicRecorder: pynput import failed: {e}")
            return False

        self._on_event = on_event
        self._t0 = time.time()

        def _on_click(x, y, button, pressed):
            if not pressed or self._on_event is None:
                return
            title, klass = self._get_window()
            self._on_event(MimicEvent(
                kind="click",
                timestamp=time.time() - self._t0,
                data={"x": int(x), "y": int(y), "button": str(button).split(".")[-1]},
                window_title=title,
                window_class=klass,
            ))

        def _on_scroll(x, y, dx, dy):
            if self._on_event is None:
                return
            title, klass = self._get_window()
            self._on_event(MimicEvent(
                kind="scroll",
                timestamp=time.time() - self._t0,
                data={"x": int(x), "y": int(y), "dx": int(dx), "dy": int(dy)},
                window_title=title,
                window_class=klass,
            ))

        def _on_press(key):
            if self._on_event is None:
                return
            title, klass = self._get_window()
            try:
                ch = key.char  # type: ignore[attr-defined]
            except AttributeError:
                ch = None
            data: dict = {"key": str(key).replace("Key.", "")}
            if ch is not None:
                data["char"] = ch
            self._on_event(MimicEvent(
                kind="key_press",
                timestamp=time.time() - self._t0,
                data=data,
                window_title=title,
                window_class=klass,
            ))

        def _on_release(key):
            if self._on_event is None:
                return
            self._on_event(MimicEvent(
                kind="key_release",
                timestamp=time.time() - self._t0,
                data={"key": str(key).replace("Key.", "")},
            ))

        try:
            self._mouse_listener = mouse.Listener(on_click=_on_click, on_scroll=_on_scroll)
            self._kb_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
            self._mouse_listener.start()
            self._kb_listener.start()
            return True
        except Exception as e:
            logger.logger.error(f"MimicRecorder: failed to attach pynput listeners: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        for listener in (self._mouse_listener, self._kb_listener):
            try:
                if listener is not None:
                    listener.stop()
            except Exception:
                pass
        self._mouse_listener = None
        self._kb_listener = None
        self._on_event = None


# ── Recorder ─────────────────────────────────────────────────────────


# Default cap so a forgotten recording session can't eat unbounded memory.
_MAX_EVENTS = 5000

# Maximum recording duration. After this we auto-stop and warn — most
# real-world workflows complete in well under five minutes.
_MAX_DURATION_SECONDS = 600.0


class MimicRecorder:
    """Captures input events into an in-memory buffer.

    Thread-safe: hook callbacks run on listener threads, ``start``/``stop``
    on the executor thread.
    """

    def __init__(self, hook: HookBackend | None = None):
        self._hook = hook or _PynputHook()
        self._events: list[MimicEvent] = []
        self._active_name: Optional[str] = None
        self._started_at: float = 0.0
        self._lock = threading.Lock()

    # ── State queries ────────────────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._active_name is not None

    @property
    def active_name(self) -> Optional[str]:
        with self._lock:
            return self._active_name

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def snapshot(self) -> list[MimicEvent]:
        """Return a copy of currently-buffered events (safe for reading)."""
        with self._lock:
            return list(self._events)

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self, name: str = "untitled_skill") -> bool:
        """Begin recording under *name*.

        Returns ``True`` on success. Returns ``False`` if a session is
        already running OR the underlying hook backend isn't available
        (e.g. pynput not installed). The caller is expected to surface
        the failure to the user.
        """
        with self._lock:
            if self._active_name is not None:
                logger.logger.warning(
                    f"MimicRecorder: already recording '{self._active_name}', "
                    f"ignoring start('{name}')"
                )
                return False
            self._events = []
            self._active_name = name
            self._started_at = time.time()

        ok = self._hook.start(self._on_event)
        if not ok:
            with self._lock:
                self._active_name = None
            return False

        logger.logger.info(f"MimicRecorder: started recording '{name}'")
        return True

    def stop(self) -> list[MimicEvent]:
        """Stop recording. Returns the captured event list (may be empty)."""
        self._hook.stop()
        with self._lock:
            captured = list(self._events)
            name = self._active_name
            self._active_name = None
            self._events = []
        if name is not None:
            logger.logger.info(
                f"MimicRecorder: stopped recording '{name}' "
                f"({len(captured)} events captured)"
            )
        return captured

    def cancel(self) -> None:
        """Discard any in-flight recording without saving."""
        self.stop()

    # ── Internal callback ────────────────────────────────────────────

    def _on_event(self, ev: MimicEvent) -> None:
        with self._lock:
            if self._active_name is None:
                return  # stale callback after stop()
            # Hard caps: defensive against runaway recordings
            if len(self._events) >= _MAX_EVENTS:
                logger.logger.warning(
                    f"MimicRecorder: hit {_MAX_EVENTS}-event cap, auto-stopping"
                )
                self._active_name = None
                self._hook.stop()
                return
            if ev.timestamp >= _MAX_DURATION_SECONDS:
                logger.logger.warning(
                    f"MimicRecorder: hit {_MAX_DURATION_SECONDS:.0f}s duration "
                    "cap, auto-stopping"
                )
                self._active_name = None
                self._hook.stop()
                return
            self._events.append(ev)


# Module-level singleton.
mimic_recorder = MimicRecorder()
