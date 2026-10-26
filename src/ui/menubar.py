"""GestOne — QSystemTrayIcon-based menu bar app with background detection worker.

Architecture:
  GestOneMenuBar (QSystemTrayIcon)
    └─ HeartbeatWorker (QObject → QThread)
         Runs the full detection + action dispatch loop.
         Emits signals to the main thread for all UI side-effects.
    └─ HudWidget        (QWidget, always-on-top, frameless, mouse pass-through)
    └─ VisionWindow     (src.ui.vision_window, show/hide on demand)
    └─ SettingsWindow   (src.ui.settings_window, show/hide on demand)
    └─ CalibrationOverlay (src.ui.calibration, show/hide on demand)
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import threading
import time

import numpy as np
import pyautogui

try:
    from PyQt6.QtCore import (
        QEasingCurve,
        QObject,
        QPropertyAnimation,
        Qt,
        QThread,
        QTimer,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt6.QtGui import (
        QAction,
        QColor,
        QFont,
        QIcon,
        QPainter,
        QPixmap,
        QScreen,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsOpacityEffect,
        QLabel,
        QMenu,
        QSystemTrayIcon,
        QWidget,
    )
except ImportError:
    from PySide6.QtCore import (
        QEasingCurve,
        QObject,
        QPropertyAnimation,
        Qt,
        QThread,
        QTimer,
        Signal as pyqtSignal,
        Slot as pyqtSlot,
    )
    from PySide6.QtGui import (
        QAction,
        QColor,
        QFont,
        QIcon,
        QPainter,
        QPixmap,
        QScreen,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsOpacityEffect,
        QLabel,
        QMenu,
        QSystemTrayIcon,
        QWidget,
    )

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import (
    MODE_GESTURE,
    MODE_HEAD,
    MODE_MEDIA,
    MODE_MOUSE,
    MOUSE_DOUBLE_CLICK_TIMEOUT,
    default_config,
)
from src.controls.media_controller import MediaController
from src.controls.mouse_controller import MouseController
from src.core.action_router import ActionRouter
from src.core.modes import ModeManager
from src.detectors.camera_source import CameraSource
from src.detectors.gesture_detector import GestureDetector
from src.detectors.hand_mouse_tracker import HandMouseTracker
from src.detectors.head_tracker import HeadTracker
from src.detectors.two_hand_gesture_detector import TwoHandGestureDetector
from src.detectors.voice_controller import VoiceController
from src.ui.calibration import CalibrationOverlay
from src.ui.settings_window import SettingsWindow
from src.ui.vision_window import VisionWindow
from src.utils.common import Cooldown
from src.utils.config_persistence import load_overrides, apply_overrides, save_overrides
from src.utils.one_euro_filter import OneEuroFilter

# ── Action mappings ───────────────────────────────────────────────────────────
GESTURE_ACTIONS: dict[str, str] = {
    "Open_Palm":  "play_pause",
    "Thumb_Up":   "volume_up",
    "Thumb_Down": "volume_down",
    "Victory":    "next_track",
}
HEAD_ACTIONS: dict[str, str] = {
    "Turn_Right": "next_track",
    "Turn_Left":  "prev_track",
}
TWO_HAND_ACTIONS: dict[str, str] = {
    "Expand":          "fullscreen",
    "Contract":        "minimize",
    "Mission_Control": "mission_control",
}
POSTURE_MESSAGES: dict[str, str] = {
    "too_close": "Ekrana çok yakınsın. Biraz geriye yaslan.",
    "slouching": "Kambur duruş algılandı. Omuzlarını düzelt.",
}
# Human-readable labels for HUD
_ACTION_LABELS: dict[str, str] = {
    "play_pause":      "Play / Pause",
    "next_track":      "Next Track",
    "prev_track":      "Previous",
    "volume_up":       "Volume Up",
    "volume_down":     "Volume Down",
    "fullscreen":      "Fullscreen",
    "minimize":        "Minimize",
    "mission_control": "Mission Control",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_icon(emoji: str, size: int = 22) -> QIcon:
    """Render an emoji glyph into a QIcon (macOS renders natively)."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setFont(QFont("Apple Color Emoji", size - 4))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    p.end()
    return QIcon(px)


def _trigger_notification(title: str, message: str) -> None:
    cmd = f"osascript -e 'display notification \"{message}\" with title \"{title}\" sound name \"Glass\"'"
    os.system(cmd)


def _show_accessibility_warning(message: str) -> None:
    print(message)
    _trigger_notification("GestOne", message)
    try:
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ── Standalone HUD widget ─────────────────────────────────────────────────────

class HudWidget(QWidget):
    """System-wide translucent gesture-feedback overlay.

    Always on top, frameless, ignores all mouse events.
    Positioned at bottom-centre of the primary screen.
    """

    def __init__(self, duration_ms: int = 800) -> None:
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(280, 120)
        self.duration_ms = duration_ms

        # Background frame
        frame = QFrame(self)
        frame.setObjectName("hud")
        frame.setGeometry(0, 0, 280, 120)
        frame.setStyleSheet(
            """
            QFrame#hud {
                background: rgba(28, 28, 30, 210);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 28px;
            }
            """
        )

        self._icon_lbl = QLabel("◉", frame)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("color: #007AFF; background: transparent;")
        self._icon_lbl.setFont(QFont("SF Pro Display", 36, QFont.Weight.Bold))
        self._icon_lbl.setGeometry(0, 10, 280, 44)

        self._title_lbl = QLabel("", frame)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("SF Pro Text", 18, QFont.Weight.DemiBold))
        self._title_lbl.setStyleSheet("color: #F5F5F7; background: transparent;")
        self._title_lbl.setGeometry(18, 60, 244, 30)

        self._sub_lbl = QLabel("Gesture detected", frame)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont("SF Pro Text", 12))
        self._sub_lbl.setStyleSheet("color: rgba(245,245,247,150); background: transparent;")
        self._sub_lbl.setGeometry(18, 90, 244, 22)

        # Opacity animation
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self.hide()

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._hide_timer = QTimer(self, singleShot=True)
        self._hide_timer.timeout.connect(self._fade_out)

        # Reposition to bottom-centre
        self._reposition()

    def _reposition(self) -> None:
        screen: QScreen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + geo.height() - self.height() - 80
        self.move(x, y)

    @pyqtSlot(str)
    def show_message(self, text: str) -> None:
        self._title_lbl.setText(text)
        self._reposition()
        self.show()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._hide_timer.start(self.duration_ms)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.finished.connect(self.hide)
        self._anim.start()


# ── Heartbeat worker ──────────────────────────────────────────────────────────

class HeartbeatWorker(QObject):
    """Runs the full detection + dispatch loop in a QThread.

    All UI side-effects are emitted as Qt signals so they execute on the
    main thread via the normal Qt event loop — no raw thread-unsafe calls.
    """

    # (action_name, display_label)
    action_detected = pyqtSignal(str, str)
    # "active" | "no_hand" | "idle" | "camera_error"
    status_changed = pyqtSignal(str)
    # (bgr_frame, lm_list_or_None, gesture_label)
    frame_ready = pyqtSignal(object, object, str)
    # Voice requested sleep
    sleep_requested = pyqtSignal()
    # Voice requested mode switch
    mode_switch_requested = pyqtSignal(str)

    def __init__(self, service: "GestOneMenuBar") -> None:
        super().__init__()
        self._svc = service
        self._running = True
        # Set by the main thread when going to sleep/pause so worker
        # can issue drag_stop before parking.
        self._cancel_drag_event = threading.Event()

    def stop(self) -> None:
        self._running = False

    def request_drag_cancel(self) -> None:
        self._cancel_drag_event.set()

    @pyqtSlot()
    def run(self) -> None:
        svc = self._svc

        # ── Timing constants ──────────────────────────────────────────────
        _ACTIVE_SLEEP  = 1.0 / 30   # 30 Hz while something is detected
        _IDLE_SLEEP    = 1.0 / 5    # 5 Hz when idle
        _ACTIVE_LINGER = 2.0        # stay at active rate for 2 s after last detection

        # ── Local mutable state (owned by this thread; never shared) ─────
        pinch_active       = False
        drag_started       = False
        pending_click      = False
        pinch_start_time   = 0.0
        frozen_x = frozen_y = 0.0
        pinch_freeze_frames = 0
        _FREEZE_FRAMES     = 2
        _DRAG_DEADZONE     = 25
        last_click_time    = 0.0
        last_release_time  = 0.0  # noqa: F841 — kept for symmetry
        smooth_x = svc.screen_w / 2
        smooth_y = svc.screen_h / 2
        prev_gesture       = None
        _last_active_ts    = 0.0
        _last_seen_ts      = time.time()
        _is_screen_locked  = False
        _prev_status       = ""

        while self._running:
            # ── Drag-cancel request from main thread ──────────────────────
            if self._cancel_drag_event.is_set():
                self._cancel_drag_event.clear()
                if drag_started:
                    svc.mouse_ctrl.drag_stop()
                pinch_active = drag_started = pending_click = False
                pinch_freeze_frames = 0

            # ── Detection snapshot ────────────────────────────────────────
            face_present = svc.head.is_present()
            hand_state   = svc.hand_mouse.get_state()
            pos, pinch_norm, is_scrolling, scroll_delta = hand_state
            hand_present = pos is not None or svc.two_hand.get_hand_count() > 0

            # ── Adaptive sleep ────────────────────────────────────────────
            if face_present or hand_present:
                _last_active_ts = time.time()

            _behind = time.time() - _last_active_ts
            time.sleep(_ACTIVE_SLEEP if _behind < _ACTIVE_LINGER else _IDLE_SLEEP)

            # ── Config snapshot (lock-protected) ─────────────────────────
            with svc._lock:
                is_active       = svc.is_active
                pinch_threshold = svc.config.mouse_pinch_threshold
                is_calibrating  = svc.is_calibrating
                hold_drag_delay = svc.config.mouse_hold_drag_delay_sec
                enabled         = dict(svc.config.enabled_features)

            # ── Status signal ─────────────────────────────────────────────
            if not is_active:
                new_status = "idle"
            elif hand_present or face_present:
                new_status = "active"
            else:
                new_status = "no_hand"

            if new_status != _prev_status:
                self.status_changed.emit(new_status)
                _prev_status = new_status

            if not is_active:
                continue

            # ── Security auto-lock ────────────────────────────────────────
            if hand_present or face_present:
                _last_seen_ts = time.time()
                _is_screen_locked = False
            elif not _is_screen_locked and (time.time() - _last_seen_ts) > 45.0:
                os.system(
                    "/System/Library/CoreServices/Menu\\ Extras/User.menu"
                    "/Contents/Resources/CGSession -suspend"
                )
                _is_screen_locked = True

            # ── Voice commands ────────────────────────────────────────────
            if enabled.get("voice", True):
                voice_action = svc.voice.consume_action()
                if voice_action:
                    if voice_action == "sleep_mode":
                        self.sleep_requested.emit()
                    elif voice_action.startswith("mode_"):
                        self.mode_switch_requested.emit(voice_action[5:])
                    else:
                        clean = voice_action.replace("_track", "")
                        svc.action_router.execute_context_action(clean)
                        label = _ACTION_LABELS.get(clean, clean.replace("_", " ").title())
                        self.action_detected.emit(clean, label)

            # ── Posture warning ───────────────────────────────────────────
            posture_warning = svc.head.get_posture_warning()
            if posture_warning and svc.posture_cooldown.check_and_reset():
                msg = POSTURE_MESSAGES.get(posture_warning, "Duruşunu düzelt.")
                _trigger_notification("GestOne Posture", msg)

            # ── Frame for Vision window (cheap: only if window visible) ───
            if svc._vision_window_visible:
                raw_bgr = svc.camera.get_frame_flipped()
                if raw_bgr is not None:
                    lm_list = _extract_lm_list(svc.hand_mouse)
                    self.frame_ready.emit(raw_bgr, lm_list, prev_gesture or "")

            # ── Mouse mode ────────────────────────────────────────────────
            current_mode = svc.modes.current

            if current_mode == MODE_MOUSE and enabled.get("mouse", True):
                if is_calibrating and pos is not None:
                    with svc._lock:
                        svc.calibration_samples.append(pinch_norm)

                # Scroll (V-sign) overrides all pinch logic
                if is_scrolling:
                    if pinch_active:
                        if drag_started:
                            svc.mouse_ctrl.drag_stop()
                        pinch_active = drag_started = pending_click = False
                        pinch_freeze_frames = 0
                    if abs(scroll_delta) > 0.003:
                        ticks = int(np.clip(scroll_delta * 15, -8, 8))
                        svc.mouse_ctrl.scroll(ticks)
                    continue

                if pos is not None:
                    # ROI → screen pixels
                    raw_x = float(np.interp(pos[0], [0.0, 1.0], [0.0, svc.screen_w]))
                    raw_y = float(np.interp(pos[1], [0.0, 1.0], [0.0, svc.screen_h]))

                    # OneEuroFilter smoothing
                    _now = time.time()
                    smooth_x = svc.filter_x(_now, raw_x)
                    smooth_y = svc.filter_y(_now, raw_y)

                    # ── Pinch state machine ───────────────────────────────
                    is_pinching = pinch_norm < pinch_threshold

                    if is_pinching:
                        if not pinch_active:
                            # Pinch onset — arm a potential click
                            frozen_x, frozen_y = smooth_x, smooth_y
                            svc.mouse_ctrl.move_to(frozen_x, frozen_y)
                            now = time.time()
                            if now - last_click_time < MOUSE_DOUBLE_CLICK_TIMEOUT:
                                svc.mouse_ctrl.double_click()
                                pinch_active = drag_started = pending_click = False
                                last_click_time = 0.0
                                last_release_time = now
                            else:
                                pinch_active      = True
                                pending_click     = True
                                drag_started      = False
                                pinch_start_time  = now
                                pinch_freeze_frames = _FREEZE_FRAMES
                        else:
                            # Already pinching — check for drag promotion
                            if pinch_freeze_frames > 0:
                                pinch_freeze_frames -= 1
                                svc.mouse_ctrl.move_to(frozen_x, frozen_y)
                            else:
                                dist = math.hypot(smooth_x - frozen_x, smooth_y - frozen_y)
                                held = (time.time() - pinch_start_time) >= hold_drag_delay
                                if pending_click and (held or dist > _DRAG_DEADZONE):
                                    svc.mouse_ctrl.move_to(frozen_x, frozen_y)
                                    svc.mouse_ctrl.drag_start()
                                    pending_click = False
                                    drag_started  = True
                                if drag_started:
                                    svc.mouse_ctrl.move_to(smooth_x, smooth_y)
                                else:
                                    svc.mouse_ctrl.move_to(frozen_x, frozen_y)
                    else:
                        # Pinch released
                        if pinch_active:
                            if drag_started:
                                svc.mouse_ctrl.drag_stop()
                            elif pending_click:
                                svc.mouse_ctrl.move_to(frozen_x, frozen_y)
                                svc.mouse_ctrl.click()
                                last_click_time = time.time()
                            pinch_active = drag_started = pending_click = False
                            pinch_freeze_frames = 0
                            last_release_time = time.time()
                        else:
                            svc.mouse_ctrl.move_to(smooth_x, smooth_y)
                else:
                    # Hand lost mid-drag
                    if pinch_active:
                        if drag_started:
                            svc.mouse_ctrl.drag_stop()
                        pinch_active = drag_started = pending_click = False
                continue  # skip non-mouse modes when in mouse mode

            # ── Two-hand gestures (available in all non-mouse modes) ──────
            if enabled.get("two_hand", True):
                action_2h = svc.two_hand.consume_action()
                if action_2h and svc.two_hand_cooldown.check_and_reset():
                    mapped = TWO_HAND_ACTIONS.get(action_2h)
                    if mapped:
                        svc.action_router.execute_context_action(mapped)
                        label = _ACTION_LABELS.get(mapped, mapped)
                        self.action_detected.emit(mapped, label)

            # ── Head mode ─────────────────────────────────────────────────
            if current_mode == MODE_HEAD and enabled.get("head", True):
                gl = svc.head.consume_action()
                if gl and svc.head_cooldown.check_and_reset():
                    act = HEAD_ACTIONS.get(gl, "").replace("_track", "")
                    if act:
                        svc.action_router.execute_context_action(act)
                        self.action_detected.emit(act, _ACTION_LABELS.get(act, act))

            # ── Gesture / media mode ──────────────────────────────────────
            elif current_mode in (MODE_GESTURE, MODE_MEDIA) and enabled.get("media", True):
                if svc.two_hand.get_hand_count() < 2:
                    curr_g = svc.gesture.get_gesture()
                    if curr_g != prev_gesture:
                        prev_gesture = curr_g
                        if curr_g:
                            act = GESTURE_ACTIONS.get(curr_g, "").replace("_track", "")
                            if act and svc.gesture_cooldown.check_and_reset():
                                svc.action_router.execute_context_action(act)
                                self.action_detected.emit(act, _ACTION_LABELS.get(act, act))


def _extract_lm_list(tracker: HandMouseTracker):
    """Pull raw normalised landmark list from the tracker's last frame."""
    # HandMouseTracker doesn't publicly expose landmarks; return None gracefully.
    # VisionWindow works fine without them (draws nothing).
    return None


# ── Main system-tray class ────────────────────────────────────────────────────

class GestOneMenuBar(QSystemTrayIcon):
    """System tray icon that owns the camera, detectors, and UI windows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Config ────────────────────────────────────────────────────────
        self.config = default_config()
        apply_overrides(self.config, load_overrides())
        if not self.config.mouse_pinch_threshold:
            self.config.mouse_pinch_threshold = 0.04

        # ── Shared mutable state (protected by self._lock) ────────────────
        self._lock              = threading.Lock()
        self.is_active          = True
        self.is_calibrating     = False
        self.calibration_samples: list[float] = []
        self._vision_window_visible = False

        # ── Hardware init ─────────────────────────────────────────────────
        self.camera = CameraSource(
            self.config.camera_index,
            self.config.camera_width,
            self.config.camera_height,
        )
        if not self.camera.start():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "GestOne", "Camera could not be started.\nCheck camera permissions.")
            sys.exit(1)

        # ── Controllers & detectors ───────────────────────────────────────
        self.media     = MediaController()
        self.mouse_ctrl = MouseController(warning_callback=_show_accessibility_warning)
        if not self.mouse_ctrl._ensure_accessibility():
            self.mouse_ctrl.request_accessibility_prompt()

        self.modes      = ModeManager(self.config.active_mode)
        self.action_router = ActionRouter(self.modes, self.media, self.mouse_ctrl)

        self.gesture   = GestureDetector(self.camera)
        self.hand_mouse = HandMouseTracker(self.camera)
        self.two_hand  = TwoHandGestureDetector(self.camera, self.config.two_hand_stability_frames)
        self.head      = HeadTracker(self.camera, yaw_threshold=1.85, stability_frames=8)
        self.voice     = VoiceController()

        self.gesture.start()
        self.hand_mouse.start()
        self.two_hand.start()
        self.head.start()
        self.voice.start()

        # ── Screen size & filters ─────────────────────────────────────────
        self.screen_w, self.screen_h = pyautogui.size()
        pyautogui.FAILSAFE = False
        _t0 = time.time()
        self.filter_x = OneEuroFilter(_t0, self.screen_w / 2, min_cutoff=0.8, beta=0.5)
        self.filter_y = OneEuroFilter(_t0, self.screen_h / 2, min_cutoff=0.8, beta=0.5)

        # ── Cooldowns ─────────────────────────────────────────────────────
        self.gesture_cooldown   = Cooldown(self.config.cooldown_sec)
        self.two_hand_cooldown  = Cooldown(self.config.two_hand_cooldown_sec)
        self.head_cooldown      = Cooldown(self.config.head_cooldown_sec)
        self.posture_cooldown   = Cooldown(60)

        # ── UI windows (created lazily, hidden on close) ──────────────────
        self._hud: HudWidget = HudWidget(self.config.hud_duration_ms)
        self._settings_win: SettingsWindow | None = None
        self._vision_win: VisionWindow | None = None
        self._calib_overlay: CalibrationOverlay | None = None

        # ── Icons ─────────────────────────────────────────────────────────
        self._icon_active = _make_icon("🖐️")
        self._icon_idle   = _make_icon("💤")
        self._icon_warn   = _make_icon("⚠️")

        self.setIcon(self._icon_active)
        self.setToolTip("GestOne — Active")
        self.setVisible(True)

        # ── Context menu ──────────────────────────────────────────────────
        self._build_menu()

        # ── Heartbeat worker ──────────────────────────────────────────────
        self._worker_thread = QThread(self)
        self._worker        = HeartbeatWorker(self)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.action_detected.connect(self._on_action)
        self._worker.status_changed.connect(self._on_status)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.sleep_requested.connect(self._go_sleep)
        self._worker.mode_switch_requested.connect(self.set_mode)

        self._worker_thread.start()

    # ── Menu construction ─────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menu = QMenu()

        # Status line (non-interactive)
        self._status_action = menu.addAction("● Active — Hand Detected")
        self._status_action.setEnabled(False)

        menu.addSeparator()

        # Pause / Resume
        self._toggle_action = menu.addAction("⏸  Pause Tracking")
        self._toggle_action.triggered.connect(self._toggle_active)

        menu.addSeparator()

        # Mode submenu
        mode_menu = QMenu("Mode", menu)
        for mode_name, label in [("mouse", "🖱  Mouse"), ("gesture", "✋  Gesture"),
                                  ("head", "🧭  Head"), ("idle", "💤  Idle")]:
            act = mode_menu.addAction(label)
            act.triggered.connect(lambda _checked, m=mode_name: self.set_mode(m))
        menu.addMenu(mode_menu)

        menu.addSeparator()

        # Vision feed toggle
        self._vision_action = menu.addAction("👁  Show Vision Feed")
        self._vision_action.setCheckable(True)
        self._vision_action.setChecked(False)
        self._vision_action.triggered.connect(self._toggle_vision)

        # Calibrate
        calib_act = menu.addAction("📍  Calibrate Gestures")
        calib_act.triggered.connect(self._launch_calibration)

        # Preferences
        prefs_act = menu.addAction("⚙️  Preferences…")
        prefs_act.triggered.connect(self._open_preferences)

        menu.addSeparator()

        # Start at Login (placeholder — requires LaunchAgent integration)
        self._login_action = menu.addAction("Launch at Login")
        self._login_action.setCheckable(True)
        self._login_action.setEnabled(False)          # TODO: wire SMLoginItemSetEnabled
        self._login_action.setToolTip("Coming soon")

        menu.addSeparator()

        quit_act = menu.addAction("Quit GestOne")
        quit_act.triggered.connect(self._quit)

        self.setContextMenu(menu)

    # ── Signal handlers (main thread) ─────────────────────────────────────────

    @pyqtSlot(str, str)
    def _on_action(self, action_name: str, label: str) -> None:
        """Show HUD flash for every successfully dispatched action."""
        self._hud.show_message(label)

    @pyqtSlot(str)
    def _on_status(self, status: str) -> None:
        """Update tray icon and status line on detection-state change."""
        if status == "active":
            self.setIcon(self._icon_active)
            self.setToolTip("GestOne — Hand Detected")
            self._status_action.setText("● Active — Hand Detected")
        elif status == "no_hand":
            self.setIcon(self._icon_warn)
            self.setToolTip("GestOne — No Hand Detected")
            self._status_action.setText("○ No Hand Detected")
        else:  # idle
            self.setIcon(self._icon_idle)
            self.setToolTip("GestOne — Paused")
            self._status_action.setText("⏸ Paused")

    @pyqtSlot(object, object, str)
    def _on_frame(self, bgr_frame, landmarks, gesture: str) -> None:
        """Forward camera frames to the vision window if visible."""
        if self._vision_win and self._vision_win.isVisible():
            self._vision_win.receive_frame(bgr_frame, landmarks, gesture)

    @pyqtSlot()
    def _go_sleep(self) -> None:
        """Voice command: put tracking to sleep."""
        self._worker.request_drag_cancel()
        with self._lock:
            self.is_active = False
        self.setIcon(self._icon_idle)
        self.setToolTip("GestOne — Paused")
        self._toggle_action.setText("▶  Resume Tracking")
        self._status_action.setText("⏸ Paused")
        _trigger_notification("GestOne", "Tracking paused.")

    # ── Menu actions ──────────────────────────────────────────────────────────

    def _toggle_active(self) -> None:
        with self._lock:
            self.is_active = not self.is_active
            active = self.is_active

        if not active:
            self._worker.request_drag_cancel()
            self.setIcon(self._icon_idle)
            self.setToolTip("GestOne — Paused")
            self._toggle_action.setText("▶  Resume Tracking")
        else:
            self.setIcon(self._icon_active)
            self.setToolTip("GestOne — Active")
            self._toggle_action.setText("⏸  Pause Tracking")

    def _toggle_vision(self, checked: bool) -> None:
        """Show or hide the Vision Feed window."""
        if checked:
            if self._vision_win is None:
                self._vision_win = VisionWindow()
                # Override closeEvent so closing hides rather than quits
                def _hide_on_close(event):
                    event.ignore()
                    self._vision_win.hide()
                    self._vision_action.setChecked(False)
                    self._vision_window_visible = False
                self._vision_win.closeEvent = _hide_on_close  # type: ignore[method-assign]
            self._vision_window_visible = True
            self._vision_win.show()
            self._vision_win.activateWindow()
            self._vision_win.raise_()
        else:
            if self._vision_win:
                self._vision_win.hide()
            self._vision_window_visible = False

    def _open_preferences(self) -> None:
        """Open the Settings window; create it lazily."""
        if self._settings_win is None:
            self._settings_win = SettingsWindow(
                self.config,
                on_save=lambda: save_overrides(self.config),
            )
            # Override closeEvent → hide
            def _hide_on_close(event):
                event.ignore()
                self._settings_win.hide()
            self._settings_win.closeEvent = _hide_on_close  # type: ignore[method-assign]
        self._settings_win.show()
        self._settings_win.activateWindow()
        self._settings_win.raise_()

    def _launch_calibration(self) -> None:
        """Launch full-screen calibration overlay."""
        box = self.config.mouse_sensitivity_box
        roi = (box, 1.0 - box, box, 1.0 - box)
        if self._calib_overlay is None or not self._calib_overlay.isVisible():
            self._calib_overlay = CalibrationOverlay(roi, self.config.calibration_hold_seconds)
        self._calib_overlay.show()

    @pyqtSlot(str)
    def set_mode(self, mode_name: str) -> None:
        """Switch tracking mode; clean up any OS-level drag."""
        self._worker.request_drag_cancel()
        with self._lock:
            self.modes.toggle(mode_name)

    def _quit(self) -> None:
        """Graceful shutdown: stop worker, detectors, camera, save config."""
        self._worker.stop()
        self._worker_thread.quit()
        self._worker_thread.wait(2000)

        self.gesture.stop()
        self.hand_mouse.stop()
        self.two_hand.stop()
        self.head.stop()
        self.voice.stop()
        self.camera.stop()

        save_overrides(self.config)
        QApplication.quit()
