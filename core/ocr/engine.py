import subprocess
import cv2
import numpy as np
import time
import os
from core.engine.event_bus import bus
from core.utils.logger import logger

class OCREngine:
    def __init__(self):
        self.last_run_time = 0
        self.cooldown = 2.0
        self.node_path = "node"
        self.worker_script = os.path.join(os.path.dirname(__file__), "node_engine", "ocr_worker.js")
        self.temp_image = os.path.join(os.path.dirname(__file__), "node_engine", "temp_ocr.png")

    def process(self, image):
        if image is None:
            return None
            
        current_time = time.time()
        if current_time - self.last_run_time < self.cooldown:
            return None
            
        try:
            # Preprocessing
            open_cv_image = np.array(image)
            if open_cv_image is None or len(open_cv_image.shape) < 2:
                return None

            # RGB to BGR
            if len(open_cv_image.shape) == 3:
                open_cv_image = open_cv_image[:, :, ::-1].copy()
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = open_cv_image
                
            if gray is None:
                return None
                
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            
            # Save temporary image for Node worker
            cv2.imwrite(self.temp_image, thresh)
            
            # Find node binary
            import shutil
            node_exe = shutil.which(self.node_path) or "node"
            
            # Call Node OCR worker
            result = subprocess.run(
                [node_exe, self.worker_script, self.temp_image],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False # Don't raise exception on error, handle manually
            )
            
            output = result.stdout
            if output and isinstance(output, str) and "RESULT_START" in output and "RESULT_END" in output:
                text = output.split("RESULT_START")[1].split("RESULT_END")[0].strip()
            else:
                text = ""

            self.last_run_time = current_time
            
            bus.publish("TEXT_UPDATED", text)
            logger.log_event("OCR_COMPLETED", {"text_length": len(text)})
            return text
        except Exception as e:
            logger.logger.error(f"OCR Node Error: {type(e).__name__}: {e}")
            return None

ocr_engine = OCREngine()

