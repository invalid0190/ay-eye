"""Perceptual-hash keyed cache for vision results.

The expensive perception steps (LLM JPEG encode, OCR subprocess, UIA tree walk)
each take 50-2000 ms but are pure functions of the screen pixels. When the
screen has not changed since the last call, we can serve the previous result
in microseconds.

Keying strategy:
    * We hash the ``ScreenFrame.processed_image`` with ``imagehash.phash``.
    * Two hashes within ``tolerance`` Hamming distance are treated as a hit
      (anti-aliasing, cursor blink, etc.).
    * Each entry has a TTL so stale screens never haunt later sessions.

The cache is namespaced (``b64``, ``ocr``, ``ui``, ...) so multiple callers
can share storage without collisions, and a thread lock keeps it safe across
the live-perception thread, the brain thread, and the orchestrator loop.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

import imagehash
from PIL import Image

from core.config import sys_config
from core.utils.logger import logger


def _compute_phash(image: Image.Image) -> imagehash.ImageHash:
    return imagehash.phash(image)


def frame_phash(frame_or_image) -> Optional[imagehash.ImageHash]:
    """Return (and lazily cache) a phash for a ScreenFrame or PIL.Image.

    Caching the hash on the frame object means hitting the cache N times for
    one frame still only does the phash once.
    """
    if frame_or_image is None:
        return None

    cached = getattr(frame_or_image, "_phash", None)
    if cached is not None:
        return cached

    image = getattr(frame_or_image, "processed_image", None) or frame_or_image
    if not isinstance(image, Image.Image):
        return None

    h = _compute_phash(image)
    try:
        setattr(frame_or_image, "_phash", h)
    except Exception:
        pass
    return h


class VisionCache:
    def __init__(self, max_entries: int = 32, ttl: float = 30.0, tolerance: int = 2):
        self.max_entries = max_entries
        self.ttl = ttl
        self.tolerance = tolerance
        self._lock = threading.Lock()
        # namespace -> OrderedDict[hash_obj, (value, expires_at)]
        self._store: dict[str, "OrderedDict[Any, tuple[Any, float]]"] = {}
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expired": 0}

    # -- internals --------------------------------------------------------

    def _purge_expired_locked(self, ns: "OrderedDict[Any, tuple[Any, float]]") -> None:
        now = time.time()
        dead = [k for k, (_, exp) in ns.items() if exp <= now]
        for k in dead:
            ns.pop(k, None)
            self._stats["expired"] += 1

    def _find_match_locked(self, ns: "OrderedDict[Any, tuple[Any, float]]", h) -> Optional[Any]:
        # Exact hit (cheap path).
        if h in ns:
            return h
        if self.tolerance <= 0:
            return None
        # Fuzzy: linear scan, fine at <= 64 entries.
        for k in ns.keys():
            try:
                if (h - k) <= self.tolerance:
                    return k
            except Exception:
                continue
        return None

    # -- public API -------------------------------------------------------

    def get(self, namespace: str, frame_or_image) -> Any:
        if not sys_config.get("vision_cache_enabled"):
            return None
        h = frame_phash(frame_or_image)
        if h is None:
            return None

        with self._lock:
            ns = self._store.get(namespace)
            if not ns:
                self._stats["misses"] += 1
                return None
            self._purge_expired_locked(ns)
            key = self._find_match_locked(ns, h)
            if key is None:
                self._stats["misses"] += 1
                return None
            value, _ = ns[key]
            ns.move_to_end(key)  # LRU touch.
            self._stats["hits"] += 1
            return value

    def set(self, namespace: str, frame_or_image, value: Any, ttl: Optional[float] = None) -> None:
        if not sys_config.get("vision_cache_enabled"):
            return
        h = frame_phash(frame_or_image)
        if h is None:
            return

        ttl = ttl if ttl is not None else self.ttl
        expires_at = time.time() + ttl

        with self._lock:
            ns = self._store.setdefault(namespace, OrderedDict())
            self._purge_expired_locked(ns)
            ns[h] = (value, expires_at)
            ns.move_to_end(h)
            while len(ns) > self.max_entries:
                ns.popitem(last=False)
                self._stats["evictions"] += 1

    def get_or_compute(self, namespace: str, frame_or_image, fn: Callable[[], Any], ttl: Optional[float] = None) -> Any:
        cached = self.get(namespace, frame_or_image)
        if cached is not None:
            return cached
        value = fn()
        if value is not None:
            self.set(namespace, frame_or_image, value, ttl=ttl)
        return value

    def invalidate(self, namespace: Optional[str] = None) -> None:
        with self._lock:
            if namespace is None:
                self._store.clear()
            else:
                self._store.pop(namespace, None)

    def stats(self) -> dict:
        with self._lock:
            sizes = {ns: len(items) for ns, items in self._store.items()}
        snapshot = dict(self._stats)
        total = snapshot["hits"] + snapshot["misses"]
        snapshot["hit_rate"] = (snapshot["hits"] / total) if total else 0.0
        snapshot["sizes"] = sizes
        return snapshot

    def reset_stats(self) -> None:
        with self._lock:
            for k in self._stats:
                self._stats[k] = 0


def _build_default_cache() -> VisionCache:
    max_entries = sys_config.get("vision_cache_max_entries") or 32
    ttl = sys_config.get("vision_cache_ttl_seconds") or 30.0
    tolerance = sys_config.get("vision_cache_phash_tolerance")
    if tolerance is None:
        tolerance = 2
    cache = VisionCache(max_entries=max_entries, ttl=ttl, tolerance=tolerance)
    logger.logger.info(
        f"VisionCache initialised: max_entries={max_entries}, ttl={ttl}s, tolerance={tolerance}"
    )
    return cache


vision_cache = _build_default_cache()
