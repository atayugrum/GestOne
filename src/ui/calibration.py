"""Calibration overlay for hand tracking zone."""

try:
    from PyQt6.QtCore import Qt, QTimer, QRect
    from PyQt6.QtGui import QFont, QColor, QPainter, QPen
    from PyQt6.QtWidgets import QWidget, QLabel
except ImportError:
    from PySide6.QtCore import Qt, QTimer, QRect
    from PySide6.QtGui import QFont, QColor, QPainter, QPen
    from PySide6.QtWidgets import QWidget, QLabel

import cv2
import numpy as np


class CalibrationOverlay(QWidget):
    """Full-screen calibration overlay.

    Shows a green skeleton when hand is in the ROI zone, red when outside.
    Guides user to keep hand in calibration zone for 3+ seconds.
    """

    def __init__(self, roi_box, calibration_hold_seconds: float = 3.0):
        super().__init__()
        self.roi_box = roi_box  # (x_min, x_max, y_min, y_max) in [0, 1] normalized coords
        self.calibration_hold_seconds = calibration_hold_seconds

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 200);")

        # Full screen
        self.showFullScreen()

        # Instruction label
        self.label = QLabel(self)
        self.label.setStyleSheet("color: #F5F5F7; font-size: 24px; background: transparent;")
        self.label.setFont(QFont("SF Pro Display", 24, QFont.Weight.Medium))
        self.label.setText("📍 Keep hand in green zone for 3 seconds")
        self.label.adjustSize()
        self.label.move(
            (self.width() - self.label.width()) // 2,
            self.height() // 2 + 200,
        )

        # Timer for calibration hold detection
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(False)
        self.hold_timer.timeout.connect(self._check_hold)
        self.hold_timer.start(100)

        self.frame_buffer = None
        self.hand_landmarks = None
        self.in_zone_since = None
        self.green_frames = 0

    def receive_frame(self, frame: np.ndarray, landmarks=None):
        """Receive frame and landmarks from detector."""
        self.frame_buffer = frame.copy()
        self.hand_landmarks = landmarks

    def paintEvent(self, event):
        """Draw calibration overlay."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))

        if self.frame_buffer is None:
            return

        # Draw frame preview (optional, can skip for performance)
        # For now, just draw the ROI zones

        w, h = self.width(), self.height()
        x_min, x_max, y_min, y_max = self.roi_box
        rx1, rx2 = int(x_min * w), int(x_max * w)
        ry1, ry2 = int(y_min * h), int(y_max * h)

        # Draw safe zone (green if hand in zone, red otherwise)
        in_zone = False
        if self.hand_landmarks is not None:
            # Check if hand center is in zone
            lm_array = np.array(self.hand_landmarks)
            hand_center_x = np.mean(lm_array[:, 0])
            hand_center_y = np.mean(lm_array[:, 1])
            in_zone = (x_min <= hand_center_x <= x_max) and (y_min <= hand_center_y <= y_max)

        zone_color = QColor(0, 200, 100, 100) if in_zone else QColor(200, 50, 50, 100)
        painter.fillRect(rx1, ry1, rx2 - rx1, ry2 - ry1, zone_color)

        # Draw border
        pen = QPen(QColor(0, 255, 100, 200) if in_zone else QColor(255, 100, 100, 200), 3)
        painter.setPen(pen)
        painter.drawRect(rx1, ry1, rx2 - rx1, ry2 - ry1)

        # Draw hand skeleton if present
        if self.hand_landmarks is not None:
            self._draw_skeleton(painter, self.hand_landmarks, in_zone)

        # Draw progress indicator
        if in_zone:
            progress = min(self.green_frames / 30, 1.0)  # 30 frames = 3 seconds at 10fps
            arc_w, arc_h = 100, 100
            arc_x = (w - arc_w) // 2
            arc_y = h // 2 - 100
            painter.setPen(QPen(QColor(0, 255, 100, 150), 4))
            painter.drawArc(arc_x, arc_y, arc_w, arc_h, 0, int(360 * 16 * progress))

    def _draw_skeleton(self, painter: QPainter, landmarks, in_zone: bool):
        """Draw hand skeleton."""
        w, h = self.width(), self.height()
        color = QColor(0, 200, 100, 200) if in_zone else QColor(200, 100, 100, 200)
        point_color = QColor(0, 255, 150, 255) if in_zone else QColor(255, 150, 100, 255)

        # Draw connections (MediaPipe Hand 21 points)
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),
            (0, 5), (5, 6), (6, 7), (7, 8),
            (0, 9), (9, 10), (10, 11), (11, 12),
            (0, 13), (13, 14), (14, 15), (15, 16),
            (0, 17), (17, 18), (18, 19), (19, 20),
        ]

        painter.setPen(QPen(color, 2))
        for start, end in connections:
            if start < len(landmarks) and end < len(landmarks):
                p1 = landmarks[start]
                p2 = landmarks[end]
                x1, y1 = int(p1[0] * w), int(p1[1] * h)
                x2, y2 = int(p2[0] * w), int(p2[1] * h)
                painter.drawLine(x1, y1, x2, y2)

        # Draw points
        painter.setPen(QPen(point_color, 0))
        for lm in landmarks:
            x, y = int(lm[0] * w), int(lm[1] * h)
            painter.drawEllipse(x - 4, y - 4, 8, 8)

    def _check_hold(self):
        """Check if hand has been in zone long enough."""
        # Simple heuristic: if frame received and landmarks exist
        if self.hand_landmarks is not None:
            lm_array = np.array(self.hand_landmarks)
            hand_center_x = np.mean(lm_array[:, 0])
            hand_center_y = np.mean(lm_array[:, 1])

            x_min, x_max, y_min, y_max = self.roi_box
            in_zone = (x_min <= hand_center_x <= x_max) and (y_min <= hand_center_y <= y_max)

            if in_zone:
                self.green_frames += 1
                if self.green_frames >= int(self.calibration_hold_seconds * 10):
                    self.close()
            else:
                self.green_frames = 0

        self.update()

    def closeEvent(self, event):
        """Stop timers on close."""
        self.hold_timer.stop()
        event.accept()
