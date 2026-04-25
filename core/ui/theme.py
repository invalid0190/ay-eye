from PyQt6.QtGui import QColor, QFont

class Theme:
    # Terminal Dark + Glassmorphism
    BG_COLOR = QColor(15, 15, 15, 200) # Near black, semi-transparent
    ACCENT_COLOR = QColor(0, 180, 255, 255) # Soft Blue/Cyan
    TEXT_COLOR = QColor(240, 240, 240, 255) # Soft White
    GRAY_COLOR = QColor(100, 100, 100, 255)
    
    # Logic for confidence colors
    @staticmethod
    def get_confidence_color(val):
        if val < 0.5: return Theme.GRAY_COLOR
        if val < 0.8: return QColor(200, 180, 0) # Soft Yellow
        return Theme.ACCENT_COLOR

    # Typography
    FONT_FAMILY = "Segoe UI Semibold" # Minimal technical look
    FONT_SIZE_SMALL = 10
    FONT_SIZE_NORMAL = 12

theme = Theme()
