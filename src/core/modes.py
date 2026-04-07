"""Mode manager — tracks and transitions the active interaction mode."""

from config import ALL_MODES, MODE_IDLE


class ModeManager:
    def __init__(self, initial_mode: str = MODE_IDLE) -> None:
        if initial_mode not in ALL_MODES:
            raise ValueError(f"Unknown mode: {initial_mode}")
        self._mode = initial_mode

    @property
    def current(self) -> str:
        return self._mode

    def switch(self, mode: str) -> None:
        if mode not in ALL_MODES:
            raise ValueError(f"Unknown mode: {mode}")
        if mode != self._mode:
            print(f"[mode] {self._mode} → {mode}")
            self._mode = mode

    def toggle(self, mode: str) -> None:
        """Switch to mode; if already active switch to idle."""
        self.switch(MODE_IDLE if self._mode == mode else mode)

    def __repr__(self) -> str:
        return f"ModeManager(current={self._mode!r})"
