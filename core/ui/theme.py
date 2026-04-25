from PyQt6.QtGui import QColor, QFont

class Theme:
    # Terminal Dark + Glassmorphism
    BG_COLOR = QColor(15, 15, 15, 180) # Semi-transparent dark
    BG_SOLID = QColor(15, 15, 15, 255)
    ACCENT_COLOR = QColor(0, 180, 255, 255) # Cyan
    ACCENT_LOW = QColor(0, 180, 255, 100)
    TEXT_COLOR = QColor(240, 240, 240, 255)
    GRAY_COLOR = QColor(100, 100, 100, 255)
    
    # Status Colors
    IDLE = QColor(100, 100, 100, 150)
    RECORDING = QColor(255, 50, 50, 255)
    THINKING = QColor(0, 180, 255, 255)
    ACTING = QColor(50, 255, 50, 255)

    @staticmethod
    def get_confidence_color(val):
        if val < 0.5: return Theme.GRAY_COLOR
        if val < 0.8: return QColor(255, 200, 0)
        return Theme.ACCENT_COLOR

    # Typography
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    
    # Glassmorphism Style
    GLASS_STYLE = f"""
        background-color: rgba(15, 15, 15, 200);
        border: 1px solid rgba(255, 255, 255, 30);
        border-radius: 12px;
    """

theme = Theme()
