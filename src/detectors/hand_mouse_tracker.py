"""HandMouseTracker — ROI boundary box + WMA smoothing + micro-noise gate.
Lightweight: model_complexity=0, static pinch threshold, no dynamic calibration.
"""

import math
import time
import threading
from collections import deque
from typing import Optional, Tuple
import numpy as np
import mediapipe as mp
from .camera_source import CameraSource

# ── ROI (Region of Interest) Boundary Box ─────────────────────────────────────
# Only hand movements inside this normalized rectangle drive the cursor.
# Maps central 70%×70% of the camera feed → full screen.
# Eliminates edge-jitter; makes corners 100% reachable.
ROI_X_MIN: float = 0.25
ROI_X_MAX: float = 0.75
ROI_Y_MIN: float = 0.25
ROI_Y_MAX: float = 0.75

# Micro-noise gate: ROI-space delta below this is suppressed (≈ 5px on 640px feed)
_NOISE_GATE: float = 0.008


class _WMA2D:
    """Weighted Moving Average — recent frames carry exponentially more weight."""
    def __init__(self, window: int = 5) -> None:
        self._buf: deque = deque(maxlen=window)
        self._weights = np.arange(1, window + 1, dtype=float)

    def update(self, x: float, y: float) -> Tuple[float, float]:
        self._buf.append((x, y))
        n = len(self._buf)
        arr = np.array(self._buf)
        w = self._weights[-n:]
        return float(np.average(arr[:, 0], weights=w)), float(np.average(arr[:, 1], weights=w))


class _WMA1D:
    """Weighted Moving Average for scalar (scroll delta)."""
    def __init__(self, window: int = 5) -> None:
        self._buf: deque = deque(maxlen=window)
        self._weights = np.arange(1, window + 1, dtype=float)

    def update(self, v: float) -> float:
        self._buf.append(v)
        n = len(self._buf)
        w = self._weights[-n:]
        return float(np.average(list(self._buf), weights=w))


class HandMouseTracker:
    def __init__(self, camera_source: CameraSource) -> None:
        self._cam = camera_source
        self._lock = threading.Lock()

        # ROI-normalized [0..1] position within the boundary box
        self._position: Optional[Tuple[float, float]] = None
        self._pinch_norm: float = 1.0
        self._is_scrolling: bool = False
        self._scroll_delta: float = 0.0
        self._prev_scroll_y: Optional[float] = None

        # WMA smoothers
        self._wma_pos = _WMA2D(window=5)
        self._wma_scroll = _WMA1D(window=5)

        # Micro-noise gate state
        self._prev_pos: Optional[Tuple[float, float]] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mp_hands = mp.solutions.hands

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get_state(self) -> Tuple[Optional[Tuple[float, float]], float, bool, float]:
        """Returns (roi_pos, pinch_norm, is_scrolling, scroll_delta).
        roi_pos is [0..1] within the ROI box, ready for np.interp → screen coords.
        """
        with self._lock:
            return self._position, self._pinch_norm, self._is_scrolling, self._scroll_delta

    def _run(self) -> None:
        with self._mp_hands.Hands(
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        ) as hands:
            while not self._stop_event.is_set():
                rgb = self._cam.get_rgb_flipped()
                if rgb is None:
                    time.sleep(0.01)
                    continue

                result = hands.process(rgb)
                pos, pinch_norm, is_scrolling, scroll_delta = None, 1.0, False, 0.0

                if result.multi_hand_landmarks:
                    lm = result.multi_hand_landmarks[0].landmark

                    # 1. Palm centroid (vectorized) — landmarks 0 (wrist), 5 (index MCP), 9 (middle MCP)
                    pts = np.array([[lm[i].x, lm[i].y] for i in (0, 5, 9)])
                    raw_x, raw_y = float(pts[:, 0].mean()), float(pts[:, 1].mean())

                    # 2. Clip to ROI and remap to [0..1] — vectorized via np.interp
                    roi_x = float(np.interp(raw_x, [ROI_X_MIN, ROI_X_MAX], [0.0, 1.0]))
                    roi_y = float(np.interp(raw_y, [ROI_Y_MIN, ROI_Y_MAX], [0.0, 1.0]))
                    roi_x = float(np.clip(roi_x, 0.0, 1.0))
                    roi_y = float(np.clip(roi_y, 0.0, 1.0))

                    # 3. WMA smoothing
                    wx, wy = self._wma_pos.update(roi_x, roi_y)

                    # 4. Micro-noise gate — suppress sub-threshold jitter
                    if self._prev_pos is not None:
                        if abs(wx - self._prev_pos[0]) < _NOISE_GATE and abs(wy - self._prev_pos[1]) < _NOISE_GATE:
                            wx, wy = self._prev_pos
                    self._prev_pos = (wx, wy)
                    pos = (wx, wy)

                    # 5. Pinch — use 2D normalized distance for more stable click behavior
                    tip8, tip4 = lm[8], lm[4]
                    pinch_norm = math.hypot(tip4.x - tip8.x, tip4.y - tip8.y)

                    # 6. Scroll detection (V-sign ✌️)
                    index_up = lm[8].y < lm[5].y
                    middle_up = lm[12].y < lm[9].y
                    others_down = lm[16].y > lm[13].y and lm[20].y > lm[17].y

                    if index_up and middle_up and others_down:
                        is_scrolling = True
                        if self._prev_scroll_y is not None:
                            raw_delta = self._prev_scroll_y - roi_y
                            scroll_delta = self._wma_scroll.update(raw_delta)
                        self._prev_scroll_y = roi_y
                    else:
                        self._prev_scroll_y = None

                with self._lock:
                    self._position = pos
                    self._pinch_norm = pinch_norm
                    self._is_scrolling = is_scrolling
                    self._scroll_delta = scroll_delta

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
