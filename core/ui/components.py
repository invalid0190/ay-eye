from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, 
    QPushButton, QFrame, QScrollArea, QGraphicsOpacityEffect, QLineEdit
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath
from core.ui.theme import theme
from core.engine.event_bus import bus
from datetime import datetime


# ═══════════════════════════════════════════
#  DRAGGABLE BASE
# ═══════════════════════════════════════════

class DraggableMixin:
    def init_draggable(self):
        self._drag_pos = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


# ═══════════════════════════════════════════
#  STATUS BAR (Persistent Pill)
# ═══════════════════════════════════════════

class PillStatusBar(QWidget, DraggableMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Paint an actual surface (avoid true transparency for better vision/OCR)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.init_draggable()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 7, 16, 7)
        layout.setSpacing(10)
        
        # Animated dot
        self.dot = QLabel("●")
        self._dot_style_base = f"font-size: 10pt; background:transparent; border:none;"
        self.dot.setStyleSheet(f"color: {theme.IDLE.name()}; {self._dot_style_base}")
        
        # Status
        self.label = QLabel("IDLE")
        self.label.setStyleSheet(f"""
            color: {theme.TEXT_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 8pt; 
            font-weight: 600; 
            letter-spacing: 3px;
            background:transparent; border:none;
        """)
        
        # Separator
        sep = QLabel("│")
        sep.setStyleSheet(f"color: rgba(255,255,255,20); font-size: 9pt; background:transparent; border:none;")
        
        # App name
        self.app_label = QLabel("SYSTEM")
        self.app_label.setStyleSheet(f"""
            color: {theme.TEXT_DIM.name()}; 
            font-family: {theme.FONT_FAMILY}; 
            font-size: 7pt;
            letter-spacing: 1px;
            background:transparent; border:none;
        """)
        
        # Uptime
        self.uptime_label = QLabel("00:00")
        self.uptime_label.setStyleSheet(f"""
            color: {theme.ACCENT_COLOR.name()};
            font-family: {theme.FONT_MONO};
            font-size: 7pt;
            background:transparent; border:none;
        """)
        
        # Dry Run Badge
        self.dry_run_label = QLabel("DRY RUN")
        self.dry_run_label.setStyleSheet(f"""
            color: #FFB74D;
            background: rgba(255, 183, 77, 15);
            border: 1px solid rgba(255, 183, 77, 30);
            border-radius: 4px;
            font-family: {theme.FONT_MONO};
            font-size: 6pt;
            font-weight: bold;
            padding: 1px 4px;
        """)
        self.dry_run_label.setVisible(False)
        
        # Panel toggle (manual open/close)
        self.panel_btn = QPushButton("≡")
        self.panel_btn.setFixedSize(18, 18)
        self.panel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panel_btn.setStyleSheet(f"""
            QPushButton {{
                color: {theme.TEXT_DIM.name()};
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,12);
                border-radius: 6px;
                font-family: {theme.FONT_MONO};
                font-size: 9pt;
                padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(0,186,255,35);
                color: {theme.TEXT_COLOR.name()};
                border-color: rgba(0,186,255,80);
            }}
        """)
        self.panel_btn.clicked.connect(lambda: bus.publish("TOGGLE_COMMAND_PANEL"))

        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addWidget(self.dry_run_label)
        layout.addWidget(sep)
        layout.addWidget(self.app_label)
        layout.addStretch()
        layout.addWidget(self.uptime_label)
        layout.addWidget(self.panel_btn)
        
        self.setStyleSheet(theme.GLASS_STYLE)
        self.setFixedSize(322, 34)
        
        self._start_time = datetime.now()
        self._uptime_timer = QTimer()
        self._uptime_timer.timeout.connect(self._update_uptime)
        self._uptime_timer.start(1000)
        
        self._pulse_visible = True
        self._current_color = theme.IDLE.name()
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse)
    
    def _update_uptime(self):
        elapsed = datetime.now() - self._start_time
        mins = int(elapsed.total_seconds() // 60)
        secs = int(elapsed.total_seconds() % 60)
        self.uptime_label.setText(f"{mins:02d}:{secs:02d}")
    
    def _pulse(self):
        self._pulse_visible = not self._pulse_visible
        opacity = 255 if self._pulse_visible else 0
        self.dot.setStyleSheet(f"color: rgba({self._current_rgb},{opacity}); {self._dot_style_base}")
    
    def update_status(self, status, app_name=""):
        self.label.setText(status.upper())
        self.app_label.setText(app_name[:18].upper() if app_name else "SYSTEM")
        
        from core.config import sys_config
        self.dry_run_label.setVisible(sys_config.get("dry_run_enabled"))
        
        colors = {"idle": theme.IDLE, "thinking": theme.THINKING, "recording": theme.RECORDING, "acting": theme.ACTING}
        color = colors.get(status, theme.IDLE)
        self._current_color = color.name()
        self._current_rgb = f"{color.red()},{color.green()},{color.blue()}"
        self.dot.setStyleSheet(f"color: {color.name()}; {self._dot_style_base}")
        
        if status in ("recording", "thinking"):
            self._pulse_timer.start(500)
        else:
            self._pulse_timer.stop()
            self._pulse_visible = True
            self.dot.setStyleSheet(f"color: {color.name()}; {self._dot_style_base}")


# ═══════════════════════════════════════════
#  LOG ENTRY
# ═══════════════════════════════════════════

class LogEntry(QFrame):
    def __init__(self, icon, text, color, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none; padding: 1px 0;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)
        
        ts = datetime.now().strftime("%H:%M:%S")
        
        time_lbl = QLabel(ts)
        time_lbl.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 6.5pt; background:transparent; border:none;")
        time_lbl.setFixedWidth(48)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 8pt; background:transparent; border:none;")
        icon_lbl.setFixedWidth(16)
        
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(f"color: {theme.TEXT_DIM.name()}; font-family: {theme.FONT_FAMILY}; font-size: 7.5pt; background:transparent; border:none;")
        
        layout.addWidget(time_lbl)
        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl, 1)


# ═══════════════════════════════════════════
#  COMMAND PANEL
# ═══════════════════════════════════════════

class CommandPanel(QFrame, DraggableMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_draggable()
        self.setVisible(False)
        
        self.setFixedWidth(340)
        self.setMinimumHeight(260)
        self.setMaximumHeight(480)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(8)
        
        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(8)
        
        title_icon = QLabel("◆")
        title_icon.setStyleSheet(f"color: {theme.ACCENT_COLOR.name()}; font-size: 12pt; background:transparent; border:none;")
        
        title = QLabel("AY-EYE")
        title.setStyleSheet(f"""
            color: {theme.TEXT_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 9pt; 
            font-weight: bold; 
            letter-spacing: 4px;
            background:transparent; border:none;
        """)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{ color: {theme.GRAY_COLOR.name()}; background: transparent; border: none; font-size: 9pt; }}
            QPushButton:hover {{ color: {theme.ERROR.name()}; }}
        """)
        self.close_btn.clicked.connect(lambda: self.setVisible(False))
        
        header.addWidget(title_icon)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.close_btn)
        main_layout.addLayout(header)
        
        # ── Suggestion Card ──
        self.suggestion_frame = QFrame()
        self.suggestion_frame.setStyleSheet(theme.GLASS_STYLE_INNER)
        sug_layout = QVBoxLayout(self.suggestion_frame)
        sug_layout.setContentsMargins(12, 10, 12, 10)
        sug_layout.setSpacing(5)
        
        # Intent + confidence row
        intent_row = QHBoxLayout()
        self.intent_badge = QLabel("● GUIDE")
        self.intent_badge.setStyleSheet(f"""
            color: {theme.ACCENT_COLOR.name()}; font-family: {theme.FONT_MONO}; 
            font-size: 6.5pt; font-weight: bold; letter-spacing: 2px;
            background:transparent; border:none;
        """)
        
        self.confidence_value = QLabel("--")
        self.confidence_value.setStyleSheet(f"""
            color: {theme.ACCENT_COLOR.name()}; font-family: {theme.FONT_MONO}; 
            font-size: 7pt; font-weight: bold;
            background:transparent; border:none;
        """)
        intent_row.addWidget(self.intent_badge)
        intent_row.addStretch()
        intent_row.addWidget(self.confidence_value)
        sug_layout.addLayout(intent_row)
        
        # Message
        self.suggestion_label = QLabel("Waiting for command...")
        self.suggestion_label.setWordWrap(True)
        self.suggestion_label.setStyleSheet(f"""
            color: {theme.TEXT_COLOR.name()}; 
            font-family: {theme.FONT_FAMILY}; 
            font-size: 9.5pt; 
            line-height: 140%;
            background:transparent; border:none;
        """)
        sug_layout.addWidget(self.suggestion_label)
        
        # Confidence bar
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setFixedHeight(2)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,6); border:none; border-radius: 1px; }
            QProgressBar::chunk { background-color: rgba(0,186,255,200); border-radius: 1px; }
        """)
        sug_layout.addWidget(self.confidence_bar)
        
        main_layout.addWidget(self.suggestion_frame)
        
        # ── Activity Section ──
        act_header = QLabel("ACTIVITY")
        act_header.setStyleSheet(f"""
            color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; 
            font-size: 6.5pt; letter-spacing: 3px;
            background:transparent; border:none;
            margin-top: 2px;
        """)
        main_layout.addWidget(act_header)
        
        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 3px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,25); border-radius: 1px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self.log_scroll.setFixedHeight(110)
        
        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(1)
        self.log_layout.addStretch()
        
        self.log_scroll.setWidget(self.log_container)
        main_layout.addWidget(self.log_scroll)
        
        # ── Typed Input (manual command) ──
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a command… (Enter to send)")
        self.text_input.setClearButtonEnabled(True)
        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                color: {theme.TEXT_COLOR.name()};
                background-color: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,10);
                border-radius: 8px;
                padding: 6px 8px;
                font-family: {theme.FONT_FAMILY};
                font-size: 8.5pt;
            }}
            QLineEdit:focus {{
                border-color: rgba(0,186,255,120);
                background-color: rgba(0,186,255,10);
            }}
        """)
        
        import threading
        def _submit_text():
            text = (self.text_input.text() or "").strip()
            if not text:
                return
            self.text_input.clear()
            # IMPORTANT: don't block the Qt UI thread; Brain does heavy work.
            threading.Thread(
                target=lambda: bus.publish("VOICE_INPUT_RECEIVED", text),
                daemon=True,
            ).start()
        
        self.text_input.returnPressed.connect(_submit_text)
        
        input_row.addWidget(self.text_input, 1)
        main_layout.addLayout(input_row)
        
        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        
        self.btn_confirm = QPushButton("✓  CONFIRM")
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.clicked.connect(lambda: bus.publish("CONFIRM_HOTKEY"))
        self.btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {theme.ACCENT_COLOR.name()}, stop:1 rgba(0,220,255,255));
                color: #080808;
                border-radius: 8px;
                padding: 7px 0;
                font-family: {theme.FONT_MONO};
                font-weight: bold;
                font-size: 7.5pt;
                letter-spacing: 1px;
                border: none;
            }}
            QPushButton:hover {{ background: white; }}
        """)
        
        self.btn_dismiss = QPushButton("✕  DISMISS")
        self.btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dismiss.clicked.connect(lambda: self.setVisible(False))
        self.btn_dismiss.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,255,255,5);
                color: {theme.TEXT_DIM.name()};
                border: 1px solid rgba(255,255,255,10);
                border-radius: 8px;
                padding: 7px 0;
                font-family: {theme.FONT_MONO};
                font-weight: bold;
                font-size: 7.5pt;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ 
                background-color: rgba(255,55,55,20); 
                color: {theme.ERROR.name()};
                border-color: rgba(255,55,55,30);
            }}
        """)
        
        btn_row.addWidget(self.btn_confirm, 1)
        btn_row.addWidget(self.btn_dismiss, 1)
        main_layout.addLayout(btn_row)
        
        # ── Footer ──
        hint = QLabel("Alt+Z speak  ·  Alt+Enter confirm  ·  Ctrl+Shift+X stop")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            color: rgba(255,255,255,25); 
            font-family: {theme.FONT_MONO}; 
            font-size: 6pt;
            background:transparent; border:none;
            padding-top: 2px;
        """)
        main_layout.addWidget(hint)
        
        self.setStyleSheet(theme.GLASS_STYLE)
        self._log_count = 0
    
    def add_log(self, icon, text, color=None):
        color = color or theme.TEXT_DIM.name()
        entry = LogEntry(icon, text, color, self.log_container)
        self.log_layout.insertWidget(self.log_layout.count() - 1, entry)
        self._log_count += 1
        if self._log_count > 25:
            item = self.log_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                self._log_count -= 1
        QTimer.singleShot(50, lambda: self.log_scroll.verticalScrollBar().setValue(
            self.log_scroll.verticalScrollBar().maximum()
        ))
    
    def show_suggestion(self, text, confidence, intent="guide"):
        self.suggestion_label.setText(text)
        self.confidence_bar.setValue(int(confidence * 100))
        self.confidence_value.setText(f"{int(confidence * 100)}%")
        
        color = theme.get_confidence_color(confidence)
        self.confidence_bar.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,6); border:none; border-radius: 1px; }}
            QProgressBar::chunk {{ background-color: {color.name()}; border-radius: 1px; }}
        """)
        self.confidence_value.setStyleSheet(f"""
            color: {color.name()}; font-family: {theme.FONT_MONO}; 
            font-size: 7pt; font-weight:bold; background:transparent; border:none;
        """)
        
        intent_colors = {"guide": theme.ACCENT_COLOR, "act": theme.ACTING, "ask": theme.WARNING, "ignore": theme.GRAY_COLOR}
        ic = intent_colors.get(intent, theme.ACCENT_COLOR)
        self.intent_badge.setText(f"● {intent.upper()}")
        self.intent_badge.setStyleSheet(f"""
            color: {ic.name()}; font-family: {theme.FONT_MONO}; 
            font-size: 6.5pt; font-weight:bold; letter-spacing: 2px;
            background:transparent; border:none;
        """)
        self.setVisible(True)


# ═══════════════════════════════════════════
#  CHAT BUBBLE
# ═══════════════════════════════════════════

class ChatBubble(QFrame):
    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(240)
        
        if is_user:
            label.setStyleSheet(f"""
                color: {theme.TEXT_COLOR.name()};
                background-color: rgba(0, 186, 255, 15);
                border: 1px solid rgba(0, 186, 255, 30);
                border-radius: 10px;
                padding: 5px 9px;
                font-family: {theme.FONT_FAMILY};
                font-size: 7.5pt;
            """)
            layout.addStretch()
            layout.addWidget(label)
        else:
            label.setStyleSheet(f"""
                color: {theme.TEXT_DIM.name()};
                background-color: rgba(255, 255, 255, 4);
                border: 1px solid rgba(255, 255, 255, 8);
                border-radius: 10px;
                padding: 5px 9px;
                font-family: {theme.FONT_FAMILY};
                font-size: 7.5pt;
            """)
            layout.addWidget(label)
            layout.addStretch()


# ═══════════════════════════════════════════
#  HEALTH STATUS BAR
# ═══════════════════════════════════════════

class HealthBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(14)
        
        self.indicators = {}
        for name in ["LLM", "TTS", "STT"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-size: 5pt; background:transparent; border:none;")
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 6pt; letter-spacing: 1px; background:transparent; border:none;")
            
            pair = QHBoxLayout()
            pair.setSpacing(3)
            pair.addWidget(dot)
            pair.addWidget(lbl)
            layout.addLayout(pair)
            self.indicators[name] = dot
        
        layout.addStretch()
    
    def set_status(self, name, ok):
        if name in self.indicators:
            color = theme.SUCCESS.name() if ok else theme.ERROR.name()
            self.indicators[name].setStyleSheet(f"color: {color}; font-size: 5pt; background:transparent; border:none;")


# ═══════════════════════════════════════════
#  AUDIO LEVEL BAR
# ═══════════════════════════════════════════

class AudioLevelBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self._level = 0.0
    
    def set_level(self, level):
        self._level = max(0.0, min(1.0, level))
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 6))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 1, 1)
        if self._level > 0:
            fill_w = int(self.width() * self._level)
            color = theme.SUCCESS if self._level < 0.5 else (theme.WARNING if self._level < 0.8 else theme.ERROR)
            painter.setBrush(color)
            painter.drawRoundedRect(0, 0, fill_w, self.height(), 1, 1)


# ═══════════════════════════════════════════
#  BACKWARD COMPAT
# ═══════════════════════════════════════════

ActionPanel = CommandPanel
