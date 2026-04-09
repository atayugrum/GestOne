"""Gesture detector — Robust rotation-invariant recognition."""

import time
import threading
import math
from typing import Optional
import mediapipe as mp
from .base import BaseDetector, DetectionResult
from .camera_source import CameraSource

_STABILITY_FRAMES = 12  # Titremeleri engellemek için 4'ten 12'ye çıkarıldı

def _distance(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)

def _classify(hand_lm) -> Optional[str]:
    lm = hand_lm.landmark
    wrist = lm[0]
    
    tips = [8, 12, 16, 20]
    mcps = [5, 9, 13, 17]
    
    extended = []
    # Rotasyondan bağımsız mantık: Bir parmağın ucu, ekleminden daha uzaktaysa açıktır.
    for t, m in zip(tips, mcps):
        extended.append(_distance(lm[t], wrist) > _distance(lm[m], wrist) * 1.3)
        
    n_ext = sum(extended)
    
    # Baş parmak uzantısı için serçe parmak tabanını (17) uzak referans alıyoruz
    thumb_tip = lm[4]
    thumb_base = lm[17] 
    thumb_ext = _distance(thumb_tip, thumb_base) > _distance(lm[2], thumb_base) * 1.1

    if n_ext == 4 and thumb_ext:
        return "Open_Palm"
    if extended[0] and extended[1] and not extended[2] and not extended[3]:
        return "Victory"
    if n_ext == 0 and thumb_ext:
        # Baş parmak yönü için hafif Y ekseni kontrolü yeterli
        if thumb_tip.y < lm[5].y - 0.05:
            return "Thumb_Up"
        if thumb_tip.y > lm[5].y + 0.05:
            return "Thumb_Down"
            
    return None

class GestureDetector(BaseDetector):
    def __init__(self, camera_source: CameraSource) -> None:
        self._cam = camera_source
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._raw: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="gesture-loop")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def get_gesture(self) -> Optional[str]:
        with self._lock:
            return self._current

    def get_raw_gesture(self) -> Optional[str]:
        """Dashboard'da 'Algılanıyor...' yazısını göstermek için anlık durumu döner."""
        with self._lock:
            return self._raw

    def detect(self) -> Optional[DetectionResult]:
        g = self.get_gesture()
        return DetectionResult(label=g, confidence=1.0) if g else None

    def _run(self) -> None:
        hands_mod = mp.solutions.hands
        with hands_mod.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=1,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.85,
        ) as hands:
            stable_label: Optional[str] = None
            stable_count: int = 0

            while not self._stop_event.is_set():
                rgb = self._cam.get_rgb()
                if rgb is None:
                    time.sleep(0.01)
                    continue

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
                    self._raw = raw
                    self._current = committed