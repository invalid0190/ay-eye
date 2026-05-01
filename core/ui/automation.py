import ctypes

import comtypes.client

from core.engine.event_bus import bus
from core.utils.logger import logger


class UIAutoScanner:
    def __init__(self):
        try:
            # Import UIAutomationClient
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient
            self.uia = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
        except Exception as e:
            logger.logger.error(f"UIAutomation init error: {e}")
            self.uia = None

    def scan_active_window(self):
        if not self.uia:
            return []

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
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
            logger.logger.error(f"UI scan error: {e}")
            return []


ui_scanner = UIAutoScanner()
