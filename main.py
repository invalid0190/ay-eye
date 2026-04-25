import time
import threading
import sys
from PyQt6.QtWidgets import QApplication
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
from core.vision.audio_capture import audio_capture
from core.state.manager import state_manager
from core.utils.logger import logger
from core.engine.event_bus import bus
from core.ui.dashboard import AyEyeDashboard
from core.ui.overlay import VisualOverlay

class Orchestrator:
    def __init__(self):
        self.running = False
        self.thread = None
        self.last_heartbeat = 0
        
        # Setup subscribers
        bus.subscribe("SCREEN_UPDATED", self.on_screen_update)
        bus.subscribe("AI_TRIGGERED", lambda d: logger.log_event("AI_CALL_REQUESTED", d))

    def start(self):
        self.running = True
        hotkey_manager.start()
        
        # Launch engine loop in background
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        
        # Startup Greeting (with small delay for TTS readiness)
        def _greet():
            time.sleep(2)
            bus.publish("AI_GREETING", {"text": "System online. I am Ay-Eye, standing by for your commands."})
        threading.Thread(target=_greet, daemon=True).start()
        
        logger.log_event("SYSTEM_STARTED")

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
            rect = win_info.get("rect")
            if not rect or rect[2] <= 0 or rect[3] <= 0:
                time.sleep(1)
                continue
                
            img = capture_module.capture_region(rect)
            
            # 3. Change Detection (Emits SCREEN_UPDATED if changed)
            if img:
                change_detector.process(img)
            
            # 4. Idle Check
            trigger_engine.check_idle()
            
            # Heartbeat every 5s
            if time.time() - self.last_heartbeat > 5:
                data = {"active_window": win_info["window"]}
                logger.log_event("HEARTBEAT", data)
                bus.publish("HEARTBEAT", data)
                self.last_heartbeat = time.time()

            # Performance Guardrail: Max 2Hz loop
            elapsed = time.time() - start_time
            sleep_time = max(0.5 - elapsed, 0.1)
            time.sleep(sleep_time)
            
            logger.log_performance("MAIN_LOOP", int(elapsed * 1000))

    def on_screen_update(self, image):
        # Triggered when screen actually changes
        ui_elements = ui_scanner.scan_active_window()
        text = ocr_engine.process(image)
        
        if text:
            state_manager.update(
                ui_elements=ui_elements,
                ocr_text=text
            )
            trigger_engine.check_error(text)
        else:
            state_manager.update(ui_elements=ui_elements)

if __name__ == "__main__":
    # 1. Initialize QApplication on the MAIN thread
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 2. Initialize Overlay (Highlighter)
    overlay = VisualOverlay()
    
    # 3. Initialize Dashboard (Status Bar)
    dashboard = AyEyeDashboard(overlay=overlay)
    
    # 4. Start the Orchestrator Engine (Background Thread)
    orch = Orchestrator()
    orch.start()
    
    # 5. Enter the Qt Main Loop
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        orch.stop()
        sys.exit(0)
