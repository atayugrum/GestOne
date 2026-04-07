"""Hand mouse tracker — palm-center cursor + size-normalized pinch.

Improvements over v1:
  - Uses palm center (wrist + index/middle knuckles) instead of raw fingertip
    for a much stabler cursor position signal.
  - Normalizes pinch distance by hand size (wrist→middle-knuckle span) so
    the threshold works across different hand sizes and distances from camera.
  - Consumes frames from shared CameraSource (no own VideoCapture).
"""

import math
import time
import threading
from typing import Optional, Tuple

import cv2
import mediapipe as mp

from .camera_source import CameraSource

# Landmarks
_INDEX_TIP  = 8
_THUMB_TIP  = 4
_WRIST      = 0
_INDEX_MCP  = 5   # index knuckle
_MIDDLE_MCP = 9   # middle knuckle


def _palm_center(lm) -> Tuple[float, float]:
    """Stable cursor anchor: average of wrist + index/middle knuckles."""
    x = (lm[_WRIST].x + lm[_INDEX_MCP].x + lm[_MIDDLE_MCP].x) / 3.0
    y = (lm[_WRIST].y + lm[_INDEX_MCP].y + lm[_MIDDLE_MCP].y) / 3.0
    return x, y


def _hand_size(lm) -> float:
    """Approximate hand size: wrist to middle knuckle distance."""
    dx = lm[_MIDDLE_MCP].x - lm[_WRIST].x
    dy = lm[_MIDDLE_MCP].y - lm[_WRIST].y
    return max(math.hypot(dx, dy), 0.01)  # avoid div/0


class HandMouseTracker:
    """Background tracker: stable cursor position + normalized pinch."""

    def __init__(self, camera_source: CameraSource) -> None:
        self._cam = camera_source
        self._lock = threading.Lock()
        self._position: Optional[Tuple[float, float]] = None
        self._pinch_norm: float = 1.0   # 0 = fully pinched, 1 = open; threshold ~0.25
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="hand-mouse-loop")
        self._thread.start()
        print("[hand_mouse_tracker] started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        print("[hand_mouse_tracker] stopped")

    def get_state(self) -> Tuple[Optional[Tuple[float, float]], float]:
        """Return (normalized_position, pinch_norm). Thread-safe."""
        with self._lock:
            return self._position, self._pinch_norm

    def _run(self) -> None:
        hands_mod = mp.solutions.hands
        with hands_mod.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.6,
        ) as hands:
            while not self._stop_event.is_set():
                frame = self._cam.get_frame_flipped()
                if frame is None:
                    time.sleep(0.01)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)

                if result.multi_hand_landmarks:
                    lm = result.multi_hand_landmarks[0].landmark
                    pos = _palm_center(lm)
                    size = _hand_size(lm)
                    raw_pinch = math.hypot(
                        lm[_INDEX_TIP].x - lm[_THUMB_TIP].x,
                        lm[_INDEX_TIP].y - lm[_THUMB_TIP].y,
                    )
                    pinch_norm = raw_pinch / size   # ~0.2 pinched, ~0.6+ open
                    with self._lock:
                        self._position = pos
                        self._pinch_norm = pinch_norm
                else:
                    with self._lock:
                        self._position = None
