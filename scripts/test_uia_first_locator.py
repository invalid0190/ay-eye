"""Regression tests for ScreenLocator's UIA-first behaviour and the
RapidOCR pytesseract-shape compatibility layer.

We cannot rely on a real UIAutomation provider or RapidOCR install at test
time, so each backend method is monkeypatched with a deterministic stub.

Covered:
  * UIA returns a moderate-confidence hit -> OCR is never invoked.
  * UIA returns nothing -> OCR fallback runs and is returned.
  * UIA below short-circuit but OCR also weak -> highest above min_confidence wins.
  * Generic targets ("button", "icon") are rejected before any backend runs.
  * RapidOCR.image_to_data shape matches what _best_ocr_result consumes.
  * Locating against a synthetic OCR data dict produces a desktop-space click point.

Run:
    .venv\\Scripts\\python scripts\\test_uia_first_locator.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vision.screen_locator import ScreenLocator, ScreenLocatorResult


PASS = []
FAIL = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


# -- helpers ------------------------------------------------------------

def make_uia_result(target, confidence, label="Button"):
    return ScreenLocatorResult(
        target=target,
        method="uia",
        label=label,
        x=100,
        y=200,
        bbox=(80, 180, 40, 40),
        confidence=confidence,
    )


def make_ocr_result(target, confidence, label="Button"):
    return ScreenLocatorResult(
        target=target,
        method="ocr",
        label=label,
        x=300,
        y=400,
        bbox=(280, 380, 40, 40),
        confidence=confidence,
    )


class StubbedLocator(ScreenLocator):
    """Replace the real backend probes with deterministic stubs."""

    def __init__(self, uia=None, ocr=None):
        super().__init__()
        self._uia_result = uia
        self._ocr_result = ocr
        self.uia_calls = 0
        self.ocr_calls = 0

    def _locate_uia(self, target):
        self.uia_calls += 1
        return self._uia_result

    def _locate_ocr(self, target, frame=None):
        self.ocr_calls += 1
        return self._ocr_result


# -- tests --------------------------------------------------------------

def test_uia_short_circuit_skips_ocr():
    loc = StubbedLocator(uia=make_uia_result("Save", 0.85), ocr=make_ocr_result("Save", 0.95))
    out = loc.locate("Save")
    check(out is not None and out.method == "uia", "UIA result returned when above short-circuit threshold")
    check(loc.ocr_calls == 0, "OCR backend never invoked when UIA short-circuits")


def test_low_uia_falls_back_to_ocr_when_ocr_strong():
    # UIA confidence below the UIA short-circuit (0.78) but above min_confidence;
    # OCR is strong enough to win. Highest-confidence result must be returned.
    loc = StubbedLocator(uia=make_uia_result("Save", 0.65), ocr=make_ocr_result("Save", 0.95))
    out = loc.locate("Save")
    check(out is not None and out.method == "ocr", "OCR wins when its confidence beats a low-UIA hit")
    check(loc.ocr_calls == 1, "OCR backend invoked when UIA didn't short-circuit")


def test_uia_only_when_ocr_unavailable():
    loc = StubbedLocator(uia=make_uia_result("Save", 0.7), ocr=None)
    out = loc.locate("Save")
    check(out is not None and out.method == "uia", "UIA result returned when OCR returns nothing")


def test_below_min_confidence_returns_none():
    loc = StubbedLocator(uia=make_uia_result("Save", 0.4), ocr=make_ocr_result("Save", 0.3))
    out = loc.locate("Save")
    check(out is None, "below default min_confidence -> None")


def test_uia_short_circuit_threshold_is_lower_than_visual():
    # 0.78 (UIA short-circuit) MUST be lower than 0.92 (visual/OCR short-circuit)
    # otherwise UIA-first does nothing extra over the previous behaviour.
    check(
        ScreenLocator.UIA_SHORT_CIRCUIT_CONFIDENCE < 0.92,
        "UIA short-circuit threshold tighter than visual/OCR threshold",
    )


def test_generic_targets_rejected_early():
    loc = StubbedLocator(uia=make_uia_result("button", 0.99), ocr=make_ocr_result("button", 0.99))
    out = loc.locate("button")
    check(out is None, "generic target 'button' rejected before backends run")
    check(loc.uia_calls == 0 and loc.ocr_calls == 0, "no backend probes for generic target")


def test_min_confidence_override_takes_effect():
    # min_confidence higher than the UIA hit's confidence -> UIA does not short-circuit.
    loc = StubbedLocator(uia=make_uia_result("Save", 0.80), ocr=make_ocr_result("Save", 0.94))
    out = loc.locate("Save", min_confidence=0.93)
    check(out is not None and out.method == "ocr", "min_confidence override forces OCR fallback")


def test_rapidocr_image_to_data_shape_consumable_by_locator():
    """Synthetic RapidOCR-style words must produce a real OCR locate result."""
    from PIL import Image

    locator = ScreenLocator()
    # Build a pytesseract-shaped dict identical to what RapidOcrEngine.image_to_data emits.
    ocr_data = {
        "text":      ["Cancel", "Save",  "File"],
        "left":      [10,       100,     200],
        "top":       [10,       10,      10],
        "width":     [40,       40,      40],
        "height":    [16,       16,      16],
        "block_num": [1, 1, 1],
        "par_num":   [1, 1, 1],
        "line_num":  [1, 1, 1],
        "conf":      [98.0, 99.0, 70.0],
    }
    result = locator._best_ocr_result("Save", ocr_data, offset=(-1920, 0))
    check(result is not None, "RapidOCR-shaped dict produces an OCR locate result")
    if result is None:
        return
    # Center of "Save" word: x=100..140, y=10..26 -> center (120, 18) + offset (-1920, 0).
    check(result.x == -1800 and result.y == 18, "OCR center mapped through desktop offset correctly")
    check(result.method == "ocr", "result tagged as ocr method")
    check(result.confidence >= 0.78, "high-confidence label match scored well")


# -- runner -------------------------------------------------------------

def main():
    test_uia_short_circuit_skips_ocr()
    test_low_uia_falls_back_to_ocr_when_ocr_strong()
    test_uia_only_when_ocr_unavailable()
    test_below_min_confidence_returns_none()
    test_uia_short_circuit_threshold_is_lower_than_visual()
    test_generic_targets_rejected_early()
    test_min_confidence_override_takes_effect()
    test_rapidocr_image_to_data_shape_consumable_by_locator()

    print(f"\n=== UIA-first locator: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
