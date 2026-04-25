from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from core.ui.theme import theme

class PillStatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_pos = None
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 4, 12, 4)
        self.layout.setSpacing(8)
        
        self.dot = QLabel("●")
        self.label = QLabel("IDLE")
        self.app_label = QLabel("| WINDOW")
        
        for lbl in [self.dot, self.label, self.app_label]:
            lbl.setStyleSheet(f"color: {theme.TEXT_COLOR.name()}; font-family: {theme.FONT_FAMILY}; font-size: 9pt; font-weight: bold; background:transparent; border:none;")
        
        self.app_label.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_FAMILY}; font-size: 8pt; background:transparent; border:none;")
        
        self.layout.addWidget(self.dot)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.app_label)
        
        self.setStyleSheet(theme.GLASS_STYLE)
        self.setFixedSize(220, 32)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def update_status(self, status, app_name=""):
        self.label.setText(status.upper())
        self.app_label.setText(f"| {app_name[:15].upper() if app_name else 'IDLE'}")
        
        color = theme.IDLE
        if status == "thinking": color = theme.THINKING
        elif status == "recording": color = theme.RECORDING
        elif status == "acting": color = theme.ACTING
        
        self.dot.setStyleSheet(f"color: {color.name()}; background:transparent; border:none;")

class ActionPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_pos = None
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.setVisible(False)
        
        self.title = QLabel("AI SUGGESTION")
        self.title.setStyleSheet(f"color: {theme.ACCENT_COLOR.name()}; font-size: 8pt; font-weight: bold; letter-spacing: 1px;")
        
        self.suggestion_label = QLabel("Suggestion ready")
        self.suggestion_label.setWordWrap(True)
        self.suggestion_label.setStyleSheet(f"color: {theme.TEXT_COLOR.name()}; font-size: 11pt; margin-top: 5px;")
        
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setFixedHeight(2)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("QProgressBar { background: rgba(255,255,255,10); border:none; }")
        
        self.btn_confirm = QPushButton("CONFIRM [ALT+ENTER]")
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.clicked.connect(lambda: bus.publish("CONFIRM_HOTKEY"))
        
        btn_style = f"""
            QPushButton {{
                background-color: {theme.ACCENT_COLOR.name()}; 
                color: #0f0f0f; 
                border-radius: 6px; 
                padding: 8px; 
                font-weight: bold;
                font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: white; }}
        """
        self.btn_confirm.setStyleSheet(btn_style)
        
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.suggestion_label)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.confidence_bar)
        self.layout.addSpacing(15)
        self.layout.addWidget(self.btn_confirm)
        
        self.setStyleSheet(theme.GLASS_STYLE)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def show_suggestion(self, text, confidence):
        self.suggestion_label.setText(text)
        self.confidence_bar.setValue(int(confidence * 100))
        color = theme.get_confidence_color(confidence)
        self.confidence_bar.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,10); border:none; }}
            QProgressBar::chunk {{ background-color: {color.name()}; }}
        """)
        self.setVisible(True)

