import time
import threading
from core.engine.event_bus import bus
from core.engine.hotkeys import hotkey_manager
from core.utils.logger import logger

class ConfirmationBridge:
    def __init__(self):
        self.pending_confirmation = False
        self.confirmed = False
        self.timeout = 3.0
        
        bus.subscribe("CONFIRMATION_REQUIRED", self.wait_for_confirm)
        # Register Alt+Enter in hotkey manager logic (manually checked in hotkeys.py)
        
    def wait_for_confirm(self, action_data):
        self.pending_confirmation = True
        self.confirmed = False
        
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.confirmed:
                bus.publish("ACTION_CONFIRMED", action_data)
                self.pending_confirmation = False
                return
            time.sleep(0.1)
            
        logger.logger.warning("Confirmation timeout")
        bus.publish("ACTION_CANCELLED")
        self.pending_confirmation = False

    def confirm(self):
        if self.pending_confirmation:
            self.confirmed = True

confirm_bridge = ConfirmationBridge()
