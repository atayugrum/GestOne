"""Head Tracker — Face Mesh 2D Ratio + Posture & Presence Detection."""

import time
import threading
from collections import deque
import mediapipe as mp
import numpy as np
from typing import Optional
from .camera_source import CameraSource

class HeadTracker:
    def __init__(self, camera_source: CameraSource, yaw_threshold: float = 1.4,
                 stability_frames: int = 4, deadzone: float = 0.12, ema_alpha: float = 0.25, **kwargs):
        self._cam = camera_source
        self._lock = threading.Lock()

        # Orijinal baş hareketleri
        self._action: Optional[str] = None
        self._raw: Optional[str] = None

        # Yeni: Varlık ve Sağlık
        self._is_present: bool = False
        self._posture_warning: Optional[str] = None

        self._too_close_since: Optional[float] = None
        self._slouch_since: Optional[float] = None
        _TOO_CLOSE_AREA = 0.22   # face bbox > 22% of frame area → too close
        _TOO_CLOSE_SEC  = 5.0    # must persist for 5 s before firing
        _SLOUCH_SEC = 4.0        # poor posture must persist briefly before warning
        self._TOO_CLOSE_AREA = _TOO_CLOSE_AREA
        self._TOO_CLOSE_SEC  = _TOO_CLOSE_SEC
        self._SLOUCH_SEC = _SLOUCH_SEC

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stability_frames = stability_frames
        self._yaw_thresh = yaw_threshold
        # Deadzone: ratio must exceed (1.0 + deadzone) before being considered a turn
        self._deadzone = deadzone
        # EMA for ratio smoothing — removes frame-to-frame jitter
        self._ema_alpha = ema_alpha
        self._smooth_ratio: float = 1.0
        self._ratio_ma: deque = deque(maxlen=4)  # Stage 1: moving average

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="head-loop")
        self._thread.start()

    def consume_action(self) -> Optional[str]:
        with self._lock:
            act = self._action
            self._action = None
            return act
            
    def get_head_gesture(self) -> Optional[str]:
        with self._lock:
            return self._raw

    # --- YENİ EKLENEN METOTLAR ---
    def is_present(self) -> bool:
        """Kamera kadrajında bir yüz olup olmadığını döner."""
        with self._lock:
            return self._is_present

    def get_posture_warning(self) -> Optional[str]:
        """Varsa duruş bozukluğu uyarısını döner ve sıfırlar."""
        with self._lock:
            w = self._posture_warning
            self._posture_warning = None
            return w

    def _run(self) -> None:
        mp_face_mesh = mp.solutions.face_mesh
        with mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.85,
        ) as face_mesh:
            stable_action = None
            count = 0

            while not self._stop_event.is_set():
                rgb = self._cam.get_rgb_flipped()
                if rgb is None:
                    time.sleep(0.01)
                    continue

                results = face_mesh.process(rgb)

                raw_action = None
                is_pres = False
                posture_warn = None

                if results.multi_face_landmarks:
                    is_pres = True
                    lm = results.multi_face_landmarks[0].landmark
                    
                    # Yüz hatları
                    nose = lm[1]
                    left_cheek = lm[234]
                    right_cheek = lm[454]
                    forehead = lm[10]
                    chin = lm[152]
                    
                    # ── 1. ERGONOMİ ANALİZİ (POSTURE) ──
                    # Face bounding-box area relative to frame (normalized [0,1]).
                    # Large area = user too close to monitor.
                    xs = [l.x for l in lm]
                    ys = [l.y for l in lm]
                    face_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                    _now = time.monotonic()
                    if face_area > self._TOO_CLOSE_AREA:
                        if self._too_close_since is None:
                            self._too_close_since = _now
                        elif _now - self._too_close_since >= self._TOO_CLOSE_SEC:
                            posture_warn = "too_close"
                            self._too_close_since = None  # reset so it re-arms after recovery
                    else:
                        self._too_close_since = None

                    # Head drifting lower in frame and nose moving closer to chin
                    # both correlate better with slouch/neck collapse than nose.y alone.
                    face_height = max(chin.y - forehead.y, 1e-4)
                    nose_drop_ratio = (nose.y - forehead.y) / face_height
                    is_slouching = nose.y > 0.69 and nose_drop_ratio > 0.60
                    if is_slouching:
                        if self._slouch_since is None:
                            self._slouch_since = _now
                        elif _now - self._slouch_since >= self._SLOUCH_SEC:
                            posture_warn = posture_warn or "slouching"
                    else:
                        self._slouch_since = None
                        
                    # ── 2. BAŞ HAREKETİ (MEDIA KONTROLÜ) ──
                    dist_left = abs(nose.x - left_cheek.x)
                    dist_right = abs(nose.x - right_cheek.x)
                    
                    if dist_left > 0.001 and dist_right > 0.001:
                        raw_ratio = dist_right / dist_left
                        # Stage 1: moving average to kill sensor noise
                        self._ratio_ma.append(raw_ratio)
                        ma_ratio = float(np.mean(self._ratio_ma))
                        # Stage 2: EMA for trajectory smoothing
                        self._smooth_ratio = (
                            self._ema_alpha * ma_ratio
                            + (1.0 - self._ema_alpha) * self._smooth_ratio
                        )
                        ratio = self._smooth_ratio
                        # Only fire outside the deadzone (neutral band around 1.0)
                        if ratio > (1.0 + self._deadzone) and ratio > self._yaw_thresh:
                            raw_action = "Turn_Left"
                        elif ratio < (1.0 - self._deadzone) and (1.0 / ratio) > self._yaw_thresh:
                            raw_action = "Turn_Right"

                # Durumları Kilitleyerek Paylaş
                with self._lock:
                    self._raw = raw_action
                    self._is_present = is_pres
                    # Eğer yeni bir uyarı varsa ve önceki tüketildiyse üzerine yaz
                    if posture_warn and not self._posture_warning:
                        self._posture_warning = posture_warn

                # Filtreleme (Titreme engelleme)
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
