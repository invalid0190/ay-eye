"""Regression tests for vision coordinate conversion."""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vision.live_perception import ScreenFrame, live_perception


def make_frame():
    raw = Image.new("RGB", (3840, 2160), "black")
    processed = Image.new("RGB", (1920, 1080), "black")
    return ScreenFrame(
        raw_image=raw,
        processed_image=processed,
        raw_size=(3840, 2160),
        processed_size=(1920, 1080),
        desktop_offset=(-1920, 0),
        monitor_info={"left": -1920, "top": 0, "width": 3840, "height": 2160},
        timestamp=123.0,
    )


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[PASS] {label}")


def main():
    frame = make_frame()
    with live_perception._lock:
        live_perception._latest_frame = frame

    response = {
        "actions": [
            {"type": "click", "x": 960, "y": 540},
            {"type": "drag", "x1": 100, "y1": 50, "x2": 300, "y2": 150},
            {"type": "ocr_screen", "x": 10, "y": 20, "w": 200, "h": 100},
        ]
    }
    live_perception.scale_actions(response)

    click = response["actions"][0]
    assert_equal((click["x"], click["y"]), (0, 1080), "click processed -> desktop with offset")
    assert_equal(click["_coord_space"], "desktop", "click coordinate space marked")
    assert_equal((click["_image_x"], click["_image_y"]), (960, 540), "click original image point kept")

    drag = response["actions"][1]
    assert_equal((drag["x1"], drag["y1"], drag["x2"], drag["y2"]), (-1720, 100, -1320, 300), "drag processed -> desktop")

    ocr = response["actions"][2]
    assert_equal((ocr["x"], ocr["y"], ocr["w"], ocr["h"]), (-1900, 40, 400, 200), "ocr region processed -> desktop")

    live_perception.scale_actions(response)
    assert_equal((click["x"], click["y"]), (0, 1080), "second scaling pass does not double-scale")

    print("\n=== Coordinate mapping tests passed ===")


if __name__ == "__main__":
    main()
