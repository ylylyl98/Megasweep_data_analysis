from __future__ import annotations

import os
import subprocess
import sys
import traceback

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from megasweep_analysis import (
    compute_rc_spectra,
    estimate_global_baseline,
    extract_line_cut,
    find_all_cut_values,
    classify_axis_role,
    plot_line_cut_spectrogram,
    plot_map,
    save_line_csv,
    save_map_csv,
    validate_axis_selection,
)
from ui.app_state import AppState
from ui.workers import (
    AnalysisRefreshWorker,
    BackgroundLoadWorker,
    BatchLineWorker,
    CsvLoadWorker,
    IntensityWorker,
    LineWorker,
    PeakWorker,
    TransformWorker,
)


_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)


_STYLE = """
QMainWindow, QWidget { font-size: 11px; }

/* ── Group boxes ── */
QGroupBox {
    font-weight: bold;
    font-size: 11px;
    border: 1px solid #4a4a4a;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 8px;
    background: #2b2b2b;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #b8b8b8;
}

/* ── Input controls ── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    padding: 2px 6px;
    min-height: 24px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #5b9bd5;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #4a4a4a;
    selection-background-color: #3a6ea5;
}

/* ── Standard buttons ── */
QPushButton {
    background: #3c3f41;
    color: #d4d4d4;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 10px;
    min-height: 24px;
}
QPushButton:hover  { background: #4c5052; border-color: #6a6a6a; }
QPushButton:pressed { background: #2a2d2f; }
QPushButton:disabled { background: #2a2d2f; color: #555; border-color: #3a3a3a; }

/* ── Primary action buttons (plot buttons) – class applied in code ── */
QPushButton[class="primary"] {
    background: #2b5190;
    color: #e8eaf0;
    border: 1px solid #3a68b8;
    font-weight: bold;
}
QPushButton[class="primary"]:hover  { background: #3461a8; border-color: #4a7acc; }
QPushButton[class="primary"]:pressed { background: #1e3d6e; }
QPushButton[class="primary"]:disabled { background: #243650; color: #556; border-color: #2a3a50; }

/* ── Table ── */
QTableWidget {
    background: #1e1e1e;
    color: #e0e0e0;
    gridline-color: #3a3a3a;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
}
QHeaderView::section {
    background: #2e3033;
    color: #b8b8b8;
    border: none;
    border-right: 1px solid #4a4a4a;
    border-bottom: 1px solid #4a4a4a;
    padding: 3px 5px;
    font-weight: bold;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    background: #252525;
}
QTabBar::tab {
    background: #2b2b2b;
    color: #999;
    border: 1px solid #4a4a4a;
    border-bottom: none;
    padding: 5px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #323232; color: #ddd; border-bottom: none; }
QTabBar::tab:hover:!selected { background: #333; color: #bbb; }

/* ── Scrollbars ── */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #5a5a5a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1e1e;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #5a5a5a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ── */
QSplitter::handle { background: #3a3a3a; }
QSplitter::handle:hover { background: #5b9bd5; }
"""

_LIGHT_STYLE = """
QMainWindow, QWidget {
    font-size: 11px;
    color: #1f2937;
    background: #f5f7fb;
}

QLabel {
    background: transparent;
}

QWidget#SidebarPanel,
QWidget#PreviewPanel,
QWidget#StatusPanel {
    background: #f5f7fb;
}

QFrame#StageCard,
QFrame#PanelCard {
    background: #ffffff;
    border: 1px solid #d9e2f2;
    border-radius: 14px;
}

QWidget[class="sectionContent"],
QWidget[class="inlineRow"] {
    background: transparent;
}

QToolButton[class="sectionToggle"] {
    background: transparent;
    border: none;
    color: #16324f;
    font-size: 12px;
    font-weight: 600;
    padding: 10px 12px;
    text-align: left;
}
QToolButton[class="sectionToggle"]:hover {
    color: #27496d;
}

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    border-radius: 9px;
    padding: 4px 8px;
    min-height: 28px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #4f7edc;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    selection-background-color: #dbeafe;
    selection-color: #16324f;
}

QPushButton {
    background: #ffffff;
    color: #27496d;
    border: 1px solid #d3ddea;
    border-radius: 10px;
    padding: 6px 12px;
    min-height: 28px;
    font-weight: 500;
}
QPushButton:hover {
    background: #f3f7ff;
    border-color: #b8c8e0;
}
QPushButton:pressed {
    background: #e7eefb;
}
QPushButton:disabled {
    background: #f5f7fb;
    color: #94a3b8;
    border-color: #dbe3ef;
}

QPushButton[class="primary"] {
    background: #3566c1;
    color: #ffffff;
    border: 1px solid #2f5aac;
    font-weight: 600;
}
QPushButton[class="primary"]:hover {
    background: #3d73d7;
    border-color: #3566c1;
}
QPushButton[class="primary"]:pressed {
    background: #2f5aac;
}
QPushButton[class="primary"]:disabled {
    background: #b8c9ea;
    color: #eff4fd;
    border-color: #b8c9ea;
}

QPushButton[class="ghost"] {
    background: #f8fbff;
    color: #35506b;
    border: 1px solid #d9e2f2;
}

QTableWidget {
    background: #ffffff;
    color: #1f2937;
    gridline-color: #e3eaf5;
    border: 1px solid #d3ddea;
    border-radius: 10px;
}
QHeaderView::section {
    background: #eef4fb;
    color: #35506b;
    border: none;
    border-right: 1px solid #d9e2f2;
    border-bottom: 1px solid #d9e2f2;
    padding: 6px 8px;
    font-weight: 600;
}

QTabWidget::pane {
    border: 1px solid #d9e2f2;
    border-radius: 12px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #eef3fb;
    color: #5a7088;
    border: 1px solid #d9e2f2;
    border-bottom: none;
    padding: 7px 16px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #16324f;
}
QTabBar::tab:hover:!selected {
    background: #f5f8fe;
    color: #27496d;
}

QTextEdit {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #d3ddea;
    border-radius: 12px;
    padding: 6px;
}

QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background: #eef4fb;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #bfd0e9;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #9fb8dc;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #eef4fb;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #bfd0e9;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #9fb8dc;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QSplitter::handle {
    background: #d9e2f2;
}
QSplitter::handle:hover {
    background: #9fb8dc;
}
"""


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
        self.toggle.clicked.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(12, 0, 12, 12)
        body_layout.setSpacing(0)
        body_layout.addWidget(content)
        layout.addWidget(self.body)
        self.body.setVisible(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self.toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.body.setVisible(checked)


class PlotTab(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self.current_figure = None
        self.toolbar = None
        self.canvas = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

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
        self._layout.removeWidget(self.placeholder)
        self.placeholder.hide()
        self.canvas = FigureCanvasQTAgg(figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
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


class MainWindow(QMainWindow):
    _LOG_COLORS = {
        "info": "#334155",
        "success": "#15803d",
        "error": "#b91c1c",
        "warn": "#b45309",
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Megasweep PL Analysis")
        self.setMinimumSize(1280, 760)
        self.setStyleSheet(_LIGHT_STYLE)

        self.state = AppState()
        self._thread: QThread | None = None
        self._worker = None
        self._pending_context = ""
        self._building_combos = False
        self._intensity_range_user_modified = False
        self._intensity_defaults_csv_signature: tuple[str, float, float, int] | None = None
        self._suppress_intensity_tracking = False
        self._baseline_user_modified = False
        self._suppress_baseline_tracking = False
        self._background_paths: list[str] = []
        self._reflection_preview_message: str | None = None
        self._dirty_views = {
            "intensity_original": True,
            "intensity_transformed": True,
            "peak_original": True,
            "peak_transformed": True,
            "line_cuts": True,
        }

        self._setup_ui()
        self.setAcceptDrops(True)
        self._refresh_stage_states()

    @staticmethod
    def _describe_range(values: np.ndarray) -> str:
        array = np.asarray(values, dtype=float)
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            return "no finite values"
        return f"{float(np.min(finite)):.4f} to {float(np.max(finite)):.4f}"

    @staticmethod
    def _extract_csv_paths_from_mime(mime_data, *, allow_multiple: bool = True) -> list[str]:
        if not mime_data.hasUrls():
            return []
        paths = []
        for url in mime_data.urls():
            path = url.toLocalFile().strip()
            if path.lower().endswith(".csv"):
                paths.append(path)
        if not allow_multiple:
            return paths[:1]
        return paths

    @staticmethod
    def _widget_contains_global_pos(widget: QWidget, global_pos) -> bool:
        if widget is None or not widget.isVisible():
            return False
        local_pos = widget.mapFromGlobal(global_pos)
        return widget.rect().contains(local_pos)

    def _drop_target_from_global_pos(self, global_pos) -> str:
        if (
            hasattr(self, "bg_section")
            and self.bg_section.isVisible()
            and any(
                self._widget_contains_global_pos(widget, global_pos)
                for widget in (self.bg_section, self.bg_csv_edit, self.bg_average_mode_combo, self.load_bg_btn)
            )
        ):
            return "background"
        return "primary"

    def _log_map_payload(
        self,
        stage_name: str,
        payload: dict,
        x_name: str,
        y_name: str,
        *,
        ratio: float | None = None,
    ) -> None:
        mapping = (
            f"Axis X={self.state.selected_x_col or 'X'}, "
            f"Axis Y={self.state.selected_y_col or 'Y'}"
        )
        summary = (
            f"{stage_name} payload: X{np.shape(payload['X2D'])}, Y{np.shape(payload['Y2D'])}, "
            f"Z{np.shape(payload['Z2D'])}"
        )
        if ratio is not None:
            summary += f", ratio={ratio:.4f}"
        self._append_log(summary, "info")
        self._append_log(
            f"{x_name} range: {self._describe_range(payload['X2D'])}; "
            f"{y_name} range: {self._describe_range(payload['Y2D'])}; "
            f"Z range: {self._describe_range(payload['Z2D'])}; {mapping}",
            "info",
        )

    def _handle_plot_failure(self, stage_name: str, message: str, tb: str, tab: PlotTab, figure_key: str) -> None:
        self.state.figures.pop(figure_key, None)
        tab.clear()
        self._append_log(f"{stage_name} plotting failed: {message}", "error")
        self._append_log(tb, "error")

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(8)

        self.left_panel = QWidget()
        self.left_panel.setObjectName("SidebarPanel")
        self.left_panel.setMinimumWidth(320)
        self.left_panel.setMaximumWidth(460)
        left_panel_layout = QVBoxLayout(self.left_panel)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 8, 2)
        left_layout.setSpacing(12)
        left_layout.addWidget(CollapsibleSection("Data", self._build_load_group(), expanded=True))
        self.bg_section = CollapsibleSection("Background", self._build_background_group(), expanded=False)
        self.bg_section.setVisible(False)
        left_layout.addWidget(self.bg_section)
        left_layout.addWidget(CollapsibleSection("Analysis Settings", self._build_analysis_group(), expanded=True))
        left_layout.addWidget(CollapsibleSection("Line Cuts", self._build_linecuts_group(), expanded=False))
        left_layout.addWidget(CollapsibleSection("Export", self._build_export_group(), expanded=False))
        left_layout.addStretch()
        left_scroll.setWidget(left_widget)
        left_panel_layout.addWidget(left_scroll, 1)

        right_splitter = QSplitter(Qt.Vertical)

        preview_widget = QWidget()
        preview_widget.setObjectName("PreviewPanel")
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        self.workspace_tabs = QTabWidget()

        self.maps_workspace = QWidget()
        maps_layout = QVBoxLayout(self.maps_workspace)
        maps_layout.setContentsMargins(8, 8, 8, 8)
        maps_layout.setSpacing(8)
        map_controls = QFrame()
        map_controls.setObjectName("PanelCard")
        map_controls_layout = QVBoxLayout(map_controls)
        map_controls_layout.setContentsMargins(12, 10, 12, 10)
        map_controls_layout.setSpacing(8)
        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(8)
        map_row.addWidget(QLabel("Map Type"))
        self.map_type_combo = QComboBox()
        self.map_type_combo.addItems(["Intensity", "Peak Energy"])
        self.map_type_combo.setFixedWidth(90)
        self.map_type_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self.map_type_combo)
        map_row.addWidget(QLabel("Axes:"))
        self.map_axes_combo = QComboBox()
        self.map_axes_combo.addItems(["Original", "Transformed"])
        self.map_axes_combo.setFixedWidth(90)
        self.map_axes_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self.map_axes_combo)
        map_row.addWidget(QLabel("Cmap:"))
        self.map_cmap_combo = QComboBox()
        self.map_cmap_combo.addItems([
            "RdBu_r", "jet", "viridis", "plasma", "inferno",
            "seismic", "coolwarm", "bwr", "Spectral_r", "RdYlBu_r",
        ])
        self.map_cmap_combo.setCurrentText("RdBu_r")
        self.map_cmap_combo.setFixedWidth(90)
        map_row.addWidget(self.map_cmap_combo)
        map_row.addStretch()
        self.refresh_current_btn = QPushButton("Refresh Current View")
        self.refresh_current_btn.setProperty("class", "primary")
        self.refresh_current_btn.clicked.connect(self._refresh_current_map_view)
        self.refresh_current_btn.style().unpolish(self.refresh_current_btn)
        self.refresh_current_btn.style().polish(self.refresh_current_btn)
        self.refresh_all_maps_btn = QPushButton("Refresh All Maps")
        self.refresh_all_maps_btn.clicked.connect(self._refresh_all_maps)
        map_row.addWidget(self.refresh_current_btn)
        map_row.addWidget(self.refresh_all_maps_btn)
        map_controls_layout.addLayout(map_row)

        # ── Color scale row ───────────────────────────────────────────────
        scale_row = QHBoxLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(4)
        self.map_auto_scale_check = QCheckBox("Auto scale")
        self.map_auto_scale_check.setChecked(True)
        self.map_vmin_spin = self._dspin(-1e6, 1e6, 0.001, 4, 0.0)
        self.map_vmin_spin.setEnabled(False)
        self.map_vmin_spin.setFixedWidth(80)
        self.map_vmax_spin = self._dspin(-1e6, 1e6, 0.001, 4, 1.0)
        self.map_vmax_spin.setEnabled(False)
        self.map_vmax_spin.setFixedWidth(80)
        self.map_auto_scale_check.toggled.connect(
            lambda checked: (
                self.map_vmin_spin.setEnabled(not checked),
                self.map_vmax_spin.setEnabled(not checked),
                self._sync_color_limit_controls() if checked else None,
            )
        )
        scale_row.addWidget(self.map_auto_scale_check)
        scale_row.addWidget(QLabel("vmin"))
        scale_row.addWidget(self.map_vmin_spin)
        scale_row.addSpacing(8)
        scale_row.addWidget(QLabel("vmax"))
        scale_row.addWidget(self.map_vmax_spin)
        scale_row.addStretch()
        map_controls_layout.addLayout(scale_row)
        # ─────────────────────────────────────────────────────────────────

        self.map_status_label = QLabel("Load a CSV, choose settings, then refresh a map view.")
        self.map_status_label.setWordWrap(True)
        self.map_status_label.setStyleSheet("color:#5a7088;")
        map_controls_layout.addWidget(self.map_status_label)
        maps_layout.addWidget(map_controls)
        self.map_plot_tab = PlotTab("Map")
        maps_layout.addWidget(self.map_plot_tab, 1)

        self.line_workspace = QWidget()
        line_layout = QVBoxLayout(self.line_workspace)
        line_layout.setContentsMargins(8, 8, 8, 8)
        line_layout.setSpacing(0)
        self.line_plot_tab = PlotTab("Line Cuts")
        line_layout.addWidget(self.line_plot_tab, 1)

        self.workspace_tabs.addTab(self.maps_workspace, "Maps")
        self.workspace_tabs.addTab(self.line_workspace, "Line Cuts")
        preview_layout.addWidget(self.workspace_tabs, 1)

        log_widget = QWidget()
        log_widget.setObjectName("StatusPanel")
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas, Courier New, monospace", 9))
        self.progress_label = ProgressLabel()
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        self.batch_progress_bar.setTextVisible(True)
        self.batch_progress_bar.setFixedHeight(16)
        self.batch_progress_bar.setStyleSheet(
            "QProgressBar { border:1px solid #4a4a4a; border-radius:3px; background:#1e1e1e; color:#e0e0e0; font-size:10px; }"
            "QProgressBar::chunk { background:#3a6ea8; border-radius:2px; }"
        )
        log_layout.addWidget(self.progress_label)
        log_layout.addWidget(self.batch_progress_bar)
        log_layout.addWidget(self.log_text, 1)
        self.open_folder_btn = QPushButton("Open Output Folder")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        log_layout.addWidget(self.open_folder_btn)

        right_splitter.addWidget(preview_widget)
        right_splitter.addWidget(log_widget)
        right_splitter.setSizes([540, 220])

        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(right_splitter)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([380, 900])
        root.addWidget(self.main_splitter)

    def _build_load_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 8, 0, 0)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["PL", "Reflection"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        form.addRow("Mode:", self.mode_combo)

        self.csv_edit = CsvDropLineEdit()
        self.csv_edit.setPlaceholderText("Select input CSV...")
        self.csv_edit.textChanged.connect(self._on_csv_text_changed)
        self.csv_edit.editingFinished.connect(self._on_csv_path_changed)
        self.csv_edit.csv_paths_dropped.connect(self._on_primary_csv_dropped)
        csv_btn = QPushButton("Browse")
        csv_btn.clicked.connect(self._browse_csv)
        form.addRow("CSV file:", self._hrow(self.csv_edit, csv_btn))

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Output folder...")
        self.out_edit.editingFinished.connect(self._on_output_dir_changed)
        out_btn = QPushButton("Browse")
        out_btn.clicked.connect(self._browse_output)
        form.addRow("Output dir:", self._hrow(self.out_edit, out_btn))

        self.vbg_combo = QComboBox()
        self.vtg_combo = QComboBox()
        axis_help = (
            "Raw gate sweeps: Axis X should be BG/Vbg and Axis Y should be TG/Vtg. "
            "Transformed files: Axis X should be doping and Axis Y should be efield."
        )
        self.vbg_combo.setToolTip(axis_help)
        self.vtg_combo.setToolTip(axis_help)
        self._sweep_x_label = QLabel("Axis X column:")
        self._sweep_y_label = QLabel("Axis Y column:")
        self._sweep_x_label.setToolTip(axis_help)
        self._sweep_y_label.setToolTip(axis_help)
        self.vbg_combo.currentTextChanged.connect(self._on_gate_columns_changed)
        self.vtg_combo.currentTextChanged.connect(self._on_gate_columns_changed)
        form.addRow(self._sweep_x_label, self.vbg_combo)
        form.addRow(self._sweep_y_label, self.vtg_combo)

        self.load_csv_btn = QPushButton("Load CSV")
        self.load_csv_btn.clicked.connect(self._start_csv_load)
        form.addRow("", self.load_csv_btn)

        self.summary_label = QLabel("No CSV loaded.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color:#5a7088;")
        form.addRow("Summary:", self.summary_label)
        return group

    def _build_background_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 8, 0, 0)
        
        self.bg_csv_edit = CsvDropLineEdit(allow_multiple=True)
        self.bg_csv_edit.setPlaceholderText("Select one or more background CSVs...")
        self.bg_csv_edit.textChanged.connect(self._on_background_text_changed)
        self.bg_csv_edit.csv_paths_dropped.connect(self._on_background_csvs_dropped)
        bg_btn = QPushButton("Browse")
        bg_btn.clicked.connect(self._browse_background_csv)
        form.addRow("Background CSV:", self._hrow(self.bg_csv_edit, bg_btn))

        self.bg_average_mode_combo = QComboBox()
        self.bg_average_mode_combo.addItem("Average all frames", "all_frames")
        self.bg_average_mode_combo.addItem("Average first frame per CSV", "first_frame")
        self.bg_average_mode_combo.addItem("Average last frame per CSV", "last_frame")
        form.addRow("Background mode:", self.bg_average_mode_combo)
        
        self.load_bg_btn = QPushButton("Load Background")
        self.load_bg_btn.clicked.connect(self._start_background_load)
        form.addRow("", self.load_bg_btn)
        
        self.bg_status_label = QLabel("No background loaded.")
        self.bg_status_label.setWordWrap(True)
        self.bg_status_label.setStyleSheet("color:#5a7088;")
        form.addRow("Status:", self.bg_status_label)
        
        return group

    def _build_analysis_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(6)
        form.setContentsMargins(0, 8, 0, 0)
        self.analysis_group = group

        self.int_min_spin = self._dspin(0.01, 10.0, 0.01, 3, 1.247)
        self.int_max_spin = self._dspin(0.01, 10.0, 0.01, 3, 1.428)
        self.baseline_spin = self._dspin(0.0, 1e6, 1.0, 2, 595.0)
        self.ratio_spin = self._dspin(0.001, 100.0, 0.01, 4, 1.0)
        self.int_min_spin.valueChanged.connect(self._on_energy_window_changed)
        self.int_max_spin.valueChanged.connect(self._on_energy_window_changed)
        self.baseline_spin.valueChanged.connect(self._on_baseline_changed)
        self.ratio_spin.valueChanged.connect(self._on_ratio_changed)
        self.auto_baseline_check = QCheckBox("Auto")
        self.auto_baseline_check.setChecked(True)
        self.auto_baseline_check.toggled.connect(self._on_auto_baseline_toggled)
        self.estimate_baseline_btn = QPushButton("Estimate")
        self.estimate_baseline_btn.clicked.connect(lambda: self._estimate_and_apply_baseline())
        self.baseline_spin.setEnabled(False)

        self.sg_window_spin = QSpinBox()
        self.sg_window_spin.setRange(3, 501)
        self.sg_window_spin.setSingleStep(2)
        self.sg_window_spin.setValue(31)
        self.sg_window_spin.valueChanged.connect(self._on_peak_settings_changed)

        self.sg_poly_spin = QSpinBox()
        self.sg_poly_spin.setRange(0, 10)
        self.sg_poly_spin.setValue(3)
        self.sg_poly_spin.valueChanged.connect(self._on_peak_settings_changed)

        # RC preview spinboxes (separate rows so they fit the sidebar width)
        self.reflection_preview_vbg_spin = self._dspin(-1e4, 1e4, 0.1, 3, 0.0)
        self.reflection_preview_vtg_spin = self._dspin(-1e4, 1e4, 0.1, 3, 0.0)
        self.preview_rc_btn = QPushButton("Preview RC Spectrum")
        self.preview_rc_btn.clicked.connect(self._preview_reflection_spectra)

        self.reflection_preview_status_label = QLabel(
            "Load CSV + background, then preview an RC spectrum at the chosen sweep coordinates."
        )
        self.reflection_preview_status_label.setWordWrap(True)
        self.reflection_preview_status_label.setStyleSheet("color:#5a7088;")

        self.convention_combo = QComboBox()
        self.convention_combo.addItems([
            "D = TG + r·BG,  E = TG − r·BG",
            "D = r·TG + BG,  E = r·TG − BG",
        ])
        self.convention_combo.currentIndexChanged.connect(self._on_convention_changed)

        self.formula_label = QLabel(self._formula_text())
        self.formula_label.setWordWrap(True)
        self.formula_label.setStyleSheet("color:#5a7088; font-size:9px;")

        self.analysis_status_label = QLabel("Load a CSV to start.")
        self.analysis_status_label.setWordWrap(True)
        self.analysis_status_label.setStyleSheet("color:#5a7088;")

        # --- energy window and shared settings (always visible) ---
        form.addRow("E min (eV):", self.int_min_spin)
        form.addRow("E max (eV):", self.int_max_spin)

        # Baseline row – keep a reference so we can hide it in Reflection mode
        self.baseline_form_label = QLabel("Baseline:")
        self.baseline_row_widget = self._hrow(
            self.baseline_spin,
            self.auto_baseline_check,
            self.estimate_baseline_btn,
        )
        form.addRow(self.baseline_form_label, self.baseline_row_widget)

        form.addRow("Ratio:", self.ratio_spin)
        form.addRow("Convention:", self.convention_combo)
        form.addRow("", self.formula_label)

        # --- RC-specific rows (shown only when mode == "Reflection") ---
        self._rc_vbg_label = QLabel("Preview X:")
        form.addRow(self._rc_vbg_label, self.reflection_preview_vbg_spin)

        self._rc_vtg_label = QLabel("Preview Y:")
        form.addRow(self._rc_vtg_label, self.reflection_preview_vtg_spin)

        self._rc_btn_placeholder = QLabel("")
        form.addRow(self._rc_btn_placeholder, self.preview_rc_btn)

        self._rc_status_row_label = QLabel("RC preview:")
        form.addRow(self._rc_status_row_label, self.reflection_preview_status_label)

        # Peak-smoothing parameters
        form.addRow("SG window:", self.sg_window_spin)
        form.addRow("SG poly:", self.sg_poly_spin)
        form.addRow("Status:", self.analysis_status_label)

        # Hide RC rows by default (PL mode)
        self._rc_sidebar_widgets = [
            self._rc_vbg_label, self.reflection_preview_vbg_spin,
            self._rc_vtg_label, self.reflection_preview_vtg_spin,
            self._rc_btn_placeholder, self.preview_rc_btn,
            self._rc_status_row_label, self.reflection_preview_status_label,
        ]
        for w in self._rc_sidebar_widgets:
            w.setVisible(False)

        return group

    def _build_export_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 8, 0, 0)
        self.export_group = group

        self.save_current_png_btn = QPushButton("Save Current PNG")
        self.save_current_png_btn.clicked.connect(lambda: self._save_current_view("png"))
        self.save_current_csv_btn = QPushButton("Save Current CSV")
        self.save_current_csv_btn.clicked.connect(lambda: self._save_current_view("csv"))
        self.save_all_maps_btn = QPushButton("Save All Maps")
        self.save_all_maps_btn.clicked.connect(self._save_all_maps)
        self.save_lines_png_btn = QPushButton("Save Line-Cut PNG")
        self.save_lines_png_btn.clicked.connect(self._save_lines_png)
        self.save_lines_csv_btn = QPushButton("Save Line-Cut CSVs")
        self.save_lines_csv_btn.clicked.connect(self._save_lines_csvs)

        layout.addWidget(self._hrow(self.save_current_png_btn, self.save_current_csv_btn))
        layout.addWidget(self.save_all_maps_btn)
        layout.addWidget(self._hrow(self.save_lines_png_btn, self.save_lines_csv_btn))
        return group

    def _build_intensity_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 8, 0, 0)
        self.intensity_group = group

        self.int_min_spin = self._dspin(0.01, 10.0, 0.01, 3, 1.25)
        self.int_max_spin = self._dspin(0.01, 10.0, 0.01, 3, 1.425)
        self.baseline_spin = self._dspin(0.0, 1e6, 1.0, 0, 595.0)
        self.int_min_spin.valueChanged.connect(self._on_energy_window_changed)
        self.int_max_spin.valueChanged.connect(self._on_energy_window_changed)
        self.baseline_spin.valueChanged.connect(self._on_intensity_settings_changed)

        self.plot_original_btn = QPushButton("Plot Original Map")
        self.plot_original_btn.clicked.connect(self._start_intensity_stage)
        self.plot_original_btn.setProperty("class", "primary")
        self.plot_original_btn.style().unpolish(self.plot_original_btn)
        self.plot_original_btn.style().polish(self.plot_original_btn)
        self.save_original_png_btn = QPushButton("Save PNG")
        self.save_original_png_btn.clicked.connect(lambda: self._save_map("original", "png"))
        self.save_original_csv_btn = QPushButton("Save CSV")
        self.save_original_csv_btn.clicked.connect(lambda: self._save_map("original", "csv"))

        form.addRow("E min (eV):", self.int_min_spin)
        form.addRow("E max (eV):", self.int_max_spin)
        form.addRow("Baseline:", self.baseline_spin)
        form.addRow("", self.plot_original_btn)
        form.addRow("", self._hrow(self.save_original_png_btn, self.save_original_csv_btn))
        return group

    def _build_transform_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 8, 0, 0)
        self.transform_group = group

        self.plot_transformed_btn = QPushButton("Plot Transformed Map")
        self.plot_transformed_btn.clicked.connect(self._start_transform_stage)
        self.plot_transformed_btn.setProperty("class", "primary")
        self.plot_transformed_btn.style().unpolish(self.plot_transformed_btn)
        self.plot_transformed_btn.style().polish(self.plot_transformed_btn)
        self.save_transformed_png_btn = QPushButton("Save PNG")
        self.save_transformed_png_btn.clicked.connect(lambda: self._save_map("transformed", "png"))
        self.save_transformed_csv_btn = QPushButton("Save CSV")
        self.save_transformed_csv_btn.clicked.connect(lambda: self._save_map("transformed", "csv"))

        form.addRow("", self.plot_transformed_btn)
        form.addRow("", self._hrow(self.save_transformed_png_btn, self.save_transformed_csv_btn))
        return group

    def _build_peak_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 8, 0, 0)
        self.peak_group = group

        self.sg_window_spin = QSpinBox()
        self.sg_window_spin.setRange(3, 501)
        self.sg_window_spin.setSingleStep(2)
        self.sg_window_spin.setValue(31)
        self.sg_window_spin.valueChanged.connect(self._on_peak_settings_changed)

        self.sg_poly_spin = QSpinBox()
        self.sg_poly_spin.setRange(0, 10)
        self.sg_poly_spin.setValue(3)
        self.sg_poly_spin.valueChanged.connect(self._on_peak_settings_changed)

        self.peak_axes_combo = QComboBox()
        self.peak_axes_combo.addItems(["original", "transformed"])
        self.peak_axes_combo.currentTextChanged.connect(self._on_peak_axes_requested)

        self.plot_peak_btn = QPushButton("Plot Peak Map")
        self.plot_peak_btn.clicked.connect(self._start_peak_stage)
        self.plot_peak_btn.setProperty("class", "primary")
        self.plot_peak_btn.style().unpolish(self.plot_peak_btn)
        self.plot_peak_btn.style().polish(self.plot_peak_btn)
        self.save_peak_png_btn = QPushButton("Save PNG")
        self.save_peak_png_btn.clicked.connect(self._save_peak_png)
        self.save_peak_csv_btn = QPushButton("Save CSV")
        self.save_peak_csv_btn.clicked.connect(self._save_peak_csv)

        form.addRow("SG window:", self.sg_window_spin)
        form.addRow("SG poly order:", self.sg_poly_spin)
        form.addRow("Axes:", self.peak_axes_combo)
        form.addRow("", self.plot_peak_btn)
        form.addRow("", self._hrow(self.save_peak_png_btn, self.save_peak_csv_btn))
        return group

    def _build_linecuts_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 8, 0, 0)
        self.linecuts_group = group

        self.cuts_table = QTableWidget(0, 3)
        self.cuts_table.setHorizontalHeaderLabels(["Type", "Const. value (V)", "Epsilon (V)"])
        header = self.cuts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.cuts_table.setColumnWidth(0, 96)
        self.cuts_table.setColumnWidth(2, 90)
        self.cuts_table.verticalHeader().setVisible(False)
        self.cuts_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.cuts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.cuts_table.itemChanged.connect(self._on_linecut_item_changed)
        layout.addWidget(self.cuts_table)

        self.plot_lines_btn = QPushButton("Extract Line Cuts")
        self.plot_lines_btn.clicked.connect(self._start_line_stage)
        self.plot_lines_btn.setProperty("class", "primary")
        self.plot_lines_btn.style().unpolish(self.plot_lines_btn)
        self.plot_lines_btn.style().polish(self.plot_lines_btn)
        layout.addWidget(self.plot_lines_btn)

        self.batch_epsilon_spin = self._dspin(0.0, 1.0, 0.01, 3, 0.0)
        self.extract_all_doping_btn = QPushButton("All Doping")
        self.extract_all_doping_btn.clicked.connect(
            lambda: self._start_batch_line_stage(["doping"])
        )
        self.extract_all_efield_btn = QPushButton("All Efield")
        self.extract_all_efield_btn.clicked.connect(
            lambda: self._start_batch_line_stage(["efield"])
        )
        self.extract_all_both_btn = QPushButton("All (Both)")
        self.extract_all_both_btn.clicked.connect(
            lambda: self._start_batch_line_stage(self._batch_cut_types(["axis1", "axis2"]))
        )
        self.batch_preview_btn = QPushButton("Preview")
        self.batch_preview_btn.setToolTip("Count how many line cuts (and output files) each batch will produce.")
        self.batch_preview_btn.clicked.connect(self._update_batch_preview)
        eps_label = QLabel("Batch ε:")
        layout.addWidget(self._hrow(eps_label, self.batch_epsilon_spin, self.batch_preview_btn))
        layout.addWidget(self._hrow(self.extract_all_doping_btn, self.extract_all_efield_btn, self.extract_all_both_btn))

        self.batch_preview_label = QLabel("")
        self.batch_preview_label.setWordWrap(True)
        self.batch_preview_label.setStyleSheet("color:#5a7088; font-family: monospace;")
        layout.addWidget(self.batch_preview_label)

        self.linecuts_status_label = QLabel("Line cuts use the transformed coordinate view and the current ratio setting.")
        self.linecuts_status_label.setWordWrap(True)
        self.linecuts_status_label.setStyleSheet("color:#5a7088;")
        layout.addWidget(self.linecuts_status_label)

        self._add_cut("doping", 0.0, 0.0)
        return group

    def _resize_linecuts_table(self) -> None:
        """Keep the line-cut table compact until enough rows need scrolling."""
        if not hasattr(self, "cuts_table"):
            return
        row_count = max(1, self.cuts_table.rowCount())
        visible_rows = min(row_count, 4)
        header_height = max(
            self.cuts_table.horizontalHeader().height(),
            self.cuts_table.horizontalHeader().sizeHint().height(),
        )
        row_height = max(
            self.cuts_table.verticalHeader().defaultSectionSize(),
            self.cuts_table.sizeHintForRow(0) if self.cuts_table.rowCount() else 0,
            28,
        )
        frame = self.cuts_table.frameWidth() * 2
        height = header_height + visible_rows * row_height + frame + 6
        self.cuts_table.setMinimumHeight(height)
        self.cuts_table.setMaximumHeight(height)

    @staticmethod
    def _hrow(*widgets) -> QWidget:
        row = QWidget()
        row.setProperty("class", "inlineRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for widget in widgets:
            layout.addWidget(widget)
        return row

    @staticmethod
    def _dspin(lo: float, hi: float, step: float, decimals: int, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setValue(value)
        return spin

    def _mark_dirty(self, *keys: str) -> None:
        for key in keys:
            self._dirty_views[key] = True

    def _mark_clean(self, *keys: str) -> None:
        for key in keys:
            self._dirty_views[key] = False

    def _current_view_key(self) -> str:
        map_kind = "intensity" if self.map_type_combo.currentIndex() == 0 else "peak"
        axes = "original" if self.map_axes_combo.currentText() == "Original" else "transformed"
        return f"{map_kind}_{axes}"

    def _current_view_description(self) -> str:
        if self.map_type_combo.currentIndex() == 0:
            label = "RC Peak-to-Peak" if self.state.mode == "Reflection" else "Intensity"
        else:
            label = "RC Peak Position" if self.state.mode == "Reflection" else "Peak Energy"
        return f"{label} on {self.map_axes_combo.currentText().lower()} axes"

    def _required_tasks_for_view(self, view_key: str) -> list[str]:
        match view_key:
            case "intensity_original":
                return ["intensity_original"]
            case "intensity_transformed":
                return ["intensity_original", "intensity_transformed"]
            case "peak_original":
                return ["intensity_original", "peak_original"]
            case "peak_transformed":
                return ["intensity_original", "intensity_transformed", "peak_transformed"]
        return ["intensity_original"]

    def _current_map_payload(self) -> dict | None:
        view_key = self._current_view_key()
        mapping = {
            "intensity_original": self.state.original_map,
            "intensity_transformed": self.state.transformed_map,
            "peak_original": self.state.peak_map_original,
            "peak_transformed": self.state.peak_map_transformed,
        }
        return mapping.get(view_key)

    def _current_map_figure(self):
        view_key = self._current_view_key()
        key_map = {
            "intensity_original": "original_map",
            "intensity_transformed": "transformed_map",
            "peak_original": "peak_map_original",
            "peak_transformed": "peak_map_transformed",
        }
        return self.state.figures.get(key_map[view_key])

    def _sync_color_limit_controls(self) -> None:
        """Show the current map's actual finite data range while auto-scale is on."""
        if not hasattr(self, "map_vmin_spin") or not self.map_auto_scale_check.isChecked():
            return
        payload = self._current_map_payload()
        if payload is None or "Z2D" not in payload:
            return
        z_data = np.asarray(payload["Z2D"], dtype=float)
        finite = z_data[np.isfinite(z_data)]
        if finite.size == 0:
            return
        vmin = float(np.min(finite))
        vmax = float(np.max(finite))
        old_vmin_block = self.map_vmin_spin.blockSignals(True)
        old_vmax_block = self.map_vmax_spin.blockSignals(True)
        self.map_vmin_spin.setValue(vmin)
        self.map_vmax_spin.setValue(vmax)
        self.map_vmin_spin.blockSignals(old_vmin_block)
        self.map_vmax_spin.blockSignals(old_vmax_block)

    def _show_current_map_view(self) -> None:
        figure = self._current_map_figure()
        if figure is None:
            self.map_plot_tab.clear()
        else:
            self.map_plot_tab.set_figure(figure)
        self._sync_color_limit_controls()
        self._update_status_labels()

    def _on_map_selection_changed(self, _value: str) -> None:
        self._show_current_map_view()
        self.save_current_png_btn.setEnabled(self._current_map_figure() is not None)
        self.save_current_csv_btn.setEnabled(self._current_map_payload() is not None)

    def _update_status_labels(self) -> None:
        if self.state.data is None:
            self.analysis_status_label.setText("Load a CSV to start configuring the analysis.")
            if self.state.mode == "Reflection":
                self.map_status_label.setText("Load a reflection CSV and background, preview RC spectra, then refresh a map view.")
            else:
                self.map_status_label.setText("Load a CSV, choose settings, then refresh a map view.")
            self.linecuts_status_label.setText("Line cuts become available after a transformed map refresh.")
            return

        dirty_names = {
            "intensity_original": "intensity/original",
            "intensity_transformed": "intensity/transformed",
            "peak_original": "peak/original",
            "peak_transformed": "peak/transformed",
            "line_cuts": "line cuts",
        }
        dirty_list = [label for key, label in dirty_names.items() if self._dirty_views.get(key, False)]
        if dirty_list:
            self.analysis_status_label.setText("Needs refresh: " + ", ".join(dirty_list) + ".")
        else:
            self.analysis_status_label.setText("All cached views are up to date with the current settings.")

        current_key = self._current_view_key()
        if self._dirty_views.get(current_key, True):
            self.map_status_label.setText(
                f"{self._current_view_description()} is stale. Use Refresh Current View to update it."
            )
        elif self._current_map_figure() is None:
            self.map_status_label.setText(
                f"{self._current_view_description()} has not been generated yet."
            )
        else:
            self.map_status_label.setText(
                f"Showing {self._current_view_description()}."
            )

        if self._dirty_views.get("line_cuts", True):
            if self.state.data.get("axis_space") == "transformed":
                self.linecuts_status_label.setText(
                    "Line cuts are stale or not extracted yet. Loaded D/E axes are ready for extraction."
                )
            else:
                self.linecuts_status_label.setText(
                    "Line cuts are stale or not extracted yet. Refresh the transformed map first, then extract cuts."
                )
        else:
            self.linecuts_status_label.setText("Line cuts match the current transformed coordinate settings.")

    def _refresh_current_map_view(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before refreshing map views.", "error")
            return
        if self.int_min_spin.value() >= self.int_max_spin.value():
            self._append_log("Intensity range is invalid: E min must be less than E max.", "error")
            return
        if not self._validate_reflection_background_ready():
            return
        view_key = self._current_view_key()
        tasks = self._required_tasks_for_view(view_key)
        self._start_analysis_refresh(tasks, f"Refreshing {self._current_view_description()}")

    def _refresh_all_maps(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before refreshing map views.", "error")
            return
        if self.int_min_spin.value() >= self.int_max_spin.value():
            self._append_log("Intensity range is invalid: E min must be less than E max.", "error")
            return
        if not self._validate_reflection_background_ready():
            return
        tasks = [
            "intensity_original",
            "intensity_transformed",
            "peak_original",
            "peak_transformed",
        ]
        self._start_analysis_refresh(tasks, "Refreshing all map views")

    def _start_analysis_refresh(self, tasks: list[str], context: str) -> None:
        worker = AnalysisRefreshWorker(
            self.state.data,
            self.int_min_spin.value(),
            self.int_max_spin.value(),
            self.baseline_spin.value(),
            self.ratio_spin.value(),
            self.sg_window_spin.value(),
            self.sg_poly_spin.value(),
            tasks,
            tg_is_y=True,
            mode=self.state.mode,
            background_spectra=self.state.background_spectra,
            convention=self._current_convention(),
        )
        self._run_worker(worker, self._on_analysis_refresh_ready, context=context)

    def _save_current_view(self, output_type: str) -> None:
        payload = self._current_map_payload()
        figure = self._current_map_figure()
        if payload is None or figure is None:
            self._append_log("The selected map view has not been generated yet.", "warn")
            return
        base = self._ensure_output_dir()
        source = self.state.data["source_name"]
        axes_suffix = payload.get("target_axes", "original")
        z_name = payload["z_name"]
        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
        e_tag = f"_{e_lo:.3f}to{e_hi:.3f}eV"
        path = os.path.join(base, f"{source}_{z_name}{e_tag}_{axes_suffix}.{output_type}")
        if output_type == "png":
            figure.savefig(path, dpi=300, bbox_inches="tight", transparent=True)
        else:
            save_map_csv(
                payload["X2D"],
                payload["Y2D"],
                payload["Z2D"],
                path,
                x_name=payload["x_name"],
                y_name=payload["y_name"],
                z_name=payload["z_name"],
            )
        self._append_log(f"Saved {os.path.basename(path)}", "success")

    def _save_all_maps(self) -> None:
        saved_any = False
        for kind in ("original", "transformed"):
            if (kind == "original" and self.state.original_map is not None) or (
                kind == "transformed" and self.state.transformed_map is not None
            ):
                self._save_map(kind, "png")
                self._save_map(kind, "csv")
                saved_any = True
        for axes in ("original", "transformed"):
            peak_map = self.state.peak_map_original if axes == "original" else self.state.peak_map_transformed
            if peak_map is not None:
                current_index = self.map_type_combo.currentIndex(), self.map_axes_combo.currentIndex()
                self.map_type_combo.setCurrentIndex(1)
                self.map_axes_combo.setCurrentText("Original" if axes == "original" else "Transformed")
                self._save_current_view("png")
                self._save_current_view("csv")
                self.map_type_combo.setCurrentIndex(current_index[0])
                self.map_axes_combo.setCurrentIndex(current_index[1])
                saved_any = True
        if not saved_any:
            self._append_log("No map views are available to save yet.", "warn")

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select megasweep CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self._set_primary_csv_path(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self.out_edit.text() or os.path.expanduser("~"),
        )
        if path:
            self.out_edit.setText(path)
            self._on_output_dir_changed()

    def _on_peak_preview_changed(self, index: int) -> None:
        if index == 1 and self.state.transformed_map is not None:
            self.peak_axes_combo.setCurrentText("transformed")
        else:
            self.peak_axes_combo.setCurrentText("original")

    def _on_peak_axes_requested(self, axes_mode: str) -> None:
        if axes_mode == "transformed" and self.state.transformed_map is not None:
            self.peak_plot_tabs.setCurrentWidget(self.peak_transformed_plot_tab)
        else:
            self.peak_plot_tabs.setCurrentWidget(self.peak_original_plot_tab)

    def _on_csv_path_changed(self) -> None:
        path = self.csv_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._refresh_stage_states()
            return
        try:
            columns = pd.read_csv(path, nrows=0).columns.tolist()
        except Exception as exc:
            self._append_log(f"ERROR reading CSV headers: {exc}", "error")
            self._refresh_stage_states()
            return

        gate_columns = self._extract_gate_columns(columns)
        y_guess, x_guess = self._guess_gate_columns(gate_columns)

        self._building_combos = True
        self.vbg_combo.clear()
        self.vtg_combo.clear()
        self.vbg_combo.addItems(gate_columns)
        self.vtg_combo.addItems(gate_columns)
        if x_guess:
            self.vbg_combo.setCurrentText(x_guess)
        if y_guess:
            self.vtg_combo.setCurrentText(y_guess)
        self._building_combos = False
        self._update_axis_ui_text()

        self.state.header_columns = columns
        self.state.gate_columns = gate_columns
        if not self.out_edit.text().strip():
            self.out_edit.setText(os.path.dirname(path))
            self._on_output_dir_changed()

        self._append_log(
            f"Headers detected. Auto-selected Axis X={self.vbg_combo.currentText()} and "
            f"Axis Y={self.vtg_combo.currentText()}. {self._axis_selection_status()['message']}",
            "info",
        )

        if self.state.data is not None and path != self.state.csv_path:
            self._invalidate_from_stage(1, "CSV path changed. Cached results were cleared.")
        else:
            self._refresh_stage_states()

    def _on_csv_text_changed(self, _text: str) -> None:
        self._refresh_stage_states()

    def _on_primary_csv_dropped(self, paths: list[str]) -> None:
        if not paths:
            return
        self._set_primary_csv_path(paths[0])

    def _on_output_dir_changed(self) -> None:
        self.state.output_dir = self.out_edit.text().strip()
        self.open_folder_btn.setEnabled(bool(self.state.output_dir))

    @staticmethod
    def _normalize_csv_paths(paths: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for raw_path in paths:
            cleaned = str(raw_path).strip().strip('"')
            if not cleaned:
                continue
            path = os.path.abspath(os.path.expanduser(cleaned))
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(path)
        return normalized

    @classmethod
    def _parse_csv_path_text(cls, text: str) -> list[str]:
        parts = []
        for line in text.splitlines():
            for token in line.split(";"):
                cleaned = token.strip()
                if cleaned:
                    parts.append(cleaned)
        return cls._normalize_csv_paths(parts)

    def _set_primary_csv_path(self, path: str) -> None:
        normalized_paths = self._normalize_csv_paths([path])
        if not normalized_paths:
            return
        self.csv_edit.setText(normalized_paths[0])
        self._on_csv_path_changed()

    def _set_background_paths(self, paths: list[str]) -> None:
        self._background_paths = self._normalize_csv_paths(paths)
        text = "; ".join(self._background_paths)
        self.bg_csv_edit.blockSignals(True)
        self.bg_csv_edit.setText(text)
        self.bg_csv_edit.blockSignals(False)
        self.bg_csv_edit.setToolTip("\n".join(self._background_paths))
        self._refresh_stage_states()

    def _get_background_paths(self) -> list[str]:
        typed_paths = self._parse_csv_path_text(self.bg_csv_edit.text())
        if typed_paths:
            self._background_paths = typed_paths
        return list(self._background_paths)

    def _on_background_text_changed(self, text: str) -> None:
        self._background_paths = self._parse_csv_path_text(text)
        self.bg_csv_edit.setToolTip("\n".join(self._background_paths))
        self._refresh_stage_states()

    def _on_background_csvs_dropped(self, paths: list[str]) -> None:
        self._set_background_paths(paths)

    def _clear_background_state(self, status_text: str = "No background loaded.") -> None:
        self.state.background_spectra = None
        self.state.background_wavelength = None
        self.state.background_path = ""
        self.state.background_paths = []
        self.bg_status_label.setText(status_text)

    def _validate_reflection_background_ready(self) -> bool:
        if self.state.mode != "Reflection":
            return True
        if self.state.background_spectra is None:
            self._append_log("Reflection mode requires a loaded background before RC maps or line cuts can be computed.", "error")
            return False
        if self.state.data is None:
            self._append_log("Load the reflection CSV before validating the background spectrum.", "error")
            return False
        background = np.asarray(self.state.background_spectra, dtype=float).reshape(-1)
        expected = int(self.state.data["Intensity"].shape[1])
        if background.shape[0] != expected:
            self._append_log(
                "Loaded background does not match the current reflection dataset. "
                f"Data has {expected} channels while the background has {background.shape[0]}. Reload a matching background CSV.",
                "error",
            )
            return False
        return True

    def _clear_reflection_preview(self) -> None:
        self._reflection_preview_message = None
        if self.state.figures.get("line_cuts") is None:
            self.line_plot_tab.clear()

    # (legacy method removed – use _preview_reflection_spectra instead)

    def _axis_selection_status(self) -> dict:
        x_name = self.vbg_combo.currentText().strip() or self.state.selected_x_col or "X"
        y_name = self.vtg_combo.currentText().strip() or self.state.selected_y_col or "Y"
        return validate_axis_selection(x_name, y_name)

    def _update_axis_ui_text(self) -> None:
        x_name = self.vbg_combo.currentText().strip() or self.state.selected_x_col or "X"
        y_name = self.vtg_combo.currentText().strip() or self.state.selected_y_col or "Y"

        self._sweep_x_label.setText(f"Axis X column ({x_name}):")
        self._sweep_y_label.setText(f"Axis Y column ({y_name}):")
        self._rc_vbg_label.setText(f"Preview {x_name}:")
        self._rc_vtg_label.setText(f"Preview {y_name}:")

        status = self._axis_selection_status()
        if status["mode"] == "raw_gate":
            mode_text = "Raw gates: X=BG/Vbg, Y=TG/Vtg"
        elif status["mode"] == "transformed":
            mode_text = "Transformed: X=doping, Y=efield"
        elif status["mode"].startswith("swapped"):
            mode_text = "Axis selection looks swapped"
        else:
            mode_text = status["message"]
        current_summary = self.summary_label.text().strip() if hasattr(self, "summary_label") else ""
        if not current_summary or current_summary == "No CSV loaded." or current_summary.startswith("Axis selection:") or current_summary.startswith("Sweep selection:"):
            self.summary_label.setText(f"Axis selection: X={x_name}, Y={y_name} | {mode_text}")

    def _on_gate_columns_changed(self) -> None:
        if self._building_combos:
            return
        self._update_axis_ui_text()
        if self.state.data is not None:
            self._invalidate_from_stage(1, "Gate-column selection changed. Cached analysis results were cleared.")

    def _preview_reflection_spectra(self) -> None:
        if self.state.mode != "Reflection":
            self._append_log("RC spectra preview is only available in Reflection mode.", "warn")
            return
        if self.state.data is None:
            self._append_log("Load a reflection CSV before previewing RC spectra.", "error")
            return
        if not self._validate_reflection_background_ready():
            return

        try:
            from scipy.signal import savgol_filter as _sgf
            from megasweep_analysis import compute_rc_peak_position as _rc_peak_pos

            rc_spectra = compute_rc_spectra(self.state.data["Intensity"], self.state.background_spectra)
            x_data = np.asarray(self.state.data["x_data"], dtype=float).reshape(-1)
            y_data = np.asarray(self.state.data["y_data"], dtype=float).reshape(-1)
            energy = np.asarray(self.state.data["energy"], dtype=float).reshape(-1)
            target_x = float(self.reflection_preview_vbg_spin.value())
            target_y = float(self.reflection_preview_vtg_spin.value())

            if x_data.size == 0 or y_data.size == 0 or rc_spectra.shape[0] == 0:
                raise ValueError("No reflection points are available for RC preview.")

            finite_mask = np.isfinite(x_data) & np.isfinite(y_data)
            if not np.any(finite_mask):
                raise ValueError("Reflection dataset does not contain any finite sweep-coordinate points.")

            finite_indices = np.flatnonzero(finite_mask)
            distances = (x_data[finite_mask] - target_x) ** 2 + (y_data[finite_mask] - target_y) ** 2
            row_index = int(finite_indices[int(np.argmin(distances))])
            actual_x = float(x_data[row_index])
            actual_y = float(y_data[row_index])
            spectrum = np.asarray(rc_spectra[row_index], dtype=float).reshape(-1)
        except Exception:
            self._append_log(traceback.format_exc(), "error")
            return

        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())

        # ── Smoothed spectrum ─────────────────────────────────────────────
        n_pts = spectrum.size
        win = min(21, n_pts if n_pts % 2 == 1 else n_pts - 1)
        win = max(5, win)
        if win >= n_pts:
            win = n_pts if n_pts % 2 == 1 else n_pts - 1
        try:
            spectrum_smooth = _sgf(spectrum, window_length=win, polyorder=2, mode="interp")
        except Exception:
            spectrum_smooth = spectrum.copy()

        # ── RC statistics inside the analysis window ──────────────────────
        win_mask = (energy >= e_lo) & (energy <= e_hi)
        if np.any(win_mask):
            rc_win = spectrum[win_mask]
            rc_max = float(np.nanmax(rc_win))
            rc_min = float(np.nanmin(rc_win))
            rc_p2p = rc_max - rc_min
            e_arr = energy[win_mask]
            e_max = float(e_arr[np.nanargmax(rc_win)])
            e_min_pt = float(e_arr[np.nanargmin(rc_win)])
        else:
            rc_max = rc_min = rc_p2p = float("nan")
            e_max = e_min_pt = float("nan")

        # ── Peak position (dominant feature) ─────────────────────────────
        try:
            pk_energy, pk_value = _rc_peak_pos(energy, spectrum, e_lo, e_hi)
        except Exception:
            pk_energy, pk_value = float("nan"), float("nan")

        # ── Plot ──────────────────────────────────────────────────────────
        fig = Figure(figsize=(7, 4.8))
        ax = fig.add_subplot(111)

        ax.plot(energy, spectrum, color="#93c5fd", linewidth=1.0, alpha=0.7, label="Raw RC")
        ax.plot(energy, spectrum_smooth, color="#1d4ed8", linewidth=1.8, label="Smoothed")
        ax.axvspan(e_lo, e_hi, color="#fef08a", alpha=0.25, label=f"Window [{e_lo:.3f}–{e_hi:.3f} eV]")

        if np.isfinite(rc_max) and np.isfinite(e_max):
            ax.scatter([e_max], [rc_max], color="#dc2626", zorder=5, s=50, label=f"Max {rc_max:.4f}")
        if np.isfinite(rc_min) and np.isfinite(e_min_pt):
            ax.scatter([e_min_pt], [rc_min], color="#2563eb", zorder=5, s=50, label=f"Min {rc_min:.4f}")
        if np.isfinite(rc_p2p):
            if np.isfinite(e_min_pt) and np.isfinite(rc_min) and np.isfinite(rc_max):
                ax.plot(
                    [e_min_pt, e_min_pt], [rc_min, rc_max],
                    color="black", linestyle="--", linewidth=1.2,
                    label=f"P2P = {rc_p2p:.4f}",
                )
        if np.isfinite(pk_energy) and np.isfinite(pk_value):
            ax.axvline(pk_energy, color="#16a34a", linestyle=":", linewidth=1.4)
            ax.annotate(
                f"Peak\n{pk_energy:.4f} eV",
                xy=(pk_energy, pk_value),
                xytext=(6, 6),
                textcoords="offset points",
                color="#15803d",
                fontsize=8,
            )

        ax.set_xlabel("Energy (eV)")
        ax.set_ylabel("RC (ΔI/I₀)")
        x_label = self.state.data.get("x_name", "X")
        y_label = self.state.data.get("y_name", "Y")
        ax.set_title(f"RC spectrum  {x_label} = {actual_x:.3f},  {y_label} = {actual_y:.3f}")
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()

        self.line_plot_tab.set_figure(fig)
        self.workspace_tabs.setCurrentIndex(1)

        p2p_str = f"{rc_p2p:.4f}" if np.isfinite(rc_p2p) else "n/a"
        pk_str = f"{pk_energy:.4f} eV" if np.isfinite(pk_energy) else "n/a"
        self._reflection_preview_message = (
            f"RC preview: {x_label}={actual_x:.3f}, {y_label}={actual_y:.3f} | "
            f"P2P={p2p_str} | Peak={pk_str}"
        )
        self.reflection_preview_status_label.setText(self._reflection_preview_message)

    def _on_intensity_settings_changed(self) -> None:
        if self.state.data is None:
            return
        self.state.original_map = None
        self.state.transformed_map = None
        self.state.figures.pop("original_map", None)
        self.state.figures.pop("transformed_map", None)
        self._mark_dirty("intensity_original", "intensity_transformed")
        self._show_current_map_view()
        self._append_log("Intensity settings changed. Intensity views need refresh.", "warn")
        self._refresh_stage_states()

    def _on_energy_window_changed(self) -> None:
        if not self._suppress_intensity_tracking:
            self._intensity_range_user_modified = True
        if self.state.mode == "Reflection":
            if self._reflection_preview_message is not None:
                # A preview is already visible — refresh it in-place with the new energy window
                self._preview_reflection_spectra()
            else:
                self._clear_reflection_preview()
        elif self.auto_baseline_check.isChecked() and self.state.data is not None:
            self._estimate_and_apply_baseline(log=False, mark_dirty=False)
        self._on_intensity_settings_changed()

    def _on_baseline_changed(self) -> None:
        if not self._suppress_baseline_tracking:
            self._baseline_user_modified = True
        self._on_intensity_settings_changed()

    def _on_auto_baseline_toggled(self, checked: bool) -> None:
        self.baseline_spin.setEnabled(not checked)
        if checked:
            self._baseline_user_modified = False
            self._estimate_and_apply_baseline()

    def _estimate_and_apply_baseline(self, log: bool = True, mark_dirty: bool = True) -> bool:
        if self.state.data is None:
            if log:
                self._append_log("Load a CSV before estimating the baseline.", "warn")
            return False
        if self.state.mode == "Reflection":
            return False

        try:
            baseline, info = estimate_global_baseline(
                self.state.data["Intensity"],
                self.state.data["energy"],
                self.int_min_spin.value(),
                self.int_max_spin.value(),
                return_info=True,
            )
        except Exception as exc:
            if log:
                self._append_log(f"Auto baseline estimate failed: {exc}", "error")
            return False

        self._suppress_baseline_tracking = True
        self.baseline_spin.setValue(baseline)
        self._suppress_baseline_tracking = False
        self._baseline_user_modified = not self.auto_baseline_check.isChecked()

        if log:
            level = "warn" if info.get("fallback") else "success"
            method = "full-spectrum fallback" if info.get("fallback") else "outside-window spectra"
            self._append_log(
                f"Baseline estimated: {baseline:.3f} counts/channel from {method} "
                f"({info.get('used_spectrum_count', info.get('spectrum_count'))} spectra, "
                f"{info.get('baseline_channels')} channels).",
                level,
            )
        if mark_dirty:
            self._on_intensity_settings_changed()
        return True

    def _on_ratio_changed(self) -> None:
        self.state.current_ratio = self.ratio_spin.value()
        if self.state.data is None:
            return
        if self.state.mode == "Reflection":
            self._clear_reflection_preview()
        self.state.transformed_map = None
        self.state.peak_map_transformed = None
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("transformed_map", None)
        self.state.figures.pop("peak_map_transformed", None)
        self.state.figures.pop("line_cuts", None)
        self.line_plot_tab.clear()
        self._mark_dirty("intensity_transformed", "peak_transformed", "line_cuts")
        self._append_log(
            "Ratio changed. Transformed views and line cuts need refresh.",
            "warn",
        )
        self._refresh_stage_states()

    def _on_convention_changed(self) -> None:
        self.formula_label.setText(self._formula_text())
        convention = self._current_convention()
        self.state.transform_convention = convention
        if self.state.data is None:
            return
        self.state.transformed_map = None
        self.state.peak_map_transformed = None
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("transformed_map", None)
        self.state.figures.pop("peak_map_transformed", None)
        self.state.figures.pop("line_cuts", None)
        self.line_plot_tab.clear()
        self._mark_dirty("intensity_transformed", "peak_transformed", "line_cuts")
        self._append_log(
            f"Axis convention changed to '{convention}'. Transformed views and line cuts need refresh.",
            "warn",
        )
        self._refresh_stage_states()

    def _current_convention(self) -> str:
        """Return the internal convention key for the current combo selection."""
        return "TG+rBG" if self.convention_combo.currentIndex() == 0 else "rTG+BG"

    def _formula_text(self) -> str:
        """Return the D/E definition text for the current convention."""
        idx = self.convention_combo.currentIndex() if hasattr(self, "convention_combo") else 0
        if idx == 0:
            return "D = TG + r·BG\nE = TG − r·BG"
        else:
            return "D = r·TG + BG\nE = r·TG − BG"

    def _axis_labels(self) -> tuple[str, str]:
        """Return (D label, E label) for the transformed map axes."""
        r = self.ratio_spin.value()
        if self._current_convention() == "TG+rBG":
            return f"TG + {r}·BG (V)", f"TG − {r}·BG (V)"
        else:
            return f"{r}·TG + BG (V)", f"{r}·TG − BG (V)"

    def _batch_cut_types(self, axes: list[str]) -> list[str]:
        """Map 'axis1' (D) / 'axis2' (E) to 'doping'/'efield' strings."""
        return [{"axis1": "doping", "axis2": "efield"}[a] for a in axes]

    def _batch_linecuts_ready(self) -> bool:
        """Return whether batch line cuts can be extracted from current axes."""
        if self.state.data is None:
            return False
        if self.state.data.get("axis_space") == "transformed":
            return True
        return self.state.transformed_map is not None and not self._dirty_views.get("intensity_transformed", True)

    def _on_peak_settings_changed(self) -> None:
        if self.state.data is None:
            return
        self.state.peak_map_original = None
        self.state.peak_map_transformed = None
        self.state.figures.pop("peak_map_original", None)
        self.state.figures.pop("peak_map_transformed", None)
        self._mark_dirty("peak_original", "peak_transformed")
        self._show_current_map_view()
        self._append_log("Peak settings changed. Peak views need refresh.", "warn")
        self._refresh_stage_states()

    def _on_linecut_settings_changed(self) -> None:
        if self.state.data is None:
            return
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("line_cuts", None)
        self.line_plot_tab.clear()
        self._mark_dirty("line_cuts")
        self._append_log("Line-cut settings changed. Re-extract cuts when ready.", "warn")
        self._refresh_stage_states()

    def _on_linecut_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 1:
            self._snap_linecut_row_value(item.row())
        else:
            self._on_linecut_settings_changed()

    def _on_linecut_type_changed(self, combo: QComboBox) -> None:
        for row in range(self.cuts_table.rowCount()):
            if self.cuts_table.cellWidget(row, 0) is combo:
                self._snap_linecut_row_value(row)
                return
        self._on_linecut_settings_changed()

    def _nearest_cut_value(self, cut_type: str, requested: float, epsilon: float) -> float | None:
        data = self.state.data
        if data is None:
            return None
        values = find_all_cut_values(
            data["x_data"],
            data["y_data"],
            cut_type,
            self.state.current_ratio,
            epsilon,
            convention=self._current_convention(),
            axis_space=data.get("axis_space", "gate"),
            x_axis_name=data.get("x_name", ""),
            y_axis_name=data.get("y_name", ""),
        )
        if not values:
            return None
        arr = np.asarray(values, dtype=float)
        distances = np.abs(arr - requested)
        min_dist = np.min(distances)
        return float(arr[distances == min_dist][0])

    def _snap_linecut_row_value(self, row: int) -> None:
        if self.state.data is None:
            self._on_linecut_settings_changed()
            return
        combo = self.cuts_table.cellWidget(row, 0)
        value_item = self.cuts_table.item(row, 1)
        eps_item = self.cuts_table.item(row, 2)
        if combo is None or value_item is None or eps_item is None:
            self._on_linecut_settings_changed()
            return

        try:
            requested = float(value_item.text())
            epsilon = float(eps_item.text())
        except ValueError:
            self._on_linecut_settings_changed()
            return

        snapped = self._nearest_cut_value(combo.currentText(), requested, epsilon)
        if snapped is None:
            self.linecuts_status_label.setText("No existing line-cut values are available for snapping.")
            self._on_linecut_settings_changed()
            return

        if not np.isclose(snapped, requested, rtol=0.0, atol=5e-7):
            self.cuts_table.blockSignals(True)
            value_item.setText(f"{snapped:.6g}")
            self.cuts_table.blockSignals(False)
            self.linecuts_status_label.setText(
                f"Snapped {combo.currentText()} cut from {requested:.4f} to {snapped:.4f} V."
            )

        self._on_linecut_settings_changed()

    def _extract_gate_columns(self, columns: list[str]) -> list[str]:
        gate_columns = []
        for column in columns:
            try:
                float(column)
            except ValueError:
                gate_columns.append(column)
        return gate_columns or columns[:2]

    def _guess_gate_columns(self, gate_columns: list[str]) -> tuple[str, str]:
        def pick_role(role: str, exclude: str = "") -> str:
            for column in gate_columns:
                if column == exclude:
                    continue
                if classify_axis_role(column) == role:
                    return column
            for column in gate_columns:
                if column != exclude:
                    return column
            return ""

        transformed_x = pick_role("doping")
        transformed_y = pick_role("efield", exclude=transformed_x)
        if transformed_x and transformed_y:
            return transformed_y, transformed_x

        vtg = pick_role("tg")
        vbg = pick_role("bg", exclude=vtg)
        if not vbg:
            vbg = pick_role("unknown", exclude=vtg)
        if not vtg:
            vtg = pick_role("unknown", exclude=vbg)
        return vtg, vbg

    def _collect_line_specs(self) -> list[dict]:
        specs = []
        for row in range(self.cuts_table.rowCount()):
            combo = self.cuts_table.cellWidget(row, 0)
            value_item = self.cuts_table.item(row, 1)
            eps_item = self.cuts_table.item(row, 2)
            if combo is None or value_item is None or eps_item is None:
                continue
            try:
                specs.append(
                    {
                        "cut_type": combo.currentText(),
                        "c_value": float(value_item.text()),
                        "epsilon": float(eps_item.text()),
                    }
                )
            except ValueError:
                self._append_log(f"Skipping invalid line cut row {row + 1}.", "warn")
        return specs

    def _add_cut(self, cut_type: str, c_value: float, epsilon: float) -> None:
        row = self.cuts_table.rowCount()
        self.cuts_table.insertRow(row)
        combo = QComboBox()
        combo.addItems(["doping", "efield"])
        combo.setCurrentText(cut_type)
        combo.currentTextChanged.connect(lambda _text, c=combo: self._on_linecut_type_changed(c))
        self.cuts_table.setCellWidget(row, 0, combo)
        self.cuts_table.setItem(row, 1, QTableWidgetItem(str(c_value)))
        self.cuts_table.setItem(row, 2, QTableWidgetItem(str(epsilon)))
        self._resize_linecuts_table()

    def _remove_selected_cut(self) -> None:
        rows = sorted({index.row() for index in self.cuts_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.cuts_table.removeRow(row)
        self._resize_linecuts_table()
        self._on_linecut_settings_changed()

    def _start_csv_load(self) -> None:
        csv_path = self.csv_edit.text().strip()
        if not csv_path or not os.path.isfile(csv_path):
            self._append_log("Select a valid CSV file first.", "error")
            return

        vbg = self.vbg_combo.currentText()
        vtg = self.vtg_combo.currentText()
        if not vbg or not vtg:
            self._append_log("Select both sweep-axis columns before loading.", "error")
            return

        axis_status = validate_axis_selection(vbg, vtg)
        if not axis_status["ok"]:
            self._append_log(axis_status["message"], "error")
            QMessageBox.warning(self, "Axis Selection", axis_status["message"])
            return
        if axis_status["mode"].startswith("unknown"):
            self._append_log(axis_status["message"], "warn")

        self.state.csv_path = csv_path
        csv_stem = os.path.splitext(os.path.basename(csv_path))[0]
        self.state.output_dir = os.path.join(os.path.dirname(csv_path), f"{csv_stem}_outputs")
        self.out_edit.setText(self.state.output_dir)
        self.state.selected_x_col = vbg
        self.state.selected_y_col = vtg
        if axis_status["mode"] == "raw_gate":
            self.state.selected_bg_col = vbg
            self.state.selected_tg_col = vtg
        else:
            self.state.selected_bg_col = ""
            self.state.selected_tg_col = ""

        worker = CsvLoadWorker(csv_path, x_col=vbg, y_col=vtg)
        self._run_worker(worker, self._on_csv_loaded, context="Loading CSV")

    def _start_intensity_stage(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before plotting the original map.", "error")
            return
        if self.int_min_spin.value() >= self.int_max_spin.value():
            self._append_log("Intensity range is invalid: E min must be less than E max.", "error")
            return

        worker = IntensityWorker(
            self.state.data,
            self.int_min_spin.value(),
            self.int_max_spin.value(),
            self.baseline_spin.value(),
        )
        self._run_worker(worker, self._on_intensity_ready, context="Stage 2: building original map")

    def _start_transform_stage(self) -> None:
        if self.state.original_map is None:
            self._append_log("Plot the original intensity map first.", "error")
            return
        worker = TransformWorker(
            self.state.original_map,
            self.ratio_spin.value(),
            tg_is_y=True,
            convention=self._current_convention(),
        )
        self._run_worker(worker, self._on_transform_ready, context="Stage 3: building transformed map")

    def _start_peak_stage(self) -> None:
        if self.state.original_map is None:
            self._append_log("Plot the original map before computing the peak map.", "error")
            return
        axes_mode = self.peak_axes_combo.currentText()
        if axes_mode == "transformed" and self.state.transformed_map is None:
            self._append_log("Run Stage 3 before requesting a transformed-axis peak map.", "error")
            return

        worker = PeakWorker(
            self.state.data,
            self.sg_window_spin.value(),
            self.sg_poly_spin.value(),
            self.state.original_map,
            self.state.transformed_map,
            axes_mode,
        )
        self._run_worker(worker, self._on_peak_ready, context="Stage 4: computing peak map")

    def _start_line_stage(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before extracting line cuts.", "error")
            return
        if not self._validate_reflection_background_ready():
            return
        specs = self._collect_line_specs()
        if not specs:
            self._append_log("Add at least one valid line cut row.", "error")
            return
        worker = LineWorker(
            self.state.data,
            specs,
            self.state.current_ratio,
            tg_is_y=True,
            background_spectra=self.state.background_spectra if self.state.mode == "Reflection" else None,
            convention=self._current_convention(),
        )
        self._run_worker(worker, self._on_lines_ready, context="Extracting line cuts")

    def _update_batch_preview(self) -> None:
        data = self.state.data
        if data is None:
            self.batch_preview_label.setText("No data loaded.")
            return
        x = data["x_data"]
        y = data["y_data"]
        ratio = self.state.current_ratio
        epsilon = self.batch_epsilon_spin.value()
        convention = self._current_convention()
        try:
            axis_space = data.get("axis_space", "gate")
            x_name = data.get("x_name", "")
            y_name = data.get("y_name", "")

            def _find_values(cut_type: str, *, dominant_lattice_only: bool = True):
                return find_all_cut_values(
                    x, y, cut_type, ratio, epsilon,
                    convention=convention,
                    axis_space=axis_space,
                    x_axis_name=x_name,
                    y_axis_name=y_name,
                    dominant_lattice_only=dominant_lattice_only,
                )

            doping_vals = _find_values("doping")
            efield_vals = _find_values("efield")
            if axis_space == "gate":
                doping_skipped = max(
                    0,
                    len(_find_values("doping", dominant_lattice_only=False)) - len(doping_vals),
                )
                efield_skipped = max(
                    0,
                    len(_find_values("efield", dominant_lattice_only=False)) - len(efield_vals),
                )
            else:
                doping_skipped = 0
                efield_skipped = 0
        except Exception as exc:
            self.batch_preview_label.setText(f"Preview error: {exc}")
            return

        def _range_str(vals):
            if not vals:
                return "(none)"
            if len(vals) == 1:
                return f"{vals[0]:.3f}"
            return f"{vals[0]:.3f} … {vals[-1]:.3f}"

        n_doping = len(doping_vals)
        n_efield = len(efield_vals)
        label_lines = [
            f"Doping : {n_doping} cuts   [{_range_str(doping_vals)}]",
            f"Efield : {n_efield} cuts   [{_range_str(efield_vals)}]",
            f"Both   : {n_doping + n_efield} cuts total  (see log for values)",
        ]
        if doping_skipped or efield_skipped:
            label_lines.append(
                f"Skipped off-lattice: Doping {doping_skipped}, Efield {efield_skipped}"
            )
        self.batch_preview_label.setText("\n".join(label_lines))

        def _log_vals(label, vals):
            if not vals:
                self._append_log(f"{label}: (none)", "info")
                return
            chunk_size = 10
            chunks = [vals[i:i + chunk_size] for i in range(0, len(vals), chunk_size)]
            self._append_log(f"{label} ({len(vals)} values):", "info")
            for chunk in chunks:
                self._append_log("  " + ",  ".join(f"{v:.3f}" for v in chunk), "info")

        self._append_log(f"── Batch preview  (epsilon={epsilon}) ──", "info")
        if doping_skipped or efield_skipped:
            self._append_log(
                f"Skipped off-lattice batch cuts: Doping {doping_skipped}, Efield {efield_skipped}",
                "info",
            )
        _log_vals("Doping", doping_vals)
        _log_vals("Efield", efield_vals)

    def _start_batch_line_stage(self, cut_types: list[str]) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before batch-extracting line cuts.", "error")
            return
        if not self._batch_linecuts_ready():
            self._append_log("Refresh the transformed map with the current settings before batch-extracting line cuts.", "error")
            return
        if not self._validate_reflection_background_ready():
            return

        epsilon = self.batch_epsilon_spin.value()
        if epsilon < 0:
            self._append_log("Batch epsilon must be zero or greater.", "error")
            return

        output_dir = self._ensure_output_dir()
        worker = BatchLineWorker(
            self.state.data,
            cut_types,
            epsilon,
            output_dir,
            self.state.data["source_name"],
            self.state.current_ratio,
            tg_is_y=True,
            background_spectra=self.state.background_spectra if self.state.mode == "Reflection" else None,
            convention=self._current_convention(),
        )
        context = f"Batch extracting {' + '.join(cut_types)} line cuts"
        self._run_worker(worker, self._on_batch_lines_ready, context=context)

    def _run_worker(self, worker, on_success, context: str) -> None:
        if self._thread is not None:
            self._append_log("An analysis task is already running. Please wait for it to finish.", "warn")
            return

        self._pending_context = context
        self.progress_label.setVisible(True)
        self._set_controls_enabled(False)

        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)

        self._thread.started.connect(worker.run)
        worker.log.connect(self._log_worker_message)
        worker.progress.connect(self._on_worker_progress)
        worker.finished.connect(on_success)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._thread.quit)
        worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()
        self._append_log(context, "info")

    def _log_worker_message(self, message: str) -> None:
        self._append_log(message, "info")

    def _on_worker_progress(self, current: int, total: int) -> None:
        if total <= 0:
            return
        self.batch_progress_bar.setMaximum(total)
        self.batch_progress_bar.setValue(current)
        self.batch_progress_bar.setFormat(f"{current} / {total}  (%p%)")
        self.batch_progress_bar.setVisible(True)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _on_worker_finished(self, _result) -> None:
        try:
            self.progress_label.setVisible(False)
            self.batch_progress_bar.setVisible(False)
            self.batch_progress_bar.setValue(0)
            self._set_controls_enabled(True)
            self._refresh_stage_states()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_worker_error(self, tb: str) -> None:
        try:
            self._append_log(tb, "error")
            self._set_controls_enabled(True)
            self.progress_label.setVisible(False)
            self.batch_progress_bar.setVisible(False)
            self.batch_progress_bar.setValue(0)
            context = f" ({self._pending_context})" if self._pending_context else ""
            self._append_log(f"Worker failed{context}.", "error")
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _append_log(self, message: str, level: str = "info") -> None:
        msg = message.strip()
        if not msg:
            return
        color = {"info": "#334155", "success": "#15803d", "error": "#b91c1c", "warn": "#b45309"}.get(level, "#334155")
        html_msg = f'<span style="color: {color};">{msg}</span>'
        self.log_text.append(html_msg)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.load_csv_btn.setEnabled(enabled)
        self.load_bg_btn.setEnabled(enabled)
        self.preview_rc_btn.setEnabled(enabled)
        self.refresh_current_btn.setEnabled(enabled)
        self.refresh_all_maps_btn.setEnabled(enabled)
        self.plot_lines_btn.setEnabled(enabled)
        self.extract_all_doping_btn.setEnabled(enabled)
        self.extract_all_efield_btn.setEnabled(enabled)
        self.extract_all_both_btn.setEnabled(enabled)

    def _ensure_output_dir(self) -> str:
        if self.state.output_dir:
            os.makedirs(self.state.output_dir, exist_ok=True)
            return self.state.output_dir
        if self.state.csv_path:
            csv_stem = os.path.splitext(os.path.basename(self.state.csv_path))[0]
            output_dir = os.path.join(os.path.dirname(os.path.abspath(self.state.csv_path)), f"{csv_stem}_outputs")
            self.state.output_dir = output_dir
            os.makedirs(output_dir, exist_ok=True)
            self.out_edit.setText(output_dir)
            return output_dir
        raise ValueError("No output directory set and no CSV loaded.")

    def _open_output_folder(self) -> None:
        try:
            output_dir = self._ensure_output_dir()
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", output_dir])
            else:
                subprocess.Popen(["xdg-open", output_dir])
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _invalidate_from_stage(self, stage_number: int, message: str) -> None:
        self.state.reset_from_stage(stage_number)
        self._dirty_views = {k: True for k in self._dirty_views.keys()}
        self._clear_reflection_preview()
        for plot_tab in [self.map_plot_tab, self.line_plot_tab]:
            plot_tab.clear()
        self._append_log(message, "warn")
        self._refresh_stage_states()

    def _on_csv_loaded(self, result: dict) -> None:
        try:
            data = result["data"]
            self.state.data = data
            self.state.csv_path = data.get("source_name", "")
            
            x_data = data["x_data"]
            y_data = data["y_data"]
            energy = data["energy"]
            intensity = data["Intensity"]
            
            self.state.row_count = len(x_data)
            self.state.spectral_channel_count = intensity.shape[1]
            self.state.energy_range = (float(np.min(energy)), float(np.max(energy)))
            self.state.unique_x_count = len(np.unique(x_data))
            self.state.unique_y_count = len(np.unique(y_data))
            
            if not self._intensity_range_user_modified:
                energy_sorted = np.sort(energy[np.isfinite(energy)])
                if len(energy_sorted) >= 10:
                    e_lo = float(np.percentile(energy_sorted, 10))
                    e_hi = float(np.percentile(energy_sorted, 90))
                else:
                    e_lo, e_hi = float(energy_sorted[0]), float(energy_sorted[-1])
                self._suppress_intensity_tracking = True
                self.int_min_spin.setValue(e_lo)
                self.int_max_spin.setValue(e_hi)
                self._suppress_intensity_tracking = False
                self._intensity_defaults_csv_signature = (data.get("source_name", ""), e_lo, e_hi, self.state.spectral_channel_count)
            
            if self.auto_baseline_check.isChecked() and self.state.mode != "Reflection":
                self._estimate_and_apply_baseline(log=True, mark_dirty=False)
            elif not self._baseline_user_modified:
                self._suppress_baseline_tracking = True
                self.baseline_spin.setValue(595.0)
                self._suppress_baseline_tracking = False
            
            summary_text = (
                f"{self.state.row_count} rows × {self.state.spectral_channel_count} channels | "
                f"E: {self.state.energy_range[0]:.3f}–{self.state.energy_range[1]:.3f} eV | "
                f"Grid: {self.state.unique_x_count}×{self.state.unique_y_count}"
            )
            axis_status = validate_axis_selection(data.get("x_name", ""), data.get("y_name", ""))
            if axis_status["mode"] == "raw_gate":
                summary_text += " | Axes: X=BG/Vbg, Y=TG/Vtg"
            elif axis_status["mode"] == "transformed":
                summary_text += " | Axes: X=doping, Y=efield"
            self.summary_label.setText(summary_text)
            self._append_log(axis_status["message"], "info" if axis_status["mode"] in {"raw_gate", "transformed"} else "warn")

            if self.state.background_spectra is not None:
                bg_wavelength = None if self.state.background_wavelength is None else np.asarray(self.state.background_wavelength, dtype=float)
                data_wavelength = np.asarray(data["wavelength"], dtype=float)
                if (
                    bg_wavelength is None
                    or bg_wavelength.shape != data_wavelength.shape
                    or not np.allclose(bg_wavelength, data_wavelength, rtol=1e-9, atol=1e-9)
                ):
                    self._clear_background_state("Background cleared: reload a matching background for this dataset.")
                    self._append_log(
                        "The previously loaded background does not match this CSV's spectral channels and was cleared.",
                        "warn",
                    )

            self._clear_reflection_preview()
            self._dirty_views = {k: True for k in self._dirty_views.keys()}
            self._refresh_stage_states()
            self._append_log(f"CSV loaded: {data.get('source_name', 'unknown')}", "success")
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_analysis_refresh_ready(self, payload: dict) -> None:
        try:
            cmap = self.map_cmap_combo.currentText()
            vmin_val = None if self.map_auto_scale_check.isChecked() else self.map_vmin_spin.value()
            vmax_val = None if self.map_auto_scale_check.isChecked() else self.map_vmax_spin.value()
            is_rc = self.state.mode == "Reflection"
            e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
            e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
            e_suffix = f" | {e_lo:.3f}–{e_hi:.3f} eV"

            for map_key, map_data in payload.items():
                if map_key not in ["original_map", "transformed_map", "peak_map_original", "peak_map_transformed"]:
                    continue

                try:
                    target_axes = map_data.get("target_axes", "original")

                    if map_key == "original_map":
                        self.state.original_map = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = "RC Peak-to-Peak" if is_rc else "PL Intensity"
                        z_label = "RC Amplitude (a.u.)" if is_rc else "PL Intensity (a.u.)"
                        source = self.state.data.get("source_name", "data")
                        title = f"{z_name} Map | {source}{e_suffix}"
                        self._dirty_views["intensity_original"] = False
                        figure_key = "original_map"

                    elif map_key == "transformed_map":
                        self.state.transformed_map = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = "RC Peak-to-Peak" if is_rc else "PL Intensity"
                        z_label = "RC Amplitude (a.u.)" if is_rc else "PL Intensity (a.u.)"
                        ratio = map_data.get("ratio", self.ratio_spin.value())
                        if self.state.data.get("axis_space") == "transformed":
                            title = f"{z_name} Map | Loaded transformed axes{e_suffix}"
                        else:
                            title = f"{z_name} Map | Transformed (ratio={ratio:.4g}){e_suffix}"
                        self._dirty_views["intensity_transformed"] = False
                        figure_key = "transformed_map"

                    elif map_key == "peak_map_original":
                        self.state.peak_map_original = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = "RC Peak Position" if is_rc else "Peak Energy"
                        z_label = "RC Peak Position (eV)" if is_rc else "Peak Energy (eV)"
                        source = self.state.data.get("source_name", "data")
                        title = f"{z_name} Map | {source}{e_suffix}"
                        self._dirty_views["peak_original"] = False
                        figure_key = "peak_map_original"

                    elif map_key == "peak_map_transformed":
                        self.state.peak_map_transformed = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = "RC Peak Position" if is_rc else "Peak Energy"
                        z_label = "RC Peak Position (eV)" if is_rc else "Peak Energy (eV)"
                        ratio = map_data.get("ratio", self.ratio_spin.value())
                        if self.state.data.get("axis_space") == "transformed":
                            title = f"{z_name} Map | Loaded transformed axes{e_suffix}"
                        else:
                            title = f"{z_name} Map | Transformed (ratio={ratio:.4g}){e_suffix}"
                        self._dirty_views["peak_transformed"] = False
                        figure_key = "peak_map_transformed"

                    else:
                        continue

                    # Annotate map_data with display metadata
                    map_data["x_name"] = x_name
                    map_data["y_name"] = y_name
                    map_data["z_name"] = z_name
                    map_data["target_axes"] = target_axes

                    # Render figure
                    fig, _ = plot_map(
                        map_data["X2D"], map_data["Y2D"], map_data["Z2D"],
                        x_label=x_name, y_label=y_name, z_label=z_label,
                        title=title,
                        cmap=cmap,
                        vmin=vmin_val,
                        vmax=vmax_val,
                    )
                    self.state.figures[figure_key] = fig
                    self._log_map_payload(z_name, map_data, x_name, y_name)

                except Exception:
                    self._append_log(traceback.format_exc(), "error")

            self._show_current_map_view()
            self._update_status_labels()

        except Exception:
            self._append_log(traceback.format_exc(), "error")

    # ── Background loading ────────────────────────────────────────────────

    def _start_background_load(self) -> None:
        paths = self._get_background_paths()
        if not paths:
            self._append_log("Select at least one background CSV file first.", "error")
            return

        for p in paths:
            if not os.path.isfile(p):
                self._append_log(f"Background file not found: {p}", "error")
                return

        if self.state.data is None:
            self._append_log(
                "Load the primary reflection CSV first so the background channels can be validated.",
                "error",
            )
            return

        mode = self.bg_average_mode_combo.currentData() or "all_frames"
        worker = BackgroundLoadWorker(
            paths,
            x_col=self.vbg_combo.currentText(),
            y_col=self.vtg_combo.currentText(),
            average_mode=mode,
            expected_wavelength=self.state.data["wavelength"],
        )
        self._run_worker(worker, self._on_background_loaded, context="Loading background CSV")

    def _on_background_loaded(self, result: dict) -> None:
        try:
            self.state.background_spectra = result["background_spectra"]
            self.state.background_wavelength = result.get("wavelength")
            self.state.background_path = result.get("background_path", "")
            self.state.background_paths = result.get("background_paths", [])
            self.state.background_average_mode = result.get("average_mode", "all_frames")
            n_spectra = result.get("spectrum_count", "?")
            n_channels = np.asarray(self.state.background_spectra).shape[0]
            self.bg_status_label.setText(
                f"Background: {n_channels} ch, averaged from {n_spectra} spectra. "
                f"({os.path.basename(self.state.background_path)})"
            )
            self._append_log(
                f"Background loaded: {n_channels} channels, {n_spectra} spectra averaged.",
                "success",
            )
            # Invalidate any previously computed maps since background changed
            self._invalidate_from_stage(2, "Background updated – RC maps need refresh.")
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    # ── Mode switching ────────────────────────────────────────────────────

    def _on_mode_changed(self, mode: str) -> None:
        self.state.mode = mode
        is_rc = mode == "Reflection"

        # Show/hide background section
        self.bg_section.setVisible(is_rc)

        # Show/hide baseline
        self.baseline_form_label.setVisible(not is_rc)
        self.baseline_row_widget.setVisible(not is_rc)

        # Show/hide RC preview sidebar controls
        for w in self._rc_sidebar_widgets:
            w.setVisible(is_rc)

        # Set sensible default colormap
        self.map_cmap_combo.setCurrentText("RdBu_r" if is_rc else "jet")

        if not is_rc and self.state.data is not None and self.auto_baseline_check.isChecked():
            self._estimate_and_apply_baseline(log=True, mark_dirty=False)

        if self.state.data is not None:
            self._invalidate_from_stage(2, f"Mode switched to {mode} – maps need refresh.")
        else:
            self._refresh_stage_states()

    # ── Stage-state refresh ───────────────────────────────────────────────

    def _refresh_stage_states(self) -> None:
        try:
            has_csv_path = bool(self.csv_edit.text().strip())
            csv_is_file = has_csv_path and os.path.isfile(self.csv_edit.text().strip())
            has_data = self.state.data is not None
            is_rc = self.state.mode == "Reflection"
            has_background = self.state.background_spectra is not None
            has_original_map = self.state.original_map is not None
            has_transformed_map = self.state.transformed_map is not None and not self._dirty_views.get("intensity_transformed", True)
            batch_linecuts_ready = self._batch_linecuts_ready()

            self.load_csv_btn.setEnabled(bool(csv_is_file))
            self.load_bg_btn.setEnabled(bool(has_data and is_rc))
            self.preview_rc_btn.setEnabled(bool(has_data and is_rc and has_background))
            self.refresh_current_btn.setEnabled(bool(has_data and (not is_rc or has_background)))
            self.refresh_all_maps_btn.setEnabled(bool(has_data and (not is_rc or has_background)))
            self.plot_lines_btn.setEnabled(bool(has_data))
            self.extract_all_doping_btn.setEnabled(bool(batch_linecuts_ready))
            self.extract_all_efield_btn.setEnabled(bool(batch_linecuts_ready))
            self.extract_all_both_btn.setEnabled(bool(batch_linecuts_ready))

            save_enabled = bool(self._current_map_figure() is not None)
            self.save_current_png_btn.setEnabled(save_enabled)
            self.save_current_csv_btn.setEnabled(bool(self._current_map_payload() is not None))
            self.save_all_maps_btn.setEnabled(bool(has_original_map))
            has_lines = self.state.figures.get("line_cuts") is not None
            self.save_lines_png_btn.setEnabled(has_lines)
            self.save_lines_csv_btn.setEnabled(bool(self.state.line_cut_results))
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    # ── Legacy per-stage callbacks (kept for compat) ──────────────────────

    def _on_intensity_ready(self, result: dict) -> None:
        try:
            self.state.original_map = result
            self.state.original_map["x_name"] = self.state.data.get("x_name", "x")
            self.state.original_map["y_name"] = self.state.data.get("y_name", "y")
            self.state.original_map["z_name"] = "PL Intensity"
            self._dirty_views["intensity_original"] = False
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=self.state.original_map["x_name"],
                y_label=self.state.original_map["y_name"],
                z_label="PL Intensity (a.u.)",
                title=f"PL Intensity | {self.state.data.get('source_name', '')}",
                cmap=cmap,
            )
            self.state.figures["original_map"] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_transform_ready(self, result: dict) -> None:
        try:
            if self.state.data.get("axis_space") == "transformed":
                x_label = self.state.data.get("x_name", "doping")
                y_label = self.state.data.get("y_name", "efield")
                title = "PL Intensity | Loaded transformed axes"
            else:
                x_label, y_label = self._axis_labels()
                ratio = result.get("ratio", self.ratio_spin.value())
                title = f"PL Intensity | Transformed (ratio={ratio:.4g})"
            self.state.transformed_map = result
            self.state.transformed_map["x_name"] = x_label
            self.state.transformed_map["y_name"] = y_label
            self.state.transformed_map["z_name"] = "PL Intensity"
            self._dirty_views["intensity_transformed"] = False
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=x_label, y_label=y_label,
                z_label="PL Intensity (a.u.)",
                title=title,
                cmap=cmap,
            )
            self.state.figures["transformed_map"] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_peak_ready(self, result: dict) -> None:
        try:
            axes = result.get("target_axes", "original")
            if axes == "transformed":
                if self.state.data.get("axis_space") == "transformed":
                    x_label = self.state.data.get("x_name", "doping")
                    y_label = self.state.data.get("y_name", "efield")
                    title = "Peak Energy Map (loaded transformed axes)"
                else:
                    x_label, y_label = self._axis_labels()
                    title = f"Peak Energy Map ({axes} axes)"
                self.state.peak_map_transformed = result
                self.state.peak_map_transformed["x_name"] = x_label
                self.state.peak_map_transformed["y_name"] = y_label
                self.state.peak_map_transformed["z_name"] = "Peak Energy"
                self._dirty_views["peak_transformed"] = False
                figure_key = "peak_map_transformed"
            else:
                self.state.peak_map_original = result
                self.state.peak_map_original["x_name"] = self.state.data.get("x_name", "x")
                self.state.peak_map_original["y_name"] = self.state.data.get("y_name", "y")
                self.state.peak_map_original["z_name"] = "Peak Energy"
                self._dirty_views["peak_original"] = False
                figure_key = "peak_map_original"
                title = f"Peak Energy Map ({axes} axes)"
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=result.get("x_name", "x"),
                y_label=result.get("y_name", "y"),
                z_label="Peak Energy (eV)",
                title=title,
                cmap=cmap,
            )
            self.state.figures[figure_key] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_lines_ready(self, result: dict) -> None:
        try:
            line_cuts = result.get("line_cuts", [])
            if not line_cuts:
                self._append_log("No line cuts were extracted.", "warn")
                return

            self.state.line_cut_results = line_cuts
            self._dirty_views["line_cuts"] = False
            is_rc = self.state.mode == "Reflection"
            cmap = "RdBu_r" if is_rc else "jet"
            z_label = "RC (ΔI/I₀)" if is_rc else "PL Intensity (a.u.)"

            # Pick the first multi-row cut for the preview figure
            preview_cut = next(
                (lc for lc in line_cuts if np.asarray(lc["spectra"]).shape[0] >= 2),
                line_cuts[0],
            )
            c_used = preview_cut.get("c_value_used", 0.0)
            cut_type = preview_cut.get("cut_type", "cut")
            title = f"RC spectra near {cut_type} = {c_used:.3f} V" if is_rc else f"{cut_type} = {c_used:.3f} V"
            if np.asarray(preview_cut["spectra"]).shape[0] >= 2:
                fig, ax = plot_line_cut_spectrogram(
                    preview_cut, title=title, cmap=cmap, z_label=z_label
                )
            else:
                fig = Figure(figsize=(7, 4.8))
                ax = fig.add_subplot(111)
                s = np.asarray(preview_cut["spectra"], dtype=float).reshape(-1)
                ax.plot(preview_cut["energy"], s, color="#1d4ed8", linewidth=1.5)
                ax.set_xlabel("Energy (eV)")
                ax.set_ylabel(z_label)
                ax.set_title(title)
                fig.tight_layout()

            # Shade the analysis window
            e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
            e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
            ax.axvspan(e_lo, e_hi, color="#fef08a", alpha=0.15)

            self.state.figures["line_cuts"] = fig
            self.line_plot_tab.set_figure(fig)
            self.workspace_tabs.setCurrentIndex(1)
            self._append_log(f"Extracted {len(line_cuts)} line cut(s).", "success")
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_batch_lines_ready(self, result: dict) -> None:
        try:
            total = result.get("total_cuts", 0)
            n_files = len(result.get("saved_files", []))
            self._append_log(f"Batch line cut done: {total} cuts, {n_files} files saved.", "success")
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    # ── Save helpers ──────────────────────────────────────────────────────

    def _save_map(self, kind: str, output_type: str) -> None:
        map_payload = self.state.original_map if kind == "original" else self.state.transformed_map
        figure_key = "original_map" if kind == "original" else "transformed_map"
        figure = self.state.figures.get(figure_key)
        if map_payload is None or figure is None:
            self._append_log(f"No {kind} map available to save.", "warn")
            return
        base = self._ensure_output_dir()
        source = self.state.data["source_name"]
        z_name = map_payload.get("z_name", kind)
        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
        e_tag = f"_{e_lo:.3f}to{e_hi:.3f}eV"
        path = os.path.join(base, f"{source}_{z_name}{e_tag}_{kind}.{output_type}")
        if output_type == "png":
            figure.savefig(path, dpi=300, bbox_inches="tight", transparent=True)
        else:
            save_map_csv(
                map_payload["X2D"], map_payload["Y2D"], map_payload["Z2D"],
                path,
                x_name=map_payload.get("x_name", "x"),
                y_name=map_payload.get("y_name", "y"),
                z_name=z_name,
            )
        self._append_log(f"Saved: {os.path.basename(path)}", "success")

    def _save_peak_png(self) -> None:
        axes = "original"
        for a, fig_key in [("original", "peak_map_original"), ("transformed", "peak_map_transformed")]:
            if self.state.figures.get(fig_key) is not None:
                axes = a
                break
        fig_key = f"peak_map_{axes}"
        figure = self.state.figures.get(fig_key)
        map_data = self.state.peak_map_original if axes == "original" else self.state.peak_map_transformed
        if figure is None or map_data is None:
            self._append_log("No peak map available to save.", "warn")
            return
        base = self._ensure_output_dir()
        source = self.state.data["source_name"]
        path = os.path.join(base, f"{source}_peak_{axes}.png")
        figure.savefig(path, dpi=300, bbox_inches="tight", transparent=True)
        self._append_log(f"Saved: {os.path.basename(path)}", "success")

    def _save_peak_csv(self) -> None:
        for axes, attr, fig_key in [
            ("original", "peak_map_original", "peak_map_original"),
            ("transformed", "peak_map_transformed", "peak_map_transformed"),
        ]:
            map_data = getattr(self.state, attr)
            if map_data is None:
                continue
            base = self._ensure_output_dir()
            source = self.state.data["source_name"]
            path = os.path.join(base, f"{source}_peak_{axes}.csv")
            save_map_csv(
                map_data["X2D"], map_data["Y2D"], map_data["Z2D"],
                path,
                x_name=map_data.get("x_name", "x"),
                y_name=map_data.get("y_name", "y"),
                z_name=map_data.get("z_name", "Peak Energy"),
            )
            self._append_log(f"Saved: {os.path.basename(path)}", "success")

    def _save_lines_png(self) -> None:
        figure = self.state.figures.get("line_cuts")
        if figure is None:
            self._append_log("No line-cut figure available to save.", "warn")
            return
        base = self._ensure_output_dir()
        source = self.state.data["source_name"]
        path = os.path.join(base, f"{source}_linecuts.png")
        figure.savefig(path, dpi=300, bbox_inches="tight", transparent=True)
        self._append_log(f"Saved: {os.path.basename(path)}", "success")

    def _save_lines_csvs(self) -> None:
        if not self.state.line_cut_results:
            self._append_log("No line cuts available to save.", "warn")
            return
        base = self._ensure_output_dir()
        source = self.state.data["source_name"]
        saved = 0
        for lc in self.state.line_cut_results:
            cut_type = lc.get("cut_type", "cut")
            c_val = lc.get("c_value_used", 0.0)
            path = os.path.join(base, f"{source}_{cut_type}_{c_val:+.4f}.csv")
            save_line_csv(lc, path)
            saved += 1
        self._append_log(f"Saved {saved} line-cut CSV(s).", "success")

    # ── Browse background ─────────────────────────────────────────────────

    def _browse_background_csv(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select background CSV file(s)",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if paths:
            self._set_background_paths(paths)

    # ── Drag-and-drop for main window ─────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        try:
            gpos = event.pos()
            target = self._drop_target_from_global_pos(self.mapToGlobal(gpos))
        except Exception:
            target = "primary"

        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return

        if target == "background":
            self._set_background_paths(paths)
        else:
            self._set_primary_csv_path(paths[0])
        event.acceptProposedAction()
        
