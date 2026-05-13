import ctypes
import time

import comtypes.client

from core.engine.event_bus import bus
from core.utils.logger import logger
from core.utils.vision_cache import vision_cache
from core.vision.live_perception import live_perception


# Per-window element budget when walking many windows. The previous single-
# window scanner had a 250-element cap; multiplying that across N windows
# would dominate the orchestrator loop, so we shrink per-window and cap total.
_PER_WINDOW_ELEMENT_LIMIT = 120
_TOTAL_ELEMENT_LIMIT = 800

WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
)


class UIAutoScanner:
    def __init__(self):
        self._last_error_log = 0
        try:
            # Import UIAutomationClient
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient
            self.uia = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
        except Exception as e:
            logger.logger.error(f"UIAutomation init error: {e}")
            self.uia = None

    @staticmethod
    def _window_title(hwnd):
        if not hwnd:
            return ""

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""

        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def _is_visible(hwnd) -> bool:
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        if not user32.IsWindowVisible(hwnd):
            return False
        # Skip cloaked/minimised windows. GetWindowRect on a minimised window
        # returns -32000 coords, which we filter below anyway, but checking
        # iconic state up front avoids needless UIA traversals.
        if user32.IsIconic(hwnd):
            return False
        return True

    @staticmethod
    def _window_rect(hwnd):
        rect = ctypes.wintypes.RECT() if hasattr(ctypes, "wintypes") else None
        if rect is None:
            from ctypes import wintypes
            rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        left, top = rect.left, rect.top
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        # Filter offscreen/minimised sentinel coordinates.
        if left <= -30000 or top <= -30000:
            return None
        return left, top, width, height

    def _enumerate_top_level_windows(self):
        """Return a list of HWNDs for visible, non-trivial top-level windows,
        sorted with the foreground window first (so its labels win ties in the
        locator)."""
        hwnds: list[int] = []

        def _cb(hwnd, _lparam):
            try:
                if not self._is_visible(hwnd):
                    return True
                if not self._window_rect(hwnd):
                    return True
                title = self._window_title(hwnd)
                # Many shell-owned popups have empty titles. Skip them to keep
                # the tree small; named windows are what users refer to.
                if not title or len(title.strip()) < 2:
                    return True
                hwnds.append(int(hwnd))
            except Exception:
                pass
            return True

        ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

        foreground = ctypes.windll.user32.GetForegroundWindow()
        if foreground in hwnds:
            hwnds.remove(foreground)
            hwnds.insert(0, foreground)
        return hwnds

    def _walk_window(self, hwnd, per_window_limit=_PER_WINDOW_ELEMENT_LIMIT):
        """Walk the UI Automation subtree of a single window and return
        normalised element dicts. Returns [] on any error so one bad window
        cannot poison the whole scan."""
        try:
            root = self.uia.ElementFromHandle(hwnd)
        except Exception:
            return []
        if not root:
            return []

        try:
            condition = self.uia.CreateTrueCondition()
            found = root.FindAll(4, condition)  # TreeScope_Subtree
            total = min(found.Length, per_window_limit)
        except Exception:
            return []

        title = self._window_title(hwnd) or ""
        out = []
        for idx in range(total):
            try:
                element = found.GetElement(idx)
                rect = element.CurrentBoundingRectangle
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                name = (element.CurrentName or "").strip()
                role = (
                    getattr(element, "CurrentLocalizedControlType", "")
                    or element.CurrentClassName
                    or ""
                ).strip()
            except Exception:
                continue

            if width <= 0 or height <= 0:
                continue
            if not name and not role:
                continue
            # Reject sentinel offscreen coordinates UIA sometimes returns for
            # minimised / cloaked children.
            if rect.left <= -30000 or rect.top <= -30000:
                continue

            out.append({
                "name": name or role,
                "role": role,
                "rect": [rect.left, rect.top, width, height],
                "text": name,
                "window_hwnd": int(hwnd),
                "window_title": title,
            })
        return out

    def scan_active_window(self):
        """Scan every visible top-level window so cross-monitor targets stay
        findable even when their owning window is not the active one.

        The method name is preserved for backward compatibility with the rest
        of the codebase, but the semantics are now "scan all visible windows
        with the active one prioritised".
        """
        if not self.uia:
            return []

        try:
            foreground = ctypes.windll.user32.GetForegroundWindow()
            active_title = self._window_title(foreground).lower()
            if "blender" in active_title:
                # Blender's GPU-rendered viewport defeats UIA; keep skipping it
                # so we don't burn cycles walking 0-element trees.
                return []

            # Cache key combines screen-pixels phash + a fingerprint of the
            # current window set, so opening or closing a window invalidates
            # the cached scan even when pixels look similar.
            current_frame = live_perception.get_latest_frame()
            hwnds = self._enumerate_top_level_windows()
            fingerprint = tuple(hwnds[:16])
            cache_ns = f"ui_elements:{hash(fingerprint)}"
            cached = vision_cache.get(cache_ns, current_frame) if current_frame else None
            if cached is not None:
                bus.publish("UI_UPDATED", cached)
                return cached

            elements: list[dict] = []
            for hwnd in hwnds:
                if len(elements) >= _TOTAL_ELEMENT_LIMIT:
                    break
                remaining = _TOTAL_ELEMENT_LIMIT - len(elements)
                limit = min(_PER_WINDOW_ELEMENT_LIMIT, remaining)
                elements.extend(self._walk_window(hwnd, per_window_limit=limit))

            if current_frame is not None:
                vision_cache.set(cache_ns, current_frame, elements)
            bus.publish("UI_UPDATED", elements)
            return elements
        except Exception as e:
            now = time.time()
            if now - self._last_error_log > 10:
                logger.logger.warning(f"UI scan skipped after automation error: {e}")
                self._last_error_log = now
            return []


ui_scanner = UIAutoScanner()
