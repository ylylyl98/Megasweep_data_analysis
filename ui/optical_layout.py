from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.map_display import WrapLayout
from ui.styles import CAPTION_FONT_PX


from ui.widgets import ProgressLabel, CollapsibleSection, PlotTab, CsvDropLineEdit


from ui.transport import TransportPanel
from ui.spectral_slices import SpectralSlicesPanel
from ui.auto_update import AutoUpdateControls

class OpticalLayoutMixin:
    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.setChildrenCollapsible(False)

        self.left_panel = QWidget()
        self.left_panel.setObjectName("SidebarPanel")
        self.left_panel.setMinimumWidth(368)
        self.left_panel.setMaximumWidth(620)
        self.left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_panel_layout = QVBoxLayout(self.left_panel)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(0)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar_scroll.verticalScrollBar().setSingleStep(24)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 4, 4)
        left_layout.setSpacing(4)

        self.workflow_hint_label = QLabel(
            "1. Load data  →  2. Choose analysis settings  →  3. View / Update Now"
        )
        self.workflow_hint_label.setWordWrap(True)
        self.workflow_hint_label.setStyleSheet(
            "color:#365b87; background:#eef5ff; border:1px solid #cfe0f5; "
            "border-radius:4px; padding:4px 6px; font-weight:600;"
        )
        left_layout.addWidget(self.workflow_hint_label)

        self.data_section = CollapsibleSection("1  Data", self._build_load_group(), expanded=True)
        left_layout.addWidget(self.data_section)
        self.bg_section = CollapsibleSection("Background", self._build_background_group(), expanded=False)
        self.bg_section.setVisible(False)
        left_layout.addWidget(self.bg_section)
        self.analysis_section = CollapsibleSection(
            "2  Analysis Settings", self._build_analysis_group(), expanded=True
        )
        left_layout.addWidget(self.analysis_section)
        self.linecuts_section = CollapsibleSection(
            "3  Line Cuts", self._build_linecuts_group(), expanded=False
        )
        left_layout.addWidget(self.linecuts_section)
        self.export_section = CollapsibleSection(
            "4  Export", self._build_export_group(), expanded=False
        )
        left_layout.addWidget(self.export_section)
        left_layout.addStretch()
        self.sidebar_scroll.setWidget(left_widget)
        left_panel_layout.addWidget(self.sidebar_scroll, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        preview_widget = QWidget()
        preview_widget.setObjectName("PreviewPanel")
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)

        self.workspace_tabs = QTabWidget()

        self.maps_workspace = QWidget()
        maps_layout = QVBoxLayout(self.maps_workspace)
        maps_layout.setContentsMargins(4, 4, 4, 4)
        maps_layout.setSpacing(4)
        map_controls = QFrame()
        map_controls.setObjectName("PanelCard")
        map_controls_layout = QVBoxLayout(map_controls)
        map_controls_layout.setContentsMargins(6, 4, 6, 4)
        map_controls_layout.setSpacing(4)
        map_row = WrapLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(4)
        self.map_type_combo = QComboBox()
        self.map_type_combo.addItems(
            ["Intensity", "Peak Energy", "Ibias", "Resistance"]
        )
        self.map_type_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.map_type_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self._hrow(QLabel("Map Type"), self.map_type_combo))
        self.map_axes_combo = QComboBox()
        self.map_axes_combo.addItems(["Original", "Transformed"])
        self.map_axes_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.map_axes_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self._hrow(QLabel("Axes"), self.map_axes_combo))
        self.map_cmap_combo = QComboBox()
        self.map_cmap_combo.addItems([
            "RdBu_r", "jet", "viridis", "plasma", "inferno",
            "seismic", "coolwarm", "bwr", "Spectral_r", "RdYlBu_r",
        ])
        self.map_cmap_combo.setCurrentText("RdBu_r")
        self.map_cmap_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.map_updates = AutoUpdateControls(self._refresh_current_map_view, self._can_auto_map, delay=500, parent=self)
        self.map_auto_update_check = self.map_updates.checkbox
        self.refresh_current_btn = self.map_updates.button
        self.refresh_current_btn.style().unpolish(self.refresh_current_btn)
        self.refresh_current_btn.style().polish(self.refresh_current_btn)
        self.refresh_all_maps_btn = QPushButton("Refresh All Maps")
        self.refresh_all_maps_btn.clicked.connect(self._refresh_all_maps)
        map_row.addWidget(self._hrow(self.map_updates, self.refresh_all_maps_btn))
        map_controls_layout.addLayout(map_row)

        # ── Color scale row ───────────────────────────────────────────────
        scale_row = WrapLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(4)
        self.map_auto_scale_check = QCheckBox("Auto scale")
        self.map_auto_scale_check.setChecked(True)
        self.map_vmin_spin = self._dspin(-1e6, 1e6, 0.001, 4, 0.0)
        self.map_vmin_spin.setEnabled(False)
        self.map_vmin_spin.setFixedWidth(self.map_vmin_spin.fontMetrics().horizontalAdvance('-1234567.1234') + 36)
        self.map_vmax_spin = self._dspin(-1e6, 1e6, 0.001, 4, 1.0)
        self.map_vmax_spin.setEnabled(False)
        self.map_vmax_spin.setFixedWidth(self.map_vmax_spin.fontMetrics().horizontalAdvance('-1234567.1234') + 36)
        self.map_auto_scale_check.toggled.connect(
            lambda checked: (
                self.map_vmin_spin.setEnabled(not checked),
                self.map_vmax_spin.setEnabled(not checked),
                self._sync_color_limit_controls() if checked else None,
            )
        )
        scale_row.addWidget(self._hrow(QLabel("Colormap"), self.map_cmap_combo))
        scale_row.addWidget(self._hrow(self.map_auto_scale_check, QLabel("Min"),
                                      self.map_vmin_spin, QLabel("Max"), self.map_vmax_spin))
        map_controls_layout.addLayout(scale_row)
        ranges_row = WrapLayout()
        ranges_row.addWidget(self._build_axis_range_group("x"))
        ranges_row.addWidget(self._build_axis_range_group("y"))
        map_controls_layout.addLayout(ranges_row)
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
        line_layout.setContentsMargins(4, 4, 4, 4)
        line_layout.setSpacing(0)
        self.line_plot_tab = PlotTab("Line Cuts")
        line_layout.addWidget(self.line_plot_tab, 1)

        self.raw_background_workspace = QWidget()
        raw_background_layout = QVBoxLayout(self.raw_background_workspace)
        raw_background_layout.setContentsMargins(4, 4, 4, 4)
        raw_background_layout.setSpacing(0)
        self.raw_background_plot_tab = PlotTab("Raw / Background")
        raw_background_layout.addWidget(self.raw_background_plot_tab, 1)

        self.workspace_tabs.addTab(self.maps_workspace, "Maps")
        self.workspace_tabs.addTab(self.line_workspace, "Line Cuts")
        self.raw_background_tab_index = self.workspace_tabs.addTab(
            self.raw_background_workspace,
            "Raw / Background",
        )
        self.workspace_tabs.setTabVisible(self.raw_background_tab_index, False)
        self.transport_panel = TransportPanel(PlotTab, self._ensure_output_dir, self._append_log)
        for plot in (self.map_plot_tab, self.line_plot_tab, self.raw_background_plot_tab,
                     self.transport_panel.map_plot, self.transport_panel.cut_plot):
            plot.export_message.connect(self._append_log)
        self.transport_settings_section = CollapsibleSection("2  Transport Plot", self.transport_panel.settings_widget)
        self.transport_cuts_section = CollapsibleSection("3  Transport Line Cut", self.transport_panel.cut_controls_widget, expanded=False)
        self.transport_export_section = CollapsibleSection("4  Transport Export", self.transport_panel.export_widget, expanded=False)
        self.transport_panel.changed.connect(lambda: self.transport_cuts_section.setVisible(
            self.state.mode == "Transport" and self.transport_panel.plot_kind_combo.currentData() == "map"))
        for section in (self.transport_settings_section, self.transport_cuts_section, self.transport_export_section):
            left_layout.insertWidget(left_layout.count() - 1, section)
            section.hide()
        self.transport_tab_index = self.workspace_tabs.addTab(self.transport_panel, "Transport")
        self.workspace_tabs.setTabVisible(self.transport_tab_index, False)
        self.spectral_slices_panel = SpectralSlicesPanel(self)
        self.spectral_slices_tab_index = self.workspace_tabs.addTab(
            self.spectral_slices_panel, "Spectral Slices")
        preview_layout.addWidget(self.workspace_tabs, 1)

        log_widget = QWidget()
        log_widget.setObjectName("StatusPanel")
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas, Courier New, monospace", 10))
        self.log_text.setFixedHeight(140)
        self.log_text.hide()
        self.log_toggle = QPushButton("Log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setToolTip("Show or hide processing messages. Errors open the log automatically.")
        self.log_toggle.toggled.connect(self.log_text.setVisible)
        self.progress_label = ProgressLabel()
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        self.batch_progress_bar.setTextVisible(True)
        self.batch_progress_bar.setMinimumHeight(22)
        self.batch_progress_bar.setStyleSheet(
            f"QProgressBar {{ border:1px solid #4a4a4a; border-radius:3px; background:#1e1e1e; color:#e0e0e0; font-size:{CAPTION_FONT_PX}px; }}"
            "QProgressBar::chunk { background:#3a6ea8; border-radius:2px; }"
        )
        log_layout.addWidget(self.progress_label)
        log_layout.addWidget(self.batch_progress_bar)
        self.open_folder_btn = QPushButton("Open Output Folder")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        log_header = QHBoxLayout()
        log_header.addWidget(self.log_toggle)
        self.log_summary = QLabel("Ready")
        self.log_summary.setTextFormat(Qt.PlainText)
        self.log_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        log_header.addWidget(self.log_summary, 1)
        log_header.addWidget(self.open_folder_btn)
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_text)

        right_layout.addWidget(preview_widget, 1)
        right_layout.addWidget(log_widget)

        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setSizes([360, 920])
        root.addWidget(self.main_splitter)


    def _build_load_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        self._configure_sidebar_form(form, stacked=True)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems([self._fixed_mode] if self._fixed_mode else ["PL", "Reflection", "Transport"])
        self.mode_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.mode_combo.setMinimumContentsLength(12)
        self.mode_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        if self._fixed_mode:
            self.mode_combo.hide()
        else:
            form.addRow("Mode:", self.mode_combo)

        self.csv_edit = CsvDropLineEdit()
        self.csv_edit.setPlaceholderText("Select input CSV...")
        self.csv_edit.setClearButtonEnabled(True)
        self.csv_edit.setMinimumWidth(0)
        self.csv_edit.textChanged.connect(self._on_csv_text_changed)
        self.csv_edit.editingFinished.connect(self._on_csv_path_changed)
        self.csv_edit.csv_paths_dropped.connect(self._on_primary_csv_dropped)
        csv_btn = QPushButton("Browse…")
        csv_btn.setToolTip("Choose the primary measurement CSV.")
        csv_btn.clicked.connect(self._browse_csv)
        form.addRow("CSV file:", self._hrow(self.csv_edit, csv_btn))

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Output folder...")
        self.out_edit.setClearButtonEnabled(True)
        self.out_edit.setMinimumWidth(0)
        self.out_edit.editingFinished.connect(self._on_output_dir_changed)
        out_btn = QPushButton("Browse…")
        out_btn.setToolTip("Choose where exported maps and line cuts are saved.")
        out_btn.clicked.connect(self._browse_output)
        form.addRow("Output dir:", self._hrow(self.out_edit, out_btn))

        self.active_output_label = QLabel(
            "Select a CSV to determine its results subfolder."
        )
        self.active_output_label.setWordWrap(True)
        # Unbroken measurement paths must not set the scroll area's minimum width.
        self.active_output_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.active_output_label.setMinimumWidth(0)
        self.active_output_label.setTextFormat(Qt.PlainText)
        self.active_output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.active_output_label.setStyleSheet(f"color:#5a7088; font-size:{CAPTION_FONT_PX}px;")
        form.addRow("Saves to:", self.active_output_label)

        self.vbg_combo = QComboBox()
        self.vtg_combo = QComboBox()
        for combo in (self.vbg_combo, self.vtg_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(16)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        axis_help = (
            "Raw gate sweeps: Axis X should be BG/Vbg and Axis Y should be TG/Vtg. "
            "Transformed files: Axis X should be doping and Axis Y should be efield."
        )
        self.vbg_combo.setToolTip(axis_help)
        self.vtg_combo.setToolTip(axis_help)
        self._sweep_x_label = QLabel("Axis X column:")
        self._sweep_y_label = QLabel("Axis Y column:")
        self._sweep_x_label.setWordWrap(True)
        self._sweep_y_label.setWordWrap(True)
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
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.summary_label.setMinimumWidth(0)
        self.summary_label.setTextFormat(Qt.PlainText)
        self.summary_label.setStyleSheet("color:#5a7088;")
        form.addRow("Summary:", self.summary_label)
        return group


    def _build_background_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        self._configure_sidebar_form(form, stacked=True)

        self.bg_csv_edit = CsvDropLineEdit(allow_multiple=True)
        self.bg_csv_edit.setPlaceholderText("Select one or more background CSVs...")
        self.bg_csv_edit.setClearButtonEnabled(True)
        self.bg_csv_edit.setMinimumWidth(0)
        self.bg_csv_edit.textChanged.connect(self._on_background_text_changed)
        self.bg_csv_edit.csv_paths_dropped.connect(self._on_background_csvs_dropped)
        bg_btn = QPushButton("Browse…")
        bg_btn.setToolTip("Choose one or more reference/background CSV files.")
        bg_btn.clicked.connect(self._browse_background_csv)
        form.addRow("Background CSV:", self._hrow(self.bg_csv_edit, bg_btn))

        self.bg_average_mode_combo = QComboBox()
        self.bg_average_mode_combo.addItem("Average all frames", "all_frames")
        self.bg_average_mode_combo.addItem("Average first frame per CSV", "first_frame")
        self.bg_average_mode_combo.addItem("Average last frame per CSV", "last_frame")
        self.bg_average_mode_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.bg_average_mode_combo.setMinimumContentsLength(16)
        self.bg_average_mode_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        form.addRow("Background mode:", self.bg_average_mode_combo)

        self.load_bg_btn = QPushButton("Load Background")
        self.load_bg_btn.clicked.connect(self._start_background_load)
        form.addRow("", self.load_bg_btn)

        self.bg_status_label = QLabel("No background loaded.")
        self.bg_status_label.setWordWrap(True)
        self.bg_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.bg_status_label.setMinimumWidth(0)
        self.bg_status_label.setTextFormat(Qt.PlainText)
        self.bg_status_label.setStyleSheet("color:#5a7088;")
        form.addRow("Status:", self.bg_status_label)

        return group


    def _build_analysis_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        self._configure_sidebar_form(form)
        self.analysis_group = group

        self.int_min_spin = self._dspin(0.01, 10.0, 0.000001, 6, 1.247)
        self.int_max_spin = self._dspin(0.01, 10.0, 0.000001, 6, 1.428)
        self.fixed_energy_spin = self._dspin(0.01, 10.0, 0.000001, 6, 1.3375)
        self.baseline_spin = self._dspin(0.0, 1e6, 1.0, 2, 595.0)
        self.ratio_spin = self._dspin(0.001, 100.0, 0.01, 4, 1.0)
        self.int_min_spin.valueChanged.connect(self._on_energy_window_changed)
        self.int_max_spin.valueChanged.connect(self._on_energy_window_changed)
        self.fixed_energy_spin.valueChanged.connect(self._on_fixed_energy_changed)
        energy_window_help = (
            "Shared analysis window. In Reflection mode, preview one RC frame "
            "and drag across its spectrum to set this range. RC Peak-to-Peak and "
            "RC Peak Position use this window."
        )
        self.int_min_spin.setToolTip(energy_window_help)
        self.int_max_spin.setToolTip(energy_window_help)
        self.fixed_energy_spin.setToolTip(
            "Exact photon energy for the RC at Energy map. Each spectrum is "
            "linearly interpolated at this energy."
        )
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
        self.rc_feature_combo = QComboBox()
        self.rc_feature_combo.addItem("Auto: peak, then dip", "auto")
        self.rc_feature_combo.addItem("Peak: local maximum", "peak")
        self.rc_feature_combo.addItem("Dip: local minimum", "dip")
        self.rc_feature_combo.currentIndexChanged.connect(
            self._on_peak_settings_changed
        )
        self.background_scale_check = QCheckBox(
            "Scale background using both side windows"
        )
        self.background_scale_check.setChecked(True)
        self.scale_left_min_spin = self._dspin(
            0.01, 10.0, 0.000001, 6, 1.530000
        )
        self.scale_left_max_spin = self._dspin(
            0.01, 10.0, 0.000001, 6, 1.545000
        )
        self.scale_right_min_spin = self._dspin(
            0.01, 10.0, 0.000001, 6, 1.565000
        )
        self.scale_right_max_spin = self._dspin(
            0.01, 10.0, 0.000001, 6, 1.580000
        )
        self.estimate_background_scale_btn = QPushButton(
            "Estimate Scale from Preview Frame"
        )
        self.background_scale_status_label = QLabel("Scale α: not estimated")
        self.background_scale_status_label.setWordWrap(True)
        self.background_scale_status_label.setStyleSheet("color:#5a7088;")
        self.background_scale_check.toggled.connect(
            self._on_background_scale_enabled_changed
        )
        for spin in (
            self.scale_left_min_spin,
            self.scale_left_max_spin,
            self.scale_right_min_spin,
            self.scale_right_max_spin,
        ):
            spin.valueChanged.connect(self._on_background_scale_window_changed)
        self.estimate_background_scale_btn.clicked.connect(
            self._estimate_and_apply_background_scale
        )
        self.preview_updates = AutoUpdateControls(lambda: self._preview_reflection_spectra(automatic=True),
                                                 self._can_auto_preview, delay=300, parent=self,
                                                 manual_callback=self._preview_reflection_spectra)
        self.preview_auto_update_check = self.preview_updates.checkbox
        self.preview_rc_btn = self.preview_updates.button
        self.preview_rc_btn.setToolTip(
            "Plot the RC spectrum for the nearest X/Y frame. Drag horizontally "
            "on the plot to set the peak window; the purple marker shows Fixed E."
        )

        self.reflection_preview_status_label = QLabel(
            "Load CSV + background, choose X/Y, then preview one RC frame. "
            "Drag across the spectrum to set the peak window, or enter Fixed E "
            "for an RC-at-energy map."
        )
        self.reflection_preview_status_label.setWordWrap(True)
        self.reflection_preview_status_label.setStyleSheet("color:#5a7088;")

        self.convention_combo = QComboBox()
        self.convention_combo.addItems([
            "D = TG + r·BG,  E = TG − r·BG",
            "D = r·TG + BG,  E = r·TG − BG",
        ])
        self.convention_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.convention_combo.setMinimumContentsLength(12)
        self.convention_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.convention_combo.currentIndexChanged.connect(self._on_convention_changed)

        self.formula_label = QLabel(self._formula_text())
        self.formula_label.setWordWrap(True)
        self.formula_label.setStyleSheet(f"color:#5a7088; font-size:{CAPTION_FONT_PX}px;")

        self.analysis_status_label = QLabel("Load a CSV to start.")
        self.analysis_status_label.setWordWrap(True)
        self.analysis_status_label.setStyleSheet("color:#5a7088;")

        # --- energy window and shared settings (always visible) ---
        form.addRow(self._compact_pair("E min (eV)", self.int_min_spin, "E max (eV)", self.int_max_spin))

        # Baseline row – keep a reference so we can hide it in Reflection mode
        self.baseline_form_label = QLabel("Baseline:")
        self.baseline_row_widget = QWidget()
        baseline_layout = QHBoxLayout(self.baseline_row_widget)
        baseline_layout.setContentsMargins(0, 0, 0, 0)
        baseline_layout.setSpacing(4)
        self.baseline_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        baseline_layout.addWidget(self.baseline_spin)
        baseline_layout.addWidget(self.auto_baseline_check)
        baseline_layout.addWidget(self.estimate_baseline_btn)
        form.addRow(self.baseline_form_label, self.baseline_row_widget)

        advanced_content = QWidget()
        advanced_form = QFormLayout(advanced_content)
        self._configure_sidebar_form(advanced_form)
        advanced_form.addRow("Ratio:", self.ratio_spin)
        advanced_form.addRow("Convention:", self.convention_combo)
        advanced_form.addRow(self.formula_label)
        advanced_form.addRow(self._compact_pair("SG window", self.sg_window_spin, "Poly", self.sg_poly_spin))
        self.advanced_analysis_section = CollapsibleSection(
            "Advanced Settings", advanced_content, expanded=False)
        self.advanced_analysis_section.toggle.setToolTip("Coordinate transform ratio and convention; peak smoothing window and polynomial order.")

        # --- RC-specific rows (shown only when mode == "Reflection") ---
        self._rc_fixed_energy_label = QLabel("Fixed E (eV):")
        form.addRow(self._rc_fixed_energy_label, self.fixed_energy_spin)

        self._rc_feature_label = QLabel("RC feature:")
        form.addRow(self._rc_feature_label, self.rc_feature_combo)

        background_scale_content = QWidget()
        background_scale_form = QFormLayout(background_scale_content)
        self._configure_sidebar_form(background_scale_form)
        background_scale_form.addRow("", self.background_scale_check)
        background_scale_form.addRow(QLabel("Left window (eV)"))
        background_scale_form.addRow(self._compact_pair("Min", self.scale_left_min_spin, "Max", self.scale_left_max_spin))
        background_scale_form.addRow(QLabel("Right window (eV)"))
        background_scale_form.addRow(self._compact_pair("Min", self.scale_right_min_spin, "Max", self.scale_right_max_spin))
        background_scale_form.addRow("", self.estimate_background_scale_btn)
        background_scale_form.addRow(
            "Status:",
            self.background_scale_status_label,
        )
        self.background_scale_section = CollapsibleSection(
            "Background Scaling",
            background_scale_content,
            expanded=False,
        )
        form.addRow(self.background_scale_section)

        self._rc_vbg_label = QLabel("Preview X:")

        self._rc_vtg_label = QLabel("Preview Y:")
        self.rc_preview_coordinates = self._compact_pair(
            self._rc_vbg_label, self.reflection_preview_vbg_spin,
            self._rc_vtg_label, self.reflection_preview_vtg_spin)
        form.addRow(self.rc_preview_coordinates)

        self._rc_btn_placeholder = QLabel("")
        form.addRow(self.preview_updates)

        self._rc_status_row_label = QLabel("RC preview:")
        form.addRow(self._rc_status_row_label, self.reflection_preview_status_label)

        # Peak-smoothing parameters
        form.addRow(self.advanced_analysis_section)
        form.addRow("Status:", self.analysis_status_label)

        # Hide RC rows by default (PL mode)
        self._rc_sidebar_widgets = [
            self._rc_fixed_energy_label, self.fixed_energy_spin,
            self._rc_feature_label, self.rc_feature_combo,
            self.background_scale_section,
            self.rc_preview_coordinates,
            self._rc_vbg_label, self.reflection_preview_vbg_spin,
            self._rc_vtg_label, self.reflection_preview_vtg_spin,
            self._rc_btn_placeholder, self.preview_updates,
            self._rc_status_row_label, self.reflection_preview_status_label,
        ]
        for w in self._rc_sidebar_widgets:
            w.setVisible(False)

        return group


    def _build_export_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 4, 0, 0)
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
        self.save_lines_png_btn.hide()
        self.save_lines_csv_btn.hide()

        current_exports = WrapLayout()
        current_exports.addWidget(self.save_current_png_btn)
        current_exports.addWidget(self.save_current_csv_btn)
        layout.addLayout(current_exports)
        layout.addWidget(self.save_all_maps_btn)
        line_exports = WrapLayout()
        line_exports.addWidget(self.save_lines_png_btn)
        line_exports.addWidget(self.save_lines_csv_btn)
        layout.addLayout(line_exports)
        return group


    def _build_intensity_group(self) -> QWidget:
        group = QWidget()
        form = QFormLayout(group)
        form.setSpacing(4)
        form.setContentsMargins(0, 4, 0, 0)
        self.intensity_group = group

        self.int_min_spin = self._dspin(0.01, 10.0, 0.000001, 6, 1.25)
        self.int_max_spin = self._dspin(0.01, 10.0, 0.000001, 6, 1.425)
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
        form.setSpacing(4)
        form.setContentsMargins(0, 4, 0, 0)
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
        form.setSpacing(4)
        form.setContentsMargins(0, 4, 0, 0)
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
        layout.setSpacing(4)
        layout.setContentsMargins(0, 4, 0, 0)
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
        layout.addWidget(eps_label)
        layout.addWidget(self._hrow(self.batch_epsilon_spin, self.batch_preview_btn))
        layout.addWidget(self.extract_all_doping_btn)
        layout.addWidget(self.extract_all_efield_btn)
        layout.addWidget(self.extract_all_both_btn)

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
    def _compact_pair(first_label, first_control, second_label, second_control):
        """Keep related values side by side, wrapping whole fields if necessary."""
        row = QWidget()
        layout = WrapLayout()
        layout.setSpacing(6)
        row.setLayout(layout)
        for label, control in ((first_label, first_control), (second_label, second_control)):
            label = QLabel(label) if isinstance(label, str) else label
            label.setBuddy(control)
            control.setAccessibleName(label.text())
            # Account for the active font, precision, range and native spin arrows.
            # Wider fields wrap as a unit instead of hiding significant digits.
            control.ensurePolished()
            control.setFixedWidth(max(96, control.sizeHint().width()))
            layout.addWidget(OpticalLayoutMixin._hrow(label, control))
        return row

    @staticmethod
    def _hrow(*widgets) -> QWidget:
        row = QWidget()
        row.setProperty("class", "inlineRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for widget in widgets:
            layout.addWidget(widget)
        return row


    @staticmethod
    def _configure_sidebar_form(form: QFormLayout, *, stacked: bool = False) -> None:
        """Make sidebar forms responsive instead of clipping long rows."""
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(
            QFormLayout.WrapAllRows if stacked else QFormLayout.WrapLongRows
        )
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFormAlignment(Qt.AlignTop)


    @staticmethod
    def _dspin(lo: float, hi: float, step: float, decimals: int, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setKeyboardTracking(False)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setValue(value)
        return spin
