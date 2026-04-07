# GestOne

macOS-first multimodal desktop controller. Control your computer using hand gestures, two-hand gestures, head movement, and voice commands — all running locally with no cloud dependency.

---

## Features

- **Gesture mode** — one-hand gestures trigger media actions (play/pause, volume, track skip)
- **Mouse mode** — hand position controls the cursor; pinch gesture clicks
- **Media mode** — gesture-based media control with two-hand gesture support
- **Head mode** — head nod and turn gestures trigger media actions
- **Voice mode** — stub, planned for Phase 4
- **Dashboard** — lightweight tkinter UI to switch modes and tune settings
- **Persistent config** — settings saved to `~/.gestone_config.json`

---

## Supported control modes

| Mode    | Input         | Actions                              |
|---------|---------------|--------------------------------------|
| gesture | One hand      | play/pause, volume up/down, next/prev |
| mouse   | One hand      | cursor movement, pinch to click       |
| media   | One/two hands | play/pause, next/prev, volume         |
| head    | Face tracking | play/pause, next/prev track           |
| voice   | Microphone    | not yet implemented                  |

---

## Install (macOS)

**Requirements:** Python 3.10+, macOS 12+, webcam

```bash
# 1. Clone
git clone https://github.com/your-username/GestOne.git
cd GestOne

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### macOS permissions

Grant these before running:

- **Camera** — System Settings → Privacy & Security → Camera → Terminal (or your IDE)
- **Accessibility** — System Settings → Privacy & Security → Accessibility → Terminal
  - Required for `pyautogui` to move the cursor and simulate clicks

---

## Run

```bash
python app.py
```

The dashboard window opens. Click a mode button to activate it. Close the dashboard to shut down all detectors.

---

## Configuration

Settings are saved automatically to `~/.gestone_config.json` when you click **Save** in the dashboard.

Editable fields:

| Field                    | Description                            | Default |
|--------------------------|----------------------------------------|---------|
| `cooldown_sec`           | Min seconds between gesture actions    | 0.5     |
| `mouse_smoothing_alpha`  | Cursor EMA smoothing (0=max, 1=raw)    | 0.25    |
| `mouse_click_cooldown_sec` | Min seconds between pinch clicks     | 0.6     |
| `mouse_pinch_threshold`  | Pinch distance to trigger click        | 0.055   |
| `head_cooldown_sec`      | Min seconds between head actions       | 1.0     |
| `two_hand_cooldown_sec`  | Min seconds between two-hand actions   | 1.2     |

Additional constants (camera index, thresholds, stability frames) are set in `config.py`.

---

## Gesture / action reference

### One-hand gestures (gesture and media modes)

| Gesture     | Action      |
|-------------|-------------|
| Open Palm   | Play / Pause |
| Thumb Up    | Volume Up   |
| Thumb Down  | Volume Down |
| Victory (✌) | Next Track  |

### Head gestures (head mode)

| Movement    | Action      |
|-------------|-------------|
| Nod down    | Play / Pause |
| Turn right  | Next Track  |
| Turn left   | Previous Track |

### Two-hand gestures (gesture and media modes)

Detected via `TwoHandGestureDetector`. Requires both hands visible for `stability_frames` consecutive frames before firing.

### Mouse mode

- Move hand in frame → cursor follows index finger tip
- Pinch thumb + index → left click

---

## Known limitations

- **Camera conflict** — all detectors open the same camera index. On some machines this may cause frame drops. If you see issues, only activate one mode at a time.
- **pyautogui safety margin** — `pyautogui` blocks cursor movement near screen edges by default (`FAILSAFE = True`). Moving to a top-left corner will raise an exception and exit.
- **Voice mode is a stub** — the `VoiceController` class exists but does not yet capture or recognize audio.
- **Two-hand detection sensitivity** — requires reasonable lighting and both hands clearly in frame.
- **Head mode calibration** — thresholds in `config.py` are tuned for a 640×480 webcam at ~50cm distance. Adjust `head_yaw_threshold` and `head_pitch_threshold` if too sensitive or unresponsive.
- **macOS only** — `pyautogui` cursor control and media key dispatch use macOS-specific behavior. Linux/Windows not tested.

---

## Roadmap

- [ ] Phase 4 — Real voice command recognition (Whisper or SpeechRecognition)
- [ ] Phase 5 — Expanded dashboard: editable gesture→action mappings, per-mode sensitivity
- [ ] Scroll mode in mouse mode (two-finger gesture)
- [ ] Mode persistence across restarts
- [ ] Packaging as a standalone `.app`

---

## Project structure

```
app.py               # Entry point and main loop
config.py            # All constants and GestOneConfig dataclass
src/
  core/
    dispatcher.py    # Action dispatch registry
    modes.py         # Mode manager
  detectors/
    gesture_detector.py         # One-hand gesture detection
    hand_mouse_tracker.py       # Hand position for mouse control
    two_hand_gesture_detector.py
    head_tracker.py
    voice_controller.py         # Stub
  controls/
    mouse_controller.py
    media_controller.py
  ui/
    dashboard.py     # tkinter dashboard
  utils/
    common.py        # Cooldown utility
    config_persistence.py  # ~/.gestone_config.json read/write
```
