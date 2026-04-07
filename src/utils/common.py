"""Shared utilities — keep small; add here only if used in 2+ modules."""

import time


class Cooldown:
    """Simple cooldown gate to prevent rapid re-triggering."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last: float = 0.0

    def ready(self) -> bool:
        return (time.monotonic() - self._last) >= self.seconds

    def reset(self) -> None:
        self._last = time.monotonic()

    def check_and_reset(self) -> bool:
        """Return True and reset if cooldown elapsed, else False."""
        if self.ready():
            self.reset()
            return True
        return False
