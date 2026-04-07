"""GestOne — macOS multimodal desktop controller.

Entry point. Reliability refactor: single shared camera pipeline.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pyautogui

from config import default_config, MODE_GESTURE, MODE_MEDIA, MODE_MOUSE, MODE_HEAD, MODE_VOICE, ALL_MODES
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
from src.ui.dashboard import Dashboard
from src.utils.common import Cooldown
from src.utils.config_persistence import load_overrides, apply_overrides, save_overrides, EDITABLE_FIELDS

GESTURE_ACTIONS = {
    "Open_Palm":  "play_pause",
    "Thumb_Up":   "volume_up",
    "Thumb_Down": "volume_down",
    "Victory":    "next_track",
}

# Nod_Down removed: unreliable. Turn_Left/Right only.
HEAD_ACTIONS = {
    "Turn_Right": "next_track",
    "Turn_Left":  "prev_track",
}

DASHBOARD_MODES = [MODE_GESTURE, MODE_MOUSE, MODE_MEDIA, MODE_HEAD, MODE_VOICE]


def build_dispatcher(dispatcher: Dispatcher, media: MediaController, modes: ModeManager) -> None:
    dispatcher.register("play_pause",   media.play_pause)
    dispatcher.register("next_track",   media.next_track)
    dispatcher.register("prev_track",   media.prev_track)
    dispatcher.register("volume_up",    media.volume_up)
    dispatcher.register("volume_down",  media.volume_down)
    dispatcher.register("mode_gesture", lambda: modes.toggle(MODE_GESTURE))
    dispatcher.register("mode_media",   lambda: modes.toggle(MODE_MEDIA))
    dispatcher.register("mode_mouse",   lambda: modes.toggle(MODE_MOUSE))
    dispatcher.register("mode_head",    lambda: modes.toggle(MODE_HEAD))
    dispatcher.register("mode_voice",   lambda: modes.toggle(MODE_VOICE))


def main() -> None:
    config = default_config()
    overrides = load_overrides()
    apply_overrides(config, overrides)

    modes    = ModeManager(config.active_mode)
    dispatch = Dispatcher()
    media    = MediaController()
    mouse    = MouseController()

    build_dispatcher(dispatch, media, modes)

    # ── Single shared camera source ──────────────────────────────────────────
    camera = CameraSource(
        camera_index=config.camera_index,
        width=config.camera_width,
        height=config.camera_height,
    )
    ok = camera.start()
    if not ok:
        print("[gestone] ERROR: camera failed to open — exiting")
        return

    # ── All detectors share the single camera ────────────────────────────────
    gesture    = GestureDetector(camera_source=camera)
    hand_mouse = HandMouseTracker(camera_source=camera)
    two_hand   = TwoHandGestureDetector(
                     camera_source=camera,
                     stability_frames=config.two_hand_stability_frames,
                 )
    head       = HeadTracker(
                     camera_source=camera,
                     yaw_threshold=config.head_yaw_threshold,
                     pitch_threshold=config.head_pitch_threshold,
                     neutral_zone=config.head_neutral_zone,
                     stability_frames=config.head_stability_frames,
                     smooth_alpha=config.head_smooth_alpha,
                 )
    voice      = VoiceController()

    gesture.start()
    hand_mouse.start()
    two_hand.start()
    head.start()
    voice.start()

    print(f"[gestone] started | mode={modes.current} | actions={dispatch.registered_actions()}")

    gesture_cooldown  = Cooldown(config.cooldown_sec)
    two_hand_cooldown = Cooldown(config.two_hand_cooldown_sec)
    head_cooldown     = Cooldown(config.head_cooldown_sec)
    click_cooldown    = Cooldown(config.mouse_click_cooldown_sec)
    voice_cooldown    = Cooldown(1.5)

    screen_w, screen_h = pyautogui.size()
    smooth_x: float = screen_w / 2
    smooth_y: float = screen_h / 2
    prev_gesture: str | None = None

    # Pinch hysteresis: 'open' → ready to click; 'wait_release' → must re-open first
    pinch_state: str = "open"

    def on_tick() -> None:
        nonlocal prev_gesture, smooth_x, smooth_y, pinch_state

        # ── Voice commands (always active when voice mode is on) ─────────────
        voice_action = voice.consume_action()
        if voice_action and voice_cooldown.check_and_reset():
            print(f"[gestone] voice → {voice_action}")
            dispatch.dispatch(voice_action)
            if voice_action:
                return  # don't double-dispatch this tick

        current_mode = modes.current

        # ── Two-hand gestures ────────────────────────────────────────────────
        if current_mode != MODE_MOUSE:
            action = two_hand.consume_action()
            if action and two_hand_cooldown.check_and_reset():
                print(f"[gestone] two-hand → {action}")
                dispatch.dispatch(action)

        # ── Head mode ────────────────────────────────────────────────────────
        if current_mode == MODE_HEAD:
            gesture_label = head.consume_action()
            if gesture_label and head_cooldown.check_and_reset():
                action = HEAD_ACTIONS.get(gesture_label)
                if action:
                    print(f"[gestone] head={gesture_label} → {action}")
                    dispatch.dispatch(action)
            return

        # ── Mouse mode ───────────────────────────────────────────────────────
        if current_mode == MODE_MOUSE:
            pos, pinch_norm = hand_mouse.get_state()
            if pos is not None:
                nx, ny = pos
                target_x = nx * screen_w
                target_y = ny * screen_h
                alpha = config.mouse_smoothing_alpha
                new_x = alpha * target_x + (1 - alpha) * smooth_x
                new_y = alpha * target_y + (1 - alpha) * smooth_y
                dx = abs(new_x - smooth_x)
                dy = abs(new_y - smooth_y)
                if dx > config.mouse_deadzone_px or dy > config.mouse_deadzone_px:
                    smooth_x = new_x
                    smooth_y = new_y
                sx = max(0, min(screen_w - 1, smooth_x))
                sy = max(0, min(screen_h - 1, smooth_y))
                mouse.move_to(sx, sy)

                # Pinch hysteresis: require open → pinch → re-open cycle
                if pinch_state == "open":
                    if pinch_norm < config.mouse_pinch_threshold and click_cooldown.check_and_reset():
                        print(f"[gestone] pinch click at ({sx:.0f}, {sy:.0f})")
                        mouse.click()
                        pinch_state = "wait_release"
                elif pinch_state == "wait_release":
                    if pinch_norm > config.mouse_pinch_release_threshold:
                        pinch_state = "open"
            else:
                pinch_state = "open"  # reset on hand loss
            return

        # ── Gesture / media mode ─────────────────────────────────────────────
        current_gesture = gesture.get_gesture()
        if current_gesture != prev_gesture:
            prev_gesture = current_gesture
            if current_gesture:
                action = GESTURE_ACTIONS.get(current_gesture)
                if action and gesture_cooldown.check_and_reset():
                    print(f"[gestone] gesture={current_gesture} → {action}")
                    dispatch.dispatch(action)

    def on_close() -> None:
        print("[gestone] shutting down…")
        gesture.stop()
        hand_mouse.stop()
        two_hand.stop()
        head.stop()
        voice.stop()
        camera.stop()

    def get_status() -> str | None:
        if modes.current == MODE_MOUSE:
            pos, pinch = hand_mouse.get_state()
            if pos:
                return f"cursor ({smooth_x:.0f}, {smooth_y:.0f})  pinch={pinch:.3f}"
            return "mouse mode — no hand"
        if modes.current == MODE_HEAD:
            label = head.get_head_gesture()
            return f"head: {label}" if label else "head: neutral"
        combo = two_hand.get_combo()
        if combo:
            return f"[2H] {combo}"
        return gesture.get_gesture()

    def _det_alive(det) -> bool:
        t = getattr(det, "_thread", None)
        return bool(t and t.is_alive())

    def get_detector_status() -> dict:
        return {
            "gesture":  _det_alive(gesture),
            "mouse":    _det_alive(hand_mouse),
            "two_hand": _det_alive(two_hand),
            "head":     _det_alive(head),
            "voice":    _det_alive(voice),
        }

    def get_settings() -> dict:
        return {k: getattr(config, k) for k in EDITABLE_FIELDS if hasattr(config, k)}

    def on_save_settings(values: dict) -> None:
        for key, val in values.items():
            if hasattr(config, key):
                setattr(config, key, type(getattr(config, key))(val))
        gesture_cooldown.seconds  = config.cooldown_sec
        two_hand_cooldown.seconds = config.two_hand_cooldown_sec
        head_cooldown.seconds     = config.head_cooldown_sec
        click_cooldown.seconds    = config.mouse_click_cooldown_sec
        save_overrides(config)
        print("[gestone] settings saved")

    def on_mode_switch(mode: str) -> None:
        modes.toggle(mode)

    dashboard = Dashboard(
        get_mode=lambda: modes.current,
        on_close=on_close,
        modes=DASHBOARD_MODES,
        on_mode_switch=on_mode_switch,
        get_gesture=get_status,
        on_tick=on_tick,
        get_detector_status=get_detector_status,
        get_settings=get_settings,
        on_save_settings=on_save_settings,
    )
    dashboard.start()


if __name__ == "__main__":
    main()
