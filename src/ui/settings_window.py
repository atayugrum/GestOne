"""Settings Dashboard for GestOne."""

import cv2

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QLabel,
        QMainWindow,
        QScrollArea,
        QSlider,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QLabel,
        QMainWindow,
        QScrollArea,
        QSlider,
        QVBoxLayout,
        QWidget,
    )

from config import GestOneConfig


class SettingRow(QFrame):
    """Single setting row: label + control."""

    def __init__(self, label_text: str, control: QWidget):
        super().__init__()
        self.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 8);
                border-radius: 8px;
                padding: 12px;
                margin: 6px 0;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFont(QFont("SF Pro Text", 13, QFont.Weight.Medium))
        label.setStyleSheet("color: #F5F5F7;")

        layout.addWidget(label)
        layout.addWidget(control)


class SettingsWindow(QMainWindow):
    """Settings Dashboard for GestOne.

    Allows user to adjust sensitivity, camera, and feature toggles.
    """

    def __init__(self, config: GestOneConfig, on_save=None):
        super().__init__()
        self.config = config
        self.on_save = on_save

        self.setWindowTitle("GestOne Settings")
        self.resize(500, 700)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #09090B;
            }
            QLabel {
                color: #F5F5F7;
            }
            QComboBox, QSlider, QCheckBox {
                color: #F5F5F7;
            }
            """
        )

        # Central widget
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title
        title = QLabel("Settings")
        title.setFont(QFont("SF Pro Display", 32, QFont.Weight.Bold))
        title.setStyleSheet("color: #F5F5F7;")
        main_layout.addWidget(title)

        # Scroll area for settings
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        # ── Camera Selection ──
        camera_combo = QComboBox()
        camera_combo.setStyleSheet(
            """
            QComboBox {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 8px;
                padding: 8px;
                color: #F5F5F7;
            }
            """
        )
        cameras = ["Camera 0"]
        for i in range(1, 5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append(f"Camera {i}")
                cap.release()
        camera_combo.addItems(cameras)
        camera_combo.setCurrentIndex(config.camera_index)
        camera_combo.currentIndexChanged.connect(
            lambda i: setattr(config, "camera_index", i)
        )
        scroll_layout.addWidget(SettingRow("Camera Device", camera_combo))

        # ── Pinch Threshold ──
        pinch_slider = QSlider(Qt.Orientation.Horizontal)
        pinch_slider.setMinimum(10)
        pinch_slider.setMaximum(100)
        pinch_slider.setValue(int(config.mouse_pinch_threshold * 1000))
        pinch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pinch_slider.setTickInterval(10)

        def update_pinch(val):
            config.mouse_pinch_threshold = val / 1000.0

        pinch_slider.sliderMoved.connect(update_pinch)
        scroll_layout.addWidget(SettingRow("Pinch Sensitivity", pinch_slider))

        # ── Mouse Smoothing ──
        smooth_slider = QSlider(Qt.Orientation.Horizontal)
        smooth_slider.setMinimum(1)
        smooth_slider.setMaximum(30)
        smooth_slider.setValue(int(config.mouse_smoothing_alpha * 100))
        smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        def update_smooth(val):
            config.mouse_smoothing_alpha = val / 100.0

        smooth_slider.sliderMoved.connect(update_smooth)
        scroll_layout.addWidget(SettingRow("Cursor Smoothing", smooth_slider))

        # ── Head Neutral Zone ──
        head_slider = QSlider(Qt.Orientation.Horizontal)
        head_slider.setMinimum(1)
        head_slider.setMaximum(100)
        head_slider.setValue(int(config.head_neutral_zone * 1000))
        head_slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        def update_head(val):
            config.head_neutral_zone = val / 1000.0

        head_slider.sliderMoved.connect(update_head)
        scroll_layout.addWidget(SettingRow("Head Neutral Zone", head_slider))

        # ── Feature Toggles ──
        self.feature_checks = {}
        for feature in ["media", "mouse", "head", "two_hand", "voice"]:
            check = QCheckBox(feature.capitalize())
            check.setChecked(config.enabled_features.get(feature, True))
            check.setStyleSheet(
                "QCheckBox { color: #F5F5F7; spacing: 8px; } "
                "QCheckBox::indicator { width: 18px; height: 18px; }"
            )

            def make_toggle(feat):
                def toggle(state):
                    config.enabled_features[feat] = state == Qt.CheckState.Checked.value

                return toggle

            check.stateChanged.connect(make_toggle(feature))
            self.feature_checks[feature] = check
            scroll_layout.addWidget(SettingRow(f"Enable {feature}", check))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # Status bar
        self.status = QLabel("Changes saved automatically")
        self.status.setStyleSheet("color: #A1A1A6; font-size: 12px;")
        main_layout.addWidget(self.status)

    def closeEvent(self, event):
        """Save config on close."""
        if self.on_save:
            self.on_save()
        event.accept()
