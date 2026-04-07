"""GestOne configuration — all tunable values live here."""

from dataclasses import dataclass, field
from typing import Dict

# ── Mode names ──────────────────────────────────────────────────────────────
MODE_GESTURE = "gesture"
MODE_MOUSE   = "mouse"
MODE_MEDIA   = "media"
MODE_HEAD    = "head"
MODE_VOICE   = "voice"
MODE_IDLE    = "idle"

ALL_MODES = [MODE_GESTURE, MODE_MOUSE, MODE_MEDIA, MODE_HEAD, MODE_VOICE, MODE_IDLE]

# ── Thresholds & timings ─────────────────────────────────────────────────────
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.75
DEFAULT_COOLDOWN_SEC: float = 0.5
DEFAULT_DEBOUNCE_SEC: float = 0.1
CAMERA_INDEX: int = 0
CAMERA_WIDTH: int = 640
CAMERA_HEIGHT: int = 480

# ── Mouse control ────────────────────────────────────────────────────────────
MOUSE_SMOOTHING_ALPHA: float = 0.25    # EMA weight; higher = more responsive, more jitter
MOUSE_CLICK_COOLDOWN_SEC: float = 0.8  # min seconds between clicks
MOUSE_PINCH_THRESHOLD: float = 0.26    # pinch_norm below this → click armed
MOUSE_PINCH_RELEASE_THRESHOLD: float = 0.42  # must re-open above this before next click
MOUSE_DEADZONE_PX: float = 5.0         # pixel movement below this is suppressed

# ── Two-hand gestures ────────────────────────────────────────────────────────
TWO_HAND_STABILITY_FRAMES: int = 5   # consecutive matching frames before firing
TWO_HAND_COOLDOWN_SEC: float = 1.2   # min seconds between two-hand actions

# ── Head tracking ─────────────────────────────────────────────────────────────
HEAD_YAW_THRESHOLD: float    = 0.07   # normalized nose-offset to trigger left/right
HEAD_PITCH_THRESHOLD: float  = 0.18   # raised: nod disabled effectively (too unreliable)
HEAD_NEUTRAL_ZONE: float     = 0.035  # head must return here to reset
HEAD_STABILITY_FRAMES: int   = 8      # frames gesture must hold before firing (raised for fewer false positives)
HEAD_COOLDOWN_SEC: float     = 1.2    # min seconds between head actions
HEAD_SMOOTH_ALPHA: float     = 0.30   # EMA weight for yaw/pitch smoothing


@dataclass
class GestOneConfig:
    active_mode: str = MODE_IDLE
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    cooldown_sec: float = DEFAULT_COOLDOWN_SEC
    debounce_sec: float = DEFAULT_DEBOUNCE_SEC
    camera_index: int = CAMERA_INDEX
    camera_width: int = CAMERA_WIDTH
    camera_height: int = CAMERA_HEIGHT
    mouse_smoothing_alpha: float = MOUSE_SMOOTHING_ALPHA
    mouse_click_cooldown_sec: float = MOUSE_CLICK_COOLDOWN_SEC
    mouse_pinch_threshold: float = MOUSE_PINCH_THRESHOLD
    mouse_pinch_release_threshold: float = MOUSE_PINCH_RELEASE_THRESHOLD
    mouse_deadzone_px: float = MOUSE_DEADZONE_PX
    two_hand_stability_frames: int = TWO_HAND_STABILITY_FRAMES
    two_hand_cooldown_sec: float = TWO_HAND_COOLDOWN_SEC
    head_yaw_threshold: float = HEAD_YAW_THRESHOLD
    head_pitch_threshold: float = HEAD_PITCH_THRESHOLD
    head_neutral_zone: float = HEAD_NEUTRAL_ZONE
    head_stability_frames: int = HEAD_STABILITY_FRAMES
    head_cooldown_sec: float = HEAD_COOLDOWN_SEC
    head_smooth_alpha: float = HEAD_SMOOTH_ALPHA
    # gesture → action mapping; populated by each mode
    command_map: Dict[str, str] = field(default_factory=dict)


def default_config() -> GestOneConfig:
    return GestOneConfig()
