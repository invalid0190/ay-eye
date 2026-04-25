from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from core.ui.theme import theme

class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.icon = QLabel("●")
        self.label = QLabel("ay-eye: idle")
        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.label)
        self.setStyleSheet(f"color: {theme.TEXT_COLOR.name()}; font-family: {theme.FONT_FAMILY};")

class ActionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setVisible(False)
        
        self.suggestion_label = QLabel("Suggestion ready")
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setFixedHeight(4)
        self.confidence_bar.setTextVisible(False)
        
        self.btn_confirm = QPushButton("Confirm [Alt+Enter]")
        self.btn_cancel = QPushButton("Cancel")
        
        btn_style = f"background-color: {theme.ACCENT_COLOR.name()}; color: black; border-radius: 3px; font-weight: bold;"
        self.btn_confirm.setStyleSheet(btn_style)
        self.btn_cancel.setStyleSheet("color: gray; border: none;")
        
        self.layout.addWidget(self.suggestion_label)
        self.layout.addWidget(self.confidence_bar)
        
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addWidget(self.btn_confirm)
        self.btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(self.btn_layout)

    def show_suggestion(self, text, confidence):
        self.suggestion_label.setText(text)
        self.confidence_bar.setValue(int(confidence * 100))
        color = theme.get_confidence_color(confidence)
        self.confidence_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color.name()}; }}")
        self.setVisible(True)

