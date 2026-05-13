"""
Tests for Activity Tracker + Productivity Roast.

We never start the real sampling thread or call any LLM — every layer
is exercised through injected fakes.

Run:
    .venv\\Scripts\\python scripts\\test_productivity_roast.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.utils.activity_tracker import (
    ActivitySample,
    ActivityStore,
    ActivityTracker,
    ForegroundProbe,
    ForegroundSnapshot,
)
from core.engine.productivity_roast import (
    RoastEngine,
    RoastScheduler,
    RoastStore,
    RoastRecord,
    build_roast_prompt,
    parse_roast_response,
    _format_summary_block,
    _TONE_PRESETS,
    _MIN_TOTAL_MINUTES_FOR_ROAST,
)


# ── Test runner ─────────────────────────────────────────────────────

PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Fakes ───────────────────────────────────────────────────────────


class FakeProbe(ForegroundProbe):
    """ForegroundProbe that returns whatever we set on it."""

    def __init__(self, snapshots: list[ForegroundSnapshot]):
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self) -> ForegroundSnapshot:
        if not self._snapshots:
            return ForegroundSnapshot("", "")
        idx = min(self.calls, len(self._snapshots) - 1)
        self.calls += 1
        return self._snapshots[idx]


def _temp_store_dir() -> str:
    return tempfile.mkdtemp(prefix="ay-eye-activity-")


# ── ActivityStore ───────────────────────────────────────────────────


def test_store_append_creates_per_day_jsonl_file():
    store = ActivityStore(root_dir=_temp_store_dir())
    sample = ActivitySample(
        timestamp=datetime(2026, 5, 13, 14, 0).timestamp(),
        title="Discord", process_name="Discord.exe", interval_s=60.0,
    )
    ok = store.append(sample)
    check(ok is True, "append() returns True on success")
    files = os.listdir(store.root_dir)
    check(any(f == "2026-05-13.jsonl" for f in files),
          "JSONL file is created with the local-day name")


def test_store_round_trip_via_load_day():
    store = ActivityStore(root_dir=_temp_store_dir())
    day = date(2026, 5, 13)
    expected = ActivitySample(
        timestamp=datetime(2026, 5, 13, 14, 0).timestamp(),
        title="VS Code", process_name="Code.exe", interval_s=60.0,
    )
    store.append(expected)
    loaded = store.load_day(day)
    check(len(loaded) == 1, "load_day returns one sample after one append")
    check(loaded[0].title == "VS Code" and loaded[0].process_name == "Code.exe",
          "loaded sample fields match what was written")


def test_store_load_day_handles_missing_file():
    store = ActivityStore(root_dir=_temp_store_dir())
    out = store.load_day(date(2099, 1, 1))
    check(out == [],
          "load_day on a missing file returns an empty list (no crash)")


def test_store_skips_malformed_lines():
    store = ActivityStore(root_dir=_temp_store_dir())
    day = date(2026, 5, 13)
    path = os.path.join(store.root_dir, f"{day.isoformat()}.jsonl")
    os.makedirs(store.root_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"ts":1.0,"title":"OK","process":"a.exe","interval_s":60}\n')
        f.write("not json at all\n")
        f.write('{"ts":2.0,"title":"OK2","process":"b.exe","interval_s":60}\n')
    loaded = store.load_day(day)
    titles = [s.title for s in loaded]
    check(titles == ["OK", "OK2"],
          "malformed lines are skipped, valid ones survive")


# ── ActivityTracker ─────────────────────────────────────────────────


def _frozen_clock(values: list[float]):
    """Return a callable that pops from *values* on each call."""
    state = {"i": 0}
    def _now():
        i = state["i"]
        state["i"] = min(i + 1, len(values) - 1)
        return values[i]
    return _now


def test_tracker_sample_now_persists_and_caches_last():
    store = ActivityStore(root_dir=_temp_store_dir())
    probe = FakeProbe([ForegroundSnapshot("Discord", "Discord.exe")])
    tracker = ActivityTracker(
        store=store, probe=probe, interval_s=60,
        clock=_frozen_clock([1700000000.0, 1700000060.0]),
    )
    s = tracker.sample_now()
    check(s is not None and s.title == "Discord",
          "sample_now returns the captured sample")
    check(tracker.last_sample is not None and tracker.last_sample.title == "Discord",
          "last_sample reflects the most recent capture")


def test_tracker_skips_blank_foreground():
    store = ActivityStore(root_dir=_temp_store_dir())
    probe = FakeProbe([ForegroundSnapshot("", "")])
    tracker = ActivityTracker(
        store=store, probe=probe, interval_s=60,
        clock=_frozen_clock([1700000000.0]),
    )
    s = tracker.sample_now()
    check(s is None,
          "blank foreground snapshot does not write a sample")
    check(os.listdir(store.root_dir) == [],
          "no file is created when there is nothing to record")


def test_tracker_interval_floor_is_five_seconds():
    tracker = ActivityTracker(interval_s=1.0)
    check(tracker.interval_s == 5.0,
          "interval_s is clamped to a 5-second floor (no busy-loop foot-gun)")


def test_tracker_is_running_starts_false():
    tracker = ActivityTracker()
    check(tracker.is_running is False,
          "freshly-constructed tracker reports is_running=False")


# ── daily_summary ───────────────────────────────────────────────────


def test_daily_summary_groups_by_category_using_window_arranger_taxonomy():
    store = ActivityStore(root_dir=_temp_store_dir())
    probe = FakeProbe([])
    tracker = ActivityTracker(store=store, probe=probe, interval_s=60)
    day = date(2026, 5, 13)
    base = datetime.combine(day, datetime.min.time()).timestamp() + 9 * 3600

    samples = [
        ("brain.py - Visual Studio Code", "Code.exe"),
        ("brain.py - Visual Studio Code", "Code.exe"),
        ("#general - Discord", "Discord.exe"),
        ("Reddit - Google Chrome", "chrome.exe"),
        ("Reddit - Google Chrome", "chrome.exe"),
        ("Reddit - Google Chrome", "chrome.exe"),
        ("Spotify Premium", "Spotify.exe"),
    ]
    for i, (title, proc) in enumerate(samples):
        store.append(ActivitySample(
            timestamp=base + i * 60.0,
            title=title, process_name=proc, interval_s=60.0,
        ))

    summary = tracker.daily_summary(day)
    check(summary["samples"] == 7,
          "summary reports correct sample count")
    cat = summary["category_minutes"]
    check(cat.get("ide", 0) == 2.0,
          "two minutes attributed to 'ide' category")
    check(cat.get("chat", 0) == 1.0,
          "one minute attributed to 'chat' category")
    check(cat.get("browser", 0) == 3.0,
          "three minutes attributed to 'browser' category")
    check(cat.get("music", 0) == 1.0,
          "one minute attributed to 'music' category")
    check(summary["total_minutes"] == 7.0,
          "total time = sum of all category minutes")


def test_daily_summary_top_titles_sorted_by_time_spent():
    store = ActivityStore(root_dir=_temp_store_dir())
    probe = FakeProbe([])
    tracker = ActivityTracker(store=store, probe=probe, interval_s=60)
    day = date(2026, 5, 13)
    base = datetime.combine(day, datetime.min.time()).timestamp()

    # Reddit appears 3x, Twitter appears 1x; expect Reddit first.
    for i in range(3):
        store.append(ActivitySample(
            timestamp=base + i, title="Reddit - Chrome",
            process_name="chrome.exe", interval_s=60.0,
        ))
    store.append(ActivitySample(
        timestamp=base + 4, title="Twitter - Chrome",
        process_name="chrome.exe", interval_s=60.0,
    ))
    top = tracker.daily_summary(day)["top_titles"]
    check(top[0]["title"] == "Reddit - Chrome",
          "most-used title appears first in top_titles")
    check(top[0]["minutes"] >= top[1]["minutes"],
          "top_titles is sorted descending by minutes")


def test_daily_summary_empty_day_returns_zero_block():
    tracker = ActivityTracker(store=ActivityStore(root_dir=_temp_store_dir()))
    summary = tracker.daily_summary(date(2099, 1, 1))
    check(summary["total_minutes"] == 0.0 and summary["samples"] == 0,
          "empty day reports zeros without crashing")


# ── _format_summary_block ───────────────────────────────────────────


def test_format_summary_block_includes_total_and_categories():
    summary = {
        "date": "2026-05-13",
        "total_minutes": 312.5,
        "category_minutes": {"ide": 47.0, "browser": 120.5, "chat": 30.0},
        "app_minutes": {"chrome.exe": 90.0, "Code.exe": 47.0},
        "top_titles": [],
        "samples": 312,
    }
    text = _format_summary_block(summary)
    check("DATE: 2026-05-13" in text,
          "summary block includes the date header")
    check("TOTAL_TIME_TRACKED: 312.5 min" in text,
          "summary block includes total minutes")
    check("ide" in text and "browser" in text and "chat" in text,
          "every category appears in the summary block")


def test_format_summary_block_handles_zero_categories():
    summary = {
        "date": "2099-01-01",
        "total_minutes": 0.0,
        "category_minutes": {},
        "app_minutes": {},
        "top_titles": [],
        "samples": 0,
    }
    text = _format_summary_block(summary)
    check("(none)" in text,
          "empty category list rendered as '(none)' instead of crashing")


def test_format_summary_block_caps_apps_at_eight():
    summary = {
        "date": "2026-05-13",
        "total_minutes": 100.0,
        "category_minutes": {},
        "app_minutes": {f"app{i}.exe": 10.0 - i for i in range(20)},
        "top_titles": [],
        "samples": 0,
    }
    text = _format_summary_block(summary)
    # Count "  - app" lines under TOP 8 APPS
    after = text.split("TOP 8 APPS", 1)[1]
    line_count = sum(1 for line in after.splitlines() if line.startswith("  - "))
    check(line_count == 8,
          "summary block lists at most 8 apps")


# ── build_roast_prompt ──────────────────────────────────────────────


def test_build_prompt_default_tone_is_savage():
    out = build_roast_prompt({"date": "x", "category_minutes": {}, "app_minutes": {}})
    check("brutally honest" in out["system"],
          "default tone preset is 'savage'")


def test_build_prompt_unknown_tone_falls_back_to_savage():
    out = build_roast_prompt(
        {"date": "x", "category_minutes": {}, "app_minutes": {}},
        tone="purple-haze",
    )
    check("brutally honest" in out["system"],
          "unknown tone gracefully falls back to 'savage'")


def test_build_prompt_includes_summary_block_in_user_message():
    out = build_roast_prompt({
        "date": "2026-05-13", "total_minutes": 100.0,
        "category_minutes": {"ide": 30.0}, "app_minutes": {"Code.exe": 30.0},
        "top_titles": [], "samples": 100,
    })
    check("2026-05-13" in out["user"],
          "user message contains the formatted summary block")
    check("ide" in out["user"] and "Code.exe" in out["user"],
          "category and app data flow into the user prompt")


def test_build_prompt_demands_json_only_response():
    out = build_roast_prompt({"date": "x", "category_minutes": {}, "app_minutes": {}})
    check('"headline"' in out["system"] and '"roast"' in out["system"],
          "system prompt declares the required JSON keys")
    check("Do not include any prose outside the JSON" in out["system"],
          "system prompt forbids prose around the JSON object")


def test_build_prompt_supports_hinglish_tone():
    out = build_roast_prompt(
        {"date": "x", "category_minutes": {}, "app_minutes": {}},
        tone="hinglish",
    )
    check("Hinglish" in out["system"],
          "hinglish tone preset is wired through")


# ── parse_roast_response ────────────────────────────────────────────


def test_parse_response_strips_markdown_fence():
    raw = '```json\n{"headline":"Lazy day","roast":"meh","stats_callout":"x","tomorrow_nudge":"y"}\n```'
    out = parse_roast_response(raw)
    check(out is not None and out.get("headline") == "Lazy day",
          "JSON inside ```json fence is recovered")


def test_parse_response_extracts_json_with_trailing_text():
    raw = '{"headline":"Hi","roast":"r","stats_callout":"s","tomorrow_nudge":"n"}\n\nHope that helps!'
    out = parse_roast_response(raw)
    check(out is not None and out["roast"] == "r",
          "trailing prose after JSON does not break parsing")


def test_parse_response_returns_none_for_no_json():
    check(parse_roast_response("just a sentence") is None,
          "non-JSON text returns None")
    check(parse_roast_response("") is None,
          "empty string returns None")
    check(parse_roast_response(None) is None,  # type: ignore[arg-type]
          "None input returns None")


def test_parse_response_returns_none_for_array_top_level():
    raw = '["just an array"]'
    check(parse_roast_response(raw) is None,
          "top-level JSON array returns None (we expect an object)")


# ── RoastStore ──────────────────────────────────────────────────────


def test_roast_store_save_and_load_round_trip():
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    rec = RoastRecord(
        day=date(2026, 5, 13), tone="savage",
        summary={"date": "2026-05-13", "total_minutes": 100.0},
        response={"headline": "Lazy", "roast": "meh", "stats_callout": "x", "tomorrow_nudge": "y"},
        timestamp=time.time(),
    )
    ok = store.save(rec)
    check(ok is True, "save returns True")
    loaded = store.load(rec.day)
    check(loaded is not None and loaded.day == rec.day,
          "loaded record day matches original")
    check(loaded is not None and loaded.response["headline"] == "Lazy",
          "response payload survives the round trip")


def test_roast_store_has_roast_correctly_reports_existence():
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    day = date(2026, 5, 13)
    check(store.has_roast(day) is False,
          "has_roast() returns False for an untouched day")
    store.save(RoastRecord(
        day=day, tone="savage", summary={}, response={"x": 1}, timestamp=0.0,
    ))
    check(store.has_roast(day) is True,
          "has_roast() returns True after save()")


# ── RoastScheduler ──────────────────────────────────────────────────


def test_scheduler_returns_none_before_scheduled_time():
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    sched = RoastScheduler(store=store, roast_hour=23, roast_minute=0)
    now = datetime(2026, 5, 13, 22, 30)
    # Mark yesterday as already roasted so we don't catch it as the
    # backfill case.
    store.save(RoastRecord(day=date(2026, 5, 12), tone="savage",
                           summary={}, response={}, timestamp=0.0))
    check(sched.due_for(now) is None,
          "before 23:00, no roast is due")


def test_scheduler_returns_today_after_scheduled_time():
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    sched = RoastScheduler(store=store, roast_hour=23, roast_minute=0)
    now = datetime(2026, 5, 13, 23, 5)
    # Yesterday already roasted -> only today is candidate
    store.save(RoastRecord(day=date(2026, 5, 12), tone="savage",
                           summary={}, response={}, timestamp=0.0))
    check(sched.due_for(now) == date(2026, 5, 13),
          "after 23:00 today's roast becomes due")


def test_scheduler_does_not_double_roast_today():
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    sched = RoastScheduler(store=store, roast_hour=23, roast_minute=0)
    today = date(2026, 5, 13)
    yesterday = today - timedelta(days=1)
    store.save(RoastRecord(day=today, tone="savage", summary={}, response={}, timestamp=0.0))
    store.save(RoastRecord(day=yesterday, tone="savage", summary={}, response={}, timestamp=0.0))
    check(sched.due_for(datetime(2026, 5, 13, 23, 30)) is None,
          "scheduler refuses to roast a day that already has a record")


def test_scheduler_backfills_missed_yesterday():
    """Ay-Eye was offline at 11 PM yesterday. User boots up next morning
    — we should still produce yesterday's roast."""
    store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    sched = RoastScheduler(store=store, roast_hour=23, roast_minute=0)
    now = datetime(2026, 5, 14, 9, 0)  # next morning
    target = sched.due_for(now)
    check(target == date(2026, 5, 13),
          "scheduler returns yesterday when backfill is needed")


def test_scheduler_clamps_invalid_hour_minute():
    sched = RoastScheduler(roast_hour=99, roast_minute=-5)
    check(sched.roast_hour == 23, "hour clamped to <=23")
    check(sched.roast_minute == 0, "minute clamped to >=0")


# ── RoastEngine end-to-end ──────────────────────────────────────────


def _make_engine_with_fakes(today=date(2026, 5, 13), llm_text='{"headline":"X","roast":"Y","stats_callout":"Z","tomorrow_nudge":"W"}'):
    """Build a RoastEngine wired with stubs and pre-seeded activity."""
    activity_dir = _temp_store_dir()
    a_store = ActivityStore(root_dir=activity_dir)
    base = datetime.combine(today, datetime.min.time()).timestamp() + 9 * 3600
    # Seed >30 min of activity so the engine doesn't bail out early.
    for i in range(40):
        a_store.append(ActivitySample(
            timestamp=base + i * 60,
            title="brain.py - Visual Studio Code",
            process_name="Code.exe", interval_s=60.0,
        ))

    tracker = ActivityTracker(store=a_store, probe=FakeProbe([]), interval_s=60)
    r_store = RoastStore(root_dir=tempfile.mkdtemp(prefix="roasts-"))
    sched = RoastScheduler(store=r_store, roast_hour=23, roast_minute=0)

    captured_prompts: list[dict] = []
    def fake_llm(prompt: dict) -> str:
        captured_prompts.append(prompt)
        return llm_text

    engine = RoastEngine(
        tracker=tracker,
        store=r_store,
        scheduler=sched,
        llm_caller=fake_llm,
        clock=lambda: datetime(today.year, today.month, today.day, 23, 30),
    )
    return engine, r_store, captured_prompts


def test_engine_roast_for_writes_record_when_llm_succeeds():
    engine, r_store, prompts = _make_engine_with_fakes()
    rec = engine.roast_for(date(2026, 5, 13), tone="savage")
    check(rec is not None and rec.tone == "savage",
          "roast_for produces a record on the happy path")
    check(r_store.has_roast(date(2026, 5, 13)) is True,
          "the record is persisted to the roast store")
    check(rec is not None and rec.response.get("headline") == "X",
          "parsed LLM response is attached to the record")
    check(len(prompts) == 1,
          "the LLM caller is invoked exactly once")


def test_engine_returns_none_for_under_threshold_activity():
    activity_dir = _temp_store_dir()
    a_store = ActivityStore(root_dir=activity_dir)
    today = date(2026, 5, 13)
    base = datetime.combine(today, datetime.min.time()).timestamp()
    # Only 10 samples = 10 min, below the 30-min threshold
    for i in range(10):
        a_store.append(ActivitySample(
            timestamp=base + i * 60, title="x", process_name="x.exe", interval_s=60.0,
        ))
    tracker = ActivityTracker(store=a_store, probe=FakeProbe([]), interval_s=60)
    engine = RoastEngine(tracker=tracker, llm_caller=lambda p: '{"x":1}',
                         store=RoastStore(root_dir=tempfile.mkdtemp(prefix="r-")),
                         clock=lambda: datetime(today.year, today.month, today.day, 23, 30))
    check(engine.roast_for(today) is None,
          "engine refuses to roast a near-empty day")


def test_engine_returns_none_when_llm_returns_garbage():
    engine, _, _ = _make_engine_with_fakes(llm_text="this isn't json at all")
    rec = engine.roast_for(date(2026, 5, 13))
    check(rec is None,
          "garbage LLM output yields None instead of a malformed record")


def test_engine_returns_none_when_llm_caller_raises():
    activity_dir = _temp_store_dir()
    a_store = ActivityStore(root_dir=activity_dir)
    today = date(2026, 5, 13)
    base = datetime.combine(today, datetime.min.time()).timestamp()
    for i in range(40):
        a_store.append(ActivitySample(
            timestamp=base + i * 60, title="x", process_name="x.exe", interval_s=60.0,
        ))
    tracker = ActivityTracker(store=a_store, probe=FakeProbe([]), interval_s=60)
    def boom(prompt):
        raise RuntimeError("network down")
    engine = RoastEngine(
        tracker=tracker,
        store=RoastStore(root_dir=tempfile.mkdtemp(prefix="r-")),
        llm_caller=boom,
        clock=lambda: datetime(today.year, today.month, today.day, 23, 30),
    )
    check(engine.roast_for(today) is None,
          "LLM exceptions don't crash the engine; roast is silently skipped")


def test_engine_tick_only_fires_when_due():
    today = date(2026, 5, 13)
    engine, r_store, prompts = _make_engine_with_fakes(today=today)
    # Pre-mark today as roasted so tick should be a no-op
    r_store.save(RoastRecord(day=today, tone="savage", summary={}, response={"x": 1}, timestamp=0.0))
    # Yesterday already roasted too
    r_store.save(RoastRecord(day=today - timedelta(days=1), tone="savage", summary={},
                             response={"x": 1}, timestamp=0.0))
    out = engine.tick()
    check(out is None,
          "tick() returns None when no day is due")
    check(len(prompts) == 0,
          "tick() does not invoke the LLM when not due")


def test_engine_tick_fires_for_backfill_yesterday():
    """Boot-after-midnight scenario: yesterday wasn't roasted, do it now."""
    today = date(2026, 5, 14)
    yesterday = today - timedelta(days=1)
    activity_dir = _temp_store_dir()
    a_store = ActivityStore(root_dir=activity_dir)
    # Seed yesterday with enough activity
    base = datetime.combine(yesterday, datetime.min.time()).timestamp()
    for i in range(40):
        a_store.append(ActivitySample(
            timestamp=base + i * 60,
            title="brain.py - Visual Studio Code",
            process_name="Code.exe", interval_s=60.0,
        ))
    tracker = ActivityTracker(store=a_store, probe=FakeProbe([]), interval_s=60)
    r_store = RoastStore(root_dir=tempfile.mkdtemp(prefix="r-"))
    sched = RoastScheduler(store=r_store, roast_hour=23, roast_minute=0)
    captured: list[dict] = []
    def fake_llm(p):
        captured.append(p)
        return '{"headline":"H","roast":"R","stats_callout":"S","tomorrow_nudge":"N"}'
    engine = RoastEngine(
        tracker=tracker, store=r_store, scheduler=sched,
        llm_caller=fake_llm,
        clock=lambda: datetime(today.year, today.month, today.day, 9, 0),
    )
    rec = engine.tick()
    check(rec is not None and rec.day == yesterday,
          "tick() backfills yesterday on next-day startup")
    check(len(captured) == 1,
          "exactly one LLM call made for the backfill")


# ── Run ─────────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Productivity Roast: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
