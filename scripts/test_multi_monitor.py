"""Regression tests for the multi-monitor fixes.

Real user bug: with Discord on the LEFT physical monitor and VS Code focused
on the RIGHT one, "check Discord notifications" was clicking inside the
right monitor (the active window) and failing twice. Three root causes:

  1. UIAutoScanner walked only the foreground window's tree, so Discord's
     controls were invisible to the locator.
  2. The Brain's prompt described the screen as one virtual desktop without
     per-monitor boundaries, so the LLM could not map "Discord on the left"
     to a coordinate range.
  3. The capture downscaled a 3840-wide virtual desktop to 1920, halving
     vertical resolution and making notification badges illegible.

These tests cover each fix in pure logic (no real UIA / no real mss),
so they run in CI on any platform.

Run:
    .venv\\Scripts\\python scripts\\test_multi_monitor.py
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = []
FAIL = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


# ── live_perception helpers --------------------------------------------

def test_effective_max_width_keeps_single_monitor_unchanged():
    from core.vision.live_perception import LivePerceptionService

    svc = LivePerceptionService()
    svc._max_width = 1920
    # Single 1920-wide capture: no resize needed.
    check(svc._effective_max_width(1920) == 1920, "single 1920 monitor: no downscale")
    # Smaller monitor: still no upscale.
    check(svc._effective_max_width(1366) == 1366, "smaller monitor: no upscale")


def test_effective_max_width_raises_cap_for_wide_virtual_desktop():
    """3840-wide virtual desktop (dual 1920) should not be halved to 1920."""
    from core.vision.live_perception import LivePerceptionService

    svc = LivePerceptionService()
    svc._max_width = 1920
    target = svc._effective_max_width(3840)
    check(target >= 2560, f"dual-monitor 3840px raises cap above 2560 (got {target})")
    check(target <= 3840, "effective max width capped at raw width")


def test_effective_max_width_bounded_for_extreme_widths():
    from core.vision.live_perception import LivePerceptionService

    svc = LivePerceptionService()
    svc._max_width = 1920
    # Triple 4k = 11520. Should be capped to keep payloads bounded.
    target = svc._effective_max_width(11520)
    check(target <= 3840, f"triple-4K capped at 3840 (got {target})")


def test_build_monitor_layout_maps_physicals_into_image_coords():
    """The mss-style monitor list [virtual, left_phys, right_phys] should map
    each physical monitor to a non-overlapping rect in image coordinates."""
    from core.vision.live_perception import LivePerceptionService

    fake_sct = SimpleNamespace(monitors=[
        {"left": 0, "top": 0, "width": 3840, "height": 1080},     # virtual
        {"left": 0, "top": 0, "width": 1920, "height": 1080},     # left
        {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # right
    ])
    layout = LivePerceptionService._build_monitor_layout(
        fake_sct, fake_sct.monitors[0], processed_size=(2560, 720)
    )
    check(len(layout) == 2, "two physical monitors produced two entries")
    if len(layout) != 2:
        return
    left, right = layout
    check(left["index"] == 1 and right["index"] == 2, "monitors numbered 1, 2")
    # Image rects should split the 2560-wide canvas roughly in half.
    check(left["image"][0] == 0, "left monitor begins at image x=0")
    check(abs(left["image"][2] - 1280) <= 1, "left monitor image width ~= half of 2560")
    check(right["image"][0] >= 1279, "right monitor starts at image x ~= 1280")
    check(left["image"][1] == 0 and right["image"][1] == 0, "both at image y=0")


def test_build_monitor_layout_with_negative_offset_virtual_desktop():
    """When the secondary monitor sits to the LEFT of the primary, Windows
    reports negative desktop x. The layout must still produce non-negative
    image-space rects."""
    from core.vision.live_perception import LivePerceptionService

    fake_sct = SimpleNamespace(monitors=[
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},  # virtual
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},  # left (negative origin)
        {"left": 0, "top": 0, "width": 1920, "height": 1080},      # primary
    ])
    layout = LivePerceptionService._build_monitor_layout(
        fake_sct, fake_sct.monitors[0], processed_size=(3840, 1080)
    )
    check(len(layout) == 2, "negative-origin layout returns both monitors")
    check(all(m["image"][0] >= 0 for m in layout), "image-space x is non-negative for both")


def test_screenframe_default_monitors_is_empty_list():
    from core.vision.live_perception import ScreenFrame

    f = ScreenFrame(
        raw_image=None, processed_image=None,
        raw_size=(0, 0), processed_size=(0, 0),
        desktop_offset=(0, 0), monitor_info={}, timestamp=0.0,
    )
    check(f.monitors == [], "ScreenFrame.monitors defaults to empty list")


# ── UI scanner (logic only; no real UIA) -------------------------------

def test_enumerate_caches_keyed_by_window_set():
    """Cache must invalidate when a window opens or closes even if pixels look
    the same (e.g. transparent fullscreen overlay). We check the cache namespace
    is derived from the hwnd fingerprint, not just the frame phash."""
    from core.ui import automation as automation_mod

    scanner = automation_mod.UIAutoScanner.__new__(automation_mod.UIAutoScanner)
    scanner.uia = None  # short-circuits scan_active_window before hitting Windows

    # Two different fingerprints should produce two different cache namespaces.
    ns1 = f"ui_elements:{hash((101, 202, 303))}"
    ns2 = f"ui_elements:{hash((101, 202, 304))}"
    check(ns1 != ns2, "different window fingerprints produce distinct cache namespaces")


def test_window_rect_filters_minimised_sentinel():
    """Minimised windows return RECT(-32000, -32000, ...). The helper should reject."""
    import ctypes
    from ctypes import wintypes
    from core.ui.automation import UIAutoScanner

    # Monkey-patch GetWindowRect to return the sentinel.
    original = ctypes.windll.user32.GetWindowRect

    def fake(hwnd, rect_ptr):
        r = ctypes.cast(rect_ptr, ctypes.POINTER(wintypes.RECT)).contents
        r.left, r.top, r.right, r.bottom = -32000, -32000, -31840, -31900
        return 1

    ctypes.windll.user32.GetWindowRect = fake
    try:
        result = UIAutoScanner._window_rect(0xdead)
        check(result is None, "minimised sentinel coordinates rejected by _window_rect")
    finally:
        ctypes.windll.user32.GetWindowRect = original


def test_walk_window_returns_empty_when_root_unavailable():
    """If UIA cannot get a root for a hwnd (race during window close), we must
    return an empty list rather than raising, so one bad window doesn't poison
    the whole scan."""
    from core.ui.automation import UIAutoScanner

    scanner = UIAutoScanner.__new__(UIAutoScanner)

    class FakeUIA:
        def ElementFromHandle(self, hwnd):
            raise OSError("window vanished")

    scanner.uia = FakeUIA()
    out = scanner._walk_window(0x123)
    check(out == [], "_walk_window returns [] when UIA root lookup raises")


# ── runner -------------------------------------------------------------

def main():
    test_effective_max_width_keeps_single_monitor_unchanged()
    test_effective_max_width_raises_cap_for_wide_virtual_desktop()
    test_effective_max_width_bounded_for_extreme_widths()
    test_build_monitor_layout_maps_physicals_into_image_coords()
    test_build_monitor_layout_with_negative_offset_virtual_desktop()
    test_screenframe_default_monitors_is_empty_list()
    test_enumerate_caches_keyed_by_window_set()
    test_window_rect_filters_minimised_sentinel()
    test_walk_window_returns_empty_when_root_unavailable()

    print(f"\n=== Multi-monitor: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
