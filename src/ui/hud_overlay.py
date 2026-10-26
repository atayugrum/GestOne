"""HUD overlay widget for gesture feedback."""

try:
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QWidget
except ImportError:
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QWidget


ACCENT_BLUE = "#007AFF"
TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "rgba(245, 245, 247, 150)"


class HudOverlay(QFrame):
    """Translucent HUD overlay for gesture/action feedback.

    Shows briefly when an action is detected, then fades out.
    """

    def __init__(self, parent: QWidget, duration_ms: int = 800):
        super().__init__(parent)
        self.setObjectName("hud")
        self.setFixedSize(260, 118)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.duration_ms = duration_ms

        self.setStyleSheet(
            """
            QFrame#hud {
                background: rgba(28, 28, 30, 190);
                border: 1px solid rgba(255, 255, 255, 46);
                border-radius: 28px;
            }
            QLabel {
                color: #F5F5F7;
                background: transparent;
            }
            """
        )

        # Icon
        self.icon = QLabel("•", self)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(f"color: {ACCENT_BLUE};")
        self.icon.setFont(QFont("SF Pro Display", 42, QFont.Weight.Bold))
        self.icon.setGeometry(0, 12, 260, 44)

        # Title (main message)
        self.title = QLabel("", self)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("SF Pro Text", 18, QFont.Weight.DemiBold))
        self.title.setGeometry(18, 62, 224, 28)

        # Subtitle
        self.subtitle = QLabel("Gesture detected", self)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setFont(QFont("SF Pro Text", 12, QFont.Weight.Medium))
        self.subtitle.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.subtitle.setGeometry(18, 88, 224, 20)

        # Fade animation
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        self.hide()

        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

    def show_message(self, text: str) -> None:
        """Show message with fade-in, then auto-fade-out after duration_ms."""
        self.title.setText(text)
        self.raise_()
        self.show()

        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity())
        self.anim.setEndValue(1.0)
        self.anim.start()

        self.hide_timer.start(self.duration_ms)

    def fade_out(self) -> None:
        """Fade out and hide."""
        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.hide)
        self.anim.start()
