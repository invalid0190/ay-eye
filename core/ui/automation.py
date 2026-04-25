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
            root = self.uia.GetFocusedElement()
            if not root:
                return []
                
            elements = []
            # Simplified scan for MVP: find all buttons/links
            # In a real app, we'd walk the tree or use a condition
            # For now, just focus on the focused element context
            info = {
                "name": root.CurrentName,
                "role": root.CurrentClassName,
                "rect": [root.CurrentBoundingRectangle.left, root.CurrentBoundingRectangle.top]
            }
            elements.append(info)
            
            bus.publish("UI_UPDATED", elements)
            return elements
        except Exception as e:
            logger.logger.error(f"UI scan error: {e}")
            return []

ui_scanner = UIAutoScanner()
