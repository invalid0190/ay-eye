"""RapidOCR (ONNX) backend.

RapidOCR is a pure-Python ONNX wrapper around the PaddleOCR detection +
recognition models. It avoids two long-standing pain points in this repo:

  * No Tesseract install required (no PATH wrangling, no eng.traineddata).
  * No Node + Tesseract.js subprocess (saves ~300-800 ms per OCR call).

This module is intentionally optional: if ``rapidocr_onnxruntime`` is not
installed, ``rapid_ocr.available`` is False and callers should fall through
to their existing backends (pytesseract -> Node).

We expose two methods so the new backend slots into the existing call sites:
  * ``process(image) -> str``                  -- matches OCREngine.process
  * ``image_to_data(image) -> dict``           -- matches pytesseract Output.DICT
                                                  shape used by screen_locator
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import numpy as np
from PIL import Image

from core.utils.logger import logger


class RapidOcrEngine:
    def __init__(self):
        self._engine: Any = None
        self._init_attempted = False
        self._init_lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------

    def _lazy_init(self) -> bool:
        if self._engine is not None:
            return True
        if self._init_attempted and self._engine is None:
            return False
        with self._init_lock:
            if self._engine is not None:
                return True
            if self._init_attempted:
                return False
            self._init_attempted = True
            try:
                from rapidocr_onnxruntime import RapidOCR
                t0 = time.time()
                self._engine = RapidOCR()
                logger.logger.info(
                    f"RapidOCR initialised in {int((time.time() - t0) * 1000)} ms"
                )
                return True
            except ImportError:
                logger.logger.info(
                    "RapidOCR not installed (pip install rapidocr-onnxruntime). "
                    "Falling back to existing OCR backends."
                )
                return False
            except Exception as exc:
                logger.logger.warning(f"RapidOCR init failed: {exc}")
                return False

    @property
    def available(self) -> bool:
        return self._lazy_init()

    # -- inference --------------------------------------------------------

    def _run(self, image: Image.Image):
        if not self._lazy_init():
            return None
        if image is None:
            return None
        try:
            arr = np.array(image.convert("RGB"))
            # RapidOCR expects BGR by default but accepts RGB; result is a list of
            # [box, text, confidence] tuples in either case.
            result, _elapsed = self._engine(arr)
            return result or []
        except Exception as exc:
            logger.logger.warning(f"RapidOCR inference failed: {exc}")
            return None

    # -- public API matching OCREngine ------------------------------------

    def process(self, image: Image.Image) -> Optional[str]:
        result = self._run(image)
        if result is None:
            return None
        words = [str(item[1]).strip() for item in result if item and len(item) >= 2]
        return " ".join(w for w in words if w)

    # -- public API matching pytesseract Output.DICT ----------------------

    def image_to_data(self, image: Image.Image) -> Optional[dict]:
        """Return a pytesseract-compatible dict so screen_locator can reuse logic."""
        result = self._run(image)
        if result is None:
            return None

        data = {
            "text": [],
            "left": [],
            "top": [],
            "width": [],
            "height": [],
            "block_num": [],
            "par_num": [],
            "line_num": [],
            "conf": [],
        }

        for idx, item in enumerate(result):
            try:
                box, text, score = item[0], item[1], item[2] if len(item) > 2 else 0.9
            except Exception:
                continue
            text = str(text).strip()
            if not text:
                continue
            try:
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
            except Exception:
                continue
            if not xs or not ys:
                continue

            left = int(min(xs))
            top = int(min(ys))
            width = int(max(xs) - min(xs))
            height = int(max(ys) - min(ys))
            if width <= 0 or height <= 0:
                continue

            data["text"].append(text)
            data["left"].append(left)
            data["top"].append(top)
            data["width"].append(width)
            data["height"].append(height)
            # RapidOCR returns one entry per text line, not per word, so we
            # encode each entry as its own line; ScreenLocator already merges
            # adjacent words into phrases via _best_ocr_result.
            data["block_num"].append(1)
            data["par_num"].append(1)
            data["line_num"].append(idx + 1)
            # pytesseract conf is 0..100; RapidOCR score is 0..1.
            try:
                data["conf"].append(float(score) * 100.0)
            except Exception:
                data["conf"].append(-1)
        return data


rapid_ocr = RapidOcrEngine()
