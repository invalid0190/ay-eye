import mss
from PIL import Image, ImageChops
import threading
import time
import base64
from io import BytesIO
import os

from core.config import sys_config
from core.engine.event_bus import bus
from core.utils.logger import logger

class ScreenFrame:
    def __init__(self, raw_image, processed_image, raw_size, processed_size, desktop_offset, monitor_info, timestamp):
        self.raw_image = raw_image
        self.processed_image = processed_image
        self.raw_size = raw_size
        self.processed_size = processed_size
        self.desktop_offset = desktop_offset
        self.monitor_info = monitor_info
        self.timestamp = timestamp

class LivePerceptionService:
    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_frame = None
        self._fps = sys_config.get("live_perception_fps") or 5
        self._max_width = sys_config.get("live_perception_max_width") or 1920
        self._jpeg_quality = sys_config.get("live_perception_jpeg_quality") or 75
        self._sct = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.logger.info("LivePerceptionService started.")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._sct:
            self._sct.close()
            self._sct = None
        logger.logger.info("LivePerceptionService stopped.")

    def _loop(self):
        try:
            self._sct = mss.mss()
            while self._running:
                start_time = time.time()
                try:
                    # Capture monitor 0 (the full virtual desktop)
                    monitor = self._sct.monitors[0]
                    screenshot = self._sct.grab(monitor)
                    
                    raw_img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    
                    # Resize logic (matching original brain.py logic)
                    processed_img = raw_img
                    if raw_img.width > self._max_width:
                        ratio = self._max_width / raw_img.width
                        processed_img = raw_img.resize((self._max_width, int(raw_img.height * ratio)), Image.Resampling.LANCZOS)
                        
                    frame = ScreenFrame(
                        raw_image=raw_img,
                        processed_image=processed_img,
                        raw_size=(raw_img.width, raw_img.height),
                        processed_size=(processed_img.width, processed_img.height),
                        desktop_offset=(monitor["left"], monitor["top"]),
                        monitor_info=monitor,
                        timestamp=time.time()
                    )
                    
                    with self._lock:
                        self._latest_frame = frame
                        
                except Exception as e:
                    logger.logger.error(f"LivePerception loop error: {e}")
                
                elapsed = time.time() - start_time
                sleep_time = max(0, (1.0 / self._fps) - elapsed)
                time.sleep(sleep_time)
        except Exception as e:
            logger.logger.error(f"LivePerception setup error: {e}")

    def get_latest_frame(self):
        with self._lock:
            return self._latest_frame

    def get_latest_frame_b64(self):
        frame = self.get_latest_frame()
        if not frame:
            return None, None
        
        buffered = BytesIO()
        frame.processed_image.save(buffered, format="JPEG", quality=self._jpeg_quality)
        b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return b64, frame

    def image_to_desktop(self, x, y):
        frame = self.get_latest_frame()
        if not frame:
            return x, y
            
        raw_width, raw_height = frame.raw_size
        proc_width, proc_height = frame.processed_size
        offset_x, offset_y = frame.desktop_offset
        
        scale_x = raw_width / proc_width
        scale_y = raw_height / proc_height
        
        desktop_x = int(x * scale_x) + offset_x
        desktop_y = int(y * scale_y) + offset_y
        
        return desktop_x, desktop_y

    def desktop_to_image(self, x, y):
        frame = self.get_latest_frame()
        if not frame:
            return x, y
            
        raw_width, raw_height = frame.raw_size
        proc_width, proc_height = frame.processed_size
        offset_x, offset_y = frame.desktop_offset
        
        scale_x = raw_width / proc_width
        scale_y = raw_height / proc_height
        
        img_x = int((x - offset_x) / scale_x)
        img_y = int((y - offset_y) / scale_y)
        
        return img_x, img_y

    def scale_actions(self, response_json):
        """Scale AI coordinates (processed image) to desktop coordinates."""
        if not response_json:
            return response_json
            
        actions = []
        if "action" in response_json:
            actions = [response_json["action"]]
        elif "actions" in response_json:
            actions = response_json["actions"]
            
        for action in actions:
            a_type = action.get("type")
            # Scale single points
            if a_type in ["click", "double_click", "right_click", "hover"]:
                if "x" in action and "y" in action:
                    rx, ry = action["x"], action["y"]
                    dx, dy = self.image_to_desktop(rx, ry)
                    action["x"] = dx
                    action["y"] = dy
                    self.mark_planned_click(rx, ry, dx, dy, a_type)
            # Scale ranges
            elif a_type == "drag":
                if all(k in action for k in ["x1", "y1", "x2", "y2"]):
                    rx1, ry1 = action["x1"], action["y1"]
                    rx2, ry2 = action["x2"], action["y2"]
                    dx1, dy1 = self.image_to_desktop(rx1, ry1)
                    dx2, dy2 = self.image_to_desktop(rx2, ry2)
                    action["x1"], action["y1"] = dx1, dy1
                    action["x2"], action["y2"] = dx2, dy2
            elif a_type == "ocr_screen":
                if all(k in action for k in ["x", "y", "w", "h"]):
                    rx, ry = action["x"], action["y"]
                    rw, rh = action["w"], action["h"]
                    dx, dy = self.image_to_desktop(rx, ry)
                    
                    frame = self.get_latest_frame()
                    if frame:
                        scale_x = frame.raw_size[0] / frame.processed_size[0]
                        scale_y = frame.raw_size[1] / frame.processed_size[1]
                        action["w"] = int(rw * scale_x)
                        action["h"] = int(rh * scale_y)
                    
                    action["x"] = dx
                    action["y"] = dy
        return response_json

    def mark_planned_click(self, raw_x, raw_y, desktop_x, desktop_y, action_type="click"):
        frame = self.get_latest_frame()
        if not frame:
            return
            
        event_data = {
            "raw_x": raw_x,
            "raw_y": raw_y,
            "desktop_x": desktop_x,
            "desktop_y": desktop_y,
            "processed_size": frame.processed_size,
            "raw_size": frame.raw_size,
            "timestamp": time.time(),
            "action": action_type
        }
        
        if sys_config.get("click_debug_enabled"):
            logger.logger.info(f"PLANNED_CLICK_DEBUG: raw=({raw_x},{raw_y}) -> desktop=({desktop_x},{desktop_y})")
            bus.publish("PLANNED_CLICK_DEBUG", event_data)

    def verify_screen_changed(self, previous_frame):
        if not sys_config.get("post_action_verify_enabled"):
            return True
            
        current_frame = self.get_latest_frame()
        if not current_frame or not previous_frame:
            return True
            
        try:
            diff = ImageChops.difference(previous_frame.processed_image, current_frame.processed_image)
            bbox = diff.getbbox()
            if not bbox:
                logger.logger.warning("Click may have missed target. No screen change detected.")
                bus.publish("ACTION_VERIFICATION_FAILED", {"reason": "no_change"})
                return False
            return True
        except Exception as e:
            logger.logger.error(f"Error in verify_screen_changed: {e}")
            return True

live_perception = LivePerceptionService()
