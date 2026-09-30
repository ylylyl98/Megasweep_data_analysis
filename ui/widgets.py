"""Shared Qt controls and Matplotlib canvas host for measurement workspaces."""
from __future__ import annotations
import os
from pathlib import Path
from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget
from ui.exporting import save_figure


class ExportNavigationToolbar(NavigationToolbar2QT):
    export_message = Signal(str, str)

    def save_figure(self, *args):
        groups = self.canvas.get_supported_filetypes_grouped()
        filters = {f"{name} ({' '.join('*.' + ext for ext in extensions)})": extensions
                   for name, extensions in sorted(groups.items())}
        default = next(label for label, extensions in filters.items()
                       if self.canvas.get_default_filetype() in extensions)
        directory = os.path.expanduser(rcParams['savefig.directory'])
        path, selected = QFileDialog.getSaveFileName(
            self, 'Save figure (existing files are kept)',
            os.path.join(directory, self.canvas.get_default_filename()),
            ';;'.join(filters), default, options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return
        if not Path(path).suffix:
            path += '.' + filters.get(selected, [self.canvas.get_default_filetype()])[0]
        try:
            result = save_figure(self.canvas.figure, path, dpi=self.canvas.figure.dpi)
        except Exception as exc:
            self.export_message.emit(f'Export failed: {exc}', 'error')
            return
        if directory:
            rcParams['savefig.directory'] = str(result.path.parent)
        self.export_message.emit(result.message, 'success')

class ProgressLabel(QLabel):
    def __init__(self):
        super().__init__("Working...")
        self.setVisible(False)
        self.setStyleSheet("color:#5a7088; padding:4px 2px; font-weight:500;")


class CollapsibleSection(QFrame):
    def __init__(self, title: str, content: QWidget, expanded: bool = True):
        super().__init__()
        self.setObjectName("StageCard")
        content.setProperty("class", "sectionContent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setProperty("class", "sectionToggle")
        self.toggle.setMinimumHeight(28)
        self.toggle.clicked.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(8, 0, 8, 6)
        body_layout.setSpacing(0)
        body_layout.addWidget(content)
        layout.addWidget(self.body)
        self.body.setVisible(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self.toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.body.setVisible(checked)

    def set_expanded(self, expanded: bool) -> None:
        """Expand/collapse the section without relying on a synthetic click."""
        self.toggle.setChecked(expanded)
        self._on_toggled(expanded)


class PlotTab(QWidget):
    export_message = Signal(str, str)

    def __init__(self, title: str):
        super().__init__()
        self.current_figure = None
        self.toolbar = None
        self.canvas = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        self.placeholder = QLabel(f"{title} preview will appear here.")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(
            "color: #7b8da5; border: 1px dashed #cbd7e7; padding: 36px; "
            "background: #f8fbff; border-radius: 12px;"
        )
        self._layout.addWidget(self.placeholder)

    def set_figure(self, figure) -> None:
        self.clear()
        self.current_figure = figure
        # A one-shot tight_layout leaves labels outside the canvas after resizing.
        # Preserve existing constrained/tight engines; fixed-size exports temporarily
        # disable the engine and restore it when they finish.
        if figure.get_layout_engine() is None or type(figure.get_layout_engine()).__name__ == "PlaceHolderLayoutEngine":
            figure.set_layout_engine("tight")
        self._layout.removeWidget(self.placeholder)
        self.placeholder.hide()
        self.canvas = FigureCanvasQTAgg(figure)
        self.toolbar = ExportNavigationToolbar(self.canvas, self)
        self.toolbar.export_message.connect(self.export_message.emit)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.toolbar)
        self._layout.addWidget(self.canvas, 1)
        self.canvas.draw_idle()

    def clear(self) -> None:
        self.current_figure = None
        if self.toolbar is not None:
            self._layout.removeWidget(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.canvas is not None:
            self._layout.removeWidget(self.canvas)
            self.canvas.deleteLater()
            self.canvas = None
        self._layout.removeWidget(self.placeholder)
        self.placeholder.show()
        self._layout.addWidget(self.placeholder)


class CsvDropLineEdit(QLineEdit):
    csv_paths_dropped = Signal(list)

    def __init__(self, *, allow_multiple: bool = False, parent=None):
        super().__init__(parent)
        self._allow_multiple = allow_multiple
        self.setAcceptDrops(True)

    def _extract_csv_paths(self, event) -> list[str]:
        if not event.mimeData().hasUrls():
            return []
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile().strip()
            if path.lower().endswith(".csv"):
                paths.append(path)
        if not self._allow_multiple:
            return paths[:1]
        return paths

    def dragEnterEvent(self, event) -> None:
        if self._extract_csv_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._extract_csv_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        paths = self._extract_csv_paths(event)
        if not paths:
            event.ignore()
            return
        self.csv_paths_dropped.emit(paths)
        event.acceptProposedAction()
