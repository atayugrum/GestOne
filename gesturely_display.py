"""Gesturely Display — standalone visual feedback app for GestOne.

Run:
    python3 gesturely_display.py

Requires:
    pip install opencv-python mediapipe PyQt6
"""

from __future__ import annotations

import math
import platform
import sys
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

try:
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap
    from PyQt6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QLabel, QMainWindow, QPushButton, QWidget
except ImportError:  # pragma: no cover - runtime fallback
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, Qt, QThread, QTimer, Signal as pyqtSignal
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap
    from PySide6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QLabel, QMainWindow, QPushButton, QWidget


ACCENT_BLUE = "#007AFF"
BG_DARK = "#09090B"
PANEL_DARK = "#111114"
TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#A1A1A6"


def distance(p1, p2) -> float:
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def classify_hand(hand_lm) -> Optional[str]:
    """Mirror the existing GestOne single-hand gesture labels."""
    lm = hand_lm.landmark
    wrist = lm[0]
    tips = [8, 12, 16, 20]
    mcps = [5, 9, 13, 17]

    extended = [distance(lm[t], wrist) > distance(lm[m], wrist) * 1.3 for t, m in zip(tips, mcps)]
    thumb_tip = lm[4]
    thumb_base = lm[17]
    thumb_ext = distance(thumb_tip, thumb_base) > distance(lm[2], thumb_base) * 1.1
    n_ext = sum(extended)

    if n_ext == 4 and thumb_ext:
        return "Play / Pause"
    if extended[0] and extended[1] and not extended[2] and not extended[3]:
        return "Next Track"
    if n_ext == 0 and thumb_ext:
        if thumb_tip.y < lm[5].y - 0.05:
            return "Volume Up"
        if thumb_tip.y > lm[5].y + 0.05:
            return "Volume Down"
    return None


@dataclass
class TrackingFrame:
    image: np.ndarray
    hand_count: int
    gesture: Optional[str]
    fps: float


class VisionThread(QThread):
    frame_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720) -> None:
        super().__init__()
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._running = True
        self._hands = mp.solutions.hands
        self._drawing = mp.solutions.drawing_utils
        self._styles = mp.solutions.drawing_styles

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            self.error.emit("Camera unavailable. Check camera permissions or camera index.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        last_ts = time.perf_counter()
        fps = 0.0

        hand_landmark_style = self._drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2)
        hand_connection_style = self._drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=1)
        active_point_style = self._drawing.DrawingSpec(color=(255, 122, 0), thickness=3, circle_radius=4)

        with self._hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.75,
        ) as hands:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    self.msleep(5)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = hands.process(rgb)
                rgb.flags.writeable = True

                overlay = frame.copy()
                gesture = None
                hand_count = 0

                if result.multi_hand_landmarks:
                    hand_count = len(result.multi_hand_landmarks)
                    for hand_lm in result.multi_hand_landmarks:
                        if gesture is None:
                            gesture = classify_hand(hand_lm)
                        self._drawing.draw_landmarks(
                            overlay,
                            hand_lm,
                            self._hands.HAND_CONNECTIONS,
                            hand_landmark_style,
                            hand_connection_style,
                        )
                        # Accent the thumb/index pinch points, matching GestOne's click logic.
                        h, w, _ = overlay.shape
                        for idx in (4, 8):
                            pt = hand_lm.landmark[idx]
                            cv2.circle(
                                overlay,
                                (int(pt.x * w), int(pt.y * h)),
                                7,
                                active_point_style.color,
                                -1,
                                lineType=cv2.LINE_AA,
                            )

                now = time.perf_counter()
                instant_fps = 1.0 / max(now - last_ts, 1e-6)
                fps = instant_fps if fps == 0.0 else (fps * 0.9 + instant_fps * 0.1)
                last_ts = now

                self.frame_ready.emit(TrackingFrame(overlay, hand_count, gesture, fps))

        cap.release()


class RoundedVideoLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(960, 540)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"background: {PANEL_DARK}; border-radius: 34px;")
        self._pixmap: Optional[QPixmap] = None

    def set_video_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
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
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for camera")


class Hud(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("hud")
        self.setFixedSize(260, 118)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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

        self.icon = QLabel("•", self)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(f"color: {ACCENT_BLUE};")
        self.icon.setFont(QFont("SF Pro Display", 42, QFont.Weight.Bold))
        self.icon.setGeometry(0, 12, 260, 44)

        self.title = QLabel("", self)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("SF Pro Text", 18, QFont.Weight.DemiBold))
        self.title.setGeometry(18, 62, 224, 28)

        self.subtitle = QLabel("Gesture detected", self)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setFont(QFont("SF Pro Text", 12, QFont.Weight.Medium))
        self.subtitle.setStyleSheet("color: rgba(245, 245, 247, 150);")
        self.subtitle.setGeometry(18, 88, 224, 20)

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        self.hide()

        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

    def show_message(self, text: str) -> None:
        self.title.setText(text)
        self.raise_()
        self.show()
        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity())
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.hide_timer.start(950)

    def fade_out(self) -> None:
        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.hide)
        self.anim.start()


class GesturelyDisplay(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Gesturely Display")
        self.resize(1180, 760)
        self.setMinimumSize(920, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._last_gesture: Optional[str] = None
        self._last_hud_ts = 0.0
        self._drag_origin: Optional[QPoint] = None

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

        self.video = RoundedVideoLabel()
        self.video.setParent(root)

        self.close_button = self._window_button(root, "#FF5F57")
        self.minimize_button = self._window_button(root, "#FFBD2E")
        self.zoom_button = self._window_button(root, "#28C840")
        self.close_button.clicked.connect(self.close)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.zoom_button.clicked.connect(self.toggle_zoom)

        self.title = QLabel("Gesturely Display", root)
        self.title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        self.title.setFont(QFont("SF Pro Display", 22, QFont.Weight.DemiBold))

        self.status = QLabel("Initializing camera", root)
        self.status.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self.status.setFont(QFont("SF Pro Text", 13, QFont.Weight.Medium))

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

        self.hud = Hud(root)

        self.vision = VisionThread()
        self.vision.frame_ready.connect(self.on_frame)
        self.vision.error.connect(self.on_error)
        self.vision.start()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        margin = 28
        header_h = 52
        self.close_button.setGeometry(margin, 28, 14, 14)
        self.minimize_button.setGeometry(margin + 22, 28, 14, 14)
        self.zoom_button.setGeometry(margin + 44, 28, 14, 14)
        self.title.setGeometry(margin + 78, 18, 360, 30)
        self.status.setGeometry(margin + 78, 47, 520, 22)
        self.badge.adjustSize()
        self.badge.move(self.width() - self.badge.width() - margin, 30)
        self.video.setGeometry(margin, header_h + 28, self.width() - margin * 2, self.height() - header_h - 56)
        self.hud.move((self.width() - self.hud.width()) // 2, (self.height() - self.hud.height()) // 2)
        super().resizeEvent(event)

    def on_frame(self, payload: TrackingFrame) -> None:
        rgb = cv2.cvtColor(payload.image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        self.video.set_video_pixmap(QPixmap.fromImage(qimg))

        hand_label = "No hands" if payload.hand_count == 0 else f"{payload.hand_count} hand{'s' if payload.hand_count != 1 else ''}"
        gesture_label = payload.gesture or "Scanning"
        self.status.setText(f"{hand_label}  ·  {gesture_label}  ·  {payload.fps:0.0f} FPS")
        self.badge.setStyleSheet(
            f"""
            color: {TEXT_PRIMARY};
            background: {'rgba(0, 122, 255, 130)' if payload.hand_count else 'rgba(255, 255, 255, 24)'};
            border: 1px solid rgba(255, 255, 255, 34);
            border-radius: 14px;
            padding: 5px 12px;
            """
        )

        now = time.monotonic()
        if payload.gesture and (payload.gesture != self._last_gesture or now - self._last_hud_ts > 2.0):
            self.hud.show_message(payload.gesture)
            self._last_gesture = payload.gesture
            self._last_hud_ts = now
        elif payload.gesture is None:
            self._last_gesture = None

    def on_error(self, message: str) -> None:
        self.status.setText(message)
        self.hud.show_message("Camera unavailable")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.vision.stop()
        super().closeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 84:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def toggle_zoom(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _window_button(self, parent: QWidget, color: str) -> QPushButton:
        button = QPushButton(parent)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background: {color};
                border: 0;
                border-radius: 7px;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(0, 0, 0, 90);
            }}
            """
        )
        return button


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Gesturely Display")
    app.setStyle("Fusion")
    window = GesturelyDisplay()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
