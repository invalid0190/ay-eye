import ctypes

from core.utils.logger import logger


def enable_dpi_awareness():
    """Keep screen capture pixels and PyAutoGUI coordinates in the same space."""
    try:
        # Windows 10+: per-monitor DPI awareness v2.
        awareness_context_per_monitor_v2 = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(awareness_context_per_monitor_v2):
            logger.logger.info("DPI awareness: per-monitor v2 enabled")
            return
    except Exception:
        pass

    try:
        # Windows 8.1 fallback: per-monitor DPI aware.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        logger.logger.info("DPI awareness: per-monitor enabled")
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        logger.logger.info("DPI awareness: system DPI aware enabled")
    except Exception as e:
        logger.logger.warning(f"DPI awareness: could not enable DPI awareness: {e}")
