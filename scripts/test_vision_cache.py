"""Regression tests for core/utils/vision_cache.py.

The cache sits in front of OCR, the UIA tree walk, and the LLM JPEG encode,
so a bug here directly causes either stale data (wrong clicks) or zero
cost-savings. We test:
  * Exact phash hit returns the cached value.
  * Different image -> miss.
  * Within-tolerance fuzzy match still hits.
  * TTL expiry forces a recompute.
  * LRU eviction at max_entries.
  * Namespacing keeps callers isolated.
  * Disabling via config returns None on every get.
  * get_or_compute only invokes the producer on miss.
  * Stats counters track hits/misses/evictions/expired.

Run:
    .venv\\Scripts\\python scripts\\test_vision_cache.py
"""

import os
import sys
import time

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import sys_config
from core.utils.vision_cache import VisionCache, frame_phash


PASS = []
FAIL = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


def img_solid(color):
    return Image.new("RGB", (256, 256), color)


def img_with_pixel(color, x, y, dot):
    """Same base image with one tiny pixel toggled -- nearly identical phash."""
    img = Image.new("RGB", (256, 256), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((x, y, x + 1, y + 1), fill=dot)
    return img


def img_random_noise(seed):
    """A visually distinct image -> different phash."""
    import random
    rng = random.Random(seed)
    img = Image.new("RGB", (256, 256))
    px = img.load()
    for y in range(0, 256, 8):
        for x in range(0, 256, 8):
            c = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
            for dy in range(8):
                for dx in range(8):
                    px[x + dx, y + dy] = c
    return img


def with_cache_enabled(fn):
    prev = sys_config.get("vision_cache_enabled")
    sys_config.set("vision_cache_enabled", True)
    try:
        fn()
    finally:
        sys_config.set("vision_cache_enabled", prev)


def test_exact_hit_and_miss():
    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=0)
    a = img_random_noise(seed=11)
    b = img_random_noise(seed=22)

    cache.set("ns", a, "value-a")
    check(cache.get("ns", a) == "value-a", "exact hit returns cached value")
    check(cache.get("ns", b) is None, "different image returns None")


def test_fuzzy_match_within_tolerance():
    # Build a base noise image and a perturbed copy: identical layout, with a
    # small block recoloured. phash compares 8x8 DCT coefficients, so a small
    # local change yields a Hamming distance of a few bits -- exactly the
    # "unchanged screen with cursor blink" case the cache is meant to absorb.
    base = img_random_noise(seed=42)
    near = base.copy()
    ImageDraw.Draw(near).rectangle((10, 10, 30, 30), fill=(255, 255, 255))
    far = img_random_noise(seed=99)

    h_base = frame_phash(base)
    h_near = frame_phash(near)
    h_far = frame_phash(far)
    near_dist = h_base - h_near
    far_dist = h_base - h_far

    check(h_base != h_near, "near-image phash actually differs (test sanity)")
    # Pick a tolerance large enough to cover the perturbation but smaller
    # than the distance to a totally different image.
    tolerance = max(near_dist, 1)
    check(far_dist > tolerance, "far-image hamming distance > tolerance")

    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=tolerance)
    cache.set("ns", base, "near-cache")
    check((h_base - h_near) <= tolerance, "near-image hamming distance <= tolerance")
    check(cache.get("ns", near) == "near-cache", "fuzzy match within tolerance hits")
    check(cache.get("ns", far) is None, "fuzzy match outside tolerance misses")


def test_ttl_expiry():
    cache = VisionCache(max_entries=8, ttl=0.05, tolerance=0)
    a = img_solid("green")
    cache.set("ns", a, "fresh")
    check(cache.get("ns", a) == "fresh", "fresh entry hits before TTL")
    time.sleep(0.1)
    check(cache.get("ns", a) is None, "expired entry returns None")


def test_lru_eviction_at_max_entries():
    cache = VisionCache(max_entries=2, ttl=60.0, tolerance=0)
    a = img_random_noise(1)
    b = img_random_noise(2)
    c = img_random_noise(3)
    cache.set("ns", a, "A")
    cache.set("ns", b, "B")
    cache.set("ns", c, "C")  # evicts A
    check(cache.get("ns", a) is None, "oldest entry evicted at capacity")
    check(cache.get("ns", b) == "B", "second-oldest still cached")
    check(cache.get("ns", c) == "C", "newest cached")
    s = cache.stats()
    check(s["evictions"] >= 1, "eviction stat incremented")


def test_namespaces_are_isolated():
    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=0)
    a = img_solid("orange")
    cache.set("ocr", a, "hello")
    cache.set("ui", a, [{"name": "Button"}])
    check(cache.get("ocr", a) == "hello", "ocr namespace hit")
    check(cache.get("ui", a) == [{"name": "Button"}], "ui namespace hit")
    cache.invalidate("ocr")
    check(cache.get("ocr", a) is None, "invalidate(ns) clears only that namespace")
    check(cache.get("ui", a) == [{"name": "Button"}], "other namespace untouched")


def test_disabled_via_config():
    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=0)
    a = img_solid("purple")
    prev = sys_config.get("vision_cache_enabled")
    sys_config.set("vision_cache_enabled", False)
    try:
        cache.set("ns", a, "v")  # silently no-op
        check(cache.get("ns", a) is None, "disabled cache returns None")
    finally:
        sys_config.set("vision_cache_enabled", prev)


def test_get_or_compute():
    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=0)
    a = img_solid("teal")
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return "computed"

    v1 = cache.get_or_compute("ns", a, producer)
    v2 = cache.get_or_compute("ns", a, producer)
    check(v1 == "computed" and v2 == "computed", "get_or_compute returns value both times")
    check(calls["n"] == 1, "producer invoked exactly once on cached image")


def test_stats_counters():
    cache = VisionCache(max_entries=8, ttl=60.0, tolerance=0)
    a = img_random_noise(seed=101)
    b = img_random_noise(seed=202)
    cache.get("ns", a)            # miss
    cache.set("ns", a, "x")
    cache.get("ns", a)            # hit
    cache.get("ns", b)            # miss
    s = cache.stats()
    check(s["hits"] == 1 and s["misses"] == 2, "hit/miss counters tracked")
    check(0 < s["hit_rate"] < 1, "hit_rate is the ratio")
    check("ns" in s["sizes"] and s["sizes"]["ns"] == 1, "sizes reflect stored entries")


def test_frame_phash_caches_on_object():
    a = img_solid("cyan")
    h1 = frame_phash(a)
    h2 = frame_phash(a)
    check(h1 is h2 or h1 == h2, "frame_phash returns same hash for same image")
    check(getattr(a, "_phash", None) is not None, "phash cached on object attr")


# -------- runner ---------------------------------------------------------

def main():
    with_cache_enabled(test_exact_hit_and_miss)
    with_cache_enabled(test_fuzzy_match_within_tolerance)
    with_cache_enabled(test_ttl_expiry)
    with_cache_enabled(test_lru_eviction_at_max_entries)
    with_cache_enabled(test_namespaces_are_isolated)
    test_disabled_via_config()
    with_cache_enabled(test_get_or_compute)
    with_cache_enabled(test_stats_counters)
    with_cache_enabled(test_frame_phash_caches_on_object)

    print(f"\n=== Vision cache: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
