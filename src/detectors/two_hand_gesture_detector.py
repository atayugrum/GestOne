"""Two Hand Gesture Detector — Minority Report style Window Management."""

import math
import time
import threading
from typing import Optional
import cv2
import mediapipe as mp
from .camera_source import CameraSource

def _is_open_palm(hand_lm) -> bool:
    tips = [8, 12, 16, 20]
    mcps = [5, 9, 13, 17]
    return all(hand_lm[t].y < hand_lm[m].y for t, m in zip(tips, mcps))

def _is_fist(hand_lm) -> bool:
    tips = [8, 12, 16, 20]
    mcps = [5, 9, 13, 17]
    return all(hand_lm[t].y > hand_lm[m].y for t, m in zip(tips, mcps))

class TwoHandGestureDetector:
    def __init__(self, camera_source: CameraSource, stability_frames: int = 5) -> None:
        self._cam = camera_source
        self._lock = threading.Lock()
        self._action: Optional[str] = None
        self._hand_count: int = 0  
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stability_frames = stability_frames

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="two-hand-loop")
        self._thread.start()

    def consume_action(self) -> Optional[str]:
        with self._lock:
            act = self._action
            self._action = None
            return act

    def get_combo(self) -> Optional[str]:
        with self._lock:
            return self._action

    def get_hand_count(self) -> int:
        with self._lock:
            return self._hand_count

    def _run(self) -> None:
        with mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=2,
            min_detection_confidence=0.7, min_tracking_confidence=0.7
        ) as hands:
            stable_action = None
            count = 0
            
            while not self._stop_event.is_set():
                frame = self._cam.get_frame_flipped()
                if frame is None:
                    time.sleep(0.01)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)
                
                raw_action = None
                current_hands = 0
                
                if result.multi_hand_landmarks:
                    current_hands = len(result.multi_hand_landmarks)
                    
                    if current_hands == 2:
                        lm1 = result.multi_hand_landmarks[0].landmark
                        lm2 = result.multi_hand_landmarks[1].landmark
                        
                        dist_x = abs(lm1[0].x - lm2[0].x)
                        
                        if _is_fist(lm1) and _is_fist(lm2):
                            raw_action = "Mission_Control"
                        elif _is_open_palm(lm1) and _is_open_palm(lm2):
                            if dist_x > 0.40:  
                                raw_action = "Expand"
                            # Mesafe anatomik olarak esnetildi (0.18 -> 0.25)
                            elif dist_x < 0.25: 
                                raw_action = "Contract"

                with self._lock:
                    self._hand_count = current_hands

                if raw_action == stable_action and raw_action is not None:
                    count += 1
                else:
                    stable_action = raw_action
                    count = 1

                if count >= self._stability_frames and stable_action:
                    with self._lock:
                        self._action = stable_action
                    count = 0  

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread: self._thread.join(timeout=3)