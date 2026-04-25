import imagehash
from core.engine.event_bus import bus
from core.utils.logger import logger

class ChangeDetector:
    def __init__(self, threshold=5):
        self.last_hash = None
        self.threshold = threshold

    def process(self, image):
        current_hash = imagehash.phash(image)
        if self.last_hash is None:
            self.last_hash = current_hash
            bus.publish("SCREEN_UPDATED", image)
            return True

        diff = current_hash - self.last_hash
        if diff > self.threshold:
            self.last_hash = current_hash
            bus.publish("SCREEN_UPDATED", image)
            logger.log_event("SCREEN_CHANGE_DETECTED", {"diff": int(diff)})
            return True
        
        return False

change_detector = ChangeDetector()
