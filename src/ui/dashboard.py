"""Dashboard — mode control, detector status, signal display, settings."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple


class Dashboard:
    """
    Improved dashboard with:
    - active mode display + mode switch buttons
    - detector status indicators
    - current signal summary
    - editable settings section with save
    """

    def __init__(
        self,
        get_mode: Callable[[], str],
        on_close: Callable[[], None],
        modes: List[str],
        on_mode_switch: Callable[[str], None],
        get_gesture: Optional[Callable[[], Optional[str]]] = None,
        on_tick: Optional[Callable[[], None]] = None,
        get_detector_status: Optional[Callable[[], Dict[str, bool]]] = None,
        get_settings: Optional[Callable[[], Dict[str, float]]] = None,
        on_save_settings: Optional[Callable[[Dict[str, float]], None]] = None,
    ) -> None:
        self._get_mode = get_mode
        self._on_close = on_close
        self._modes = modes
        self._on_mode_switch = on_mode_switch
        self._get_gesture = get_gesture
        self._on_tick = on_tick
        self._get_detector_status = get_detector_status
        self._get_settings = get_settings
        self._on_save_settings = on_save_settings
        self._root: Optional[tk.Tk] = None
        self._setting_vars: Dict[str, tk.StringVar] = {}
        self._detector_labels: Dict[str, tk.Label] = {}
        self._mode_buttons: Dict[str, tk.Button] = {}

    def start(self) -> None:
        self._root = tk.Tk()
        self._root.title("GestOne")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        pad = {"padx": 8, "pady": 4}

        # ── Mode section ──────────────────────────────────────────────────
        mode_frame = tk.LabelFrame(self._root, text="Mode", **pad)
        mode_frame.pack(fill="x", padx=8, pady=(8, 2))

        self._active_mode_label = tk.Label(
            mode_frame, text="", font=("Helvetica", 14, "bold")
        )
        self._active_mode_label.pack(pady=(4, 2))

        btn_row = tk.Frame(mode_frame)
        btn_row.pack(pady=(0, 4))
        for mode in self._modes:
            btn = tk.Button(
                btn_row,
                text=mode.capitalize(),
                width=7,
                command=lambda m=mode: self._on_mode_switch(m),
            )
            btn.pack(side="left", padx=2)
            self._mode_buttons[mode] = btn

        # ── Detector status ───────────────────────────────────────────────
        status_frame = tk.LabelFrame(self._root, text="Detectors", **pad)
        status_frame.pack(fill="x", padx=8, pady=2)

        detector_names = ["gesture", "mouse", "two_hand", "head", "voice"]
        col_frame = tk.Frame(status_frame)
        col_frame.pack(pady=2)
        for name in detector_names:
            lbl = tk.Label(col_frame, text=name, width=10, relief="groove", padx=4)
            lbl.pack(side="left", padx=2, pady=2)
            self._detector_labels[name] = lbl

        # ── Signal summary ────────────────────────────────────────────────
        signal_frame = tk.LabelFrame(self._root, text="Signal", **pad)
        signal_frame.pack(fill="x", padx=8, pady=2)

        self._signal_label = tk.Label(
            signal_frame, text="—", font=("Helvetica", 12), fg="#333333"
        )
        self._signal_label.pack(pady=4)

        # ── Settings section ──────────────────────────────────────────────
        settings_frame = tk.LabelFrame(self._root, text="Settings", **pad)
        settings_frame.pack(fill="x", padx=8, pady=2)

        SETTING_LABELS: List[Tuple[str, str]] = [
            ("cooldown_sec",          "Gesture cooldown (s)"),
            ("mouse_smoothing_alpha", "Mouse smoothing"),
            ("mouse_pinch_threshold", "Pinch threshold"),
            ("head_cooldown_sec",     "Head cooldown (s)"),
            ("two_hand_cooldown_sec", "Two-hand cooldown (s)"),
        ]

        current_settings = self._get_settings() if self._get_settings else {}
        for key, label in SETTING_LABELS:
            row = tk.Frame(settings_frame)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(current_settings.get(key, "")))
            entry = tk.Entry(row, textvariable=var, width=8)
            entry.pack(side="left")
            self._setting_vars[key] = var

        save_btn = tk.Button(
            settings_frame,
            text="Save settings",
            command=self._save_settings,
        )
        save_btn.pack(pady=(4, 6))

        self._save_status_label = tk.Label(
            settings_frame, text="", fg="#007700", font=("Helvetica", 10)
        )
        self._save_status_label.pack()

        self._refresh()
        self._root.mainloop()

    def _refresh(self) -> None:
        if self._root is None:
            return
        if self._on_tick:
            self._on_tick()

        # Update active mode label + button highlights
        current = self._get_mode()
        self._active_mode_label.config(text=f"Active: {current.upper()}")
        for mode, btn in self._mode_buttons.items():
            btn.config(
                relief="sunken" if mode == current else "raised",
                fg="black",
            )

        # Update detector status
        if self._get_detector_status:
            statuses = self._get_detector_status()
            for name, lbl in self._detector_labels.items():
                active = statuses.get(name, False)
                lbl.config(
                    bg="#44BB44" if active else "#DDDDDD",
                    fg="white" if active else "#888888",
                )

        # Update signal
        signal = self._get_gesture() if self._get_gesture else None
        self._signal_label.config(text=signal or "—")

        self._root.after(100, self._refresh)

    def _save_settings(self) -> None:
        if self._on_save_settings is None:
            return
        values: Dict[str, float] = {}
        for key, var in self._setting_vars.items():
            try:
                values[key] = float(var.get())
            except ValueError:
                pass
        self._on_save_settings(values)
        self._save_status_label.config(text="Saved.")
        if self._root:
            self._root.after(2000, lambda: self._save_status_label.config(text=""))

    def _handle_close(self) -> None:
        self._on_close()
        if self._root:
            self._root.destroy()
