"""Mouse controller — Native macOS via Quartz CoreGraphics (pyobjc)."""

import ctypes
import ctypes.util
import time
import Quartz


def _load_app_services():
    lib_path = ctypes.util.find_library("ApplicationServices")
    if not lib_path:
        return None
    try:
        return ctypes.CDLL(lib_path)
    except OSError:
        return None


_APP_SERVICES = _load_app_services()


def is_accessibility_trusted() -> bool:
    if _APP_SERVICES is None:
        return True
    try:
        fn = _APP_SERVICES.AXIsProcessTrusted
        fn.restype = ctypes.c_bool
        return bool(fn())
    except Exception:
        return True


def request_accessibility_prompt() -> bool:
    try:
        prompt_key = getattr(Quartz, "kAXTrustedCheckOptionPrompt", "AXTrustedCheckOptionPrompt")
        fn = getattr(Quartz, "AXIsProcessTrustedWithOptions", None)
        if fn is None:
            return is_accessibility_trusted()
        return bool(fn({prompt_key: True}))
    except Exception:
        return is_accessibility_trusted()


def _current_pos():
    loc = Quartz.NSEvent.mouseLocation()
    screen_h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
    return loc.x, screen_h - loc.y  # flip Quartz Y-axis


def _mouse_event(event_type, pt, button, click_state: int = 1):
    event = Quartz.CGEventCreateMouseEvent(None, event_type, pt, button)
    Quartz.CGEventSetIntegerValueField(
        event,
        Quartz.kCGMouseEventClickState,
        click_state,
    )
    return event


class MouseController:
    def __init__(self, warning_callback=None):
        self._warning_callback = warning_callback
        self._warned_untrusted = False
        self._left_button_down = False

    def request_accessibility_prompt(self) -> bool:
        return request_accessibility_prompt()

    def _ensure_accessibility(self) -> bool:
        trusted = is_accessibility_trusted()
        if trusted:
            return True
        if not self._warned_untrusted:
            self._warned_untrusted = True
            message = (
                "Mouse control is blocked because GestOne is not allowed in "
                "System Settings > Privacy & Security > Accessibility."
            )
            print(message)
            if self._warning_callback:
                try:
                    self._warning_callback(message)
                except Exception:
                    pass
        return False

    def move_to(self, x: float, y: float) -> None:
        if not self._ensure_accessibility():
            return
        screen_w = Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID())
        screen_h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
        cx = max(0.0, min(float(screen_w) - 1, x))
        cy = max(0.0, min(float(screen_h) - 1, y))
        event_type = (
            Quartz.kCGEventLeftMouseDragged
            if self._left_button_down
            else Quartz.kCGEventMouseMoved
        )
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type,
            Quartz.CGPointMake(cx, cy), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def click(self, button: str = "left") -> None:
        if not self._ensure_accessibility():
            return
        x, y = _current_pos()
        pt = Quartz.CGPointMake(x, y)
        if button == "right":
            down_type = Quartz.kCGEventRightMouseDown
            up_type   = Quartz.kCGEventRightMouseUp
            btn       = Quartz.kCGMouseButtonRight
        else:
            down_type = Quartz.kCGEventLeftMouseDown
            up_type   = Quartz.kCGEventLeftMouseUp
            btn       = Quartz.kCGMouseButtonLeft
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
            _mouse_event(down_type, pt, btn))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
            _mouse_event(up_type, pt, btn))

    def double_click(self) -> None:
        if not self._ensure_accessibility():
            return
        x, y = _current_pos()
        pt = Quartz.CGPointMake(x, y)
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            _mouse_event(Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft, click_state=1),
        )
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            _mouse_event(Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft, click_state=1),
        )
        time.sleep(0.04)
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            _mouse_event(Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft, click_state=2),
        )
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            _mouse_event(Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft, click_state=2),
        )

    def drag_start(self, button: str = "left") -> None:
        if not self._ensure_accessibility():
            return
        x, y = _current_pos()
        pt = Quartz.CGPointMake(x, y)
        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        self._left_button_down = True

    def drag_stop(self, button: str = "left") -> None:
        if not self._ensure_accessibility():
            return
        x, y = _current_pos()
        pt = Quartz.CGPointMake(x, y)
        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        self._left_button_down = False

    def scroll(self, dy: int) -> None:
        if not self._ensure_accessibility():
            return
        event = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, dy
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
