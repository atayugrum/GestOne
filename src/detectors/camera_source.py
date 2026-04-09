"""Shared camera source — single capture loop for all detectors."""

import threading
import time
from typing import Optional

import cv2
import numpy as np


class CameraSource:
    """One camera capture thread. All detectors pull frames from here."""

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480) -> None:
        self._index = camera_index
        self._width = width
        self._height = height
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._frame_flipped: Optional[np.ndarray] = None
        self._rgb: Optional[np.ndarray] = None
        self._rgb_flipped: Optional[np.ndarray] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._opened = False

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera-source")
        self._thread.start()
        # Wait long enough for the retry loop in _run (up to 5 s for OS permission)
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if self._opened or self._stop_event.is_set():
                break
            time.sleep(0.05)
        return self._opened

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=4)

    def get_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest BGR frame, or None if not ready."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def get_frame_flipped(self) -> Optional[np.ndarray]:
        """Return pre-computed horizontally-flipped BGR frame (zero-latency)."""
        with self._lock:
            return self._frame_flipped.copy() if self._frame_flipped is not None else None

    def get_rgb(self) -> Optional[np.ndarray]:
        """Return pre-converted RGB frame (no per-detector cvtColor call)."""
        with self._lock:
            return self._rgb

    def get_rgb_flipped(self) -> Optional[np.ndarray]:
        """Return pre-converted flipped RGB frame."""
        with self._lock:
            return self._rgb_flipped

    def _run(self) -> None:
        cap = None
        candidates = [self._index] + [i for i in range(4) if i != self._index]
        retry_deadline = time.monotonic() + 5.0
        while time.monotonic() < retry_deadline and cap is None:
            for idx in candidates:
                c = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
                if c.isOpened():
                    ret, _ = c.read()
                    if ret:
                        cap = c
                        self._index = idx
                        print(f"[camera_source] using camera index {idx}")
                        break
                c.release()
            if cap is None:
                time.sleep(0.5)
        if cap is None:
            print("[camera_source] ERROR: no usable camera found — check permissions")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimize latency
        self._opened = True
        print(f"[camera_source] started ({self._width}x{self._height})")

        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.005)
                continue
            flipped = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_flipped = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)
            with self._lock:
                self._frame = frame
                self._frame_flipped = flipped
                self._rgb = rgb
                self._rgb_flipped = rgb_flipped

        cap.release()
        print("[camera_source] stopped")
