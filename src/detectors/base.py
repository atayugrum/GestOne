"""Base detector interface — all detectors implement this."""

from abc import ABC, abstractmethod
from typing import Optional


class DetectionResult:
    def __init__(self, label: str, confidence: float, raw=None) -> None:
        self.label = label
        self.confidence = confidence
        self.raw = raw  # detector-specific payload

    def __repr__(self) -> str:
        return f"DetectionResult(label={self.label!r}, confidence={self.confidence:.2f})"


class BaseDetector(ABC):
    """Common interface for gesture, head, and voice detectors."""

    @abstractmethod
    def start(self) -> None:
        """Initialize resources (camera, mic, model, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Release resources."""

    @abstractmethod
    def detect(self) -> Optional[DetectionResult]:
        """Return a DetectionResult or None if nothing detected."""

    @property
    def is_available(self) -> bool:
        """Override to check hardware/permission availability."""
        return True
