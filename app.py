"""GestOne — macOS gesture-control desktop app.

Entry point: initialises QApplication, loads SF Pro font, starts the system tray.
All detection logic lives in src/ui/menubar.py (HeartbeatWorker + GestOneMenuBar).
"""

import os
import sys

# Silence MediaPipe / TF log spam before any heavy imports
os.environ["GLOG_minloglevel"] = "2"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Make project root importable regardless of working directory
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QFontDatabase
    from PyQt6.QtWidgets import QApplication
except ImportError:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

from src.ui.menubar import GestOneMenuBar


def _configure_application(app: QApplication) -> None:
    """Apply global application settings once, before any windows are shown."""
    # Keep running when the last visible window is closed (system tray app)
    app.setQuitOnLastWindowClosed(False)

    # Prefer SF Pro on macOS; fall back gracefully on other platforms
    families = QFontDatabase.families()
    if "SF Pro Text" in families:
        app.setFont(QFont("SF Pro Text", 13))
    else:
        app.setFont(QFont("Helvetica Neue", 13))

    # Enable high-DPI scaling (no-op on Qt6 which enables it by default)
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    except AttributeError:
        pass


def main() -> None:
    app = QApplication(sys.argv)
    _configure_application(app)

    tray = GestOneMenuBar()          # owns camera, detectors, UI windows, worker
    tray.show()                      # make tray icon visible

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
