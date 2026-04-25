import pygetwindow as gw
import pyautogui
from core.state.manager import state_manager
from core.utils.logger import logger

class WindowManager:
    BLACKLIST = ["Incognito", "Private Browsing", "Password Manager", "Bank", "Vault"]

    @staticmethod
    def get_active_window_info():
        try:
            active_window = gw.getActiveWindow()
            if not active_window:
                return None
            
            title = active_window.title
            app = title.split(" - ")[-1] # Basic heuristic
            
            is_sensitive = any(term.lower() in title.lower() for term in WindowManager.BLACKLIST)
            
            # Get monitor info based on mouse pos
            mouse_x, mouse_y = pyautogui.position()
            # Simple monitor detection (simplified for MVP)
            monitor = 0 
            
            info = {
                "window": title,
                "app": app,
                "monitor": monitor,
                "rect": [active_window.left, active_window.top, active_window.width, active_window.height],
                "is_sensitive": is_sensitive
            }
            
            logger.log_event("WINDOW_DETECTED", {"title": title, "is_sensitive": is_sensitive})
            return info
        except Exception as e:
            logger.logger.error(f"Error detecting window: {e}")
            return None

if __name__ == "__main__":
    # Quick test
    info = WindowManager.get_active_window_info()
    print(info)
