"""
Ghost Typing
============

The user holds a hotkey, speaks, and characters appear in whichever
text field is focused — with sub-second lag and mid-utterance
corrections handled gracefully.

Why this module exists
----------------------

The standard voice flow waits for the *full* utterance, runs whisper
once, and then types the result through ``pyautogui``. That feels
sluggish for raw dictation (especially for long messages) because the
user sees nothing on screen until they release the hotkey.

A streaming pipeline is fundamentally different:

* The transcriber emits **partial** transcripts as audio arrives.
* Whisper revises earlier guesses as more context comes in
  (e.g. ``"recognize"`` → ``"recognise"`` → ``"recognise this"``).
* We must apply those corrections by **backspacing** what we've
  typed and replacing it, not by inserting on top.

This module is the deterministic core of that pipeline. It does not
own the microphone, the whisper model, or ``pyautogui``. Those are
injected through tiny protocols so unit tests can drive every state
transition without sound or display hardware.

Public API
----------
``GhostTyper`` exposes::

    start()                    -> bool   # arm dictation
    stop()                     -> str    # disarm; returns final text
    on_partial(text: str)      -> None   # called by the transcriber
    pending_chars               -> str    # unflushed buffer (test helper)

The orchestrator computes the **typing diff** between the
already-flushed text and the newest partial, then asks the typer to
backspace and add characters. Diff math is exposed as
``compute_typing_diff`` so tests and other callers can reuse it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol


# ── Public protocols ────────────────────────────────────────────────


class TyperBackend(Protocol):
    """Whatever pushes text into the focused window.

    The default production backend wraps ``pyautogui`` (clipboard paste
    for inserts, ``backspace`` for deletes). Tests use a list-based
    fake.
    """

    def insert(self, text: str) -> None: ...
    def backspace(self, count: int) -> None: ...


class TranscriberBackend(Protocol):
    """Streaming transcriber.

    Production wires ``faster-whisper`` in chunked-streaming mode. Tests
    inject a callable that pushes synthetic partial transcripts.
    """

    def start(self, on_partial: Callable[[str], None]) -> bool: ...
    def stop(self) -> None: ...


# ── Default no-op backends ──────────────────────────────────────────


class _NullTranscriber:
    """Used when no real transcriber is wired (e.g. faster-whisper
    not installed, sound dependencies missing)."""

    def start(self, on_partial: Callable[[str], None]) -> bool:
        return False

    def stop(self) -> None:
        return None


# ── Diff math (pure, well-tested) ───────────────────────────────────


def _common_prefix_length(a: str, b: str) -> int:
    """Length of the longest shared prefix between *a* and *b*."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


@dataclass(frozen=True)
class TypingDiff:
    """How to morph what's been typed (`flushed`) into a new partial.

    * ``backspace`` — number of characters to delete from the end.
    * ``insert`` — characters to type after the deletions.

    The two operations are intended to be applied in order. After
    applying both, ``flushed[: len(flushed) - backspace] + insert``
    equals the new partial.
    """

    backspace: int
    insert: str

    @property
    def is_noop(self) -> bool:
        return self.backspace == 0 and self.insert == ""


def compute_typing_diff(flushed: str, partial: str) -> TypingDiff:
    """Compute the minimal backspace + insert needed to reach *partial*.

    Three cases:

    * Pure extension (``"hello"`` → ``"hello world"``): backspace 0,
      insert ``" world"``.
    * Pure correction (``"recognize"`` → ``"recognise"``): backspace
      ``"ze"`` (2), insert ``"se"``.
    * Wholesale change (``"hello"`` → ``"goodbye"``): backspace
      ``"hello"`` (5), insert ``"goodbye"``.

    The function is *symmetric* with respect to whitespace — leading
    space differences in the partial are preserved as inserts, never
    silently stripped, because dictation pauses are meaningful.
    """
    if flushed == partial:
        return TypingDiff(backspace=0, insert="")
    common = _common_prefix_length(flushed, partial)
    backspace = len(flushed) - common
    insert = partial[common:]
    return TypingDiff(backspace=backspace, insert=insert)


# ── Buffer policies ────────────────────────────────────────────────


@dataclass
class FlushPolicy:
    """Controls *when* we flush queued characters to the typer.

    Streaming whisper revises words mid-sentence; if we type every
    keystroke as it arrives, the user sees a stream of backspaces and
    insertions that looks broken. To smooth this out we hold characters
    in a buffer until either:

    * **Word boundary**: the partial ends with whitespace or punctuation
      (the word it just produced is unlikely to change), OR
    * **Timeout**: the partial hasn't grown for ``hold_ms``
      milliseconds, suggesting the user paused.

    ``hold_ms = 0`` disables the timer (eager flush). ``0`` chars
    held when neither condition has fired.
    """

    hold_ms: int = 220
    word_terminators: str = " \t\n.,;:!?'\")]}"

    def should_flush_now(
        self,
        flushed: str,
        partial: str,
        now_ms: int,
        last_growth_ms: int,
    ) -> bool:
        if not partial or partial == flushed:
            return False
        # Word boundary fires immediately
        last_char = partial[-1]
        if last_char in self.word_terminators:
            return True
        # Timer-based flush
        if self.hold_ms <= 0:
            return True
        return (now_ms - last_growth_ms) >= self.hold_ms


# ── Orchestrator ───────────────────────────────────────────────────


class GhostTyper:
    """Streams partial transcripts through the diff math + flush policy
    into the typer backend.

    Thread-safety: ``on_partial`` runs on the transcriber thread,
    ``flush_due`` and ``stop`` from the orchestrator thread. We guard
    state with a mutex.
    """

    def __init__(
        self,
        transcriber: TranscriberBackend | None = None,
        typer: TyperBackend | None = None,
        policy: FlushPolicy | None = None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ):
        self._transcriber = transcriber or _NullTranscriber()
        self._typer = typer
        self.policy = policy or FlushPolicy()
        self._clock_ms = clock_ms

        self._lock = threading.Lock()
        self._active = False
        self._flushed = ""              # what the typer has actually typed
        self._partial = ""              # latest partial from whisper
        self._last_growth_ms = 0

    # ── State queries (test helpers) ─────────────────────────────────

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def flushed_text(self) -> str:
        with self._lock:
            return self._flushed

    @property
    def pending_chars(self) -> str:
        with self._lock:
            return self._partial[len(self._flushed):]

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> bool:
        with self._lock:
            if self._active:
                return False
            if self._typer is None:
                return False
            self._active = True
            self._flushed = ""
            self._partial = ""
            self._last_growth_ms = self._clock_ms()

        ok = self._transcriber.start(self.on_partial)
        if not ok:
            with self._lock:
                self._active = False
            return False
        return True

    def stop(self) -> str:
        """Stop dictation, flush any pending characters, return final text."""
        try:
            self._transcriber.stop()
        except Exception:
            pass
        # One last flush so we don't strand pending characters.
        self._apply_flush()
        with self._lock:
            self._active = False
            return self._flushed

    # ── Streaming entry point ────────────────────────────────────────

    def on_partial(self, partial: str) -> None:
        """Transcriber-side hook. Called for every revised partial."""
        if not isinstance(partial, str):
            return
        now_ms = self._clock_ms()
        with self._lock:
            if not self._active:
                return
            if partial != self._partial:
                self._partial = partial
                self._last_growth_ms = now_ms
        self._maybe_flush(now_ms)

    def flush_due(self) -> None:
        """Tick from the orchestrator's main loop. Forces a timer-based
        flush if the policy says we've waited long enough."""
        self._maybe_flush(self._clock_ms())

    # ── Internal flush logic ─────────────────────────────────────────

    def _maybe_flush(self, now_ms: int) -> None:
        with self._lock:
            should = self.policy.should_flush_now(
                flushed=self._flushed,
                partial=self._partial,
                now_ms=now_ms,
                last_growth_ms=self._last_growth_ms,
            )
        if should:
            self._apply_flush()

    def _apply_flush(self) -> None:
        with self._lock:
            if self._typer is None:
                return
            diff = compute_typing_diff(self._flushed, self._partial)
            if diff.is_noop:
                return
            target_partial = self._partial
            try:
                if diff.backspace > 0:
                    self._typer.backspace(diff.backspace)
                if diff.insert:
                    self._typer.insert(diff.insert)
            except Exception:
                # Don't propagate keystroke errors — the user may have
                # alt-tabbed away. Just keep the in-memory state honest.
                pass
            self._flushed = target_partial


# Module-level singleton (no backends wired yet — call set_backends
# from the executor after the user installs audio deps).
ghost_typer = GhostTyper()


def set_backends(
    transcriber: TranscriberBackend | None = None,
    typer: TyperBackend | None = None,
) -> None:
    """Replace the singleton's backends at runtime.

    Used by the executor when the user first triggers ``start_ghost_typing``
    so we can lazily import sounddevice / faster-whisper / pyautogui.
    """
    global ghost_typer
    if transcriber is not None:
        ghost_typer._transcriber = transcriber
    if typer is not None:
        ghost_typer._typer = typer
