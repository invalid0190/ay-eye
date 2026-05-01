import ctypes
import time

import comtypes.client

from core.engine.event_bus import bus
from core.utils.logger import logger


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

    def scan_active_window(self):
        if not self.uia:
            return []

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            title = self._window_title(hwnd).lower()
            if "blender" in title:
                return []

            root = self.uia.ElementFromHandle(hwnd) if hwnd else self.uia.GetFocusedElement()
            if not root:
                return []

            elements = []
            condition = self.uia.CreateTrueCondition()
            found = root.FindAll(4, condition)  # TreeScope_Subtree
            total = min(found.Length, 250)

            for idx in range(total):
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

                if width <= 0 or height <= 0:
                    continue
                if not name and not role:
                    continue

                elements.append({
                    "name": name or role,
                    "role": role,
                    "rect": [rect.left, rect.top, width, height],
                    "text": name,
                })

            bus.publish("UI_UPDATED", elements)
            return elements
        except Exception as e:
            now = time.time()
            if now - self._last_error_log > 10:
                logger.logger.warning(f"UI scan skipped after automation error: {e}")
                self._last_error_log = now
            return []


ui_scanner = UIAutoScanner()
