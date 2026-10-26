"""Agent Interface Layer for GestOne.

This module exposes a small JSON/function-call API for AI agents without
touching the gesture recognition pipeline. It reuses the same OS control
adapters that gestures eventually call.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, TYPE_CHECKING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

if TYPE_CHECKING:
    from src.controls.media_controller import MediaController
    from src.controls.mouse_controller import MouseController


CommandHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


COMMANDS: Dict[str, str] = {
    "media.play_pause": "Toggle play/pause in Music, Spotify, or Podcasts.",
    "media.next": "Skip to the next track.",
    "media.previous": "Skip to the previous track.",
    "media.volume_up": "Increase system output volume by 10.",
    "media.volume_down": "Decrease system output volume by 10.",
    "window.fullscreen": "Toggle fullscreen for the active window.",
    "window.minimize": "Minimize the active window.",
    "window.minimize_all": "Minimize all windows for the active app.",
    "window.mission_control": "Open Mission Control.",
    "browser.forward": "Navigate forward in Safari or Chrome.",
    "browser.back": "Navigate back in Safari or Chrome.",
    "browser.next_tab": "Switch to the next browser tab.",
    "browser.previous_tab": "Switch to the previous browser tab.",
    "presentation.next": "Advance one slide in Keynote or PowerPoint.",
    "presentation.previous": "Go back one slide in Keynote or PowerPoint.",
    "mouse.move": "Move the pointer to x/y screen coordinates.",
    "mouse.click": "Click the pointer, default left button.",
    "mouse.double_click": "Double-click the pointer.",
    "mouse.drag_start": "Start a left-button drag.",
    "mouse.drag_stop": "Stop a left-button drag.",
    "mouse.scroll": "Scroll by dy line ticks.",
    "system.sleep_display": "Lock/suspend the current macOS session.",
    "agent.wait": "Wait for a number of seconds inside a multi-step task.",
}


HUMAN_INTENT_MAP: List[Dict[str, str]] = [
    {
        "intent": "Pause or resume music",
        "gesture_function": "Open_Palm -> play_pause",
        "system_action": "media.play_pause",
    },
    {
        "intent": "Increase volume",
        "gesture_function": "Thumb_Up -> volume_up",
        "system_action": "media.volume_up",
    },
    {
        "intent": "Decrease volume",
        "gesture_function": "Thumb_Down -> volume_down",
        "system_action": "media.volume_down",
    },
    {
        "intent": "Next track or contextual next",
        "gesture_function": "Victory / Turn_Right -> next_track",
        "system_action": "media.next, browser.forward, or presentation.next",
    },
    {
        "intent": "Previous track or contextual previous",
        "gesture_function": "Turn_Left -> prev_track",
        "system_action": "media.previous, browser.back, or presentation.previous",
    },
    {
        "intent": "Fullscreen active window",
        "gesture_function": "Two open palms far apart -> fullscreen",
        "system_action": "window.fullscreen",
    },
    {
        "intent": "Minimize active window",
        "gesture_function": "Two open palms close together -> minimize",
        "system_action": "window.minimize",
    },
    {
        "intent": "Open Mission Control",
        "gesture_function": "Both fists -> mission_control",
        "system_action": "window.mission_control",
    },
    {
        "intent": "Move/click/drag/scroll pointer",
        "gesture_function": "Palm centroid, pinch, pinch hold, V-sign scroll",
        "system_action": "mouse.move, mouse.click, mouse.drag_start/stop, mouse.scroll",
    },
]


@dataclass
class CommandResult:
    command: str
    ok: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "command": self.command,
            "ok": self.ok,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result


class AgentController:
    """JSON-callable wrapper around GestOne's existing control layer."""

    def __init__(self) -> None:
        self._media: Optional["MediaController"] = None
        self._mouse: Optional["MouseController"] = None
        self._lock = threading.Lock()
        self._handlers: Dict[str, CommandHandler] = {
            "media.play_pause": self._media_play_pause,
            "media.next": self._media_next,
            "media.previous": self._media_previous,
            "media.volume_up": self._media_volume_up,
            "media.volume_down": self._media_volume_down,
            "window.fullscreen": self._window_fullscreen,
            "window.minimize": self._window_minimize,
            "window.minimize_all": self._window_minimize_all,
            "window.mission_control": self._window_mission_control,
            "browser.forward": self._browser_forward,
            "browser.back": self._browser_back,
            "browser.next_tab": self._browser_next_tab,
            "browser.previous_tab": self._browser_previous_tab,
            "presentation.next": self._presentation_next,
            "presentation.previous": self._presentation_previous,
            "mouse.move": self._mouse_move,
            "mouse.click": self._mouse_click,
            "mouse.double_click": self._mouse_double_click,
            "mouse.drag_start": self._mouse_drag_start,
            "mouse.drag_stop": self._mouse_drag_stop,
            "mouse.scroll": self._mouse_scroll,
            "system.sleep_display": self._system_sleep_display,
            "agent.wait": self._agent_wait,
        }

    @property
    def media(self) -> "MediaController":
        if self._media is None:
            from src.controls.media_controller import MediaController

            self._media = MediaController()
        return self._media

    @property
    def mouse(self) -> "MouseController":
        if self._mouse is None:
            from src.controls.mouse_controller import MouseController

            self._mouse = MouseController()
        return self._mouse

    def list_commands(self) -> Dict[str, str]:
        return dict(COMMANDS)

    def intent_map(self) -> List[Dict[str, str]]:
        return list(HUMAN_INTENT_MAP)

    def execute(self, command: str, **params: Any) -> Dict[str, Any]:
        """Execute one standardized command.

        Example:
            controller.execute("window.minimize")
            controller.execute("mouse.move", x=400, y=300)
        """
        handler = self._handlers.get(command)
        if handler is None:
            return CommandResult(
                command=command,
                ok=False,
                message=f"Unknown command: {command}",
                data={"available_commands": sorted(self._handlers)},
            ).to_dict()

        with self._lock:
            try:
                data = handler(params) or {}
                return CommandResult(command=command, ok=True, data=data).to_dict()
            except Exception as exc:
                return CommandResult(command=command, ok=False, message=str(exc)).to_dict()

    def execute_json(self, payload: str | Dict[str, Any]) -> Dict[str, Any]:
        """Execute a JSON command or multi-step task.

        Accepted shapes:
            {"command": "media.play_pause"}
            {"command": "mouse.move", "params": {"x": 400, "y": 300}}
            {"commands": [{"command": "window.minimize"}, {"command": "media.play_pause"}]}
        """
        request = json.loads(payload) if isinstance(payload, str) else payload
        if "commands" in request:
            results = self.execute_many(request["commands"])
            return {"ok": all(item.get("ok") for item in results), "results": results}
        if "intent" in request:
            return self.execute_intent(str(request["intent"]), dry_run=bool(request.get("dry_run", False)))

        command = request.get("command")
        if not command:
            return {"ok": False, "message": "Missing 'command' field."}
        params = request.get("params", {})
        if not isinstance(params, dict):
            return {"ok": False, "message": "'params' must be an object."}
        return self.execute(command, **params)

    def execute_intent(self, text: str, dry_run: bool = False) -> Dict[str, Any]:
        """Resolve a natural-language request into commands and execute them.

        This is intentionally deterministic. An LLM can either call this with a
        user phrase or skip it and call execute_json() with explicit commands.
        """
        commands = self.plan_intent(text)
        if not commands:
            return {
                "ok": False,
                "message": f"Could not map intent to a GestOne command: {text}",
                "available_commands": sorted(self._handlers),
            }
        if dry_run:
            return {
                "ok": True,
                "intent": text,
                "dry_run": True,
                "planned_commands": commands,
            }
        results = self.execute_many(commands)
        return {
            "ok": all(item.get("ok") for item in results),
            "intent": text,
            "planned_commands": commands,
            "results": results,
        }

    def plan_intent(self, text: str) -> List[Dict[str, Any]]:
        """Translate natural language into the standardized command schema."""
        normalized = _normalize(text)
        chunks = [chunk.strip() for chunk in re.split(r"\b(?:and then|then|and|,)\b", normalized) if chunk.strip()]
        if not chunks:
            chunks = [normalized]

        commands: List[Dict[str, Any]] = []
        for chunk in chunks:
            planned = self._plan_single_intent(chunk)
            if planned:
                commands.extend(planned)
        return commands

    def execute_many(self, commands: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute commands in order and stop on the first failure."""
        results: List[Dict[str, Any]] = []
        for item in commands:
            command = item.get("command")
            params = item.get("params", {})
            if not command:
                result = {"command": "", "ok": False, "message": "Missing command."}
            elif not isinstance(params, dict):
                result = {"command": command, "ok": False, "message": "params must be an object."}
            else:
                result = self.execute(command, **params)
            results.append(result)
            if not result.get("ok"):
                break
        return results

    def execute_gesture_action(self, action: str) -> Dict[str, Any]:
        """Compatibility adapter for existing GestOne gesture action names."""
        mapping = {
            "play_pause": "media.play_pause",
            "next": "media.next",
            "next_track": "media.next",
            "prev": "media.previous",
            "prev_track": "media.previous",
            "volume_up": "media.volume_up",
            "volume_down": "media.volume_down",
            "fullscreen": "window.fullscreen",
            "minimize": "window.minimize",
            "mission_control": "window.mission_control",
        }
        command = mapping.get(action)
        if command is None:
            return CommandResult(action, False, f"Unknown gesture action: {action}").to_dict()
        return self.execute(command)

    def _run_osascript(self, script: str) -> None:
        subprocess.run(["osascript", "-e", script], check=True, timeout=3, capture_output=True)

    def _hotkey(self, *keys: str) -> Dict[str, Any]:
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.hotkey(*keys)
        return {"keys": list(keys)}

    def _press(self, key: str) -> Dict[str, Any]:
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.press(key)
        return {"key": key}

    def _media_play_pause(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.media.play_pause()
        return {}

    def _media_next(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.media.next_track()
        return {}

    def _media_previous(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.media.prev_track()
        return {}

    def _media_volume_up(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.media.volume_up()
        return {}

    def _media_volume_down(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.media.volume_down()
        return {}

    def _window_fullscreen(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("ctrl", "cmd", "f")

    def _window_minimize(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("cmd", "m")

    def _window_minimize_all(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("cmd", "option", "m")

    def _window_mission_control(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("ctrl", "up")

    def _browser_forward(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("cmd", "]")

    def _browser_back(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("cmd", "[")

    def _browser_next_tab(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("ctrl", "tab")

    def _browser_previous_tab(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._hotkey("ctrl", "shift", "tab")

    def _presentation_next(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._press("right")

    def _presentation_previous(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._press("left")

    def _mouse_move(self, params: Dict[str, Any]) -> Dict[str, Any]:
        x = float(params["x"])
        y = float(params["y"])
        self.mouse.move_to(x, y)
        return {"x": x, "y": y}

    def _mouse_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        button = str(params.get("button", "left"))
        self.mouse.click(button=button)
        return {"button": button}

    def _mouse_double_click(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.mouse.double_click()
        return {}

    def _mouse_drag_start(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.mouse.drag_start()
        return {}

    def _mouse_drag_stop(self, _: Dict[str, Any]) -> Dict[str, Any]:
        self.mouse.drag_stop()
        return {}

    def _mouse_scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        dy = int(params["dy"])
        self.mouse.scroll(dy)
        return {"dy": dy}

    def _system_sleep_display(self, _: Dict[str, Any]) -> Dict[str, Any]:
        os.system("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
        return {}

    def _agent_wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        seconds = float(params.get("seconds", 0.0))
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        time.sleep(seconds)
        return {"seconds": seconds}

    def _plan_single_intent(self, text: str) -> List[Dict[str, Any]]:
        if _has_any(text, "volume up", "turn up", "increase volume", "raise volume", "ses ac"):
            return [{"command": "media.volume_up"}]
        if _has_any(text, "volume down", "turn down", "decrease volume", "lower volume", "ses kis"):
            return [{"command": "media.volume_down"}]
        if _has_any(text, "pause music", "play music", "resume music", "play pause", "toggle music", "pause the music"):
            return [{"command": "media.play_pause"}]
        if _has_any(text, "next track", "next song", "skip song", "skip track"):
            return [{"command": "media.next"}]
        if _has_any(text, "previous track", "previous song", "last song", "go back a song"):
            return [{"command": "media.previous"}]
        if _has_any(text, "next tab", "switch tab", "switch to next tab", "tab switch"):
            return [{"command": "browser.next_tab"}]
        if _has_any(text, "previous tab", "last tab", "switch to previous tab"):
            return [{"command": "browser.previous_tab"}]
        if _has_any(text, "browser forward", "go forward"):
            return [{"command": "browser.forward"}]
        if _has_any(text, "browser back", "go back"):
            return [{"command": "browser.back"}]
        if _has_any(text, "minimize all", "hide all windows", "minimise all"):
            return [{"command": "window.minimize_all"}]
        if _has_any(text, "minimize", "minimise"):
            return [{"command": "window.minimize"}]
        if _has_any(text, "fullscreen", "full screen", "maximize", "maximise"):
            return [{"command": "window.fullscreen"}]
        if _has_any(text, "mission control", "show windows"):
            return [{"command": "window.mission_control"}]
        if _has_any(text, "lock screen", "sleep display"):
            return [{"command": "system.sleep_display"}]
        return []


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("ı", "i").split())


def _has_any(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def main() -> int:
    if len(sys.argv) == 1:
        print(json.dumps({"commands": COMMANDS, "intent_map": HUMAN_INTENT_MAP}, indent=2))
        return 0

    controller = AgentController()
    payload = " ".join(sys.argv[1:])
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        result = controller.execute_intent(payload)
    else:
        result = controller.execute_json(decoded)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
