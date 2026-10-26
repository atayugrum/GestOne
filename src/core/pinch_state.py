"""Pinch state machine for mouse click, double-click, drag detection."""

import time
import math
from dataclasses import dataclass


@dataclass
class PinchState:
    """Current state of a pinch gesture."""
    pinch_active: bool = False
    pending_click: bool = False
    drag_started: bool = False
    frozen_x: float = 0.0
    frozen_y: float = 0.0
    pinch_start_time: float = 0.0
    last_click_time: float = 0.0
    last_release_time: float = 0.0
    _pinch_freeze_frames: int = 0


class PinchStateMachine:
    """Manages pinch → click/double-click/drag state transitions.

    Returns action names: "click", "double_click", "drag_start", "drag_stop", "move"
    """

    def __init__(
        self,
        pinch_threshold: float,
        hold_drag_delay_sec: float,
        double_click_timeout: float = 0.35,
        drag_deadzone_px: float = 25,
        pinch_freeze_frames: int = 2,
    ):
        self.pinch_threshold = pinch_threshold
        self.hold_drag_delay_sec = hold_drag_delay_sec
        self.double_click_timeout = double_click_timeout
        self.drag_deadzone_px = drag_deadzone_px
        self._PINCH_FREEZE_FRAMES = pinch_freeze_frames

        self.state = PinchState()

    def update(
        self,
        pinch_norm: float,
        cursor_x: float,
        cursor_y: float,
        hand_present: bool,
    ) -> list[str]:
        """
        Update state machine based on pinch norm and cursor position.

        Args:
            pinch_norm: pinch distance (0=closed, 1=open)
            cursor_x: smoothed cursor x in screen pixels
            cursor_y: smoothed cursor y in screen pixels
            hand_present: whether hand is still detected

        Returns:
            List of action names: ["click"], ["double_click"], ["drag_start"], ["move"], etc.
        """
        actions = []

        if not hand_present:
            # Hand lost — clean up any active pinch
            if self.state.pinch_active:
                if self.state.drag_started:
                    actions.append("drag_stop")
                elif self.state.pending_click:
                    pass  # click was not sent, just discard
                self.state.pinch_active = False
                self.state.drag_started = False
                self.state.pending_click = False
                self.state._pinch_freeze_frames = 0
            return actions

        is_currently_pinching = pinch_norm < self.pinch_threshold

        if is_currently_pinching:
            if not self.state.pinch_active:
                # Pinch onset
                self.state.frozen_x = cursor_x
                self.state.frozen_y = cursor_y
                actions.append("move_to_frozen")

                now = time.time()
                if now - self.state.last_click_time < self.double_click_timeout:
                    # Double-click detected
                    actions.append("double_click")
                    self.state.pinch_active = False
                    self.state.drag_started = False
                    self.state.pending_click = False
                    self.state.last_click_time = 0.0
                    self.state.last_release_time = now
                else:
                    # Single-click armed
                    self.state.pinch_active = True
                    self.state.drag_started = False
                    self.state.pending_click = True
                    self.state.pinch_start_time = now
                    self.state._pinch_freeze_frames = self._PINCH_FREEZE_FRAMES
            else:
                # Already pinching — check for drag transition
                if self.state._pinch_freeze_frames > 0:
                    self.state._pinch_freeze_frames -= 1
                    actions.append("move_to_frozen")
                else:
                    dist = math.hypot(cursor_x - self.state.frozen_x, cursor_y - self.state.frozen_y)
                    held_long_enough = (time.time() - self.state.pinch_start_time) >= self.hold_drag_delay_sec

                    if self.state.pending_click and (held_long_enough or dist > self.drag_deadzone_px):
                        # Transition from click to drag
                        actions.append("move_to_frozen")
                        actions.append("drag_start")
                        self.state.pending_click = False
                        self.state.drag_started = True

                    if self.state.drag_started:
                        actions.append("move_to_cursor")
                    else:
                        actions.append("move_to_frozen")
        else:
            # Not pinching
            if self.state.pinch_active:
                # Release: short pinch becomes click, drag just releases
                if self.state.drag_started:
                    actions.append("drag_stop")
                    self.state.drag_started = False
                elif self.state.pending_click:
                    actions.append("move_to_frozen")
                    actions.append("click")
                    self.state.last_click_time = time.time()

                self.state.pinch_active = False
                self.state.pending_click = False
                self.state._pinch_freeze_frames = 0
                self.state.last_release_time = time.time()
            else:
                # Normal cursor movement (no pinch active)
                actions.append("move_to_cursor")

        return actions

    def reset(self):
        """Reset to initial state."""
        self.state = PinchState()
