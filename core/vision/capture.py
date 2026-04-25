import mss
import numpy as np
from PIL import Image
from core.engine.event_bus import bus
from core.utils.logger import logger

class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture_region(self, rect):
        try:
            # rect: [x, y, w, h]
            monitor = {"top": rect[1], "left": rect[0], "width": rect[2], "height": rect[3]}
            screenshot = self.sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Downscale for performance
            if img.width > 1280:
                img = img.resize((1280, int(img.height * (1280 / img.width))), Image.Resampling.LANCZOS)
            
            bus.publish("SCREEN_CAPTURED", img)
            return img
        except Exception as e:
            logger.logger.error(f"Capture error: {e}")
            return None

capture_module = ScreenCapture()
