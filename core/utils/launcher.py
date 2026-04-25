import os
import subprocess
from core.utils.logger import logger

class AppLauncher:
    SAFE_APPS = ["notepad", "calc", "cmd", "explorer", "chrome", "msedge", "discord", "github"]

    @staticmethod
    def launch(app_name):
        app_name = app_name.lower().strip()
        if any(safe in app_name for safe in AppLauncher.SAFE_APPS):
            try:
                # Basic launch logic
                os.startfile(app_name)
                logger.log_event("APP_LAUNCHED", {"app": app_name})
                return True
            except:
                try:
                    subprocess.Popen([app_name])
                    return True
                except Exception as e:
                    logger.logger.error(f"Launcher error: {e}")
        else:
            logger.logger.warning(f"App '{app_name}' not in whitelist")
        return False

launcher = AppLauncher()
