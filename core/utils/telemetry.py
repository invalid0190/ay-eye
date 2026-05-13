"""Per-turn cost + latency telemetry.

Each "turn" is one user-visible round-trip: voice -> LLM -> action -> reply.
We record:

  * provider + model
  * prompt_tokens, completion_tokens
  * estimated cost in USD (best-effort table; tweak via PRICING)
  * llm_ms          -- wall time of the LLM call
  * total_ms        -- wall time from turn start to end
  * vision (bool)   -- whether the call included a screenshot
  * extra section timings (e.g. "ocr", "tts")

The service publishes ``TURN_METRICS`` on the event bus on every ``end_turn``,
which the dashboard subscribes to. A rolling window keeps the last N turns
for the dashboard's running totals.

Pricing is approximate -- override per-model via core/utils/pricing.json or
``set_price(model, prompt_per_1k, completion_per_1k)``.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from typing import Any, Optional


# USD per 1,000 tokens. Public list-prices, best-effort, easy to override.
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":              (0.0025, 0.0100),
    "gpt-4o-mini":         (0.00015, 0.00060),
    "gpt-4.1":             (0.0020, 0.0080),
    "gpt-4.1-mini":        (0.00040, 0.00160),
    "gpt-4-turbo":         (0.0100, 0.0300),
    # Moonshot / Kimi
    "kimi-k2.6":           (0.0015, 0.0025),
    # Anthropic (if added later)
    "claude-sonnet-4.5":   (0.0030, 0.0150),
    "claude-opus-4":       (0.0150, 0.0750),
    # Local / Ollama (free)
    "gemma3:4b":           (0.0, 0.0),
    "gemma4:e2b":          (0.0, 0.0),
}


def _load_overrides() -> dict[str, tuple[float, float]]:
    path = os.path.join(os.path.dirname(__file__), "pricing.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: (float(v["prompt"]), float(v["completion"])) for k, v in data.items()}
    except Exception:
        return {}


class TelemetryService:
    def __init__(self, window_size: int = 50):
        self._lock = threading.Lock()
        self._turns: deque[dict[str, Any]] = deque(maxlen=window_size)
        self._open: dict[str, dict[str, Any]] = {}
        self._totals = {
            "turns": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "llm_ms": 0,
            "total_ms": 0,
        }
        self._pricing = dict(DEFAULT_PRICING)
        self._pricing.update(_load_overrides())

    # -- pricing ----------------------------------------------------------

    def set_price(self, model: str, prompt_per_1k: float, completion_per_1k: float) -> None:
        with self._lock:
            self._pricing[model] = (prompt_per_1k, completion_per_1k)

    def cost_for(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        prices = self._pricing.get(model)
        if prices is None:
            # Heuristic: fall back to the closest base model name.
            for known, p in self._pricing.items():
                if model.startswith(known):
                    prices = p
                    break
        if prices is None:
            return 0.0
        return (prompt_tokens / 1000.0) * prices[0] + (completion_tokens / 1000.0) * prices[1]

    # -- turn lifecycle ---------------------------------------------------

    def start_turn(self, turn_id: Optional[str] = None) -> str:
        tid = turn_id or uuid.uuid4().hex[:8]
        with self._lock:
            self._open[tid] = {
                "id": tid,
                "started_at": time.time(),
                "sections": {},
                "vision": False,
                "model": None,
                "provider": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "llm_ms": 0,
                "cost_usd": 0.0,
            }
        return tid

    def record_llm(
        self,
        turn_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
        vision: bool = False,
    ) -> None:
        with self._lock:
            t = self._open.get(turn_id)
            if t is None:
                return
            t["provider"] = provider
            t["model"] = model
            t["prompt_tokens"] += int(prompt_tokens or 0)
            t["completion_tokens"] += int(completion_tokens or 0)
            t["llm_ms"] += int(duration_ms or 0)
            t["vision"] = t["vision"] or bool(vision)
            t["cost_usd"] += self.cost_for(model, prompt_tokens or 0, completion_tokens or 0)

    def record_section(self, turn_id: str, name: str, duration_ms: int) -> None:
        with self._lock:
            t = self._open.get(turn_id)
            if t is None:
                return
            t["sections"][name] = t["sections"].get(name, 0) + int(duration_ms or 0)

    def end_turn(self, turn_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            t = self._open.pop(turn_id, None)
            if t is None:
                return None
            t["total_ms"] = int((time.time() - t["started_at"]) * 1000)
            self._turns.append(t)
            self._totals["turns"] += 1
            self._totals["prompt_tokens"] += t["prompt_tokens"]
            self._totals["completion_tokens"] += t["completion_tokens"]
            self._totals["cost_usd"] += t["cost_usd"]
            self._totals["llm_ms"] += t["llm_ms"]
            self._totals["total_ms"] += t["total_ms"]
            snapshot = dict(t)

        # Publish outside the lock to avoid deadlocks in subscribers.
        try:
            from core.engine.event_bus import bus
            bus.publish("TURN_METRICS", snapshot)
        except Exception:
            pass
        return snapshot

    # -- aggregates -------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self._lock:
            totals = dict(self._totals)
            last = self._turns[-1] if self._turns else None
            recent = list(self._turns)[-10:]
        if recent:
            totals["avg_total_ms"] = sum(t["total_ms"] for t in recent) // len(recent)
            totals["avg_llm_ms"] = sum(t["llm_ms"] for t in recent) // len(recent)
        else:
            totals["avg_total_ms"] = 0
            totals["avg_llm_ms"] = 0
        totals["last_turn"] = last
        return totals

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()
            self._open.clear()
            for k in self._totals:
                self._totals[k] = 0 if isinstance(self._totals[k], int) else 0.0


telemetry = TelemetryService()
