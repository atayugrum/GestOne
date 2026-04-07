"""Voice controller — Phase 4: speech recognition command detection.

Uses speech_recognition (Google backend) with graceful fallback if unavailable.
Recognized commands route through the shared dispatcher via consume_action().
"""

import threading
import time
from typing import Optional

try:
    import speech_recognition as sr
    _SR_AVAILABLE = True
except ImportError:
    _SR_AVAILABLE = False
    print("[voice_controller] speech_recognition not installed — voice disabled")

from .base import BaseDetector, DetectionResult

# Ordered longest-first so "volume up" matches before "volume"
_COMMAND_MAP = {
    "volume up":    "volume_up",
    "volume down":  "volume_down",
    "mouse mode":   "mode_mouse",
    "gesture mode": "mode_gesture",
    "head mode":    "mode_head",
    "previous":     "prev_track",
    "next":         "next_track",
    "pause":        "play_pause",
    "play":         "play_pause",
    "back":         "prev_track",
    "mouse":        "mode_mouse",
    "gesture":      "mode_gesture",
    "head":         "mode_head",
}

_VOICE_COOLDOWN_SEC = 1.5


class VoiceController(BaseDetector):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_action_time: float = 0.0

    def start(self) -> None:
        if not _SR_AVAILABLE:
            print("[voice_controller] unavailable — skipping")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="voice-loop")
        self._thread.start()
        print("[voice_controller] started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=4)
        print("[voice_controller] stopped")

    def detect(self) -> Optional[DetectionResult]:
        action = self.consume_action()
        if action:
            return DetectionResult(label=action, confidence=1.0)
        return None

    def consume_action(self) -> Optional[str]:
        """Return and clear the pending recognized action, or None."""
        with self._lock:
            action = self._pending
            self._pending = None
            return action

    def _match_command(self, text: str) -> Optional[str]:
        for phrase, action in _COMMAND_MAP.items():
            if phrase in text:
                return action
        return None

    def _run(self) -> None:
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.5

        try:
            mic = sr.Microphone()
        except Exception as exc:
            print(f"[voice_controller] microphone unavailable: {exc}")
            return

        print("[voice_controller] calibrating ambient noise (1s)…")
        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
        except Exception as exc:
            print(f"[voice_controller] calibration failed: {exc}")
            return

        print("[voice_controller] listening")

        while not self._stop_event.is_set():
            try:
                with mic as source:
                    audio = recognizer.listen(source, timeout=1.0, phrase_time_limit=3.0)

                text = recognizer.recognize_google(audio).lower()
                print(f"[voice_controller] heard: {text!r}")

                now = time.monotonic()
                if now - self._last_action_time < _VOICE_COOLDOWN_SEC:
                    continue

                action = self._match_command(text)
                if action:
                    self._last_action_time = now
                    with self._lock:
                        self._pending = action
                    print(f"[voice_controller] → {action}")

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as exc:
                print(f"[voice_controller] recognition error: {exc}")
                time.sleep(2.0)
            except Exception as exc:
                print(f"[voice_controller] error: {exc}")
                time.sleep(1.0)
