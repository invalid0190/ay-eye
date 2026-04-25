import time
import threading
import multiprocessing
import sys
from core.vision.window_manager import WindowManager
from core.vision.capture import capture_module
from core.vision.change_detector import change_detector
from core.ui.automation import ui_scanner
from core.ocr.engine import ocr_engine
from core.engine.triggers import trigger_engine
from core.engine.brain import brain
from core.engine.hotkeys import hotkey_manager
from core.ocr.stt_engine import stt_engine
from core.engine.voice_controller import voice_controller
from core.engine.action_orchestrator import action_orchestrator
from core.state.manager import state_manager
from core.utils.logger import logger
from core.engine.event_bus import bus

class Orchestrator:
    def __init__(self):
        self.running = False
        self.thread = None
        
        # Setup subscribers
        bus.subscribe("SCREEN_UPDATED", self.on_screen_update)
        bus.subscribe("AI_TRIGGERED", lambda d: logger.log_event("AI_CALL_REQUESTED", d))

    def start(self):
        self.running = True
        hotkey_manager.start()
        
        # Launch Dashboard in a separate process
        multiprocessing.Process(target=self._launch_dashboard, daemon=True).start()
        
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        logger.log_event("SYSTEM_STARTED")

    def _launch_dashboard(self):
        from core.ui.dashboard import AyEyeDashboard
        from PyQt6.QtWidgets import QApplication
        app = QApplication(sys.argv)
        window = AyEyeDashboard()
        sys.exit(app.exec())

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def loop(self):
        while self.running:
            start_time = time.time()
            
            # 1. Window Detection
            win_info = WindowManager.get_active_window_info()
            if not win_info or win_info.get("is_sensitive"):
                time.sleep(1)
                continue
                
            # 2. Capture
            img = capture_module.capture_region(win_info["rect"])
            
            # 3. Change Detection (Emits SCREEN_UPDATED if changed)
            if img:
                change_detector.process(img)
            
            # 4. Idle Check
            trigger_engine.check_idle()
            
            # Performance Guardrail: Stay within < 30% CPU
            elapsed = time.time() - start_time
            sleep_time = max(0.5 - elapsed, 0.1) # Max 2Hz loop
            time.sleep(sleep_time)
            
            logger.log_performance("MAIN_LOOP", int(elapsed * 1000))

    def on_screen_update(self, image):
        # Triggered when screen actually changes
        # 1. UI Scan
        ui_elements = ui_scanner.scan_active_window()
        
        # 2. OCR (Handles its own cooldown)
        text = ocr_engine.process(image)
        
        # 3. Update State
        state_manager.update(
            ui_elements=ui_elements,
            ocr_text=text if text else state_manager.get_state().ocr_text
        )
        
        # 4. Trigger Check
        if text:
            trigger_engine.check_error(text)

if __name__ == "__main__":
    orch = Orchestrator()
    orch.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        orch.stop()
