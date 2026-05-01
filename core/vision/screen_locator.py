import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from PIL import Image

from core.utils.logger import logger


@dataclass(frozen=True)
class ScreenLocatorResult:
    target: str
    method: str
    label: str
    x: int
    y: int
    bbox: tuple
    confidence: float


class ScreenLocator:
    """Find the most reliable click point for visible screen targets."""

    GENERIC_TARGETS = {
        "area",
        "button",
        "click",
        "contextmenu",
        "coordinate",
        "element",
        "icon",
        "menu",
        "screen",
        "somewhere",
        "target",
    }

    def __init__(self):
        self.default_min_confidence = 0.62
        self.max_ui_state_age_seconds = 10.0
        self._last_ocr_error_log = 0.0

    @staticmethod
    def clean_label(value):
        return "".join(ch for ch in (value or "").lower() if ch.isalnum())

    @staticmethod
    def _safe_conf(value):
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return None
        if conf < 0:
            return None
        return max(0.0, min(1.0, conf / 100.0))

    def is_specific_target(self, target):
        target_clean = self.clean_label(target)
        if len(target_clean) < 3:
            return False
        return target_clean not in self.GENERIC_TARGETS

    def _label_score(self, target, label):
        target_clean = self.clean_label(target)
        label_clean = self.clean_label(label)
        if not target_clean or not label_clean:
            return 0.0

        if target_clean == label_clean:
            return 1.0

        if len(target_clean) <= 2 or len(label_clean) <= 2:
            return 0.0

        if target_clean in label_clean:
            coverage = len(target_clean) / max(1, len(label_clean))
            return min(0.94, 0.78 + (coverage * 0.16))

        if label_clean in target_clean:
            coverage = len(label_clean) / max(1, len(target_clean))
            return min(0.88, 0.68 + (coverage * 0.16))

        ratio = SequenceMatcher(None, target_clean, label_clean).ratio()
        if ratio < 0.58:
            return 0.0
        return ratio * 0.86

    @staticmethod
    def _center_from_rect(rect):
        if not rect or len(rect) < 2:
            return None

        if len(rect) >= 4:
            x, y, w, h = rect[:4]
            if w <= 0 or h <= 0:
                return None
            return int(x + (w / 2)), int(y + (h / 2)), (int(x), int(y), int(w), int(h))

        x, y = rect[:2]
        return int(x), int(y), (int(x), int(y), 1, 1)

    def _locate_uia(self, target):
        try:
            from core.state.manager import state_manager

            state = state_manager.get_state()
            if state.last_update_time:
                age = (datetime.now() - state.last_update_time).total_seconds()
                if age > self.max_ui_state_age_seconds:
                    logger.logger.info(
                        f"ScreenLocator: Skipping stale UI Automation state ({age:.1f}s old)"
                    )
                    return None

            best = None
            best_score = 0.0

            for element in state.ui_elements:
                center = self._center_from_rect(element.rect)
                if not center:
                    continue

                labels = [
                    element.name or "",
                    element.text or "",
                    " ".join(part for part in [element.name, element.text, element.role] if part),
                ]

                score = max(self._label_score(target, label) for label in labels if label)
                if score > best_score:
                    x, y, bbox = center
                    best = ScreenLocatorResult(
                        target=target,
                        method="uia",
                        label=element.name or element.text or element.role,
                        x=x,
                        y=y,
                        bbox=bbox,
                        confidence=score,
                    )
                    best_score = score

            return best
        except Exception as exc:
            logger.logger.warning(f"ScreenLocator: UI Automation locate failed for '{target}': {exc}")
            return None

    def _configure_tesseract(self, pytesseract):
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Tesseract-OCR", "tesseract.exe"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return True

        if shutil.which("tesseract"):
            return True

        return False

    def _capture_image(self, frame):
        if frame and getattr(frame, "raw_image", None):
            return frame.raw_image, frame.desktop_offset

        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screenshot = sct.grab(monitor)
            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return image, (monitor["left"], monitor["top"])

    def _ocr_entries(self, ocr_data):
        entries = []
        texts = ocr_data.get("text", [])
        for idx, text in enumerate(texts):
            word = (text or "").strip()
            if not word:
                continue

            try:
                x = int(ocr_data["left"][idx])
                y = int(ocr_data["top"][idx])
                w = int(ocr_data["width"][idx])
                h = int(ocr_data["height"][idx])
            except (KeyError, IndexError, TypeError, ValueError):
                continue

            if w <= 0 or h <= 0:
                continue

            entries.append(
                {
                    "idx": idx,
                    "text": word,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "block": self._ocr_value(ocr_data, "block_num", idx),
                    "paragraph": self._ocr_value(ocr_data, "par_num", idx),
                    "line": self._ocr_value(ocr_data, "line_num", idx),
                    "conf": self._safe_conf(self._ocr_value(ocr_data, "conf", idx)),
                }
            )
        return entries

    @staticmethod
    def _ocr_value(ocr_data, key, idx):
        values = ocr_data.get(key, [])
        try:
            return values[idx]
        except (IndexError, TypeError):
            return None

    @staticmethod
    def _same_ocr_line(first, other):
        return (
            first["block"] == other["block"]
            and first["paragraph"] == other["paragraph"]
            and first["line"] == other["line"]
        )

    def _best_ocr_result(self, target, ocr_data, offset=(0, 0)):
        entries = self._ocr_entries(ocr_data)
        if not entries:
            return None

        best = None
        best_score = 0.0
        off_x, off_y = offset

        for start_i, start_entry in enumerate(entries):
            text_parts = []
            confs = []
            x1 = start_entry["x"]
            y1 = start_entry["y"]
            x2 = start_entry["x"] + start_entry["w"]
            y2 = start_entry["y"] + start_entry["h"]

            for entry in entries[start_i : min(start_i + 6, len(entries))]:
                if not self._same_ocr_line(start_entry, entry):
                    break

                text_parts.append(entry["text"])
                if entry["conf"] is not None:
                    confs.append(entry["conf"])

                x1 = min(x1, entry["x"])
                y1 = min(y1, entry["y"])
                x2 = max(x2, entry["x"] + entry["w"])
                y2 = max(y2, entry["y"] + entry["h"])

                candidate_text = " ".join(text_parts)
                text_score = self._label_score(target, candidate_text)
                if text_score <= 0:
                    continue

                ocr_quality = sum(confs) / len(confs) if confs else 0.74
                score = text_score * (0.82 + (ocr_quality * 0.18))
                if score > best_score:
                    desktop_x1 = int(off_x + x1)
                    desktop_y1 = int(off_y + y1)
                    w = int(x2 - x1)
                    h = int(y2 - y1)
                    best = ScreenLocatorResult(
                        target=target,
                        method="ocr",
                        label=candidate_text,
                        x=int(desktop_x1 + (w / 2)),
                        y=int(desktop_y1 + (h / 2)),
                        bbox=(desktop_x1, desktop_y1, w, h),
                        confidence=score,
                    )
                    best_score = score

        return best

    def _words_to_ocr_data(self, words):
        sorted_words = sorted(
            words,
            key=lambda word: (int(word.get("top", 0)), int(word.get("left", 0))),
        )
        line_centers = []
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

        for word in sorted_words:
            text = str(word.get("text", "")).strip()
            if not text:
                continue

            left = int(word.get("left", 0))
            top = int(word.get("top", 0))
            width = int(word.get("width", 0))
            height = int(word.get("height", 0))
            if width <= 0 or height <= 0:
                continue

            center_y = top + (height / 2)
            tolerance = max(8.0, height * 0.65)
            line_num = None
            for idx, existing_center in enumerate(line_centers, start=1):
                if abs(center_y - existing_center) <= tolerance:
                    line_num = idx
                    line_centers[idx - 1] = (existing_center + center_y) / 2
                    break
            if line_num is None:
                line_centers.append(center_y)
                line_num = len(line_centers)

            data["text"].append(text)
            data["left"].append(left)
            data["top"].append(top)
            data["width"].append(width)
            data["height"].append(height)
            data["block_num"].append(1)
            data["par_num"].append(1)
            data["line_num"].append(line_num)
            data["conf"].append(word.get("conf", -1))

        return data

    def _node_ocr_data(self, image):
        node_exe = shutil.which("node")
        if not node_exe:
            return None

        worker_script = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ocr", "node_engine", "ocr_data_worker.js")
        )
        if not os.path.exists(worker_script):
            return None

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name
            image.save(temp_path)

            result = subprocess.run(
                [node_exe, worker_script, temp_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=15,
                check=False,
            )
            output = result.stdout or ""
            if result.returncode != 0 or "RESULT_JSON_START" not in output:
                error = (result.stderr or output or "").strip()
                logger.logger.warning(f"ScreenLocator: Node OCR failed: {error[:200]}")
                return None

            payload = output.split("RESULT_JSON_START", 1)[1].split("RESULT_JSON_END", 1)[0].strip()
            data = json.loads(payload)
            return self._words_to_ocr_data(data.get("words", []))
        except Exception as exc:
            logger.logger.warning(f"ScreenLocator: Node OCR data failed: {exc}")
            return None
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _locate_ocr(self, target, frame=None):
        try:
            image, offset = self._capture_image(frame)

            ocr_data = None
            try:
                import pytesseract
                from pytesseract import Output

                if self._configure_tesseract(pytesseract):
                    ocr_data = pytesseract.image_to_data(image, output_type=Output.DICT)
            except Exception as exc:
                logger.logger.info(f"ScreenLocator: pytesseract unavailable, trying Node OCR: {exc}")

            if not ocr_data:
                ocr_data = self._node_ocr_data(image)

            if not ocr_data:
                return None

            return self._best_ocr_result(target, ocr_data, offset)
        except Exception as exc:
            now = time.time()
            if now - self._last_ocr_error_log > 10:
                logger.logger.warning(f"ScreenLocator: OCR locate failed for '{target}': {exc}")
                self._last_ocr_error_log = now
            return None

    def _locate_visual_near(self, target, approximate, frame=None, search_radius=72):
        if not approximate:
            return None

        try:
            import numpy as np

            image, offset = self._capture_image(frame)
            off_x, off_y = offset
            raw_x = int(approximate[0] - off_x)
            raw_y = int(approximate[1] - off_y)

            if raw_x < 0 or raw_y < 0 or raw_x >= image.width or raw_y >= image.height:
                return None

            left = max(0, raw_x - search_radius)
            top = max(0, raw_y - search_radius)
            right = min(image.width, raw_x + search_radius + 1)
            bottom = min(image.height, raw_y + search_radius + 1)
            crop = image.crop((left, top, right, bottom)).convert("RGB")
            arr = np.asarray(crop, dtype=np.int16)
            h, w = arr.shape[:2]
            if h < 6 or w < 6:
                return None

            gray = (
                (arr[:, :, 0] * 0.299)
                + (arr[:, :, 1] * 0.587)
                + (arr[:, :, 2] * 0.114)
            )

            grad = np.zeros((h, w), dtype=float)
            grad[:, 1:] += np.abs(gray[:, 1:] - gray[:, :-1])
            grad[1:, :] += np.abs(gray[1:, :] - gray[:-1, :])

            border = np.concatenate(
                [
                    arr[:2, :, :].reshape(-1, 3),
                    arr[-2:, :, :].reshape(-1, 3),
                    arr[:, :2, :].reshape(-1, 3),
                    arr[:, -2:, :].reshape(-1, 3),
                ]
            )
            background = np.median(border, axis=0)
            color_delta = np.sqrt(((arr - background) ** 2).sum(axis=2))

            edge_threshold = max(10.0, float(np.percentile(grad, 82)))
            color_threshold = max(18.0, float(np.percentile(color_delta, 75)))
            mask = ((grad >= edge_threshold) & (color_delta >= 8.0)) | (color_delta >= color_threshold)

            for _ in range(2):
                padded = np.pad(mask, 1, mode="constant", constant_values=False)
                mask = (
                    padded[1:-1, 1:-1]
                    | padded[:-2, 1:-1]
                    | padded[2:, 1:-1]
                    | padded[1:-1, :-2]
                    | padded[1:-1, 2:]
                    | padded[:-2, :-2]
                    | padded[:-2, 2:]
                    | padded[2:, :-2]
                    | padded[2:, 2:]
                )

            visited = np.zeros(mask.shape, dtype=bool)
            approx_local_x = raw_x - left
            approx_local_y = raw_y - top
            best = None
            best_score = 0.0

            ys, xs = np.nonzero(mask)
            for seed_y, seed_x in zip(ys.tolist(), xs.tolist()):
                if visited[seed_y, seed_x]:
                    continue

                stack = [(seed_x, seed_y)]
                visited[seed_y, seed_x] = True
                count = 0
                min_x = max_x = seed_x
                min_y = max_y = seed_y

                while stack:
                    px, py = stack.pop()
                    count += 1
                    min_x = min(min_x, px)
                    max_x = max(max_x, px)
                    min_y = min(min_y, py)
                    max_y = max(max_y, py)

                    for ny in range(max(0, py - 1), min(h, py + 2)):
                        for nx in range(max(0, px - 1), min(w, px + 2)):
                            if visited[ny, nx] or not mask[ny, nx]:
                                continue
                            visited[ny, nx] = True
                            stack.append((nx, ny))

                box_w = max_x - min_x + 1
                box_h = max_y - min_y + 1
                box_area = box_w * box_h
                if count < 8 or box_area < 16:
                    continue
                if box_area > (w * h * 0.55):
                    continue

                center_x = min_x + (box_w / 2)
                center_y = min_y + (box_h / 2)
                distance = ((center_x - approx_local_x) ** 2 + (center_y - approx_local_y) ** 2) ** 0.5
                if distance > search_radius * 0.95:
                    continue

                density = count / max(1, box_area)
                distance_score = max(0.0, 1.0 - (distance / max(1.0, search_radius)))
                size_score = min(1.0, (count ** 0.5) / 16.0)
                contains_point = (
                    min_x - 3 <= approx_local_x <= max_x + 3
                    and min_y - 3 <= approx_local_y <= max_y + 3
                )
                score = (
                    0.34
                    + (0.42 * distance_score)
                    + (0.14 * size_score)
                    + (0.07 * min(1.0, density * 2.0))
                    + (0.08 if contains_point else 0.0)
                )
                score = min(0.93, score)

                if score > best_score:
                    desktop_x = int(off_x + left + center_x)
                    desktop_y = int(off_y + top + center_y)
                    best = ScreenLocatorResult(
                        target=target or "visual target",
                        method="visual",
                        label=f"visual target near ({int(approximate[0])},{int(approximate[1])})",
                        x=desktop_x,
                        y=desktop_y,
                        bbox=(int(off_x + left + min_x), int(off_y + top + min_y), int(box_w), int(box_h)),
                        confidence=score,
                    )
                    best_score = score

            return best
        except Exception as exc:
            logger.logger.warning(f"ScreenLocator: Visual locate failed for '{target}': {exc}")
            return None

    def locate(self, target, frame=None, methods=("uia", "ocr"), min_confidence=None, approximate=None):
        if not self.is_specific_target(target):
            return None

        threshold = self.default_min_confidence if min_confidence is None else min_confidence
        results = []

        for method in methods:
            if method == "uia":
                result = self._locate_uia(target)
            elif method == "ocr":
                result = self._locate_ocr(target, frame)
            elif method == "visual":
                result = self._locate_visual_near(target, approximate, frame)
            else:
                continue

            if result:
                if result.confidence >= max(0.92, threshold):
                    logger.logger.info(
                        f"ScreenLocator: Located '{target}' via {result.method} as '{result.label}' "
                        f"at ({result.x},{result.y}), confidence={result.confidence:.2f}"
                    )
                    return result
                results.append(result)

        if not results:
            return None

        best = max(results, key=lambda item: item.confidence)
        if best.confidence < threshold:
            logger.logger.info(
                f"ScreenLocator: Best match for '{target}' below threshold: "
                f"{best.method} '{best.label}' confidence={best.confidence:.2f}"
            )
            return None

        logger.logger.info(
            f"ScreenLocator: Located '{target}' via {best.method} as '{best.label}' "
            f"at ({best.x},{best.y}), confidence={best.confidence:.2f}"
        )
        return best


screen_locator = ScreenLocator()
