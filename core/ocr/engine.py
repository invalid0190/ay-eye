import pytesseract
import cv2
import numpy as np
import time
from core.engine.event_bus import bus
from core.utils.logger import logger

class OCREngine:
    def __init__(self):
        self.last_run_time = 0
        self.cooldown = 2.0 # 2-3 seconds as requested

    def process(self, image):
        current_time = time.time()
        if current_time - self.last_run_time < self.cooldown:
            return None
            
        try:
            # Preprocessing
            open_cv_image = np.array(image)
            # RGB to BGR
            open_cv_image = open_cv_image[:, :, ::-1].copy()
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            
            text = pytesseract.image_to_string(thresh)
            self.last_run_time = current_time
            
            bus.publish("TEXT_UPDATED", text)
            logger.log_event("OCR_COMPLETED", {"text_length": len(text)})
            return text
        except Exception as e:
            logger.logger.error(f"OCR error: {e}")
            return None

ocr_engine = OCREngine()
