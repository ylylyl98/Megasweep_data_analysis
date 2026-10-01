"""Application shell: each measurement tab owns its sidebar, plots and state."""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from ui.measurement_workspace import MeasurementWorkspace
from ui.styles import _LIGHT_STYLE


class MainWindow(QMainWindow):
    def __init__(self, *, session_directory=None):
        super().__init__()
        self.setWindowTitle("Megasweep Analysis")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 960)
        self.setStyleSheet(_LIGHT_STYLE)
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setDocumentMode(True)
        self.workspaces = {}
        for mode in ("PL", "Reflection", "Transport"):
            workspace = MeasurementWorkspace(mode=mode, session_directory=session_directory)
            self.workspaces[mode] = workspace
            self.workspace_tabs.addTab(workspace, mode)
        self.setCentralWidget(self.workspace_tabs)
        self.workspace_tabs.currentChanged.connect(self._activate_workspace)
        self._activate_workspace()

    def _activate_workspace(self, *_):
        for workspace in self.workspaces.values():
            workspace.set_auto_update_active(self.workspace_tabs.currentWidget() is workspace)

    def closeEvent(self, event):
        # Hidden tabs may still be calculating: never destroy an active QThread.
        for index, workspace in enumerate(self.workspaces.values()):
            if workspace._thread is not None:
                self.workspace_tabs.setCurrentIndex(index)
                workspace._append_log("Please wait for this analysis task to finish before closing.", "warn")
                event.ignore()
                return
        for workspace in self.workspaces.values():
            workspace._save_session()
            workspace._session_save_timer.stop()
            workspace._stop_auto_updates()
        super().closeEvent(event)
