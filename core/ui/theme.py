from PyQt6.QtGui import QColor, QFont, QLinearGradient

class Theme:
    # Terminal Dark + Glassmorphism
    BG_COLOR = QColor(15, 15, 15, 180)
    BG_SOLID = QColor(15, 15, 15, 255)
    ACCENT_COLOR = QColor(0, 180, 255, 255)      # Cyan
    ACCENT_LOW = QColor(0, 180, 255, 100)
    ACCENT_GLOW = QColor(0, 180, 255, 40)
    TEXT_COLOR = QColor(240, 240, 240, 255)
    TEXT_DIM = QColor(160, 160, 160, 255)
    GRAY_COLOR = QColor(100, 100, 100, 255)
    SURFACE = QColor(25, 25, 30, 240)
    SURFACE_LIGHT = QColor(35, 35, 40, 200)
    BORDER = QColor(255, 255, 255, 25)
    
    # Status Colors
    IDLE = QColor(100, 100, 100, 150)
    RECORDING = QColor(255, 60, 60, 255)
    THINKING = QColor(0, 180, 255, 255)
    ACTING = QColor(50, 255, 120, 255)
    SUCCESS = QColor(50, 255, 120, 255)
    WARNING = QColor(255, 200, 0, 255)
    ERROR = QColor(255, 60, 60, 255)

    @staticmethod
    def get_confidence_color(val):
        if val < 0.4: return Theme.ERROR
        if val < 0.7: return Theme.WARNING
        return Theme.SUCCESS

    # Typography
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    
    # Glassmorphism Style
    GLASS_STYLE = """
        background-color: rgba(15, 15, 15, 210);
        border: 1px solid rgba(255, 255, 255, 20);
        border-radius: 12px;
    """
    
    GLASS_STYLE_INNER = """
        background-color: rgba(30, 30, 35, 150);
        border: 1px solid rgba(255, 255, 255, 10);
        border-radius: 8px;
    """

theme = Theme()
