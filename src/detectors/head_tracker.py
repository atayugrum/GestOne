"""Head tracker — face-mesh-based head gesture detection.

Detects three head gestures:
  Turn_Left  → prev_track
  Turn_Right → next_track
  Nod_Down   → play_pause

Consumes frames from shared CameraSource.
"""

import time
import threading
from typing import Optional

import cv2
import mediapipe as mp

from config import (
    HEAD_YAW_THRESHOLD,
    HEAD_PITCH_THRESHOLD,
    HEAD_NEUTRAL_ZONE,
    HEAD_STABILITY_FRAMES,
    HEAD_SMOOTH_ALPHA,
)
from .base import BaseDetector, DetectionResult
from .camera_source import CameraSource

_NOSE_TIP      = 1
_LEFT_EYE_OUT  = 33
_RIGHT_EYE_OUT = 263
_CHIN          = 152


def _estimate_pose(face_lm) -> tuple[float, float]:
    lm = face_lm.landmark
    nose_x = lm[_NOSE_TIP].x
    nose_y = lm[_NOSE_TIP].y
    eye_mid_x = (lm[_LEFT_EYE_OUT].x + lm[_RIGHT_EYE_OUT].x) / 2.0
    eye_mid_y = (lm[_LEFT_EYE_OUT].y + lm[_RIGHT_EYE_OUT].y) / 2.0
    ref_y = (eye_mid_y + lm[_CHIN].y) / 2.0
    yaw   = nose_x - eye_mid_x
    pitch = nose_y - ref_y
    return yaw, pitch


class HeadTracker(BaseDetector):
    """Detects head gestures from a shared CameraSource."""

    def __init__(
        self,
        camera_source: CameraSource,
        yaw_threshold: float = HEAD_YAW_THRESHOLD,
        pitch_threshold: float = HEAD_PITCH_THRESHOLD,
        neutral_zone: float = HEAD_NEUTRAL_ZONE,
        stability_frames: int = HEAD_STABILITY_FRAMES,
        smooth_alpha: float = HEAD_SMOOTH_ALPHA,
    ) -> None:
        self._cam          = camera_source
        self._yaw_thresh   = yaw_threshold
        self._pitch_thresh = pitch_threshold
        self._neutral_zone = neutral_zone
        self._stability    = stability_frames
        self._alpha        = smooth_alpha

        self._lock         = threading.Lock()
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pending: Optional[str] = None
        self._current_label: Optional[str] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="head-loop")
        self._thread.start()
        print("[head_tracker] started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        print("[head_tracker] stopped")

    def detect(self) -> Optional[DetectionResult]:
        label = self.get_head_gesture()
        return DetectionResult(label=label, confidence=1.0) if label else None

    def consume_action(self) -> Optional[str]:
        with self._lock:
            action = self._pending
            self._pending = None
            return action

    def get_head_gesture(self) -> Optional[str]:
        with self._lock:
            return self._current_label

    def _run(self) -> None:
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        smooth_yaw: float = 0.0
        smooth_pitch: float = 0.0
        candidate_label: Optional[str] = None
        stable_count: int = 0
        active_gesture: Optional[str] = None

        try:
            while not self._stop_event.is_set():
                frame = self._cam.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb)

                if not results.multi_face_landmarks:
                    smooth_yaw = 0.0
                    smooth_pitch = 0.0
                    candidate_label = None
                    stable_count = 0
                    active_gesture = None
                    with self._lock:
                        self._current_label = None
                    continue

                yaw_raw, pitch_raw = _estimate_pose(results.multi_face_landmarks[0])
                smooth_yaw   = self._alpha * yaw_raw   + (1 - self._alpha) * smooth_yaw
                smooth_pitch = self._alpha * pitch_raw + (1 - self._alpha) * smooth_pitch

                zone = self._classify_zone(smooth_yaw, smooth_pitch)

                if zone is None and active_gesture is not None:
                    active_gesture  = None
                    candidate_label = None
                    stable_count    = 0

                with self._lock:
                    self._current_label = zone

                if zone is not None and zone != active_gesture:
                    if zone == candidate_label:
                        stable_count += 1
                    else:
                        candidate_label = zone
                        stable_count    = 1

                    if stable_count >= self._stability:
                        active_gesture = zone
                        stable_count   = 0
                        with self._lock:
                            self._pending = zone
                        print(f"[head_tracker] gesture → {zone}")
                else:
                    if zone != candidate_label:
                        candidate_label = zone
                        stable_count    = 0

        finally:
            face_mesh.close()

    def _classify_zone(self, yaw: float, pitch: float) -> Optional[str]:
        if yaw > self._yaw_thresh:
            return "Turn_Right"
        if yaw < -self._yaw_thresh:
            return "Turn_Left"
        if pitch > self._pitch_thresh:
            return "Nod_Down"
        return None
