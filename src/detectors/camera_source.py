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
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._opened = False

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera-source")
        self._thread.start()
        # Wait briefly to confirm camera opened
        deadline = time.monotonic() + 3.0
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
        """Return horizontally-flipped copy (mirror view) of latest frame."""
        with self._lock:
            if self._frame is None:
                return None
            return cv2.flip(self._frame, 1)

    def _run(self) -> None:
        cap = cv2.VideoCapture(self._index)
        if not cap.isOpened():
            print("[camera_source] ERROR: cannot open camera — check permissions")
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
            with self._lock:
                self._frame = frame

        cap.release()
        print("[camera_source] stopped")
