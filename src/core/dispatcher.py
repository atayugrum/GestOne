"""Command dispatcher — maps action strings to handler callables."""

from typing import Callable, Dict


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[[], None]] = {}

    def register(self, action: str, handler: Callable[[], None]) -> None:
        self._handlers[action] = handler

    def dispatch(self, action: str) -> bool:
        """Execute handler for action. Returns True if handled."""
        handler = self._handlers.get(action)
        if handler is None:
            print(f"[dispatcher] no handler for action: {action!r}")
            return False
        try:
            handler()
            return True
        except Exception as exc:
            print(f"[dispatcher] error running {action!r}: {exc}")
            return False

    def registered_actions(self) -> list:
        return list(self._handlers.keys())
