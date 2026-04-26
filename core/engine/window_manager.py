"""
Windows Application Manager for Ay-Eye.
Handles launching apps, switching to running windows, and finding installed programs.
"""
import subprocess
import os
import ctypes
import ctypes.wintypes
from core.utils.logger import logger


class WindowManager:
    """Manages Windows application launching and window switching."""

    # Common Windows apps and their Start Menu search names / executables
    APP_REGISTRY = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "settings": "ms-settings:",
        "control panel": "control.exe",
        "snipping tool": "snippingtool.exe",
        "edge": "msedge.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        "code": "code",
        "vscode": "code",
        "vs code": "code",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "outlook": "outlook.exe",
        "spotify": os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
        "discord": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Discord", "Update.exe --processStart Discord.exe"),
        "slack": os.path.join(os.environ.get("LOCALAPPDATA", ""), "slack", "slack.exe"),
        "telegram": os.path.join(os.environ.get("APPDATA", ""), "Telegram Desktop", "Telegram.exe"),
        "whatsapp": "explorer.exe shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    }

    def launch(self, app_name):
        """Launch an application by name. Tries multiple strategies."""
        app_lower = app_name.lower().strip()

        # Strategy 1: Check the registry for known paths
        if app_lower in self.APP_REGISTRY:
            exe_path = self.APP_REGISTRY[app_lower]
            try:
                if exe_path.startswith("ms-") or exe_path.startswith("explorer.exe shell:"):
                    subprocess.Popen(f"start {exe_path}", shell=True)
                else:
                    subprocess.Popen(exe_path, shell=True)
                logger.logger.info(f"WindowManager: Launched '{app_lower}' via registry")
                return True
            except Exception as e:
                logger.logger.warning(f"WindowManager: Registry launch failed for '{app_lower}': {e}")

        # Strategy 2: Try Windows Search (Start Menu)
        try:
            subprocess.Popen(
                f'powershell -Command "Start-Process \'{app_name}\'"',
                shell=True
            )
            logger.logger.info(f"WindowManager: Launched '{app_name}' via PowerShell Start-Process")
            return True
        except Exception as e:
            logger.logger.warning(f"WindowManager: PowerShell launch failed: {e}")

        # Strategy 3: Raw 'start' command as last resort
        try:
            subprocess.Popen(f'start "" "{app_name}"', shell=True)
            logger.logger.info(f"WindowManager: Launched '{app_name}' via start command")
            return True
        except Exception as e:
            logger.logger.error(f"WindowManager: All launch strategies failed for '{app_name}': {e}")
            return False

    def switch_to(self, app_name):
        """Switch to an already-running application window by searching window titles."""
        try:
            import pyautogui

            # Use EnumWindows to find matching windows
            target = app_name.lower().strip()
            found_hwnd = None

            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            results = []

            def callback(hwnd, lParam):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLength(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buf, length + 1)
                        title = buf.value
                        if target in title.lower():
                            results.append((hwnd, title))
                return True

            EnumWindows(EnumWindowsProc(callback), 0)

            if results:
                hwnd, title = results[0]
                # Bring window to foreground
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                logger.logger.info(f"WindowManager: Switched to '{title}'")
                return True
            else:
                logger.logger.warning(f"WindowManager: No running window found for '{target}'")
                return False

        except Exception as e:
            logger.logger.error(f"WindowManager: Switch failed: {e}")
            return False

    def list_windows(self):
        """List all visible windows with titles (for debugging)."""
        windows = []
        try:
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            def callback(hwnd, lParam):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLength(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buf, length + 1)
                        windows.append(buf.value)
                return True

            EnumWindows(EnumWindowsProc(callback), 0)
        except Exception as e:
            logger.logger.error(f"WindowManager: List failed: {e}")

        return windows


window_manager = WindowManager()
