from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, 
    QPushButton, QFrame, QScrollArea, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath
from core.ui.theme import theme
from core.engine.event_bus import bus
from datetime import datetime


# ═══════════════════════════════════════════
#  DRAGGABLE BASE MIXIN
# ═══════════════════════════════════════════

class DraggableMixin:
    """Mixin that enables drag-to-move on any QWidget."""
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
#  STATUS BAR (Top Pill)
# ═══════════════════════════════════════════

class PillStatusBar(QWidget, DraggableMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_draggable()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)
        
        # Pulsing dot
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {theme.IDLE.name()}; font-size: 12pt; background:transparent; border:none;")
        
        # Status label
        self.label = QLabel("IDLE")
        self.label.setStyleSheet(f"""
            color: {theme.TEXT_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 9pt; 
            font-weight: bold; 
            letter-spacing: 2px;
            background:transparent; border:none;
        """)
        
        # Separator
        sep = QLabel("│")
        sep.setStyleSheet(f"color: rgba(255,255,255,30); font-size: 10pt; background:transparent; border:none;")
        
        # App name
        self.app_label = QLabel("SYSTEM")
        self.app_label.setStyleSheet(f"""
            color: {theme.TEXT_DIM.name()}; 
            font-family: {theme.FONT_FAMILY}; 
            font-size: 8pt;
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
        
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addWidget(sep)
        layout.addWidget(self.app_label)
        layout.addStretch()
        layout.addWidget(self.uptime_label)
        
        self.setStyleSheet(theme.GLASS_STYLE)
        self.setFixedSize(320, 36)
        
        # Uptime counter
        self._start_time = datetime.now()
        self._uptime_timer = QTimer()
        self._uptime_timer.timeout.connect(self._update_uptime)
        self._uptime_timer.start(1000)
        
        # Pulse animation
        self._pulse_visible = True
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse)
    
    def _update_uptime(self):
        elapsed = datetime.now() - self._start_time
        mins = int(elapsed.total_seconds() // 60)
        secs = int(elapsed.total_seconds() % 60)
        self.uptime_label.setText(f"{mins:02d}:{secs:02d}")
    
    def _pulse(self):
        self._pulse_visible = not self._pulse_visible
        if self._pulse_visible:
            self.dot.setStyleSheet(f"color: {self._current_color}; font-size: 12pt; background:transparent; border:none;")
        else:
            self.dot.setStyleSheet(f"color: rgba(0,0,0,0); font-size: 12pt; background:transparent; border:none;")
    
    def update_status(self, status, app_name=""):
        self.label.setText(status.upper())
        self.app_label.setText(app_name[:20].upper() if app_name else "SYSTEM")
        
        colors = {
            "idle": theme.IDLE,
            "thinking": theme.THINKING,
            "recording": theme.RECORDING,
            "acting": theme.ACTING
        }
        color = colors.get(status, theme.IDLE)
        self._current_color = color.name()
        self.dot.setStyleSheet(f"color: {color.name()}; font-size: 12pt; background:transparent; border:none;")
        
        # Pulse for active states
        if status in ("recording", "thinking"):
            self._pulse_timer.start(500)
        else:
            self._pulse_timer.stop()
            self._pulse_visible = True
            self.dot.setStyleSheet(f"color: {color.name()}; font-size: 12pt; background:transparent; border:none;")


# ═══════════════════════════════════════════
#  ACTIVITY LOG ENTRY
# ═══════════════════════════════════════════

class LogEntry(QFrame):
    def __init__(self, icon, text, color, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none; padding: 2px 0;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)
        
        ts = datetime.now().strftime("%H:%M:%S")
        
        time_lbl = QLabel(ts)
        time_lbl.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 7pt; background:transparent; border:none;")
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 8pt; background:transparent; border:none;")
        
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(f"color: {theme.TEXT_DIM.name()}; font-family: {theme.FONT_FAMILY}; font-size: 8pt; background:transparent; border:none;")
        
        layout.addWidget(time_lbl)
        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl, 1)


# ═══════════════════════════════════════════
#  MAIN COMMAND PANEL (Expandable Dashboard)
# ═══════════════════════════════════════════

class CommandPanel(QFrame, DraggableMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_draggable()
        self.setVisible(False)
        
        self.setFixedWidth(360)
        self.setMinimumHeight(280)
        self.setMaximumHeight(500)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)
        
        # ── Header Row ──
        header = QHBoxLayout()
        
        title = QLabel("◆ AY-EYE")
        title.setStyleSheet(f"""
            color: {theme.ACCENT_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 10pt; 
            font-weight: bold; 
            letter-spacing: 3px;
            background:transparent; border:none;
        """)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{ 
                color: {theme.GRAY_COLOR.name()}; 
                background: transparent; 
                border: none; 
                font-size: 10pt;
            }}
            QPushButton:hover {{ color: {theme.ERROR.name()}; }}
        """)
        self.close_btn.clicked.connect(lambda: self.setVisible(False))
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.close_btn)
        main_layout.addLayout(header)
        
        # ── Suggestion Section ──
        self.suggestion_frame = QFrame()
        self.suggestion_frame.setStyleSheet(theme.GLASS_STYLE_INNER)
        suggestion_layout = QVBoxLayout(self.suggestion_frame)
        suggestion_layout.setContentsMargins(12, 10, 12, 10)
        suggestion_layout.setSpacing(6)
        
        self.intent_badge = QLabel("● GUIDE")
        self.intent_badge.setStyleSheet(f"""
            color: {theme.ACCENT_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 7pt; 
            font-weight: bold;
            letter-spacing: 1px;
            background:transparent; border:none;
        """)
        
        self.suggestion_label = QLabel("Waiting for your command...")
        self.suggestion_label.setWordWrap(True)
        self.suggestion_label.setStyleSheet(f"""
            color: {theme.TEXT_COLOR.name()}; 
            font-family: {theme.FONT_FAMILY}; 
            font-size: 10pt; 
            line-height: 1.4;
            background:transparent; border:none;
        """)
        
        # Confidence row
        conf_row = QHBoxLayout()
        conf_label = QLabel("CONFIDENCE")
        conf_label.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 7pt; background:transparent; border:none;")
        
        self.confidence_value = QLabel("--")
        self.confidence_value.setStyleSheet(f"color: {theme.ACCENT_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 7pt; font-weight:bold; background:transparent; border:none;")
        
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setFixedHeight(3)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,8); border:none; border-radius: 1px; }
            QProgressBar::chunk { background-color: rgba(0,180,255,200); border-radius: 1px; }
        """)
        
        conf_row.addWidget(conf_label)
        conf_row.addWidget(self.confidence_bar, 1)
        conf_row.addWidget(self.confidence_value)
        
        suggestion_layout.addWidget(self.intent_badge)
        suggestion_layout.addWidget(self.suggestion_label)
        suggestion_layout.addLayout(conf_row)
        
        main_layout.addWidget(self.suggestion_frame)
        
        # ── Activity Log ──
        log_header = QLabel("ACTIVITY")
        log_header.setStyleSheet(f"""
            color: {theme.GRAY_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 7pt; 
            letter-spacing: 2px;
            background:transparent; border:none;
        """)
        main_layout.addWidget(log_header)
        
        # Scroll area for log entries
        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,30); border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.log_scroll.setFixedHeight(100)
        
        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(0)
        self.log_layout.addStretch()
        
        self.log_scroll.setWidget(self.log_container)
        main_layout.addWidget(self.log_scroll)
        
        # ── Action Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        
        self.btn_confirm = QPushButton("✓ CONFIRM")
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.clicked.connect(lambda: bus.publish("CONFIRM_HOTKEY"))
        self.btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.ACCENT_COLOR.name()};
                color: #0a0a0a;
                border-radius: 8px;
                padding: 8px 16px;
                font-family: {theme.FONT_MONO};
                font-weight: bold;
                font-size: 8pt;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background-color: white; }}
        """)
        
        self.btn_dismiss = QPushButton("✕ DISMISS")
        self.btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dismiss.clicked.connect(lambda: self.setVisible(False))
        self.btn_dismiss.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,255,255,10);
                color: {theme.TEXT_DIM.name()};
                border: 1px solid rgba(255,255,255,15);
                border-radius: 8px;
                padding: 8px 16px;
                font-family: {theme.FONT_MONO};
                font-weight: bold;
                font-size: 8pt;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ 
                background-color: rgba(255,60,60,30); 
                color: {theme.ERROR.name()};
                border-color: rgba(255,60,60,40);
            }}
        """)
        
        btn_row.addWidget(self.btn_confirm, 1)
        btn_row.addWidget(self.btn_dismiss, 1)
        main_layout.addLayout(btn_row)
        
        # ── Hotkey hint ──
        hint = QLabel("Alt+Z speak  •  Alt+Enter confirm  •  Ctrl+Shift+X stop")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            color: {theme.GRAY_COLOR.name()}; 
            font-family: {theme.FONT_MONO}; 
            font-size: 6pt;
            background:transparent; border:none;
            padding-top: 4px;
        """)
        main_layout.addWidget(hint)
        
        self.setStyleSheet(theme.GLASS_STYLE)
        
        self._log_count = 0
    
    def add_log(self, icon, text, color=None):
        """Add an entry to the activity log."""
        color = color or theme.TEXT_DIM.name()
        entry = LogEntry(icon, text, color, self.log_container)
        # Insert before the stretch
        self.log_layout.insertWidget(self.log_layout.count() - 1, entry)
        self._log_count += 1
        
        # Keep max 20 entries
        if self._log_count > 20:
            item = self.log_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                self._log_count -= 1
        
        # Auto-scroll to bottom
        QTimer.singleShot(50, lambda: self.log_scroll.verticalScrollBar().setValue(
            self.log_scroll.verticalScrollBar().maximum()
        ))
    
    def show_suggestion(self, text, confidence, intent="guide"):
        self.suggestion_label.setText(text)
        self.confidence_bar.setValue(int(confidence * 100))
        self.confidence_value.setText(f"{int(confidence * 100)}%")
        
        color = theme.get_confidence_color(confidence)
        self.confidence_bar.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,8); border:none; border-radius: 1px; }}
            QProgressBar::chunk {{ background-color: {color.name()}; border-radius: 1px; }}
        """)
        self.confidence_value.setStyleSheet(f"color: {color.name()}; font-family: {theme.FONT_MONO}; font-size: 7pt; font-weight:bold; background:transparent; border:none;")
        
        intent_colors = {
            "guide": theme.ACCENT_COLOR,
            "act": theme.ACTING,
            "ask": theme.WARNING,
            "ignore": theme.GRAY_COLOR
        }
        ic = intent_colors.get(intent, theme.ACCENT_COLOR)
        self.intent_badge.setText(f"● {intent.upper()}")
        self.intent_badge.setStyleSheet(f"color: {ic.name()}; font-family: {theme.FONT_MONO}; font-size: 7pt; font-weight:bold; letter-spacing: 1px; background:transparent; border:none;")
        
        self.setVisible(True)


# ═══════════════════════════════════════════
#  CHAT BUBBLE (Conversation History)
# ═══════════════════════════════════════════

class ChatBubble(QFrame):
    """A single message bubble for the conversation view."""
    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(260)
        
        if is_user:
            # User message - right-aligned, subtle border
            label.setStyleSheet(f"""
                color: {theme.TEXT_COLOR.name()};
                background-color: rgba(0, 180, 255, 20);
                border: 1px solid rgba(0, 180, 255, 40);
                border-radius: 10px;
                padding: 6px 10px;
                font-family: {theme.FONT_FAMILY};
                font-size: 8pt;
            """)
            layout.addStretch()
            layout.addWidget(label)
        else:
            # AI response - left-aligned
            label.setStyleSheet(f"""
                color: {theme.TEXT_DIM.name()};
                background-color: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 10px;
                padding: 6px 10px;
                font-family: {theme.FONT_FAMILY};
                font-size: 8pt;
            """)
            layout.addWidget(label)
            layout.addStretch()


# ═══════════════════════════════════════════
#  HEALTH STATUS BAR
# ═══════════════════════════════════════════

class HealthBar(QFrame):
    """Compact service health indicators."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        self.indicators = {}
        for name in ["LLM", "TTS", "STT"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-size: 6pt; background:transparent; border:none;")
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {theme.GRAY_COLOR.name()}; font-family: {theme.FONT_MONO}; font-size: 6pt; background:transparent; border:none;")
            
            pair = QHBoxLayout()
            pair.setSpacing(3)
            pair.addWidget(dot)
            pair.addWidget(lbl)
            layout.addLayout(pair)
            
            self.indicators[name] = dot
        
        layout.addStretch()
    
    def set_status(self, name, ok):
        """Update a service indicator: True=green, False=red."""
        if name in self.indicators:
            color = theme.SUCCESS.name() if ok else theme.ERROR.name()
            self.indicators[name].setStyleSheet(f"color: {color}; font-size: 6pt; background:transparent; border:none;")


# ═══════════════════════════════════════════
#  AUDIO LEVEL INDICATOR
# ═══════════════════════════════════════════

class AudioLevelBar(QWidget):
    """Horizontal mini bar that shows microphone input level."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self._level = 0.0
    
    def set_level(self, level):
        """Set audio level from 0.0 to 1.0."""
        self._level = max(0.0, min(1.0, level))
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.setBrush(QColor(255, 255, 255, 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 2, 2)
        
        # Level fill
        if self._level > 0:
            fill_width = int(self.width() * self._level)
            if self._level < 0.5:
                color = theme.SUCCESS
            elif self._level < 0.8:
                color = theme.WARNING
            else:
                color = theme.ERROR
            painter.setBrush(color)
            painter.drawRoundedRect(0, 0, fill_width, self.height(), 2, 2)


# ═══════════════════════════════════════════
#  BACKWARD COMPATIBILITY
# ═══════════════════════════════════════════

ActionPanel = CommandPanel
