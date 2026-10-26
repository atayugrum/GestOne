"""Routes gesture/voice/head actions to system commands."""

import os
import subprocess
import threading
import time
import pyautogui

from src.core.dispatcher import Dispatcher
from src.core.modes import ModeManager
from src.controls.media_controller import MediaController
from src.controls.mouse_controller import MouseController


def get_active_app() -> str:
    """Returns cached frontmost app; refreshes in background if stale."""
    global _active_app_cache, _active_app_ts, _active_app_lock

    now = time.time()
    with _active_app_lock:
        stale = (now - _active_app_ts) > 2.0
        cached = _active_app_cache

    if stale:
        def refresh():
            try:
                cmd = 'tell application "System Events" to get name of first application process whose frontmost is true'
                res = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True, timeout=1.0)
                global _active_app_cache, _active_app_ts
                with _active_app_lock:
                    _active_app_cache = res.stdout.strip()
                    _active_app_ts = time.time()
            except Exception:
                pass

        threading.Thread(target=refresh, daemon=True).start()

    return cached


# Global cache for active app
_active_app_cache = ""
_active_app_ts = 0.0
_active_app_lock = threading.Lock()


class ActionRouter:
    """Routes actions from gestures/voice/head to system commands."""

    def __init__(
        self,
        modes: ModeManager,
        media: MediaController,
        mouse_ctrl: MouseController,
    ):
        self.modes = modes
        self.media = media
        self.mouse_ctrl = mouse_ctrl
        self.dispatcher = Dispatcher()
        self._setup_handlers()

    def _setup_handlers(self):
        """Register action handlers in dispatcher."""
        # Media actions
        self.dispatcher.register("play_pause", self._action_play_pause)
        self.dispatcher.register("next_track", self._action_next_track)
        self.dispatcher.register("prev_track", self._action_prev_track)
        self.dispatcher.register("volume_up", self._action_volume_up)
        self.dispatcher.register("volume_down", self._action_volume_down)

        # Window actions
        self.dispatcher.register("fullscreen", self._action_fullscreen)
        self.dispatcher.register("minimize", self._action_minimize)
        self.dispatcher.register("mission_control", self._action_mission_control)

    def _action_play_pause(self):
        """Play/pause media or presentation."""
        app = get_active_app()
        if app in ["Keynote", "Microsoft PowerPoint"]:
            pyautogui.hotkey("cmd", "return")
        else:
            self.media.play_pause()

    def _action_next_track(self):
        """Next track/slide."""
        app = get_active_app()
        if app in ["Safari", "Google Chrome"]:
            pyautogui.hotkey("cmd", "]")
        elif app in ["Keynote", "Microsoft PowerPoint"]:
            pyautogui.press("right")
        else:
            self.media.next_track()

    def _action_prev_track(self):
        """Previous track/slide."""
        app = get_active_app()
        if app in ["Safari", "Google Chrome"]:
            pyautogui.hotkey("cmd", "[")
        elif app in ["Keynote", "Microsoft PowerPoint"]:
            pyautogui.press("left")
        else:
            self.media.prev_track()

    def _action_volume_up(self):
        """Increase volume."""
        os.system("osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'")

    def _action_volume_down(self):
        """Decrease volume."""
        os.system("osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'")

    def _action_fullscreen(self):
        """Toggle fullscreen."""
        pyautogui.hotkey("ctrl", "cmd", "f")

    def _action_minimize(self):
        """Minimize window."""
        pyautogui.hotkey("cmd", "m")

    def _action_mission_control(self):
        """Open Mission Control."""
        pyautogui.hotkey("ctrl", "up")

    def execute(self, action_name: str) -> bool:
        """Execute a registered action by name. Returns True if found."""
        return self.dispatcher.dispatch(action_name)

    def execute_context_action(self, action_type: str) -> bool:
        """Execute an action based on context (active app, mode, etc.)."""
        return self.execute(action_type)
