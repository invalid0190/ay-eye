"""
Live Commentary Mode
====================

The user fires up YouTube / Twitch / a Zoom call and says "watch with
me". Ay-Eye periodically captures a screenshot + a few seconds of
desktop audio context, asks Claude (or whichever LLM) to react like
a witty friend, and speaks the result.

Design goals
------------
The whole feature splits into three layers, each independently
testable:

1. **Capture layer** — screenshot + system-audio sampling. WASAPI
   loopback + ``mss`` are heavy and platform-bound, so this layer is
   wired through tiny protocols. Tests pass in fakes; production
   can be plugged in at install time.

2. **Scheduling + dedup layer** (``CommentaryScheduler``) — decides
   *whether* to comment on the current frame. Skips:
   - frames whose perceptual hash is identical to the last 3 we
     commented on (silent video, paused content),
   - frames captured less than ``min_interval_s`` after the previous
     commentary (rate limiting),
   - frames whose extracted-text snapshot matches a previously-spoken
     line (Whisper transcripts often repeat).

3. **Prompt + parsing layer** (pure functions) — ``build_commentary_prompt``
   and ``parse_commentary_response``. Strict JSON shape so tests can
   assert correctness without hitting an LLM.

The orchestrator (``LiveCommentaryEngine``) glues them together and
exposes ``start()`` / ``stop()`` / ``tick()``. ``tick()`` is the unit
of work — caller drives it on whatever cadence they want (a Qt timer,
a cron-like loop, or test code).

The TTS playback is delegated to a caller-supplied ``speak`` callback,
so the existing OpenAI TTS pipeline plugs in without coupling.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from core.utils.logger import logger


# ── Public data types ────────────────────────────────────────────────


@dataclass
class CommentaryContext:
    """One frame's worth of input to the LLM."""

    image_hash: str        # perceptual / sha hash of the captured image
    image_bytes: bytes     # raw screenshot for the LLM (vision-enabled)
    audio_text: str        # transcribed snippet of recent system audio
    visible_text: str      # OCR snippet of what's on screen (optional)
    timestamp: float


@dataclass
class CommentaryReply:
    """LLM-produced reaction."""

    line: str              # what to speak
    energy: str = "calm"   # "calm" | "amused" | "shocked" | ...
    skip: bool = False     # True if the model decided to stay silent
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "energy": self.energy,
            "skip": bool(self.skip),
            "confidence": float(self.confidence),
        }


# ── Capture protocols ────────────────────────────────────────────────


class ScreenSampler(Protocol):
    def capture(self) -> Optional[bytes]: ...


class AudioSampler(Protocol):
    def transcribe_recent(self, seconds: int = 8) -> str: ...


class TextSampler(Protocol):
    """OCR or accessibility-tree snapshot of the visible app."""

    def snapshot(self) -> str: ...


class _NullScreenSampler:
    def capture(self) -> Optional[bytes]:
        return None


class _NullAudioSampler:
    def transcribe_recent(self, seconds: int = 8) -> str:
        return ""


class _NullTextSampler:
    def snapshot(self) -> str:
        return ""


# ── Scheduling + dedup ───────────────────────────────────────────────


_DEFAULT_MIN_INTERVAL_S = 25.0   # never comment more often than this
_DEFAULT_DEDUP_HISTORY = 4        # how many recent hashes to remember
_DEFAULT_RECENT_LINES = 4         # how many recent spoken lines to keep
_MAX_LINE_LENGTH = 220            # don't speak essays


class CommentaryScheduler:
    """Owns 'should we comment now?' policy."""

    def __init__(
        self,
        min_interval_s: float = _DEFAULT_MIN_INTERVAL_S,
        dedup_history: int = _DEFAULT_DEDUP_HISTORY,
        recent_lines: int = _DEFAULT_RECENT_LINES,
    ):
        self.min_interval_s = float(min_interval_s)
        self.dedup_history = int(dedup_history)
        self.recent_lines = int(recent_lines)
        self._last_spoken_at: float = 0.0
        self._recent_hashes: list[str] = []
        self._recent_lines_lc: list[str] = []

    # ── Inputs ──────────────────────────────────────────────────────

    def remember_commented(self, ctx: CommentaryContext, line: str) -> None:
        self._last_spoken_at = ctx.timestamp
        if ctx.image_hash:
            self._recent_hashes.append(ctx.image_hash)
            self._recent_hashes = self._recent_hashes[-self.dedup_history:]
        normalised = _normalise_for_dedup(line)
        if normalised:
            self._recent_lines_lc.append(normalised)
            self._recent_lines_lc = self._recent_lines_lc[-self.recent_lines:]

    # ── Decisions ───────────────────────────────────────────────────

    def should_consider(self, ctx: CommentaryContext) -> tuple[bool, str]:
        """Returns ``(allowed, reason)``.

        ``allowed=False`` means the frame should be skipped without
        even calling the LLM. ``reason`` is a short label for logs / tests.
        """
        # Rate limit
        if (ctx.timestamp - self._last_spoken_at) < self.min_interval_s:
            return False, "rate_limited"
        # Duplicate frame (paused video etc.)
        if ctx.image_hash and ctx.image_hash in self._recent_hashes:
            return False, "duplicate_frame"
        # No content at all to react to
        if not ctx.audio_text and not ctx.visible_text and not ctx.image_bytes:
            return False, "empty_context"
        return True, "ok"

    def is_recent_line(self, line: str) -> bool:
        n = _normalise_for_dedup(line)
        return bool(n) and n in self._recent_lines_lc


def _normalise_for_dedup(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Lowercase, collapse whitespace + punctuation; this catches near
    # duplicates the LLM produces when it sees the same scene.
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ── Prompt + parsing ────────────────────────────────────────────────


_TONE_PRESETS: dict[str, str] = {
    "buddy": (
        "You are the user's witty best friend watching content with them. "
        "React in 1-2 short sentences max. Be observant, specific, "
        "playful, never obnoxious. Hindi/Hinglish is welcome if the "
        "audio context implies the user prefers it. If nothing "
        "interesting is happening, say nothing — return skip=true."
    ),
    "analyst": (
        "You are a thoughtful analyst watching content with the user. "
        "Surface ONE substantive observation per frame: a fact, a "
        "contradiction, a connection. 1-2 sentences. Skip empty frames."
    ),
    "hype": (
        "You are an enthusiastic gamer / streamer hype-buddy. Short, "
        "punchy reactions only. 1 sentence. Skip empty frames."
    ),
}


def build_commentary_prompt(ctx: CommentaryContext, tone: str = "buddy") -> dict:
    """Build the LLM prompt for one commentary turn.

    The image bytes are NOT included here — the bridge attaches them
    as a vision payload separately. We surface the audio + visible
    text so even text-only models can give a reasonable line.
    """
    tone_key = tone if tone in _TONE_PRESETS else "buddy"
    system = (
        _TONE_PRESETS[tone_key]
        + "\n\nReturn ONLY a JSON object with these keys:\n"
        '  "line": the sentence to speak (<= 220 chars)\n'
        '  "energy": "calm" | "amused" | "shocked" | "curious" | "hype"\n'
        '  "skip": boolean. true if you have nothing worthwhile to say.\n'
        '  "confidence": float 0-1.\n'
        "Do not include any prose outside the JSON object. Never repeat "
        "yourself; assume the user remembers your last few lines."
    )
    parts = []
    if ctx.audio_text:
        parts.append("RECENT_AUDIO:\n" + ctx.audio_text.strip())
    if ctx.visible_text:
        snippet = ctx.visible_text.strip()
        if len(snippet) > 800:
            snippet = snippet[:800] + " …"
        parts.append("VISIBLE_TEXT:\n" + snippet)
    if not parts:
        parts.append("(no audio or visible-text context provided; rely on the screenshot)")
    user = "\n\n".join(parts)
    return {"system": system, "user": user}


def parse_commentary_response(raw: str) -> Optional[CommentaryReply]:
    """Best-effort JSON extraction → ``CommentaryReply``."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        d = json.loads(text[start: end + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None

    skip = bool(d.get("skip", False))
    line = str(d.get("line", "")).strip()
    if len(line) > _MAX_LINE_LENGTH:
        # Reserve one slot for the ellipsis so the final length is
        # strictly <= _MAX_LINE_LENGTH (the API contract callers rely on).
        line = line[: _MAX_LINE_LENGTH - 1].rstrip() + "…"
    energy = str(d.get("energy", "calm")).strip().lower() or "calm"
    try:
        confidence = float(d.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if not skip and not line:
        # Model didn't return a usable line and didn't explicitly skip.
        # Treat as a skip to avoid speaking empty TTS.
        skip = True

    return CommentaryReply(line=line, energy=energy, skip=skip, confidence=confidence)


# ── Engine ───────────────────────────────────────────────────────────


CommentaryLLM = Callable[[dict, bytes], str]
SpeakFn = Callable[[CommentaryReply], None]


@dataclass
class TickOutcome:
    """What ``tick()`` did this round (used by tests + logs)."""

    fired: bool = False
    reason: str = ""
    reply: Optional[CommentaryReply] = None


def hash_image(image_bytes: Optional[bytes]) -> str:
    """Stable short hash so the scheduler can dedup identical frames."""
    if not image_bytes:
        return ""
    return hashlib.sha1(image_bytes).hexdigest()[:16]


class LiveCommentaryEngine:
    """Glue layer used by the executor."""

    def __init__(
        self,
        screen_sampler: ScreenSampler | None = None,
        audio_sampler: AudioSampler | None = None,
        text_sampler: TextSampler | None = None,
        scheduler: CommentaryScheduler | None = None,
        llm_caller: CommentaryLLM | None = None,
        speak_fn: SpeakFn | None = None,
        clock: Callable[[], float] = time.time,
        tone: str = "buddy",
    ):
        self.screen_sampler = screen_sampler or _NullScreenSampler()
        self.audio_sampler = audio_sampler or _NullAudioSampler()
        self.text_sampler = text_sampler or _NullTextSampler()
        self.scheduler = scheduler or CommentaryScheduler()
        self.llm_caller = llm_caller
        self.speak_fn = speak_fn
        self.clock = clock
        self.tone = tone
        self._active = False

    # ── Lifecycle ────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> bool:
        if self._active:
            return False
        self._active = True
        logger.logger.info(f"LiveCommentary: started (tone={self.tone})")
        return True

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        logger.logger.info("LiveCommentary: stopped")

    # ── One iteration ────────────────────────────────────────────────

    def tick(self) -> TickOutcome:
        if not self._active:
            return TickOutcome(fired=False, reason="not_active")

        # 1. Capture context.
        try:
            image = self.screen_sampler.capture()
        except Exception as e:
            logger.logger.warning(f"LiveCommentary: screen capture failed: {e}")
            image = None
        try:
            audio_text = self.audio_sampler.transcribe_recent() or ""
        except Exception as e:
            logger.logger.warning(f"LiveCommentary: audio transcribe failed: {e}")
            audio_text = ""
        try:
            visible_text = self.text_sampler.snapshot() or ""
        except Exception as e:
            logger.logger.warning(f"LiveCommentary: text snapshot failed: {e}")
            visible_text = ""

        ctx = CommentaryContext(
            image_hash=hash_image(image),
            image_bytes=image or b"",
            audio_text=audio_text,
            visible_text=visible_text,
            timestamp=self.clock(),
        )

        # 2. Scheduler veto (rate limit / dedup / empty).
        allowed, reason = self.scheduler.should_consider(ctx)
        if not allowed:
            return TickOutcome(fired=False, reason=reason)

        # 3. LLM call.
        if self.llm_caller is None:
            return TickOutcome(fired=False, reason="llm_unavailable")

        prompt = build_commentary_prompt(ctx, tone=self.tone)
        try:
            raw = self.llm_caller(prompt, ctx.image_bytes)
        except Exception as e:
            logger.logger.warning(f"LiveCommentary: LLM call failed: {e}")
            return TickOutcome(fired=False, reason=f"llm_error:{e!r}")

        reply = parse_commentary_response(raw or "")
        if reply is None:
            return TickOutcome(fired=False, reason="llm_unparseable")

        if reply.skip:
            return TickOutcome(fired=False, reason="model_skipped", reply=reply)

        # 4. Post-LLM dedup (model sometimes echoes its last line).
        if self.scheduler.is_recent_line(reply.line):
            return TickOutcome(fired=False, reason="repeat_line", reply=reply)

        # 5. Speak.
        if self.speak_fn is not None:
            try:
                self.speak_fn(reply)
            except Exception as e:
                logger.logger.warning(f"LiveCommentary: speak_fn failed: {e}")

        # 6. Remember so we don't repeat / overflow.
        self.scheduler.remember_commented(ctx, reply.line)
        logger.logger.info(
            f"LiveCommentary: spoke ({reply.energy}, "
            f"confidence={reply.confidence:.2f}): {reply.line[:80]}"
        )
        return TickOutcome(fired=True, reason="ok", reply=reply)


# Module-level singleton (no real backends wired by default).
live_commentary = LiveCommentaryEngine()
