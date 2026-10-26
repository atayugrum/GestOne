"""Vision feedback window — shows hand tracking overlay."""

import math

try:
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsOpacityEffect,
        QLabel,
        QMainWindow,
        QPushButton,
        QWidget,
    )
except ImportError:
    from PySide6.QtCore import Qt, QTimer, Signal as pyqtSignal
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QGraphicsOpacityEffect,
        QLabel,
        QMainWindow,
        QPushButton,
        QWidget,
    )

import cv2
import numpy as np


ACCENT_BLUE = "#007AFF"
BG_DARK = "#09090B"
PANEL_DARK = "#111114"
TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#A1A1A6"


class RoundedVideoLabel(QLabel):
    """Video label with rounded corners."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(960, 540)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"background: {PANEL_DARK}; border-radius: 34px;")
        self._pixmap = None

    def set_video_pixmap(self, pixmap: QPixmap) -> None:
        """Update video display."""
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        """Paint with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 34, 34)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(PANEL_DARK))

        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(QFont("SF Pro Display", 22, QFont.Weight.Medium))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for camera"
            )


class VisionWindow(QMainWindow):
    """Window showing hand tracking feedback.

    Consumes frames from CameraSource instead of opening its own camera.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GestOne Vision")
        self.resize(1180, 760)
        self.setMinimumSize(920, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._last_gesture = None
        self._last_hud_ts = 0.0
        self._fps = 0.0

        # Root widget
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)
        root.setStyleSheet(
            f"""
            QWidget#root {{
                background: {BG_DARK};
                border-radius: 36px;
            }}
            QLabel {{
                font-family: "SF Pro Text", "Helvetica Neue", Arial;
            }}
            """
        )

        # Video display
        self.video = RoundedVideoLabel()
        self.video.setParent(root)

        # Window buttons (close, minimize, zoom)
        self.close_button = self._window_button(root, "#FF5F57")
        self.minimize_button = self._window_button(root, "#FFBD2E")
        self.zoom_button = self._window_button(root, "#28C840")
        self.close_button.clicked.connect(self.close)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.zoom_button.clicked.connect(self.toggle_zoom)

        # Title
        self.title = QLabel("GestOne Vision", root)
        self.title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        self.title.setFont(QFont("SF Pro Display", 22, QFont.Weight.DemiBold))

        # Status
        self.status = QLabel("Waiting for frames", root)
        self.status.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self.status.setFont(QFont("SF Pro Text", 13, QFont.Weight.Medium))

        # Badge
        self.badge = QLabel("● Tracking", root)
        self.badge.setStyleSheet(
            f"""
            color: {TEXT_PRIMARY};
            background: rgba(255, 255, 255, 24);
            border: 1px solid rgba(255, 255, 255, 34);
            border-radius: 14px;
            padding: 5px 12px;
            """
        )
        self.badge.setFont(QFont("SF Pro Text", 12, QFont.Weight.DemiBold))

        self._is_zoomed = False

    def _window_button(self, parent: QWidget, color: str) -> QPushButton:
        """Create a traffic-light window button."""
        btn = QPushButton(parent)
        btn.setFixedSize(14, 14)
        btn.setStyleSheet(
            f"background: {color}; border-radius: 7px; border: none;"
        )
        return btn

    def toggle_zoom(self) -> None:
        """Toggle fullscreen."""
        if self._is_zoomed:
            self.showNormal()
            self._is_zoomed = False
        else:
            self.showMaximized()
            self._is_zoomed = True

    def resizeEvent(self, event) -> None:
        """Reposition UI elements on resize."""
        margin = 28
        header_h = 52
        self.close_button.setGeometry(margin, 28, 14, 14)
        self.minimize_button.setGeometry(margin + 22, 28, 14, 14)
        self.zoom_button.setGeometry(margin + 44, 28, 14, 14)
        self.title.setGeometry(margin + 78, 18, 360, 30)
        self.status.setGeometry(margin + 78, 47, 520, 22)
        self.badge.adjustSize()
        self.badge.move(self.width() - self.badge.width() - margin, 30)
        self.video.setGeometry(
            margin,
            header_h + 28,
            self.width() - margin * 2,
            self.height() - header_h - 56,
        )

    def receive_frame(
        self, rgb_frame: np.ndarray, landmarks, gesture: str = None, fps: float = 0.0
    ) -> None:
        """Receive processed frame from detector.

        Args:
            rgb_frame: BGR frame from camera
            landmarks: Detected hand landmarks
            gesture: Detected gesture label (if any)
            fps: Current FPS
        """
        self._fps = fps
        self._last_gesture = gesture

        # Draw landmarks if present
        if landmarks is not None:
            self._draw_landmarks(rgb_frame, landmarks)

        # Update status
        if gesture:
            self.status.setText(f"Gesture: {gesture} | {fps:.1f} FPS")
        else:
            self.status.setText(f"Tracking | {fps:.1f} FPS")

        # Convert to QPixmap
        h, w, c = rgb_frame.shape
        bytes_per_line = 3 * w
        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)

        self.video.set_video_pixmap(pixmap)

    def _draw_landmarks(self, frame: np.ndarray, landmarks) -> None:
        """Draw hand landmarks on frame."""
        if not landmarks:
            return

        h, w, _ = frame.shape

        # Draw connections (simplified)
        # MediaPipe Hand: 21 points, common connections
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
            (0, 5), (5, 6), (6, 7), (7, 8),  # index
            (0, 9), (9, 10), (10, 11), (11, 12),  # middle
            (0, 13), (13, 14), (14, 15), (15, 16),  # ring
            (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
        ]

        for start, end in connections:
            if start < len(landmarks) and end < len(landmarks):
                p1 = landmarks[start]
                p2 = landmarks[end]
                pt1 = (int(p1[0] * w), int(p1[1] * h))
                pt2 = (int(p2[0] * w), int(p2[1] * h))
                cv2.line(frame, pt1, pt2, (0, 200, 100), 2)

        # Draw points
        for lm in landmarks:
            pt = (int(lm[0] * w), int(lm[1] * h))
            cv2.circle(frame, pt, 4, (0, 255, 0), -1)

        # Highlight key points (index, thumb)
        if len(landmarks) >= 9:
            thumb = landmarks[4]
            index = landmarks[8]
            thumb_pt = (int(thumb[0] * w), int(thumb[1] * h))
            index_pt = (int(index[0] * w), int(index[1] * h))
            cv2.circle(frame, thumb_pt, 6, (0, 100, 255), -1)
            cv2.circle(frame, index_pt, 6, (0, 100, 255), -1)
