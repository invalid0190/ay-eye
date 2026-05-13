"""Regression tests for core/utils/telemetry.py.

Covers:
  * Pricing math for known and unknown models.
  * start/record/end_turn produces a TURN_METRICS bus event.
  * Totals accumulate across turns.
  * Rolling window keeps only the last N entries.
  * Section timings are stored alongside LLM timings.
  * Rolling averages reflect recent turns only.
  * reset() clears everything.

Run:
    .venv\\Scripts\\python scripts\\test_telemetry.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.event_bus import bus
from core.utils.telemetry import TelemetryService, telemetry  # noqa: F401


PASS = []
FAIL = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_pricing_known_model():
    t = TelemetryService()
    cost = t.cost_for("gpt-4o", 1000, 1000)
    check(approx(cost, 0.0025 + 0.0100), "gpt-4o cost = prompt + completion per 1k")


def test_pricing_unknown_model_falls_back_to_zero_or_prefix():
    t = TelemetryService()
    cost = t.cost_for("totally-made-up-model", 5000, 5000)
    check(cost == 0.0, "unknown model with no prefix match -> 0 cost")
    cost_prefix = t.cost_for("gpt-4o-2025-12-31", 1000, 0)
    check(approx(cost_prefix, 0.0025), "gpt-4o-* prefix match uses gpt-4o pricing")


def test_pricing_override():
    t = TelemetryService()
    t.set_price("custom-model", 0.001, 0.002)
    check(approx(t.cost_for("custom-model", 1000, 1000), 0.003), "set_price override applied")


def test_turn_lifecycle_publishes_event():
    t = TelemetryService()
    received = []
    bus.subscribe("TURN_METRICS", lambda d: received.append(d))

    tid = t.start_turn()
    t.record_llm(tid, "openai", "gpt-4o", prompt_tokens=500, completion_tokens=200, duration_ms=1234, vision=True)
    snapshot = t.end_turn(tid)

    check(snapshot is not None, "end_turn returns the snapshot")
    check(snapshot["prompt_tokens"] == 500 and snapshot["completion_tokens"] == 200, "tokens recorded")
    check(snapshot["llm_ms"] == 1234, "llm_ms recorded")
    check(snapshot["vision"] is True, "vision flag recorded")
    check(approx(snapshot["cost_usd"], (500 / 1000) * 0.0025 + (200 / 1000) * 0.0100), "cost computed")
    check(snapshot["total_ms"] >= 0, "total_ms is non-negative")
    check(any(d.get("id") == tid for d in received), "TURN_METRICS event published with matching id")


def test_section_timings():
    t = TelemetryService()
    tid = t.start_turn()
    t.record_section(tid, "ocr", 42)
    t.record_section(tid, "ocr", 8)        # additive
    t.record_section(tid, "tts", 100)
    snap = t.end_turn(tid)
    check(snap["sections"].get("ocr") == 50, "section timings sum across record_section calls")
    check(snap["sections"].get("tts") == 100, "second section recorded independently")


def test_totals_accumulate():
    t = TelemetryService()
    for tokens in (100, 200, 300):
        tid = t.start_turn()
        t.record_llm(tid, "openai", "gpt-4o", prompt_tokens=tokens, completion_tokens=tokens, duration_ms=10)
        t.end_turn(tid)
    s = t.stats()
    check(s["turns"] == 3, "totals.turns counts every ended turn")
    check(s["prompt_tokens"] == 600 and s["completion_tokens"] == 600, "token totals accumulate")
    check(s["last_turn"] is not None and s["last_turn"]["prompt_tokens"] == 300, "last_turn snapshot exposes the most recent turn")


def test_rolling_window_caps():
    t = TelemetryService(window_size=3)
    for i in range(5):
        tid = t.start_turn()
        t.record_llm(tid, "openai", "gpt-4o", prompt_tokens=i + 1, completion_tokens=0, duration_ms=10)
        t.end_turn(tid)
    s = t.stats()
    # Totals span every turn ever recorded, but the rolling deque only keeps the last 3.
    check(s["turns"] == 5, "totals.turns spans full history")
    check(t._turns and len(t._turns) == 3, "rolling window capped at window_size")
    check(t._turns[-1]["prompt_tokens"] == 5, "rolling window keeps newest")


def test_avg_uses_recent_turns():
    t = TelemetryService(window_size=3)
    for ms in (1000, 2000, 3000):
        tid = t.start_turn()
        t.record_llm(tid, "openai", "gpt-4o", prompt_tokens=0, completion_tokens=0, duration_ms=ms)
        # Force total_ms to be at least ms by sleeping a hair.
        time.sleep(0.001)
        t.end_turn(tid)
    s = t.stats()
    check(s["avg_llm_ms"] == 2000, "avg_llm_ms is the mean of the rolling window")


def test_reset_clears_everything():
    t = TelemetryService()
    tid = t.start_turn()
    t.record_llm(tid, "openai", "gpt-4o", 10, 10, 10)
    t.end_turn(tid)
    t.reset()
    s = t.stats()
    check(s["turns"] == 0 and s["last_turn"] is None, "reset clears totals and rolling window")


def test_record_after_end_is_noop():
    t = TelemetryService()
    tid = t.start_turn()
    t.end_turn(tid)
    # Recording after end should not raise or pollute.
    t.record_llm(tid, "openai", "gpt-4o", 10, 10, 10)
    t.record_section(tid, "ocr", 10)
    s = t.stats()
    check(s["turns"] == 1, "post-end record_llm is a no-op (turn already counted)")


# -------- runner ---------------------------------------------------------

def main():
    test_pricing_known_model()
    test_pricing_unknown_model_falls_back_to_zero_or_prefix()
    test_pricing_override()
    test_turn_lifecycle_publishes_event()
    test_section_timings()
    test_totals_accumulate()
    test_rolling_window_caps()
    test_avg_uses_recent_turns()
    test_reset_clears_everything()
    test_record_after_end_is_noop()

    print(f"\n=== Telemetry: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
