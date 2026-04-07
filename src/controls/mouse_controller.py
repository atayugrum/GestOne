"""Mouse controller — Phase 2: cursor movement and click via pyautogui."""

import pyautogui

# Disable pyautogui failsafe (corner-of-screen abort) to avoid accidental halts during demo.
# Re-enable if you want the safety feature.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0  # remove built-in delay; we manage timing ourselves


class MouseController:
    def move_to(self, x: float, y: float) -> None:
        """Move cursor to absolute screen coordinates."""
        try:
            pyautogui.moveTo(int(x), int(y))
        except Exception as exc:
            print(f"[mouse] move error: {exc}")

    def click(self, button: str = "left") -> None:
        """Send a mouse click at the current cursor position."""
        try:
            pyautogui.click(button=button)
        except Exception as exc:
            print(f"[mouse] click error: {exc}")

    def scroll(self, delta: float) -> None:
        # TODO Phase 2 extension: implement scroll gesture
        pass
