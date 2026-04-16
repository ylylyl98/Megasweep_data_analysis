"""
main.py
=======
Entry point for the Megasweep PL Analysis desktop app.

Launch:
    python main.py
or double-click launch.bat
"""

from datetime import datetime
import os
import sys
import traceback

import matplotlib

# Force the Qt-backed matplotlib backend before importing any modules that may
# pull in matplotlib.pyplot or Qt canvas helpers.
matplotlib.use("qtagg")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

# Ensure the app folder is on the path regardless of where Python is invoked from
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


_CRASH_LOG_PATH = os.path.join(APP_DIR, "megasweep_crash.log")


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

    sys.stderr.write(message)
    sys.stderr.flush()
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _log_uncaught_exception

from ui.main_window import MainWindow


def _light_palette() -> QPalette:
    """Return a light, modern-looking application palette."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(245, 247, 251))
    pal.setColor(QPalette.WindowText, QColor(31, 41, 55))
    pal.setColor(QPalette.Base, QColor(255, 255, 255))
    pal.setColor(QPalette.AlternateBase, QColor(239, 244, 251))
    pal.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipText, QColor(31, 41, 55))
    pal.setColor(QPalette.Text, QColor(31, 41, 55))
    pal.setColor(QPalette.Button, QColor(255, 255, 255))
    pal.setColor(QPalette.ButtonText, QColor(31, 41, 55))
    pal.setColor(QPalette.BrightText, QColor(190, 24, 93))
    pal.setColor(QPalette.Highlight, QColor(53, 102, 193))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.PlaceholderText, QColor(113, 128, 150))
    return pal


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Megasweep PL Analysis")
    app.setStyle("Fusion")
    app.setPalette(_light_palette())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
