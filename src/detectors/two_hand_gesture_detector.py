"""Two-hand gesture detector — consumes frames from shared CameraSource."""

import time
import threading
from typing import Optional, Tuple

import cv2
import mediapipe as mp

from .base import BaseDetector, DetectionResult
from .camera_source import CameraSource

_TIPS = [8, 12, 16, 20]
_PIPS = [6, 10, 14, 18]

_COMBO_TUPLES: dict[Tuple[str, str], str] = {
    ("Open_Palm", "Open_Palm"): "play_pause",
    ("Victory",   "Victory"):   "next_track",
    ("Thumb_Up",  "Thumb_Up"):  "volume_up",
}


def _classify_hand(hand_lm) -> Optional[str]:
    lm = hand_lm.landmark
    extended = [lm[t].y < lm[p].y for t, p in zip(_TIPS, _PIPS)]
    n = sum(extended)
    if n == 4:
        return "Open_Palm"
    if extended[0] and extended[1] and not extended[2] and not extended[3]:
        return "Victory"
    if n == 0:
        if lm[4].y < lm[0].y - 0.09:
            return "Thumb_Up"
    return None


def _match_combo(g0: Optional[str], g1: Optional[str]) -> Optional[str]:
    if g0 is None or g1 is None:
        return None
    return _COMBO_TUPLES.get(tuple(sorted([g0, g1])))  # type: ignore[arg-type]


class TwoHandGestureDetector(BaseDetector):
    """Detects two-hand gesture combos from a shared CameraSource."""

    def __init__(self, camera_source: CameraSource, stability_frames: int = 5) -> None:
        self._cam = camera_source
        self._stability_frames = stability_frames
        self._lock = threading.Lock()
        self._fired: Optional[str] = None
        self._current_combo: Optional[str] = None
        self._two_hands_present: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="two-hand-loop")
        self._thread.start()
        print("[two_hand] started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        print("[two_hand] stopped")

    def consume_action(self) -> Optional[str]:
        with self._lock:
            action = self._fired
            self._fired = None
            return action

    def get_combo(self) -> Optional[str]:
        with self._lock:
            return self._current_combo

    def two_hands_present(self) -> bool:
        with self._lock:
            return self._two_hands_present

    def detect(self) -> Optional[DetectionResult]:
        combo = self.get_combo()
        return DetectionResult(label=combo, confidence=1.0) if combo else None

    def _run(self) -> None:
        hands_mod = mp.solutions.hands
        with hands_mod.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.6,
        ) as hands:
            stable_combo: Optional[str] = None
            stable_count: int = 0
            last_committed: Optional[str] = None

            while not self._stop_event.is_set():
                frame = self._cam.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)

                raw_combo: Optional[str] = None
                present = False

                if result.multi_hand_landmarks and len(result.multi_hand_landmarks) == 2:
                    present = True
                    g0 = _classify_hand(result.multi_hand_landmarks[0])
                    g1 = _classify_hand(result.multi_hand_landmarks[1])
                    raw_combo = _match_combo(g0, g1)

                if raw_combo == stable_combo:
                    stable_count += 1
                else:
                    stable_combo = raw_combo
                    stable_count = 1

                committed = stable_combo if stable_count >= self._stability_frames else None

                with self._lock:
                    self._two_hands_present = present
                    self._current_combo = committed
                    if committed is not None and committed != last_committed:
                        self._fired = committed
                    last_committed = committed

