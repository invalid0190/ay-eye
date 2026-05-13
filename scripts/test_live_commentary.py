"""
Tests for Live Commentary Mode.

Every dependency is faked — no screenshots, no audio, no LLM, no TTS.

Run:
    .venv\\Scripts\\python scripts\\test_live_commentary.py
"""

from __future__ import annotations

import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.engine.live_commentary import (
    CommentaryContext,
    CommentaryReply,
    CommentaryScheduler,
    LiveCommentaryEngine,
    TickOutcome,
    build_commentary_prompt,
    parse_commentary_response,
    hash_image,
    _normalise_for_dedup,
    _NullScreenSampler,
    _NullAudioSampler,
    _NullTextSampler,
)


PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Fakes ──────────────────────────────────────────────────────────


class FakeScreen:
    def __init__(self, frames: list[Optional[bytes]] | None = None):
        self._frames = frames or []
        self.calls = 0

    def capture(self) -> Optional[bytes]:
        if not self._frames:
            return None
        idx = min(self.calls, len(self._frames) - 1)
        self.calls += 1
        return self._frames[idx]


class FakeAudio:
    def __init__(self, transcripts: list[str] | None = None):
        self._transcripts = transcripts or []
        self.calls = 0

    def transcribe_recent(self, seconds: int = 8) -> str:
        if not self._transcripts:
            return ""
        idx = min(self.calls, len(self._transcripts) - 1)
        self.calls += 1
        return self._transcripts[idx]


class FakeText:
    def __init__(self, snapshots: list[str] | None = None):
        self._snapshots = snapshots or []
        self.calls = 0

    def snapshot(self) -> str:
        if not self._snapshots:
            return ""
        idx = min(self.calls, len(self._snapshots) - 1)
        self.calls += 1
        return self._snapshots[idx]


class _ManualClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ── _normalise_for_dedup ───────────────────────────────────────────


def test_normalise_lowercases_and_strips_punctuation():
    check(_normalise_for_dedup("Wow!! That was AMAZING.") == "wow that was amazing",
          "punctuation stripped, case normalised")


def test_normalise_collapses_internal_whitespace():
    check(_normalise_for_dedup("hello   world\n\n!") == "hello world",
          "internal whitespace collapsed and trailing punctuation removed")


def test_normalise_handles_empty_or_non_strings():
    check(_normalise_for_dedup("") == "",
          "empty string -> empty")
    check(_normalise_for_dedup(None) == "",  # type: ignore[arg-type]
          "non-string -> empty")


# ── hash_image ─────────────────────────────────────────────────────


def test_hash_image_returns_stable_short_digest():
    h1 = hash_image(b"abc")
    h2 = hash_image(b"abc")
    check(h1 == h2 and len(h1) == 16,
          "identical bytes -> identical 16-char hex digest")
    check(hash_image(b"abc") != hash_image(b"abd"),
          "different bytes -> different digest")
    check(hash_image(None) == "",
          "None bytes -> empty hash")
    check(hash_image(b"") == "",
          "empty bytes -> empty hash")


# ── CommentaryScheduler ────────────────────────────────────────────


def _ctx(image=b"frame", audio="hello", text="", t=1000.0) -> CommentaryContext:
    return CommentaryContext(
        image_hash=hash_image(image),
        image_bytes=image or b"",
        audio_text=audio,
        visible_text=text,
        timestamp=t,
    )


def test_scheduler_first_frame_is_always_allowed():
    sched = CommentaryScheduler(min_interval_s=25.0)
    ok, reason = sched.should_consider(_ctx(t=1000.0))
    check(ok is True and reason == "ok",
          "first call passes the rate limiter")


def test_scheduler_rate_limits_consecutive_calls():
    sched = CommentaryScheduler(min_interval_s=25.0)
    ctx = _ctx(t=1000.0)
    sched.remember_commented(ctx, "first line")
    ok, reason = sched.should_consider(_ctx(image=b"diff", t=1010.0))  # 10s later
    check(ok is False and reason == "rate_limited",
          "calls within min_interval_s are rejected")


def test_scheduler_allows_after_interval_elapses():
    sched = CommentaryScheduler(min_interval_s=25.0)
    sched.remember_commented(_ctx(t=1000.0), "first")
    ok, reason = sched.should_consider(_ctx(image=b"diff", t=1030.0))
    check(ok is True and reason == "ok",
          "calls past min_interval_s pass the rate limiter")


def test_scheduler_rejects_duplicate_frame_hash():
    sched = CommentaryScheduler(min_interval_s=25.0)
    sched.remember_commented(_ctx(image=b"same", t=1000.0), "x")
    ok, reason = sched.should_consider(_ctx(image=b"same", t=1100.0))
    check(ok is False and reason == "duplicate_frame",
          "identical frame hash -> 'duplicate_frame'")


def test_scheduler_dedup_history_evicts_oldest():
    sched = CommentaryScheduler(min_interval_s=25.0, dedup_history=2)
    for i, b in enumerate([b"a", b"b", b"c"]):
        sched.remember_commented(_ctx(image=b, t=1000.0 + i * 100), f"line {i}")
    # Hash for b"a" should have been evicted; commenting on it again should be allowed
    ok, _ = sched.should_consider(_ctx(image=b"a", t=2000.0))
    check(ok is True,
          "oldest hash evicted from dedup history")


def test_scheduler_rejects_empty_context():
    sched = CommentaryScheduler(min_interval_s=0.0)
    ctx = CommentaryContext(image_hash="", image_bytes=b"",
                            audio_text="", visible_text="", timestamp=1000.0)
    ok, reason = sched.should_consider(ctx)
    check(ok is False and reason == "empty_context",
          "no image, no audio, no text -> 'empty_context'")


def test_scheduler_is_recent_line_uses_normalised_match():
    sched = CommentaryScheduler()
    sched.remember_commented(_ctx(t=1000.0), "Wow, that was amazing!")
    check(sched.is_recent_line("WOW that was AMAZING") is True,
          "case + punctuation differences still detect duplicate line")
    check(sched.is_recent_line("totally different") is False,
          "novel line is not flagged as recent")


# ── build_commentary_prompt ───────────────────────────────────────


def test_prompt_default_tone_is_buddy():
    out = build_commentary_prompt(_ctx(audio="hi"))
    check("witty best friend" in out["system"],
          "default tone preset is 'buddy'")


def test_prompt_unknown_tone_falls_back_to_buddy():
    out = build_commentary_prompt(_ctx(audio="hi"), tone="banana")
    check("witty best friend" in out["system"],
          "unknown tone falls back to 'buddy'")


def test_prompt_user_message_includes_audio_and_text():
    ctx = _ctx(audio="someone said hi", text="The screen says HELLO")
    out = build_commentary_prompt(ctx)
    check("RECENT_AUDIO" in out["user"] and "someone said hi" in out["user"],
          "audio context surfaced under RECENT_AUDIO")
    check("VISIBLE_TEXT" in out["user"] and "HELLO" in out["user"],
          "visible text surfaced under VISIBLE_TEXT")


def test_prompt_user_message_falls_back_when_no_audio_or_text():
    ctx = _ctx(audio="", text="")
    out = build_commentary_prompt(ctx)
    check("no audio or visible-text context" in out["user"],
          "fallback line is used when only the screenshot is available")


def test_prompt_visible_text_truncated():
    long_text = "x" * 2000
    ctx = _ctx(audio="", text=long_text)
    out = build_commentary_prompt(ctx)
    check(len(out["user"]) < 2000 and "…" in out["user"],
          "visible text truncated past 800 chars with ellipsis")


def test_prompt_demands_strict_json_response():
    out = build_commentary_prompt(_ctx())
    keys = ('"line"', '"energy"', '"skip"', '"confidence"')
    check(all(k in out["system"] for k in keys),
          "system prompt declares all four required keys")
    check("Do not include any prose outside the JSON" in out["system"],
          "system prompt forbids prose around JSON")


# ── parse_commentary_response ─────────────────────────────────────


def test_parse_response_happy_path():
    raw = '{"line":"that was wild","energy":"shocked","skip":false,"confidence":0.9}'
    r = parse_commentary_response(raw)
    check(r is not None and r.line == "that was wild" and r.energy == "shocked"
          and r.skip is False and abs(r.confidence - 0.9) < 1e-6,
          "valid JSON parsed into CommentaryReply")


def test_parse_response_strips_markdown_fence():
    raw = '```json\n{"line":"hi","energy":"calm","skip":false,"confidence":0.5}\n```'
    r = parse_commentary_response(raw)
    check(r is not None and r.line == "hi",
          "markdown-fenced JSON recovered")


def test_parse_response_truncates_overlong_lines():
    raw = '{"line":"' + "a" * 500 + '","energy":"calm","skip":false,"confidence":0.5}'
    r = parse_commentary_response(raw)
    check(r is not None and len(r.line) <= 220,
          "lines longer than 220 chars get truncated")
    check(r is not None and r.line.endswith("…"),
          "truncated line ends with ellipsis")


def test_parse_response_clamps_confidence():
    raw = '{"line":"ok","energy":"calm","skip":false,"confidence":2.0}'
    r = parse_commentary_response(raw)
    check(r is not None and r.confidence == 1.0,
          "confidence > 1 clamped to 1.0")
    raw2 = '{"line":"ok","energy":"calm","skip":false,"confidence":-0.5}'
    r2 = parse_commentary_response(raw2)
    check(r2 is not None and r2.confidence == 0.0,
          "confidence < 0 clamped to 0.0")


def test_parse_response_promotes_blank_line_to_skip():
    raw = '{"line":"","energy":"calm","skip":false,"confidence":0.5}'
    r = parse_commentary_response(raw)
    check(r is not None and r.skip is True,
          "empty line + skip=false coerced to skip=true (don't speak nothing)")


def test_parse_response_handles_explicit_skip():
    raw = '{"line":"","energy":"calm","skip":true,"confidence":0.4}'
    r = parse_commentary_response(raw)
    check(r is not None and r.skip is True,
          "explicit skip=true survives parsing")


def test_parse_response_returns_none_for_garbage():
    check(parse_commentary_response("just prose") is None,
          "non-JSON returns None")
    check(parse_commentary_response("") is None,
          "empty string returns None")
    check(parse_commentary_response(None) is None,  # type: ignore[arg-type]
          "non-string returns None")


def test_parse_response_returns_none_for_array_top_level():
    check(parse_commentary_response('["ignore me"]') is None,
          "top-level array returns None")


# ── Engine.tick() ──────────────────────────────────────────────────


def _build_engine(
    frames=(b"frame_a",), audio=("you hear something",), text=("on screen",),
    llm_response='{"line":"That was wild!","energy":"shocked","skip":false,"confidence":0.9}',
    llm_should_raise=False,
    speak_fn=None,
):
    captured_prompts: list[dict] = []
    captured_images: list[bytes] = []

    def _llm(prompt, image_bytes):
        captured_prompts.append(prompt)
        captured_images.append(image_bytes)
        if llm_should_raise:
            raise RuntimeError("network down")
        return llm_response

    clock = _ManualClock(1000.0)
    spoken: list[CommentaryReply] = []
    if speak_fn is None:
        def _speak(reply):
            spoken.append(reply)
        speak_fn = _speak

    eng = LiveCommentaryEngine(
        screen_sampler=FakeScreen(list(frames)),
        audio_sampler=FakeAudio(list(audio)),
        text_sampler=FakeText(list(text)),
        scheduler=CommentaryScheduler(min_interval_s=25.0),
        llm_caller=_llm,
        speak_fn=speak_fn,
        clock=clock,
    )
    return eng, captured_prompts, captured_images, spoken, clock


def test_tick_when_inactive_returns_not_active():
    eng, _, _, _, _ = _build_engine()
    out = eng.tick()
    check(out.fired is False and out.reason == "not_active",
          "tick() before start() returns reason='not_active'")


def test_tick_happy_path_speaks_and_remembers():
    eng, prompts, images, spoken, clock = _build_engine()
    eng.start()
    out = eng.tick()
    check(out.fired is True and out.reason == "ok",
          "first tick fires successfully")
    check(out.reply is not None and out.reply.line == "That was wild!",
          "reply.line attached to outcome")
    check(len(spoken) == 1,
          "speak_fn called exactly once")
    check(len(prompts) == 1 and len(images) == 1,
          "LLM called exactly once with image bytes attached")
    check(images[0] == b"frame_a",
          "image bytes forwarded to LLM caller verbatim")


def test_tick_rate_limits_back_to_back_calls():
    eng, _, _, spoken, clock = _build_engine(
        frames=(b"a", b"b"),
        audio=("first audio", "second audio"),
    )
    eng.start()
    eng.tick()
    clock.advance(5.0)  # only 5s later — under min_interval_s
    out = eng.tick()
    check(out.fired is False and out.reason == "rate_limited",
          "second tick within rate-limit window returns 'rate_limited'")
    check(len(spoken) == 1,
          "speak_fn was not called the second time")


def test_tick_skips_duplicate_frame_hash():
    eng, _, _, spoken, clock = _build_engine(
        frames=(b"same", b"same"),
        audio=("a1", "a2"),
    )
    eng.start()
    eng.tick()
    clock.advance(60.0)  # past rate limit
    out = eng.tick()
    check(out.fired is False and out.reason == "duplicate_frame",
          "second tick on identical frame returns 'duplicate_frame'")


def test_tick_handles_llm_exception_gracefully():
    eng, _, _, spoken, _ = _build_engine(llm_should_raise=True)
    eng.start()
    out = eng.tick()
    check(out.fired is False and out.reason.startswith("llm_error"),
          "LLM exception captured via reason without crashing tick()")
    check(len(spoken) == 0,
          "speak_fn not called when LLM raises")


def test_tick_handles_unparseable_llm_response():
    eng, _, _, spoken, _ = _build_engine(llm_response="garbage prose")
    eng.start()
    out = eng.tick()
    check(out.fired is False and out.reason == "llm_unparseable",
          "non-JSON LLM reply -> reason='llm_unparseable'")
    check(len(spoken) == 0,
          "speak_fn not called for unparseable replies")


def test_tick_respects_model_skip_flag():
    skip_response = '{"line":"","energy":"calm","skip":true,"confidence":0.3}'
    eng, _, _, spoken, _ = _build_engine(llm_response=skip_response)
    eng.start()
    out = eng.tick()
    check(out.fired is False and out.reason == "model_skipped",
          "skip=true reply reports reason='model_skipped'")
    check(len(spoken) == 0,
          "speak_fn not called when model skips")


def test_tick_dedups_repeated_lines():
    """Even if the model wants to speak, repeating a recent line is suppressed."""
    eng, _, _, spoken, clock = _build_engine(
        frames=(b"a", b"b"),  # different hashes so frame dedup doesn't fire
        audio=("hi", "hi again"),
        llm_response='{"line":"That was wild!","energy":"shocked","skip":false,"confidence":0.9}',
    )
    eng.start()
    eng.tick()  # speaks "That was wild!"
    clock.advance(60.0)
    out = eng.tick()  # would say the same thing
    check(out.fired is False and out.reason == "repeat_line",
          "exact-repeat line is suppressed via 'repeat_line'")
    check(len(spoken) == 1,
          "speak_fn was called only once across the two ticks")


def test_tick_skips_when_no_llm_caller():
    eng = LiveCommentaryEngine(
        screen_sampler=FakeScreen([b"a"]),
        audio_sampler=FakeAudio(["hi"]),
        text_sampler=FakeText([""]),
        scheduler=CommentaryScheduler(min_interval_s=0.0),
        llm_caller=None,
    )
    eng.start()
    out = eng.tick()
    check(out.fired is False and out.reason == "llm_unavailable",
          "no LLM caller -> reason='llm_unavailable'")


def test_lifecycle_double_start_returns_false():
    eng, _, _, _, _ = _build_engine()
    eng.start()
    check(eng.start() is False,
          "second start() while active returns False")


def test_lifecycle_stop_idempotent():
    eng, _, _, _, _ = _build_engine()
    eng.stop()  # not started — must not raise
    eng.start()
    eng.stop()
    eng.stop()  # double stop — must not raise
    check(eng.is_active is False,
          "engine is_active False after stop, even on repeated stop")


# ── Schema integration ────────────────────────────────────────────


def test_schema_accepts_start_and_stop_live_commentary_actions():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "in_progress",
        "message": "Watching with you.",
        "actions": [{"type": "start_live_commentary", "tone": "buddy"}],
        "confidence": 0.9,
    })
    check(out["valid"] is True and len(out["response"]["actions"]) == 1,
          "start_live_commentary accepted")
    out2 = response_schema.validate({
        "intent": "act",
        "status": "complete",
        "message": "Stopping.",
        "actions": [{"type": "stop_live_commentary"}],
        "confidence": 0.9,
    })
    check(out2["valid"] is True and len(out2["response"]["actions"]) == 1,
          "stop_live_commentary accepted")


def test_response_format_enum_includes_live_commentary_actions():
    from core.engine.response_format import build_action_schema
    enum = set(build_action_schema()["properties"]["type"]["enum"])
    check({"start_live_commentary", "stop_live_commentary"} <= enum,
          "JSON Schema enum lists both live commentary actions")


# ── Run ─────────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Live Commentary: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
