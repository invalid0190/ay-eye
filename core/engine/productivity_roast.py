"""
Productivity Roast — daily savage report.

Once a day (configurable, default 23:00 local) we aggregate the activity
tracker's samples into a category breakdown and ask the LLM to produce
a brutally-honest, faintly-funny accountability roast in the user's
preferred language. The roast is saved to ``analytics/roasts/`` and
played back through the existing TTS pipeline.

Architecture
------------
* ``RoastScheduler`` decides *when* to roast. It can be polled (the
  recommended pattern: tick every minute, ask "is it time?") or driven
  manually for tests / on-demand voice commands.
* ``build_roast_prompt`` / ``parse_roast_response`` are pure functions
  the unit tests exercise without touching an LLM.
* ``RoastEngine`` glues everything together and is the singleton the
  rest of the app calls.

The engine never imports the LLM bridge or TTS at module load. We
late-bind both so tests can run on a machine with no API keys.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from typing import Callable, Optional

from core.utils.activity_tracker import activity_tracker, ActivityTracker
from core.utils.logger import logger


_DEFAULT_ROAST_HOUR = 23  # 11 PM local
_DEFAULT_ROAST_MINUTE = 0
_DEFAULT_ROAST_DIR = os.path.join(os.getcwd(), "analytics", "roasts")
_MIN_TOTAL_MINUTES_FOR_ROAST = 30.0  # below this, the day is too sparse


# ── Pure helpers (LLM-free) ─────────────────────────────────────────


# Tone presets the user can pick. Friendly = encouraging; Savage = roast.
_TONE_PRESETS: dict[str, str] = {
    "friendly": (
        "You are a kind, supportive accountability coach. Be encouraging "
        "but honest. Highlight wins first, then one gentle suggestion. "
        "Keep it under 4 sentences."
    ),
    "savage": (
        "You are a brutally honest accountability AI. Roast the user's "
        "day in a funny, sarcastic, slightly mean way. Use specific "
        "stats — minutes spent, app names. Land one or two real "
        "burns but never insult the user as a person; only their "
        "choices. Hindi/Hinglish is welcome if the user uses it. "
        "Cap the roast at 5 sentences. End with a single 'kal better "
        "karte hain' style nudge."
    ),
    "hinglish": (
        "Tum ek brutal but pyaara dost ho jo user ka din dekh ke "
        "Hinglish mein roast karta hai. Funny, specific stats use karo "
        "(e.g. '3 ghante Reddit pe scroll'). Max 5 sentences. End mein "
        "ek line motivation ho. Insult only the choices, never the person."
    ),
}


def _format_summary_block(summary: dict) -> str:
    """Render a daily_summary dict into the compact text block we feed
    the LLM. Includes only the data the model actually needs to roast —
    we deliberately omit raw window titles to limit token spend and
    avoid leaking sensitive page names."""
    cats = summary.get("category_minutes", {})
    apps = summary.get("app_minutes", {})
    total = summary.get("total_minutes", 0.0)

    cat_lines = sorted(cats.items(), key=lambda x: -x[1])
    app_lines = sorted(apps.items(), key=lambda x: -x[1])[:8]

    parts = [
        f"DATE: {summary.get('date', 'unknown')}",
        f"TOTAL_TIME_TRACKED: {total:.1f} min",
        "",
        "TIME BY CATEGORY (minutes):",
    ]
    if cat_lines:
        for name, mins in cat_lines:
            parts.append(f"  - {name}: {mins:.1f}")
    else:
        parts.append("  (none)")

    parts.append("")
    parts.append("TOP 8 APPS (minutes):")
    if app_lines:
        for app, mins in app_lines:
            parts.append(f"  - {app}: {mins:.1f}")
    else:
        parts.append("  (none)")

    return "\n".join(parts)


def build_roast_prompt(summary: dict, tone: str = "savage") -> dict:
    """Construct the system + user prompt pair sent to the LLM.

    Returns a dict with ``system`` and ``user`` keys so the caller can
    plug it into whichever bridge they're using (OpenAI chat, Anthropic
    messages, etc.).
    """
    tone_key = tone if tone in _TONE_PRESETS else "savage"
    system = (
        _TONE_PRESETS[tone_key]
        + "\n\nReturn ONLY a JSON object with these keys:\n"
        '  "headline": one short headline (<= 10 words)\n'
        '  "roast": the multi-sentence roast itself\n'
        '  "stats_callout": one line citing the most striking stat\n'
        '  "tomorrow_nudge": one short suggestion for tomorrow\n'
        "Do not include any prose outside the JSON object."
    )
    user = (
        "Here is the user's activity log for the day. Roast accordingly.\n\n"
        + _format_summary_block(summary)
    )
    return {"system": system, "user": user}


def parse_roast_response(raw: str) -> dict | None:
    """Best-effort JSON extraction from an LLM reply.

    The strict-mode JSON Schema on OpenAI gpt-4o means this should be
    a no-op trim, but we stay defensive in case the model wrapped the
    JSON in markdown fences or added a sentence before / after.
    Returns ``None`` if no usable JSON is found.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    # Strip common markdown fencing.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    # Find the first { and the matching last }.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start: end + 1]
    try:
        out = json.loads(candidate)
        if not isinstance(out, dict):
            return None
        return out
    except Exception:
        return None


# ── Persistence ─────────────────────────────────────────────────────


@dataclass
class RoastRecord:
    day: date
    tone: str
    summary: dict
    response: dict
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "tone": self.tone,
            "summary": self.summary,
            "response": self.response,
            "timestamp": self.timestamp,
        }


class RoastStore:
    """Per-day JSON persistence so we never roast the same day twice."""

    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or _DEFAULT_ROAST_DIR

    def _path_for(self, day: date) -> str:
        return os.path.join(self.root_dir, f"{day.isoformat()}.json")

    def has_roast(self, day: date) -> bool:
        return os.path.exists(self._path_for(day))

    def save(self, record: RoastRecord) -> bool:
        try:
            os.makedirs(self.root_dir, exist_ok=True)
            with open(self._path_for(record.day), "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.logger.warning(f"RoastStore: save failed: {e}")
            return False

    def load(self, day: date) -> Optional[RoastRecord]:
        path = self._path_for(day)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return RoastRecord(
                day=date.fromisoformat(d["day"]),
                tone=d.get("tone", "savage"),
                summary=d.get("summary", {}),
                response=d.get("response", {}),
                timestamp=float(d.get("timestamp", 0.0)),
            )
        except Exception as e:
            logger.logger.warning(f"RoastStore: load failed: {e}")
            return None


# ── Scheduler ───────────────────────────────────────────────────────


class RoastScheduler:
    """Decides *when* a roast should fire.

    Polled rather than self-driven so it composes cleanly with whichever
    timer the dashboard already runs. Call ``due_for(now)`` once per
    minute (or whenever convenient) — it returns ``None`` if no roast
    is needed, or the ``date`` of the day that should be roasted.
    """

    def __init__(
        self,
        store: RoastStore | None = None,
        roast_hour: int = _DEFAULT_ROAST_HOUR,
        roast_minute: int = _DEFAULT_ROAST_MINUTE,
    ):
        self.store = store or RoastStore()
        self.roast_hour = max(0, min(23, int(roast_hour)))
        self.roast_minute = max(0, min(59, int(roast_minute)))

    def _scheduled_time(self, day: date) -> datetime:
        return datetime.combine(day, dtime(self.roast_hour, self.roast_minute))

    def due_for(self, now: datetime) -> Optional[date]:
        """Return the date that should be roasted right now, if any.

        Rules:
          1. If today's scheduled time has passed and today has not been
             roasted yet, return today.
          2. Else if yesterday has not been roasted yet *and* yesterday's
             scheduled time has passed, return yesterday. This catches
             the "Ay-Eye was offline at 11 PM, roast catches up at 9 AM"
             case.
          3. Otherwise return None.
        """
        today = now.date()
        if now >= self._scheduled_time(today) and not self.store.has_roast(today):
            return today

        yesterday = today - timedelta(days=1)
        if not self.store.has_roast(yesterday):
            return yesterday

        return None


# ── Engine ──────────────────────────────────────────────────────────


# Type alias for whatever LLM caller the user wires in. The contract:
# input is the prompt dict from build_roast_prompt; output is a raw
# string the model returned. We keep this abstract so tests can plug in
# a stub that returns canned JSON.
RoastLLM = Callable[[dict], str]


class RoastEngine:
    """Top-level facade — what the dashboard / executor calls."""

    def __init__(
        self,
        tracker: ActivityTracker | None = None,
        store: RoastStore | None = None,
        scheduler: RoastScheduler | None = None,
        llm_caller: RoastLLM | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.tracker = tracker or activity_tracker
        self.store = store or RoastStore()
        self.scheduler = scheduler or RoastScheduler(store=self.store)
        self.llm_caller = llm_caller  # may be None; resolved lazily
        self.clock = clock

    # ── Tick ─────────────────────────────────────────────────────────

    def tick(self, tone: str = "savage") -> Optional[RoastRecord]:
        """Run one scheduler iteration. Produces a roast if due."""
        target = self.scheduler.due_for(self.clock())
        if target is None:
            return None
        return self.roast_for(target, tone=tone)

    # ── On-demand ────────────────────────────────────────────────────

    def roast_for(self, day: date, tone: str = "savage") -> Optional[RoastRecord]:
        """Produce a roast for a specific day, regardless of schedule.

        Returns ``None`` if the day has too little activity to be worth
        roasting (avoids "you opened your laptop for 4 minutes" false
        positives) OR the LLM call fails.
        """
        summary = self.tracker.daily_summary(day)
        if summary.get("total_minutes", 0.0) < _MIN_TOTAL_MINUTES_FOR_ROAST:
            logger.logger.info(
                f"RoastEngine: skipping {day} — only "
                f"{summary.get('total_minutes', 0):.1f} min tracked"
            )
            return None

        prompt = build_roast_prompt(summary, tone=tone)
        caller = self._resolve_llm_caller()
        if caller is None:
            logger.logger.warning(
                "RoastEngine: no LLM caller wired; cannot generate roast"
            )
            return None
        try:
            raw = caller(prompt)
        except Exception as e:
            logger.logger.warning(f"RoastEngine: LLM call failed: {e}")
            return None

        parsed = parse_roast_response(raw or "")
        if parsed is None:
            logger.logger.warning("RoastEngine: LLM returned unparseable text")
            return None

        record = RoastRecord(
            day=day,
            tone=tone,
            summary=summary,
            response=parsed,
            timestamp=self.clock().timestamp(),
        )
        self.store.save(record)
        logger.logger.info(
            f"RoastEngine: roast saved for {day} (tone={tone})"
        )
        return record

    # ── LLM wiring ───────────────────────────────────────────────────

    def _resolve_llm_caller(self) -> RoastLLM | None:
        if self.llm_caller is not None:
            return self.llm_caller
        # Late-bind the project's LLM bridge so tests don't need keys.
        try:
            from core.engine.llm_bridge import LLMBridge

            bridge = LLMBridge()

            def _call(prompt: dict) -> str:
                return bridge.generate_text(
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                ) or ""

            return _call
        except Exception as e:
            logger.logger.warning(
                f"RoastEngine: failed to bind default LLM bridge: {e}"
            )
            return None


# Module-level singleton.
roast_engine = RoastEngine()
