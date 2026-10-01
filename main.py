"""
main.py
=======
Entry point for the Megasweep Analysis desktop app.

Launch:
    python main.py
or double-click Megasweep Analysis.bat
"""

from datetime import datetime
import ctypes
import os
import sys
import traceback

import matplotlib

# Force the Qt-backed matplotlib backend before importing any modules that may
# pull in matplotlib.pyplot or Qt canvas helpers.
matplotlib.use("qtagg")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtCore import Qt

# Ensure the app folder is on the path regardless of where Python is invoked from
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

APP_ICON_PATH = os.path.join(APP_DIR, "assets", "megasweep.ico")

_CRASH_LOG_PATH = os.path.join(APP_DIR, "megasweep_crash.log")
APP_ID = "YanLab.MegasweepAnalysis"
APP_NAME = "Megasweep Analysis"


def _log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    """Write uncaught exceptions to stderr and a local crash log."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    timestamp = datetime.now().isoformat(timespec="seconds")
    traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    message = f"[{timestamp}] Unhandled exception\n{traceback_text}\n"

    try:
        with open(_CRASH_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(message)
    except OSError:
        pass

    if sys.stderr is not None:
        try:
            sys.stderr.write(message)
            sys.stderr.flush()
        except OSError:
            pass
    if sys.stderr is not None and sys.__excepthook__ is not None:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _log_uncaught_exception

from ui.main_window import MainWindow


def _apply_windows_app_id(app_id: str) -> None:
    """Give the process a stable Windows taskbar identity when supported."""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _light_palette() -> QPalette:
    """Return a light, modern-looking application palette."""
    from ui.styles import theme_palette
    return theme_palette('light')


def main():
    _apply_windows_app_id(APP_ID)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Native dialogs and menus also need the readable default used by the shell.
    font = app.font()
    font.setPointSizeF(max(10.5, font.pointSizeF()))
    app.setFont(font)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    if os.path.isfile(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))

    window = MainWindow()
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
