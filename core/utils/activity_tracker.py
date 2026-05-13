"""
Activity Tracker — passive foreground-app sampler.

Every *N* seconds (default 60) we record the title + executable name of
the user's active window into ``analytics/activity/YYYY-MM-DD.jsonl``.
The Productivity Roast engine reads those logs to build a daily summary
of where the user actually spent their time.

Privacy
-------
Tracking is **off by default**. The dashboard or the user's voice
command must call ``activity_tracker.start()`` to opt in. We never
capture screen pixels or keystrokes here — just the foreground window's
title and the process basename. Per-day logs live entirely on disk in
``analytics/activity/`` so the user can audit / delete them at any time.

Architecture
------------
* ``ForegroundProbe``: thin, mockable wrapper around
  ``GetForegroundWindow`` + ``GetWindowText`` +
  ``GetWindowThreadProcessId`` + ``GetModuleBaseName``. Windows-only;
  returns blanks on every other platform.
* ``ActivityStore``: append-only JSONL persistence keyed by date.
  Idempotent on duplicate samples (same minute + same window) so a
  flapping foreground doesn't blow up the log.
* ``ActivityTracker``: orchestrator. Holds a sampling thread that wakes
  every ``interval_s`` seconds, calls the probe, and asks the store to
  record. Tests inject their own probe + clock.

The class also exposes a ``daily_summary(day)`` helper used by the
roast engine — it groups samples by category (chat / IDE / browser /
music / etc., reusing the same taxonomy as ``window_arranger``) and
returns minutes-per-category + minutes-per-app.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, date
from typing import Callable, Optional

from core.utils.logger import logger


# ── Constants ────────────────────────────────────────────────────────


_DEFAULT_INTERVAL_S = 60.0
_DEFAULT_ANALYTICS_DIR = os.path.join(os.getcwd(), "analytics", "activity")


# ── Foreground probe (mockable) ──────────────────────────────────────


_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
_kernel32 = ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None
_psapi = None
if _user32 is not None:
    try:
        _psapi = ctypes.windll.psapi
    except Exception:
        _psapi = None


@dataclass
class ForegroundSnapshot:
    title: str
    process_name: str

    def is_blank(self) -> bool:
        return not self.title and not self.process_name


class ForegroundProbe:
    """Default Win32 implementation. Tests use ``FakeProbe`` instead."""

    def snapshot(self) -> ForegroundSnapshot:
        if _user32 is None:
            return ForegroundSnapshot("", "")
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return ForegroundSnapshot("", "")

            # Title
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
            else:
                title = ""

            # Process basename via PSAPI
            process_name = ""
            if _psapi is not None and _kernel32 is not None:
                pid = wt.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000 — works
                # without elevation for any window we can read.
                handle = _kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        name_buf = ctypes.create_unicode_buffer(260)
                        _psapi.GetModuleBaseNameW(handle, None, name_buf, 260)
                        process_name = name_buf.value
                    finally:
                        _kernel32.CloseHandle(handle)

            return ForegroundSnapshot(title=title, process_name=process_name)
        except Exception as e:
            logger.logger.warning(f"ActivityTracker: foreground probe failed: {e}")
            return ForegroundSnapshot("", "")


# ── Activity store ───────────────────────────────────────────────────


@dataclass
class ActivitySample:
    timestamp: float
    title: str
    process_name: str
    interval_s: float

    def to_dict(self) -> dict:
        return {
            "ts": round(self.timestamp, 1),
            "title": self.title,
            "process": self.process_name,
            "interval_s": round(self.interval_s, 1),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActivitySample":
        return cls(
            timestamp=float(d.get("ts", 0.0)),
            title=str(d.get("title", "")),
            process_name=str(d.get("process", "")),
            interval_s=float(d.get("interval_s", _DEFAULT_INTERVAL_S)),
        )


class ActivityStore:
    """Append-only JSONL persistence, one file per local day."""

    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or _DEFAULT_ANALYTICS_DIR
        self._lock = threading.Lock()

    def _path_for(self, day: date) -> str:
        return os.path.join(self.root_dir, f"{day.isoformat()}.jsonl")

    def append(self, sample: ActivitySample, day: date | None = None) -> bool:
        """Persist one sample. Returns True on disk write success."""
        day = day or datetime.fromtimestamp(sample.timestamp).date()
        try:
            with self._lock:
                os.makedirs(self.root_dir, exist_ok=True)
                with open(self._path_for(day), "a", encoding="utf-8") as f:
                    f.write(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n")
            return True
        except Exception as e:
            logger.logger.warning(f"ActivityStore: append failed: {e}")
            return False

    def load_day(self, day: date) -> list[ActivitySample]:
        """Read a single day's log. Missing file -> empty list."""
        path = self._path_for(day)
        if not os.path.exists(path):
            return []
        out: list[ActivitySample] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(ActivitySample.from_dict(json.loads(line)))
                    except Exception:
                        continue  # skip malformed line
        except Exception as e:
            logger.logger.warning(f"ActivityStore: load_day({day}) failed: {e}")
        return out


# ── Tracker ──────────────────────────────────────────────────────────


class ActivityTracker:
    """Foreground-window sampler. Off by default; opt-in via ``start()``."""

    def __init__(
        self,
        store: ActivityStore | None = None,
        probe: ForegroundProbe | None = None,
        interval_s: float = _DEFAULT_INTERVAL_S,
        clock: Callable[[], float] = time.time,
    ):
        self.store = store or ActivityStore()
        self.probe = probe or ForegroundProbe()
        self.interval_s = max(5.0, float(interval_s))
        self.clock = clock
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_sample: Optional[ActivitySample] = None

    # ── Public API ───────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="ActivityTracker",
                daemon=True,
            )
            self._thread.start()
            logger.logger.info(
                f"ActivityTracker: started (interval={self.interval_s:.0f}s, "
                f"root={self.store.root_dir})"
            )
            return True

    def stop(self) -> None:
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            t = self._thread
            self._thread = None
        t.join(timeout=self.interval_s + 1.0)
        logger.logger.info("ActivityTracker: stopped")

    def sample_now(self) -> Optional[ActivitySample]:
        """Take one sample synchronously and persist it.

        Used both by the internal loop and by tests that want to drive
        the tracker without spinning a thread.
        """
        snap = self.probe.snapshot()
        if snap.is_blank():
            return None
        sample = ActivitySample(
            timestamp=self.clock(),
            title=snap.title,
            process_name=snap.process_name,
            interval_s=self.interval_s,
        )
        self.store.append(sample)
        with self._lock:
            self._last_sample = sample
        return sample

    @property
    def last_sample(self) -> Optional[ActivitySample]:
        with self._lock:
            return self._last_sample

    # ── Internal loop ────────────────────────────────────────────────

    def _loop(self) -> None:
        # Take an immediate sample on start so the user's first 60s
        # aren't lost to the wait.
        try:
            self.sample_now()
        except Exception as e:
            logger.logger.warning(f"ActivityTracker: initial sample failed: {e}")

        while not self._stop_event.is_set():
            if self._stop_event.wait(self.interval_s):
                break
            try:
                self.sample_now()
            except Exception as e:
                logger.logger.warning(f"ActivityTracker: sample cycle failed: {e}")

    # ── Daily aggregation (used by the Roast engine) ─────────────────

    def daily_summary(self, day: date) -> dict:
        """Return a stats dict for *day*::

            {
              "date": "2026-05-13",
              "total_minutes": 312.5,
              "category_minutes": {"ide": 47.0, "browser": 120.5, ...},
              "app_minutes": {"chrome.exe": 90.0, "Code.exe": 47.0, ...},
              "top_titles": [{"title": "...", "minutes": 33.0}, ...],
              "samples": 312,
            }
        """
        # Local import keeps the activity tracker independent of the UI
        # category taxonomy at module-load time.
        from core.engine.window_arranger import window_arranger

        samples = self.store.load_day(day)
        if not samples:
            return {
                "date": day.isoformat(),
                "total_minutes": 0.0,
                "category_minutes": {},
                "app_minutes": {},
                "top_titles": [],
                "samples": 0,
            }

        cat_seconds: dict[str, float] = {}
        app_seconds: dict[str, float] = {}
        title_seconds: dict[str, float] = {}
        for s in samples:
            cat = window_arranger.categorize(s.title, s.process_name)
            cat_seconds[cat] = cat_seconds.get(cat, 0.0) + s.interval_s
            if s.process_name:
                app_seconds[s.process_name] = app_seconds.get(s.process_name, 0.0) + s.interval_s
            if s.title:
                title_seconds[s.title] = title_seconds.get(s.title, 0.0) + s.interval_s

        def _mins(d: dict[str, float]) -> dict[str, float]:
            return {k: round(v / 60.0, 1) for k, v in d.items()}

        top_titles = sorted(title_seconds.items(), key=lambda x: -x[1])[:5]

        total_seconds = sum(cat_seconds.values())
        return {
            "date": day.isoformat(),
            "total_minutes": round(total_seconds / 60.0, 1),
            "category_minutes": _mins(cat_seconds),
            "app_minutes": _mins(app_seconds),
            "top_titles": [
                {"title": t, "minutes": round(s / 60.0, 1)} for t, s in top_titles
            ],
            "samples": len(samples),
        }


# Module-level singleton.
activity_tracker = ActivityTracker()
