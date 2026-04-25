from PyQt6.QtGui import QColor, QFont, QLinearGradient

class Theme:
    # ── Base Palette ──
    BG_COLOR = QColor(12, 12, 14, 210)
    BG_SOLID = QColor(10, 10, 12, 255)
    ACCENT_COLOR = QColor(0, 186, 255, 255)       # Electric Cyan
    ACCENT_LOW = QColor(0, 186, 255, 80)
    ACCENT_GLOW = QColor(0, 186, 255, 30)
    ACCENT_SECONDARY = QColor(120, 90, 255, 255)   # Purple accent
    TEXT_COLOR = QColor(235, 235, 240, 255)
    TEXT_DIM = QColor(140, 145, 155, 255)
    GRAY_COLOR = QColor(75, 78, 85, 255)
    SURFACE = QColor(18, 18, 22, 245)
    SURFACE_LIGHT = QColor(28, 28, 34, 220)
    BORDER = QColor(255, 255, 255, 18)
    
    # ── Status Colors ──
    IDLE = QColor(75, 78, 85, 150)
    RECORDING = QColor(255, 55, 55, 255)
    THINKING = QColor(0, 186, 255, 255)
    ACTING = QColor(40, 230, 110, 255)
    SUCCESS = QColor(40, 230, 110, 255)
    WARNING = QColor(255, 195, 0, 255)
    ERROR = QColor(255, 55, 55, 255)

    @staticmethod
    def get_confidence_color(val):
        if val < 0.4: return Theme.ERROR
        if val < 0.7: return Theme.WARNING
        return Theme.SUCCESS

    # ── Typography ──
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    
    # ── Glassmorphism Styles ──
    GLASS_STYLE = """
        background-color: rgba(12, 12, 14, 225);
        border: 1px solid rgba(255, 255, 255, 12);
        border-radius: 14px;
    """
    
    GLASS_STYLE_INNER = """
        background-color: rgba(22, 22, 28, 180);
        border: 1px solid rgba(255, 255, 255, 8);
        border-radius: 10px;
    """

theme = Theme()
