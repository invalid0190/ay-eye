"""DPI + multi-monitor coordinate-mapping regression tests.

Covers the conversion paths in core/vision/live_perception.py that translate
between three coordinate spaces:

    1. Desktop space    -- the actual virtual-desktop pixels (what PyAutoGUI clicks).
    2. Raw frame space  -- the mss screenshot, identical resolution to desktop.
    3. Processed space  -- the (possibly down-scaled) image sent to the LLM.

Bugs in this conversion translate directly into missed clicks, so we test:
  * Single-monitor at common DPI scales: 100%, 125%, 150%.
  * Secondary monitor on the left (negative offset).
  * Secondary monitor on the right (positive offset).
  * Mixed-DPI multi-monitor virtual desktops.
  * Round-trip stability: image -> desktop -> image is the identity.
  * scale_actions for click / drag / ocr_screen.
  * Idempotency: re-scaling a desktop-space action is a no-op.
  * _desktop_rect_to_processed clamping at frame edges.
  * enable_dpi_awareness does not raise.

Run with:
    .venv\\Scripts\\python scripts\\test_dpi_coordinate_mapping.py
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vision.live_perception import LivePerceptionService, ScreenFrame, live_perception


# -------- helpers --------------------------------------------------------

# Logical screen size before DPI scaling (what apps "see").
LOGICAL_W, LOGICAL_H = 1920, 1080

# AI-side processed image cap (matches config.json live_perception_max_width).
MAX_PROCESSED_W = 1920


def make_frame(
    raw_size,
    desktop_offset=(0, 0),
    max_processed_w=MAX_PROCESSED_W,
):
    """Build a ScreenFrame mimicking what LivePerceptionService._loop produces."""
    raw_w, raw_h = raw_size
    if raw_w > max_processed_w:
        ratio = max_processed_w / raw_w
        proc_size = (max_processed_w, int(raw_h * ratio))
    else:
        proc_size = (raw_w, raw_h)

    raw = Image.new("RGB", raw_size, "black")
    proc = Image.new("RGB", proc_size, "black")
    return ScreenFrame(
        raw_image=raw,
        processed_image=proc,
        raw_size=raw_size,
        processed_size=proc_size,
        desktop_offset=desktop_offset,
        monitor_info={
            "left": desktop_offset[0],
            "top": desktop_offset[1],
            "width": raw_w,
            "height": raw_h,
        },
        timestamp=0.0,
    )


# Common DPI scenarios. Each tuple = (label, raw_size, desktop_offset).
DPI_SCENARIOS = [
    ("100% single monitor",          (1920, 1080),  (0, 0)),
    ("125% single monitor",          (2400, 1350),  (0, 0)),
    ("150% single monitor",          (2880, 1620),  (0, 0)),
    ("100% secondary on left",       (3840, 2160),  (-1920, 0)),
    ("100% secondary on right",      (3840, 2160),  (0, 0)),
    ("125% secondary above primary", (2400, 2700),  (0, -1350)),
    ("150% ultrawide spanning two",  (5760, 1620),  (-2880, 0)),
]


PASS = []
FAIL = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


def approx(a, b, tol=1):
    return abs(a - b) <= tol


# -------- tests ----------------------------------------------------------

def test_image_to_desktop_for_frame():
    """Center of processed image must map to center of desktop region."""
    for label, raw_size, offset in DPI_SCENARIOS:
        frame = make_frame(raw_size, offset)
        pw, ph = frame.processed_size
        rw, rh = frame.raw_size
        ox, oy = offset

        dx, dy = LivePerceptionService.image_to_desktop_for_frame(pw // 2, ph // 2, frame)
        expected = (ox + rw // 2, oy + rh // 2)
        check(
            approx(dx, expected[0], tol=2) and approx(dy, expected[1], tol=2),
            f"[{label}] center processed -> desktop center",
        )

        dx, dy = LivePerceptionService.image_to_desktop_for_frame(0, 0, frame)
        check((dx, dy) == (ox, oy), f"[{label}] origin processed -> desktop offset")


def test_round_trip_image_desktop_image():
    """image -> desktop -> image must be identity for every scenario."""
    for label, raw_size, offset in DPI_SCENARIOS:
        frame = make_frame(raw_size, offset)
        with live_perception._lock:
            live_perception._latest_frame = frame

        for px, py in [(0, 0), (10, 20), (500, 300), (frame.processed_size[0] - 1, frame.processed_size[1] - 1)]:
            dx, dy = LivePerceptionService.image_to_desktop_for_frame(px, py, frame)
            ix, iy = live_perception.desktop_to_image(dx, dy)
            check(
                approx(ix, px, tol=2) and approx(iy, py, tol=2),
                f"[{label}] round-trip ({px},{py}) image->desktop->image",
            )


def test_scale_actions_click_per_dpi():
    """scale_actions must convert click coords using the active frame's DPI."""
    for label, raw_size, offset in DPI_SCENARIOS:
        frame = make_frame(raw_size, offset)
        with live_perception._lock:
            live_perception._latest_frame = frame

        pw, ph = frame.processed_size
        response = {"actions": [{"type": "click", "x": pw // 2, "y": ph // 2}]}
        live_perception.scale_actions(response)
        a = response["actions"][0]

        rw, rh = frame.raw_size
        ox, oy = offset
        expected_dx = int((pw // 2) * rw / pw) + ox
        expected_dy = int((ph // 2) * rh / ph) + oy
        check(
            (a["x"], a["y"]) == (expected_dx, expected_dy),
            f"[{label}] click processed -> desktop",
        )
        check(a.get("_coord_space") == "desktop", f"[{label}] click marked desktop space")
        check(
            (a.get("_image_x"), a.get("_image_y")) == (pw // 2, ph // 2),
            f"[{label}] click preserves original image coords",
        )


def test_scale_actions_drag_and_ocr():
    frame = make_frame((3840, 2160), (-1920, 0))
    with live_perception._lock:
        live_perception._latest_frame = frame

    response = {
        "actions": [
            {"type": "drag", "x1": 100, "y1": 50, "x2": 300, "y2": 150},
            {"type": "ocr_screen", "x": 10, "y": 20, "w": 200, "h": 100},
        ]
    }
    live_perception.scale_actions(response)

    drag = response["actions"][0]
    check(
        (drag["x1"], drag["y1"], drag["x2"], drag["y2"]) == (-1720, 100, -1320, 300),
        "drag processed -> desktop on secondary monitor",
    )
    ocr = response["actions"][1]
    check(
        (ocr["x"], ocr["y"], ocr["w"], ocr["h"]) == (-1900, 40, 400, 200),
        "ocr_screen processed -> desktop with width/height scaling",
    )


def test_idempotency_no_double_scale():
    """Calling scale_actions twice must be a no-op on the second call."""
    for label, raw_size, offset in DPI_SCENARIOS:
        frame = make_frame(raw_size, offset)
        with live_perception._lock:
            live_perception._latest_frame = frame

        pw, ph = frame.processed_size
        response = {"actions": [{"type": "click", "x": pw // 4, "y": ph // 4}]}
        live_perception.scale_actions(response)
        first = (response["actions"][0]["x"], response["actions"][0]["y"])
        live_perception.scale_actions(response)
        second = (response["actions"][0]["x"], response["actions"][0]["y"])
        check(first == second, f"[{label}] scale_actions is idempotent")


def test_desktop_rect_to_processed_clamps():
    """Desktop rectangles outside the frame must clamp or return None gracefully."""
    frame = make_frame((2400, 1350), (0, 0))  # 125% scale

    # Fully inside.
    rect_inside = (100, 100, 200, 200)
    out = LivePerceptionService._desktop_rect_to_processed(rect_inside, frame)
    check(out is not None and out[0] >= 0 and out[1] >= 0, "rect inside frame projects ok")

    # Partially outside the right edge -- must clamp, not None.
    rect_partial = (2200, 100, 1000, 200)
    out = LivePerceptionService._desktop_rect_to_processed(rect_partial, frame)
    check(out is not None and out[2] <= frame.processed_size[0] - 1, "rect partial clamps to right edge")

    # Fully off-screen to the left -- must return None.
    rect_off = (-5000, -5000, 100, 100)
    out = LivePerceptionService._desktop_rect_to_processed(rect_off, frame)
    check(out is None, "rect fully off-screen returns None")


def test_no_frame_does_not_crash():
    """When there is no frame yet, helpers must degrade gracefully."""
    with live_perception._lock:
        live_perception._latest_frame = None

    response = {"actions": [{"type": "click", "x": 5, "y": 7}]}
    live_perception.scale_actions(response)
    a = response["actions"][0]
    check((a["x"], a["y"]) == (5, 7), "scale_actions no-op when no frame")
    check(a.get("_coord_space") is None, "no coord-space marker without a frame")

    dx, dy = live_perception.image_to_desktop(5, 7)
    check((dx, dy) == (5, 7), "image_to_desktop falls back to identity without a frame")


def test_enable_dpi_awareness_does_not_raise():
    from core.utils.dpi import enable_dpi_awareness
    try:
        enable_dpi_awareness()
        check(True, "enable_dpi_awareness runs without raising")
    except Exception as exc:  # pragma: no cover - defensive
        check(False, f"enable_dpi_awareness raised: {exc}")


# -------- runner ---------------------------------------------------------

def main():
    test_image_to_desktop_for_frame()
    test_round_trip_image_desktop_image()
    test_scale_actions_click_per_dpi()
    test_scale_actions_drag_and_ocr()
    test_idempotency_no_double_scale()
    test_desktop_rect_to_processed_clamps()
    test_no_frame_does_not_crash()
    test_enable_dpi_awareness_does_not_raise()

    print(f"\n=== DPI coordinate mapping: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
