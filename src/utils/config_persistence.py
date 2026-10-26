"""Load/save GestOneConfig overrides from a local JSON file."""

import json
import os
from typing import Any, Dict

CONFIG_PATH = os.path.expanduser("~/.gestone_config.json")

EDITABLE_FIELDS = [
    "cooldown_sec",
    "mouse_smoothing_alpha",
    "mouse_click_cooldown_sec",
    "mouse_pinch_threshold",
    "mouse_deadzone_px",
    "head_cooldown_sec",
    "two_hand_cooldown_sec",
    "hud_duration_ms",
    "calibration_hold_seconds",
    "enabled_features",
    "camera_index",
]


def load_overrides() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def apply_overrides(config: Any, overrides: Dict[str, Any]) -> None:
    for key, val in overrides.items():
        if key in EDITABLE_FIELDS and hasattr(config, key):
            try:
                setattr(config, key, type(getattr(config, key))(val))
            except (ValueError, TypeError):
                pass


def save_overrides(config: Any) -> None:
    data = {k: getattr(config, k) for k in EDITABLE_FIELDS if hasattr(config, k)}
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
