"""Gesture detector — landmark-based single-hand gesture recognition."""

import time
import threading
from typing import Optional

import cv2
import mediapipe as mp

from .base import BaseDetector, DetectionResult
from .camera_source import CameraSource

_TIPS = [8, 12, 16, 20]
_PIPS = [6, 10, 14, 18]
_STABILITY_FRAMES = 4


def _classify(hand_lm) -> Optional[str]:
    lm = hand_lm.landmark
    extended = [lm[t].y < lm[p].y for t, p in zip(_TIPS, _PIPS)]
    n = sum(extended)

    if n == 4:
        return "Open_Palm"
    if extended[0] and extended[1] and not extended[2] and not extended[3]:
        return "Victory"
    if n == 0:
        wrist_y = lm[0].y
        tip_y = lm[4].y
        if tip_y < wrist_y - 0.09:
            return "Thumb_Up"
        if tip_y > wrist_y + 0.06:
            return "Thumb_Down"
    return None


class GestureDetector(BaseDetector):
    """Detects single-hand gestures from a shared CameraSource."""

    def __init__(self, camera_source: CameraSource) -> None:
        self._cam = camera_source
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="gesture-loop")
        self._thread.start()
        print("[gesture_detector] started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        print("[gesture_detector] stopped")

    def get_gesture(self) -> Optional[str]:
        with self._lock:
            return self._current

    def detect(self) -> Optional[DetectionResult]:
        g = self.get_gesture()
        return DetectionResult(label=g, confidence=1.0) if g else None

    def _run(self) -> None:
        hands_mod = mp.solutions.hands
        with hands_mod.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.6,
        ) as hands:
            stable_label: Optional[str] = None
            stable_count: int = 0

            while not self._stop_event.is_set():
                frame = self._cam.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)

                raw: Optional[str] = None
                if result.multi_hand_landmarks:
                    raw = _classify(result.multi_hand_landmarks[0])

                if raw == stable_label:
                    stable_count += 1
                else:
                    stable_label = raw
                    stable_count = 1

                committed = stable_label if stable_count >= _STABILITY_FRAMES else None

                with self._lock:
                    self._current = committed
