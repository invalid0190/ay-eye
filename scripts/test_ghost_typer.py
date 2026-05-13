"""
Tests for Ghost Typing.

Every layer is exercised through fakes — no real audio, no real
``pyautogui`` keystrokes. We drive the orchestrator's state machine
directly to verify diff math, flush policy, and the full lifecycle.

Run:
    .venv\\Scripts\\python scripts\\test_ghost_typer.py
"""

from __future__ import annotations

import os
import sys
from typing import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.engine.ghost_typer import (
    GhostTyper,
    FlushPolicy,
    TypingDiff,
    compute_typing_diff,
    _common_prefix_length,
    _NullTranscriber,
)


PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Fakes ───────────────────────────────────────────────────────────


class FakeTyper:
    """Records every insert/backspace, exposes the resulting buffer."""

    def __init__(self):
        self.buffer = ""
        self.inserts: list[str] = []
        self.backspaces: list[int] = []

    def insert(self, text: str) -> None:
        self.inserts.append(text)
        self.buffer += text

    def backspace(self, count: int) -> None:
        n = max(0, int(count))
        self.backspaces.append(n)
        self.buffer = self.buffer[:-n] if n > 0 else self.buffer


class FakeTranscriber:
    """Hands the typer a callback we can drive synthetically."""

    def __init__(self):
        self._on_partial: Callable[[str], None] | None = None
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_start = False

    def start(self, on_partial: Callable[[str], None]) -> bool:
        self.start_calls += 1
        if self.fail_start:
            return False
        self._on_partial = on_partial
        return True

    def stop(self) -> None:
        self.stop_calls += 1
        self._on_partial = None

    def emit(self, partial: str) -> None:
        if self._on_partial is not None:
            self._on_partial(partial)


class _ManualClock:
    def __init__(self, start: int = 0):
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


# ── _common_prefix_length ──────────────────────────────────────────


def test_common_prefix_basic_cases():
    check(_common_prefix_length("hello", "help") == 3,
          "'hello' / 'help' share prefix of length 3")
    check(_common_prefix_length("abc", "abc") == 3,
          "identical strings share full length")
    check(_common_prefix_length("", "abc") == 0,
          "empty string shares 0 with non-empty")
    check(_common_prefix_length("abc", "") == 0,
          "non-empty shares 0 with empty")
    check(_common_prefix_length("xyz", "abc") == 0,
          "no shared prefix returns 0")


# ── compute_typing_diff ────────────────────────────────────────────


def test_diff_pure_extension_yields_no_backspace():
    d = compute_typing_diff("hello", "hello world")
    check(d.backspace == 0,
          "appending text yields zero backspaces")
    check(d.insert == " world",
          f"insert is the appended substring (got {d.insert!r})")


def test_diff_pure_correction_backspaces_only_diverging_suffix():
    d = compute_typing_diff("recognize", "recognise")
    check(d.backspace == 2,
          f"diverging tail of length 2 backspaced (got {d.backspace})")
    check(d.insert == "se",
          f"insert replaces the diverged suffix (got {d.insert!r})")


def test_diff_wholesale_change():
    d = compute_typing_diff("hello", "goodbye")
    check(d.backspace == 5,
          "no shared prefix -> backspace whole flushed text")
    check(d.insert == "goodbye",
          "insert is the entire new partial")


def test_diff_identical_strings_is_noop():
    d = compute_typing_diff("hello world", "hello world")
    check(d.is_noop,
          "diff between identical strings is a no-op")


def test_diff_handles_empty_inputs():
    check(compute_typing_diff("", "abc") == TypingDiff(backspace=0, insert="abc"),
          "empty -> non-empty: zero backspaces, full insert")
    check(compute_typing_diff("abc", "") == TypingDiff(backspace=3, insert=""),
          "non-empty -> empty: backspace everything, insert nothing")


def test_diff_preserves_leading_whitespace():
    d = compute_typing_diff("hello", "hello ")
    check(d.insert == " " and d.backspace == 0,
          "trailing space is correctly inserted, not stripped")


def test_diff_round_trip_invariant():
    """For any flushed/partial pair, applying the diff yields the partial."""
    cases = [
        ("", ""),
        ("a", "ab"),
        ("ab", "a"),
        ("recognize that", "recognise that"),
        ("hello world", "goodbye"),
        ("Hi mom", "Hi mom!"),
    ]
    for flushed, partial in cases:
        d = compute_typing_diff(flushed, partial)
        result = flushed[: len(flushed) - d.backspace] + d.insert
        check(result == partial,
              f"diff round-trips: {flushed!r} -> {partial!r}")


# ── FlushPolicy ────────────────────────────────────────────────────


def test_policy_word_boundary_flushes_immediately():
    p = FlushPolicy(hold_ms=10_000)  # huge hold so timer can't fire
    # Trailing space is a word terminator
    check(p.should_flush_now("", "hello ", now_ms=0, last_growth_ms=0) is True,
          "trailing space triggers immediate flush")
    check(p.should_flush_now("", "wait...", now_ms=0, last_growth_ms=0) is True,
          "trailing punctuation triggers immediate flush")


def test_policy_holds_until_timeout_for_unfinished_word():
    p = FlushPolicy(hold_ms=200)
    # 100 ms after last growth — under threshold, hold
    check(p.should_flush_now("", "hello", now_ms=100, last_growth_ms=0) is False,
          "incomplete word held while under timeout")
    # 250 ms after last growth — over threshold, flush
    check(p.should_flush_now("", "hello", now_ms=250, last_growth_ms=0) is True,
          "incomplete word flushed once timeout elapses")


def test_policy_zero_hold_is_eager():
    p = FlushPolicy(hold_ms=0)
    check(p.should_flush_now("", "x", now_ms=0, last_growth_ms=0) is True,
          "hold_ms=0 means flush every partial immediately")


def test_policy_no_pending_chars_is_never_flushed():
    p = FlushPolicy(hold_ms=200)
    check(p.should_flush_now("hello", "hello", now_ms=10_000, last_growth_ms=0) is False,
          "no pending characters -> no flush")
    check(p.should_flush_now("", "", now_ms=10_000, last_growth_ms=0) is False,
          "empty partial -> no flush")


# ── GhostTyper lifecycle ──────────────────────────────────────────


def _build_typer(policy: FlushPolicy | None = None) -> tuple[GhostTyper, FakeTranscriber, FakeTyper, _ManualClock]:
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    clock = _ManualClock()
    g = GhostTyper(
        transcriber=transcriber,
        typer=typer,
        policy=policy or FlushPolicy(hold_ms=200),
        clock_ms=clock,
    )
    return g, transcriber, typer, clock


def test_lifecycle_start_returns_true_with_backends():
    g, t, _, _ = _build_typer()
    check(g.start() is True,
          "start() returns True when transcriber and typer are wired")
    check(g.is_active is True,
          "is_active flips to True after start")
    check(t.start_calls == 1,
          "transcriber.start was called once")


def test_lifecycle_double_start_refuses():
    g, _, _, _ = _build_typer()
    g.start()
    check(g.start() is False,
          "second start() while already active returns False")


def test_lifecycle_start_returns_false_when_transcriber_unavailable():
    g, t, _, _ = _build_typer()
    t.fail_start = True
    check(g.start() is False,
          "start() returns False when the transcriber backend can't attach")
    check(g.is_active is False,
          "is_active stays False after a failed start")


def test_lifecycle_start_requires_a_typer_backend():
    g = GhostTyper(transcriber=FakeTranscriber(), typer=None)
    check(g.start() is False,
          "start() refuses to arm when no typer backend is wired")


def test_lifecycle_stop_returns_final_text_and_releases_transcriber():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    g.start()
    t.emit("hello world ")
    final = g.stop()
    check(final == "hello world ",
          f"stop() returns the final flushed text (got {final!r})")
    check(g.is_active is False,
          "stop() leaves the typer inactive")
    check(t.stop_calls == 1,
          "transcriber.stop() called exactly once")


def test_null_transcriber_signals_unavailable_backend():
    null = _NullTranscriber()
    started = null.start(lambda p: None)
    check(started is False,
          "_NullTranscriber.start always returns False")
    null.stop()  # must not raise
    check(True, "_NullTranscriber.stop is a safe no-op")


# ── on_partial flushing behaviour ──────────────────────────────────


def test_word_terminator_flushes_through_to_typer():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=10_000))
    g.start()
    t.emit("hello ")  # trailing space -> immediate flush
    check(fk.buffer == "hello ",
          f"typer received the full partial on word boundary (got {fk.buffer!r})")


def test_partial_held_until_timer_elapses():
    g, t, fk, clock = _build_typer(FlushPolicy(hold_ms=200))
    g.start()
    # Advance the clock past start so initial last_growth_ms makes sense
    clock.advance(0)
    t.emit("hello")  # no terminator -> held
    check(fk.buffer == "",
          "no flush happens immediately for an unfinished word")
    clock.advance(250)
    g.flush_due()
    check(fk.buffer == "hello",
          "flush_due() pushes pending characters once timeout elapses")


def test_correction_backspaces_then_re_inserts():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    g.start()
    t.emit("recognize ")  # flushed -> "recognize "
    t.emit("recognise ")  # whisper revised: should backspace + retype
    check(fk.buffer == "recognise ",
          f"typer buffer reflects the corrected text (got {fk.buffer!r})")
    # The actual mechanics: at least one backspace + insert happened
    check(any(n > 0 for n in fk.backspaces),
          "at least one backspace fired for the correction")


def test_extension_does_not_emit_backspaces():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    g.start()
    t.emit("hello ")
    t.emit("hello world ")
    check(fk.backspaces == [] or all(n == 0 for n in fk.backspaces),
          "pure extension never backspaces")
    check(fk.buffer == "hello world ",
          "buffer ends up with the extended text")


def test_pending_chars_visible_until_flush():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=10_000))
    g.start()
    t.emit("incomp")
    check(g.pending_chars == "incomp",
          "pending_chars reflects unflushed buffer")
    check(fk.buffer == "",
          "typer hasn't received the unfinished word yet")


def test_stop_flushes_residual_pending_chars():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=10_000))
    g.start()
    t.emit("incomp")  # not flushed yet (no terminator, no timeout)
    final = g.stop()
    check(fk.buffer == "incomp",
          "stop() forces a final flush so 'incomp' lands in the typer")
    check(final == "incomp",
          "stop() returns the final flushed text matching the typer buffer")


def test_partials_dropped_when_inactive():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    # Note: NOT calling start()
    # Manually invoke on_partial to simulate a stale callback
    g.on_partial("ghost message")
    check(fk.buffer == "",
          "on_partial is a no-op while the typer is inactive")


def test_non_string_partials_ignored():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    g.start()
    g.on_partial(None)  # type: ignore[arg-type]
    g.on_partial(123)   # type: ignore[arg-type]
    check(fk.buffer == "",
          "non-string partials are silently ignored, no exception raised")


def test_repeated_identical_partial_is_noop():
    g, t, fk, _ = _build_typer(FlushPolicy(hold_ms=0))
    g.start()
    t.emit("hi ")
    inserts_before = list(fk.inserts)
    t.emit("hi ")
    t.emit("hi ")
    check(fk.inserts == inserts_before,
          "repeated identical partials don't emit redundant inserts")


# ── Schema integration ───────────────────────────────────────────


def test_schema_accepts_start_and_stop_ghost_typing_actions():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "in_progress",
        "message": "Dictation on.",
        "actions": [{"type": "start_ghost_typing"}],
        "confidence": 0.9,
    })
    check(out["valid"] is True and len(out["response"]["actions"]) == 1,
          "start_ghost_typing accepted with no fields")
    out2 = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Stopping.",
        "actions": [{"type": "stop_ghost_typing"}],
        "confidence": 0.9,
    })
    check(out2["valid"] is True and len(out2["response"]["actions"]) == 1,
          "stop_ghost_typing accepted with no fields")


def test_response_format_enum_includes_ghost_typing_actions():
    from core.engine.response_format import build_action_schema
    enum = set(build_action_schema()["properties"]["type"]["enum"])
    check({"start_ghost_typing", "stop_ghost_typing"} <= enum,
          "JSON Schema enum lists both ghost-typing actions")


# ── End-to-end script ──────────────────────────────────────────────


def test_end_to_end_dictation_script():
    """Replay a realistic streaming sequence and assert the final state."""
    g, t, fk, clock = _build_typer(FlushPolicy(hold_ms=200))
    g.start()
    # Mimic whisper: word-by-word with a mid-sentence correction.
    t.emit("how ")
    t.emit("how are ")
    t.emit("how are you ")
    t.emit("how are you doing today ")
    # Whisper revises a word from "today" to "today?"
    t.emit("how are you doing today?")
    # User pauses; force a timer-based flush
    clock.advance(500)
    g.flush_due()
    final = g.stop()
    check(fk.buffer == "how are you doing today?",
          f"end-to-end buffer matches dictation (got {fk.buffer!r})")
    check(final == "how are you doing today?",
          "stop() returns the same final text")


# ── Run ──────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Ghost Typer: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
