"""GestOne — macOS Menu Bar App.
Pinch (Click) ve Mouse Stabilizasyonu Güncellendi.
"""

import os
os.environ['GLOG_minloglevel'] = '2'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import sys
import time
import math
import subprocess
import threading
import numpy as np
import cv2
import pyautogui
import rumps

# Fail-safe'i kapatıyoruz ki ekran köşesinde uygulama çökmesin
pyautogui.FAILSAFE = False

import objc
from Foundation import NSObject

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import (
    ALL_MODES,
    MODE_GESTURE,
    MODE_HEAD,
    MODE_MEDIA,
    MODE_MOUSE,
    MODE_VOICE,
    MOUSE_DOUBLE_CLICK_TIMEOUT,
    default_config,
)
from src.core.modes import ModeManager
from src.core.dispatcher import Dispatcher
from src.detectors.camera_source import CameraSource
from src.detectors.gesture_detector import GestureDetector
from src.detectors.hand_mouse_tracker import HandMouseTracker
from src.detectors.head_tracker import HeadTracker
from src.detectors.voice_controller import VoiceController
from src.detectors.two_hand_gesture_detector import TwoHandGestureDetector
from src.controls.mouse_controller import MouseController
from src.controls.media_controller import MediaController
from src.utils.common import Cooldown
from src.utils.config_persistence import load_overrides, apply_overrides, save_overrides
from src.utils.one_euro_filter import OneEuroFilter  # kept for future use

GESTURE_ACTIONS = {
    "Open_Palm":  "play_pause",
    "Thumb_Up":   "volume_up",
    "Thumb_Down": "volume_down",
    "Victory":    "next_track",
}

HEAD_ACTIONS = {
    "Turn_Right": "next_track",
    "Turn_Left":  "prev_track",
}

TWO_HAND_ACTIONS = {
    "Expand": "fullscreen",
    "Contract": "minimize",
    "Mission_Control": "mission_control"
}

def trigger_mac_notification(title: str, message: str) -> None:
    cmd = f'''osascript -e 'display notification "{message}" with title "{title}" sound name "Glass"' '''
    os.system(cmd)


POSTURE_MESSAGES = {
    "too_close": "Ekrana cok yakinsin. Biraz geriye yaslan.",
    "slouching": "Kambur durus algilandi. Omuzlarini duzeltip dik otur.",
}


def show_accessibility_warning(message: str) -> None:
    print(message)
    trigger_mac_notification("GestOne", message)
    try:
        rumps.alert("GestOne", message)
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

# ── Cached active-app (BUG-06): never blocks tick_loop ────────────────────────
_active_app_cache: str = ""
_active_app_ts: float = 0.0
_active_app_lock = threading.Lock()
_ACTIVE_APP_TTL = 2.0

def _refresh_active_app() -> None:
    global _active_app_cache, _active_app_ts
    try:
        cmd = 'tell application "System Events" to get name of first application process whose frontmost is true'
        res = subprocess.run(["osascript", "-e", cmd],
                             capture_output=True, text=True, timeout=1.0)
        with _active_app_lock:
            _active_app_cache = res.stdout.strip()
            _active_app_ts = time.time()
    except Exception:
        pass

def get_active_app() -> str:
    """Returns cached frontmost app; refreshes in background every 2 s."""
    now = time.time()
    with _active_app_lock:
        stale = (now - _active_app_ts) > _ACTIVE_APP_TTL
        cached = _active_app_cache
    if stale:
        threading.Thread(target=_refresh_active_app, daemon=True).start()
    return cached

class UIUpdater(NSObject):
    def updateMenuMarks_(self, app_instance):
        curr = app_instance.modes.current
        app_instance.menu["Mod: Mouse"].state = 1 if curr == "mouse" else 0
        app_instance.menu["Mod: Gesture"].state = 1 if curr == "gesture" else 0
        app_instance.menu["Mod: Kafa"].state = 1 if curr == "head" else 0

class GestOneMenuBar(rumps.App):
    def __init__(self):
        super(GestOneMenuBar, self).__init__("🖐️", quit_button=None)
        
        self.config = default_config()
        apply_overrides(self.config, load_overrides())
        
        # Pinch Threshold Güvencesi
        if not hasattr(self.config, 'mouse_pinch_threshold') or self.config.mouse_pinch_threshold is None:
            self.config.mouse_pinch_threshold = 0.04
            
        self.MOUSE_SMOOTHNESS = 15.0  # OneEuroFilter beta — higher = less lag on fast moves
        self._lock = threading.Lock()       # BUG-01: protects shared state between main/timer threads and tick_loop
        self._last_active_time = 0.0        # BUG-05: adaptive FPS hysteresis
        self.modes = ModeManager(self.config.active_mode)
        self.dispatch = Dispatcher()
        self.media = MediaController()
        self.mouse_ctrl = MouseController(warning_callback=show_accessibility_warning)
        if not self.mouse_ctrl._ensure_accessibility():
            self.mouse_ctrl.request_accessibility_prompt()
            self.status_item = rumps.MenuItem("Durum: Erişilebilirlik izni gerekli")
        else:
            self.status_item = rumps.MenuItem("Durum: Çalışıyor")

        self.camera = CameraSource(self.config.camera_index, self.config.camera_width, self.config.camera_height)
        if not self.camera.start():
            rumps.alert("Hata", "Kamera başlatılamadı.")
            sys.exit(1)

        self.gesture = GestureDetector(self.camera)
        self.hand_mouse = HandMouseTracker(self.camera)
        self.two_hand = TwoHandGestureDetector(self.camera, self.config.two_hand_stability_frames)
        self.head = HeadTracker(self.camera, yaw_threshold=1.85, stability_frames=8)
        self.voice = VoiceController()

        self.gesture.start()
        self.hand_mouse.start()
        self.two_hand.start()
        self.head.start()
        self.voice.start()

        screen_w, screen_h = pyautogui.size()
        self.screen_w, self.screen_h = screen_w, screen_h
        
        self.gesture_cooldown = Cooldown(self.config.cooldown_sec)
        self.two_hand_cooldown = Cooldown(self.config.two_hand_cooldown_sec)
        self.head_cooldown = Cooldown(self.config.head_cooldown_sec)
        self.posture_cooldown = Cooldown(60)

        # OneEuroFilter smoothing — snappy on fast moves, stable at rest
        _t0 = time.time()
        self.filter_x = OneEuroFilter(_t0, screen_w / 2, min_cutoff=0.8, beta=0.5)
        self.filter_y = OneEuroFilter(_t0, screen_h / 2, min_cutoff=0.8, beta=0.5)
        self.smooth_x, self.smooth_y = screen_w / 2, screen_h / 2
        self.prev_gesture = None

        self._prev_scroll_y = None

        # Double-click detection
        self.last_release_time = 0.0
        self.last_click_time = 0.0

        # Pinch state machine
        self.pinch_active = False
        self.drag_started = False
        self.pending_click = False
        self.pinch_start_time = 0.0
        self.frozen_x, self.frozen_y = 0.0, 0.0
        # Pinch state-lock: freeze cursor for N frames after pinch onset to prevent jump
        self._pinch_freeze_frames: int = 0
        self._PINCH_FREEZE_FRAMES: int = 2

        self.DRAG_DEADZONE = 25
        
        self.last_seen_time = time.time()
        self.is_locked = False
        self.is_active = True
        self.is_calibrating = False
        self.calibration_samples = []

        self.ui_updater = UIUpdater.alloc().init()
        self.toggle_item = rumps.MenuItem("⏸ Duraklat", callback=self.toggle_active)
        
        self.menu = [
            self.status_item,
            self.toggle_item,
            None,
            rumps.MenuItem("Mod: Mouse", callback=lambda _: self.set_mode("mouse")),
            rumps.MenuItem("Mod: Gesture", callback=lambda _: self.set_mode("gesture")),
            rumps.MenuItem("Mod: Kafa", callback=lambda _: self.set_mode("head")),
            None,
            ("📖 Rehber (Hareketler)", [
                rumps.MenuItem("✋ Açık Avuç: Oynat/Duraklat"),
                rumps.MenuItem("👍 Başparmak Yukarı: Ses Aç"),
                rumps.MenuItem("👎 Başparmak Aşağı: Ses Kıs"),
                rumps.MenuItem("✌️ Zafer İşareti: Sonraki Şarkı / Scroll"),
                rumps.MenuItem("✊✊ İki El Yumruk: Mission Control"),
                rumps.MenuItem("👐 İki El Yaklaştır: Küçült"),
                rumps.MenuItem("👐 İki El Uzaklaştır: Tam Ekran")
            ]),
            ("🗣 Rehber (Sesli Komutlar)", [
                rumps.MenuItem("🎙️ 'Fare', 'Jest', 'Kafa'"),
                rumps.MenuItem("🎙️ 'Oynat', 'Sonraki', 'Önceki'"),
                rumps.MenuItem("🎙️ 'Tam ekran', 'Büyüt'")
            ]),
            None,
            ("⚙️ Ayarlar", [
                rumps.MenuItem("✨ Oto-Kalibrasyon Başlat", callback=self.start_calibration),
                rumps.MenuItem("Tıklama Hassasiyetini Düzenle", callback=self.edit_pinch),
                rumps.MenuItem("Fare Akıcılığını Düzenle", callback=self.edit_smoothness)
            ]),
            None,
            rumps.MenuItem("Çıkış", callback=self.clean_quit)
        ]
        
        self._update_menu_marks_safe()
        self.tick_thread = threading.Thread(target=self.tick_loop, daemon=True)
        self.tick_thread.start()

    def execute_context_action(self, action_type: str):
        app = get_active_app()
        if action_type == "next":
            if app in ["Safari", "Google Chrome"]: pyautogui.hotkey('cmd', ']')
            elif app in ["Keynote", "Microsoft PowerPoint"]: pyautogui.press('right')
            else: self.media.next_track()
        elif action_type == "prev":
            if app in ["Safari", "Google Chrome"]: pyautogui.hotkey('cmd', '[')
            elif app in ["Keynote", "Microsoft PowerPoint"]: pyautogui.press('left')
            else: self.media.prev_track()
        elif action_type == "play_pause":
            if app in ["Keynote", "Microsoft PowerPoint"]: pyautogui.hotkey('cmd', 'return')
            else: self.media.play_pause()
        elif action_type == "volume_up":
            os.system("osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'")
        elif action_type == "volume_down":
            os.system("osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'")
        elif action_type == "fullscreen":
            pyautogui.hotkey('ctrl', 'cmd', 'f')
        elif action_type == "minimize":
            pyautogui.hotkey('cmd', 'm')
        elif action_type == "mission_control":
            pyautogui.hotkey('ctrl', 'up')

    def start_calibration(self, _):
        rumps.alert("Oto-Kalibrasyon", "Lütfen 3 saniye boyunca elinizi kameraya gösterip parmaklarınızı açıp-kapatın.")
        with self._lock:
            self.calibration_samples = []
            self.is_calibrating = True
        threading.Timer(3.0, self.finish_calibration).start()

    def finish_calibration(self):
        with self._lock:
            self.is_calibrating = False
            samples = list(self.calibration_samples)
        if len(samples) > 10:
            min_val = min(samples)
            max_val = max(samples)
            new_thresh = round(min_val + (max_val - min_val) * 0.3, 2)
            with self._lock:
                self.config.mouse_pinch_threshold = new_thresh
            trigger_mac_notification("Kalibrasyon Tamamlandı", f"Yeni Eşik: {new_thresh}")
        else:
            trigger_mac_notification("Hata", "Örnek toplanamadı.")

    def edit_pinch(self, _):
        with self._lock:
            current = self.config.mouse_pinch_threshold
        resp = rumps.Window(message="Tıklama Hassasiyeti (Düşük=0.02, Normal=0.04, Yüksek=0.07):", default_text=str(current)).run()
        if resp.clicked:
            try:
                with self._lock:
                    self.config.mouse_pinch_threshold = float(resp.text)
            except Exception:
                pass

    def edit_smoothness(self, _):
        with self._lock:
            current = self.MOUSE_SMOOTHNESS
        resp = rumps.Window(message="Akıcılık (1-10):", default_text=str(current)).run()
        if resp.clicked:
            try:
                val = float(resp.text)
                with self._lock:
                    self.MOUSE_SMOOTHNESS = val
                    self.filter_x.beta = val
                    self.filter_y.beta = val
            except Exception:
                pass

    def toggle_active(self, sender):
        with self._lock:
            self.is_active = not self.is_active
            now_active = self.is_active
            if not now_active and self.pinch_active:
                if self.drag_started:
                    self.mouse_ctrl.drag_stop()
                self.pinch_active = False
                self.drag_started = False
                self.pending_click = False
        if now_active:
            self.title = "🖐️"
            self.status_item.title = "Durum: Çalışıyor"
            sender.title = "⏸ Duraklat"
            self._last_active_time = time.time()
        else:
            self.title = "💤"
            self.status_item.title = "Durum: Beklemede"
            sender.title = "▶ Başlat"

    def set_mode(self, mode_name: str):
        # BUG-04: release any OS-level held drag before switching modes
        with self._lock:
            if self.pinch_active:
                if self.drag_started:
                    self.mouse_ctrl.drag_stop()
                self.pinch_active = False
                self.drag_started = False
                self.pending_click = False
        self.modes.toggle(mode_name)
        self._update_menu_marks_safe()

    def _update_menu_marks_safe(self):
        self.ui_updater.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateMenuMarks:", self, False   # BUG-02: str not bytes
        )

    def clean_quit(self, _):
        if self.pinch_active and self.drag_started:
            self.mouse_ctrl.drag_stop()
        self.gesture.stop(); self.hand_mouse.stop(); self.two_hand.stop(); self.head.stop(); self.voice.stop(); self.camera.stop()
        rumps.quit_application()

    def tick_loop(self):
        # BUG-05: adaptive FPS constants
        _ACTIVE_SLEEP = 1.0 / 30    # 30 FPS while hand/face present
        _IDLE_SLEEP   = 1.0 / 5     # 5 FPS when nothing detected
        _ACTIVE_LINGER = 2.0        # stay at active FPS for 2 s after last detection

        while True:
            face_present = self.head.is_present()
            hand_state = self.hand_mouse.get_state()
            pos, pinch_norm, is_scrolling, scroll_delta = hand_state

            hand_present = pos is not None or self.two_hand.get_hand_count() > 0

            # BUG-05: hysteresis — stay active FPS for ACTIVE_LINGER seconds after last detection
            if face_present or hand_present:
                self._last_active_time = time.time()

            if (time.time() - self._last_active_time) < _ACTIVE_LINGER:
                time.sleep(_ACTIVE_SLEEP)
            else:
                time.sleep(_IDLE_SLEEP)

            # BUG-01: snapshot shared config values under lock
            with self._lock:
                is_active       = self.is_active
                pinch_threshold = self.config.mouse_pinch_threshold
                is_calibrating  = self.is_calibrating
                hold_drag_delay = self.config.mouse_hold_drag_delay_sec

            if not is_active:
                continue

            # --- GÜVENLİK ---
            if face_present or hand_present:
                self.last_seen_time = time.time()
                if self.is_locked:
                    self.is_locked = False
            else:
                if (time.time() - self.last_seen_time) > 45.0 and not self.is_locked:
                    os.system('/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend')
                    self.is_locked = True

            # --- SES ---
            voice_action = self.voice.consume_action()
            if voice_action:
                if voice_action == "sleep_mode":
                    with self._lock:
                        self.is_active = False
                    self.title = "💤"
                    self.status_item.title = "Durum: Beklemede"
                    self.toggle_item.title = "▶ Başlat"
                    trigger_mac_notification("GestOne", "GestOne uyku moduna alındı.")
                elif voice_action in ["mode_gesture", "mode_mouse", "mode_head"]:
                    self.set_mode(voice_action.split("_")[1])
                else:
                    self.execute_context_action(voice_action.replace("_track", ""))

            # --- DURUS ---
            posture_warning = self.head.get_posture_warning()
            if posture_warning and self.posture_cooldown.check_and_reset():
                message = POSTURE_MESSAGES.get(posture_warning, "Duruşunu düzelt.")
                trigger_mac_notification("GestOne Posture", message)

            # --- MOUSE LOGIC ---
            if self.modes.current == MODE_MOUSE:
                if is_calibrating and pos is not None:
                    with self._lock:
                        self.calibration_samples.append(pinch_norm)

                if is_scrolling:
                    # Release any held drag when scroll starts
                    if self.pinch_active:
                        if self.drag_started:
                            self.mouse_ctrl.drag_stop()
                        self.pinch_active = False
                        self.drag_started = False
                        self.pending_click = False
                        self._pinch_freeze_frames = 0
                    # Direct scroll — stable and predictable
                    if abs(scroll_delta) > 0.003:
                        ticks = int(np.clip(scroll_delta * 15, -8, 8))
                        self.mouse_ctrl.scroll(ticks)
                    continue

                if pos is not None:
                    # 1. ROI-normalized [0..1] → screen pixels via np.interp (vectorized)
                    #    HandMouseTracker already applied boundary-box + WMA + noise-gate.
                    raw_x = float(np.interp(pos[0], [0.0, 1.0], [0.0, self.screen_w]))
                    raw_y = float(np.interp(pos[1], [0.0, 1.0], [0.0, self.screen_h]))

                    # 2. OneEuroFilter — snappy on fast moves, stable at rest
                    _now = time.time()
                    target_x, target_y = raw_x, raw_y
                    self.smooth_x = self.filter_x(_now, target_x)
                    self.smooth_y = self.filter_y(_now, target_y)

                    # 4. Pinch & Click — State Machine with 2-frame freeze lock
                    is_currently_pinching = pinch_norm < pinch_threshold

                    if is_currently_pinching:
                        if not self.pinch_active:
                            # Pinch onset: arm a click first; only promote to drag after hold/move.
                            self.frozen_x, self.frozen_y = self.smooth_x, self.smooth_y
                            self.mouse_ctrl.move_to(self.frozen_x, self.frozen_y)
                            now = time.time()
                            if now - self.last_click_time < MOUSE_DOUBLE_CLICK_TIMEOUT:
                                # Double click: fire immediately, do NOT hold mouse down
                                self.mouse_ctrl.double_click()
                                self.pinch_active = False
                                self.drag_started = False
                                self.pending_click = False
                                self.last_click_time = 0.0
                                self.last_release_time = now
                            else:
                                self.pinch_active = True
                                self.drag_started = False
                                self.pending_click = True
                                self.pinch_start_time = now
                                self._pinch_freeze_frames = self._PINCH_FREEZE_FRAMES
                        else:
                            # Decrement freeze counter, then decide whether this is still a click or now a drag.
                            if self._pinch_freeze_frames > 0:
                                self._pinch_freeze_frames -= 1
                                self.mouse_ctrl.move_to(self.frozen_x, self.frozen_y)
                            else:
                                dist = math.hypot(self.smooth_x - self.frozen_x, self.smooth_y - self.frozen_y)
                                held_long_enough = (time.time() - self.pinch_start_time) >= hold_drag_delay
                                if self.pending_click and (held_long_enough or dist > self.DRAG_DEADZONE):
                                    self.mouse_ctrl.move_to(self.frozen_x, self.frozen_y)
                                    self.mouse_ctrl.drag_start()
                                    self.pending_click = False
                                    self.drag_started = True
                                if self.drag_started:
                                    self.mouse_ctrl.move_to(self.smooth_x, self.smooth_y)
                                else:
                                    self.mouse_ctrl.move_to(self.frozen_x, self.frozen_y)
                    else:
                        if self.pinch_active:
                            # Release: short pinch becomes click, drag just releases.
                            if self.drag_started:
                                self.mouse_ctrl.drag_stop()
                            elif self.pending_click:
                                self.mouse_ctrl.move_to(self.frozen_x, self.frozen_y)
                                self.mouse_ctrl.click()
                                self.last_click_time = time.time()
                            self.pinch_active = False
                            self.drag_started = False
                            self.pending_click = False
                            self._pinch_freeze_frames = 0
                            self.last_release_time = time.time()
                        else:
                            # Normal cursor movement
                            self.mouse_ctrl.move_to(self.smooth_x, self.smooth_y)
                else:
                    # El kaybolduysa temizlik
                    if self.pinch_active: 
                        if self.drag_started:
                            self.mouse_ctrl.drag_stop()
                        self.pinch_active = False
                        self.drag_started = False
                        self.pending_click = False
                continue

            # --- DİĞER MODLAR ---
            action_2h = self.two_hand.consume_action()
            if action_2h and self.two_hand_cooldown.check_and_reset():
                mapped = TWO_HAND_ACTIONS.get(action_2h)
                if mapped: self.execute_context_action(mapped)

            if self.modes.current == MODE_HEAD:
                gl = self.head.consume_action()
                if gl and self.head_cooldown.check_and_reset():
                    act = HEAD_ACTIONS.get(gl)
                    if act: self.execute_context_action(act.replace("_track", ""))
            
            elif self.modes.current in [MODE_GESTURE, MODE_MEDIA]:
                if self.two_hand.get_hand_count() < 2:
                    curr_g = self.gesture.get_gesture()
                    if curr_g != self.prev_gesture:
                        self.prev_gesture = curr_g
                        if curr_g:
                            act = GESTURE_ACTIONS.get(curr_g)
                            if act and self.gesture_cooldown.check_and_reset():
                                self.execute_context_action(act.replace("_track", ""))

def main():
    app = GestOneMenuBar()
    app.run()

if __name__ == "__main__":
    main()
