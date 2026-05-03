"""
Windows Application Manager for Ay-Eye.
Handles launching apps, switching to running windows, and finding installed programs.
"""
import subprocess
import os
import ctypes
import ctypes.wintypes
from core.utils.logger import logger


def _ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


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
        "slack": os.path.join(os.environ.get("LOCALAPPDATA", ""), "slack", "slack.exe"),
        "telegram": os.path.join(os.environ.get("APPDATA", ""), "Telegram Desktop", "Telegram.exe"),
        "whatsapp": "explorer.exe shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    }

    # Electron apps that use Update.exe --processStart
    ELECTRON_APPS = {
        "discord": ("Discord", "Discord.exe"),
        "slack": ("slack", "slack.exe"),
    }

    def _find_electron_app(self, app_name):
        """Find an Electron app that uses Update.exe in LOCALAPPDATA."""
        if app_name not in self.ELECTRON_APPS:
            return None
        folder, exe_name = self.ELECTRON_APPS[app_name]
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        update_exe = os.path.join(local_appdata, folder, "Update.exe")
        if os.path.exists(update_exe):
            return update_exe, exe_name
        return None

    def launch(self, app_name):
        """Launch an application by name. Tries multiple strategies."""
        app_lower = app_name.lower().strip()

        # Strategy 0: Electron apps (Discord, Slack, etc.)
        electron = self._find_electron_app(app_lower)
        if electron:
            update_exe, exe_name = electron
            try:
                subprocess.Popen([update_exe, "--processStart", exe_name])
                logger.logger.info(f"WindowManager: Launched '{app_lower}' via Update.exe")
                return True
            except Exception as e:
                logger.logger.warning(f"WindowManager: Electron launch failed for '{app_lower}': {e}")

        # Strategy 0.5: Special dynamic path resolution for Blender
        if app_lower == "blender":
            blender_base = r"C:\Program Files\Blender Foundation"
            if os.path.exists(blender_base):
                try:
                    for folder in os.listdir(blender_base):
                        if folder.startswith("Blender"):
                            exe_path = os.path.join(blender_base, folder, "blender.exe")
                            if os.path.exists(exe_path):
                                subprocess.Popen(f'"{exe_path}"', shell=True)
                                logger.logger.info(f"WindowManager: Launched Blender dynamically at {exe_path}")
                                return True
                except Exception as e:
                    logger.logger.warning(f"WindowManager: Blender dynamic search failed: {e}")

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
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath {_ps_quote(app_name)}"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                logger.logger.info(f"WindowManager: Launched '{app_name}' via PowerShell Start-Process")
                return True

            error = (result.stderr or result.stdout or "").strip()
            logger.logger.warning(f"WindowManager: PowerShell launch failed for '{app_name}': {error[:200]}")
        except Exception as e:
            logger.logger.warning(f"WindowManager: PowerShell launch failed: {e}")

        # Strategy 3: Raw 'start' command as last resort
        try:
            result = subprocess.run(
                ["cmd", "/c", "start", "", app_name],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                logger.logger.info(f"WindowManager: Launched '{app_name}' via start command")
                return True

            error = (result.stderr or result.stdout or "").strip()
            logger.logger.warning(f"WindowManager: start command failed for '{app_name}': {error[:200]}")
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
                # Bring window to foreground. Windows can reject a plain
                # SetForegroundWindow call from a background process, so attach
                # input queues briefly and use the standard Alt-key unlock.
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                current_hwnd = user32.GetForegroundWindow()
                current_thread = user32.GetWindowThreadProcessId(current_hwnd, None) if current_hwnd else 0
                target_thread = user32.GetWindowThreadProcessId(hwnd, None)
                this_thread = kernel32.GetCurrentThreadId()
                try:
                    pyautogui.press("alt")
                    if current_thread:
                        user32.AttachThreadInput(this_thread, current_thread, True)
                    if target_thread:
                        user32.AttachThreadInput(this_thread, target_thread, True)
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.SetFocus(hwnd)
                finally:
                    if target_thread:
                        user32.AttachThreadInput(this_thread, target_thread, False)
                    if current_thread:
                        user32.AttachThreadInput(this_thread, current_thread, False)
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
