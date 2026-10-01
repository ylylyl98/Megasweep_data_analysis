"""Native Qt settings for a sequence of measured spectral slices."""
from dataclasses import asdict
import math
from PySide6.QtCore import Qt, Signal

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QScrollArea,
                               QPushButton, QSizePolicy, QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget)

from spectral_movie import MovieOptions, select_values, timeline
from ui.widgets import NumericLineEdit
from ui.movie_preview import MoviePreviewWidget
from ui.plot_ranges import PlotRangeControls


class SpectralMovieDialog(QDialog):
    preview_requested = Signal(object)

    def __init__(self, values, axis_label, ranges=None, colors=None, recipe=None, parent=None, *, poster=None, full_ranges=None):
        super().__init__(parent)
        self.setWindowTitle('Create spectral slice MP4')
        screen = self.screen().availableGeometry()
        self.resize(min(1200, screen.width() - 48), min(780, screen.height() - 64))
        self._pending_result = None
        self._preview_configuration = None
        self.values = select_values(values)
        recipe = recipe if isinstance(recipe, dict) else {}
        colors = recipe.get('colors') or colors or dict(min=0, max=1)
        try:
            options = MovieOptions(**recipe.get('options', {}))
            options.validate()
        except (TypeError, ValueError):
            options = MovieOptions()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        self.settings = QWidget()
        settings_layout = QVBoxLayout(self.settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(12)
        title = QLabel('Create MP4')
        title.setProperty('fluentRole', 'title')
        settings_layout.addWidget(title)
        description = QLabel(f'2D spectral slices · sweep fixed {axis_label}')
        description.setWordWrap(True)
        description.setProperty('fluentRole', 'caption')
        settings_layout.addWidget(description)
        content = QWidget()
        self.form_content = content
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.first_combo, self.last_combo = QComboBox(), QComboBox()
        for combo in (self.first_combo, self.last_combo):
            for value in self.values:
                combo.addItem(f'{value:.12g}', value)
        self.last_combo.setCurrentIndex(len(self.values) - 1)
        for combo, name in ((self.first_combo, 'first'), (self.last_combo, 'last')):
            try:
                requested = float(recipe[name])
                if math.isfinite(requested):
                    combo.setCurrentIndex(min(range(len(self.values)), key=lambda i: abs(self.values[i] - requested)))
            except (KeyError, TypeError, ValueError):
                pass
        self.stride_spin = self._integer(1, 100000, recipe.get('stride', 1))
        self.stride_spin.setToolTip('Take every Nth measured coordinate within the inclusive range.')
        form.addRow('First value', self.first_combo)
        form.addRow('Last value', self.last_combo)
        form.addRow('Measured-coordinate stride', self.stride_spin)
        self.hold_spin = self._decimal(.001, 60, options.hold)
        self.speed_spin = self._decimal(.01, 100, options.speed)
        self.fps_spin = self._integer(1, 240, options.fps)
        self.head_spin = self._decimal(0, 120, options.head)
        self.tail_spin = self._decimal(0, 120, options.tail)
        self.repeats_spin = self._integer(1, 1000, options.repeats)
        self.width_spin = self._integer(320, 7680, options.width)
        self.height_spin = self._integer(240, 4320, options.height)
        self.width_spin.setSingleStep(2)
        self.height_spin.setSingleStep(2)
        self.crf_spin = self._integer(0, 51, options.crf)
        self.direction_combo = QComboBox()
        for text, value in (('Forward', 'forward'), ('Reverse', 'reverse'), ('Forward and back', 'pingpong')):
            self.direction_combo.addItem(text, value)
        self.direction_combo.setCurrentIndex(self.direction_combo.findData(options.direction))
        self.color_combo = QComboBox()
        for text, value in (('Global auto — same colors throughout', 'global'),
                            ('Manual fixed V min / V max', 'manual'),
                            ('Per-frame auto — emphasize each slice', 'frame')):
            self.color_combo.addItem(text, value)
        self.color_combo.setCurrentIndex(self.color_combo.findData(options.color_mode))
        self.vmin_edit = NumericLineEdit(str(colors.get('min', 0)))
        self.vmax_edit = NumericLineEdit(str(colors.get('max', 1)))
        self._valid_colors = dict(min=0., max=1.)
        try:
            low, high = float(colors.get('min', 0)), float(colors.get('max', 1))
            if math.isfinite(low) and math.isfinite(high) and low < high:
                self._valid_colors = dict(min=low, max=high)
        except (TypeError, ValueError):
            pass
        self.vmin_edit.setAccessibleName('Movie V min')
        self.vmax_edit.setAccessibleName('Movie V max')
        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText('Advanced')
        self.advanced_toggle.setProperty('class', 'sectionToggle')
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.setToolTip('Playback timing, direction, repetitions and encoding settings.')
        advanced_layout.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)
        self.advanced_content = QWidget()
        advanced_form = QFormLayout(self.advanced_content)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        advanced_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        advanced_form.addRow('Slice hold at 1× (s)', self.hold_spin)
        advanced_form.addRow('Playback speed', self.speed_spin)
        advanced_form.addRow('Video fps', self.fps_spin)
        advanced_form.addRow('Extra start / end hold (s)', self._pair(self.head_spin, self.tail_spin))
        advanced_form.addRow('Playback direction', self.direction_combo)
        advanced_form.addRow('Repetitions', self.repeats_spin)
        advanced_form.addRow('Output width / height (px)', self._pair(self.width_spin, self.height_spin))
        advanced_form.addRow('CRF (lower = higher quality)', self.crf_spin)
        advanced_layout.addWidget(self.advanced_content)
        self.advanced_content.hide()
        self.advanced_toggle.toggled.connect(self.advanced_content.setVisible)
        self.advanced_toggle.toggled.connect(lambda expanded: self.advanced_toggle.setArrowType(
                                            Qt.DownArrow if expanded else Qt.RightArrow))
        form.addRow('Color scale', self.color_combo)
        form.addRow('V min / V max', self._pair(self.vmin_edit, self.vmax_edit))
        self.range_controls = PlotRangeControls(title='MP4 display range', show_mode_selector=True)
        self.range_controls.restore(recipe.get('ranges', ranges or {}))
        self.range_controls.set_full_limits(full_ranges or {})
        self.range_controls.labels['x'].setText('Energy (eV)')
        self.range_controls.labels['y'].setText('Scan axis')
        self.range_controls.modes['x'].setItemText(0, 'Full')
        self.range_controls.modes['x'].setItemText(1, 'Zoom')
        form.insertRow(3, self.range_controls)
        view_label = QLabel('MP4 only · ranges stay fixed across frames.')
        view_label.setWordWrap(True)
        form.addRow(view_label)
        form.addRow(advanced)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        settings_layout.addWidget(scroll, 1)
        self.summary_label, self.values_label = QLabel(), QLabel()
        self.summary_label.setWordWrap(True)
        self.values_label.setWordWrap(True)
        settings_layout.addWidget(self.summary_label)
        settings_layout.addWidget(self.values_label)
        self.hint = QLabel('Each slice uses its own color scale; colors cannot be compared across frames.')
        self.hint.setWordWrap(True)
        self.hint.setProperty('fluentRole', 'caption')
        settings_layout.addWidget(self.hint)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setAccessibleName('Movie settings error')
        settings_layout.addWidget(self.error_label)
        self.preview = MoviePreviewWidget(poster, self)
        self.preview.busy_changed.connect(self._preview_busy_changed)
        self.preview.job_changed.connect(lambda _busy: self._update_preview())
        self.preview.idle.connect(self._preview_idle)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.settings)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 720])
        layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.export_btn = buttons.button(QDialogButtonBox.Save)
        self.export_btn.setText('Export MP4')
        self.export_btn.setProperty('class', 'primary')
        self.preview_btn = QPushButton('Preview')
        self.preview_btn.setToolTip('Play cached slice images with these settings. MP4 encoding runs only on export.')
        self.preview_btn.clicked.connect(self._request_preview)
        buttons.addButton(self.preview_btn, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for combo in (self.first_combo, self.last_combo, self.direction_combo, self.color_combo):
            combo.currentIndexChanged.connect(self._update_preview)
        for spin in (self.stride_spin, self.hold_spin, self.speed_spin, self.fps_spin,
                     self.head_spin, self.tail_spin, self.repeats_spin, self.width_spin,
                     self.height_spin, self.crf_spin):
            spin.valueChanged.connect(self._update_preview)
        for edit in (self.vmin_edit, self.vmax_edit):
            edit.textChanged.connect(self._update_preview)
            edit.editingFinished.connect(self._update_preview)
        self.range_controls.changed.connect(self._update_preview)
        self._update_preview()

    def showEvent(self, event):
        super().showEvent(event)
        # QDialogButtonBox assigns its default when shown, after construction.
        # Enter commits editor values; exporting requires explicit activation.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

    @staticmethod
    def _integer(low, high, value):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value if isinstance(value, int) else low)
        spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return spin

    @staticmethod
    def _decimal(low, high, value):
        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return spin

    @staticmethod
    def _pair(first, second):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(first)
        row.addWidget(second)
        row.addStretch(1)
        return widget

    def configuration(self):
        options = MovieOptions(hold=self.hold_spin.value(), speed=self.speed_spin.value(),
                               fps=self.fps_spin.value(), head=self.head_spin.value(),
                               tail=self.tail_spin.value(), direction=self.direction_combo.currentData(),
                               repeats=self.repeats_spin.value(), width=self.width_spin.value(),
                               height=self.height_spin.value(), crf=self.crf_spin.value(),
                               color_mode=self.color_combo.currentData())
        options.validate()
        values = select_values(self.values, self.first_combo.currentData(), self.last_combo.currentData(),
                               self.stride_spin.value())
        colors = dict(self._valid_colors)
        if options.color_mode == 'manual':
            try:
                colors = dict(min=float(self.vmin_edit.text()), max=float(self.vmax_edit.text()))
            except ValueError as exc:
                raise ValueError('Color scale requires finite V min < V max.') from exc
            if not all(math.isfinite(v) for v in colors.values()) or colors['min'] >= colors['max']:
                raise ValueError('Color scale requires finite V min < V max.')
            self._valid_colors = dict(colors)
        return dict(first=self.first_combo.currentData(), last=self.last_combo.currentData(),
                    stride=self.stride_spin.value(), values=values, options=asdict(options), colors=colors,
                    ranges=self.range_controls.recipe())

    def _update_preview(self, *_):
        manual = self.color_combo.currentData() == 'manual'
        self.hint.setVisible(self.color_combo.currentData() == 'frame')
        self.vmin_edit.setEnabled(manual)
        self.vmax_edit.setEnabled(manual)
        try:
            config = self.configuration()
            self.preview.apply_configuration(config)
            options = MovieOptions(**config['options'])
            segments = timeline(len(config['values']), options)
            count = sum(n for _, n in segments)
            self.summary_label.setText(f"{len(config['values'])} slices · {count} video frames · {count/options.fps:.2f} s")
            values = config['values']
            text = ', '.join(f'{value:.8g}' for value in values[:18])
            if len(values) > 18:
                text += f', …, {values[-1]:.8g}'
            self.values_label.setText('Measured values: ' + text)
            self.values_label.setToolTip(', '.join(f'{value:.12g}' for value in values))
            self.error_label.clear()
            self.error_label.hide()
            self.export_btn.setEnabled(not self.preview.generating)
            self.preview_btn.setEnabled(not self.preview.working)
        except (ValueError, TypeError) as exc:
            self.preview.invalidate()
            self.summary_label.setText('Check movie settings before exporting.')
            self.values_label.clear()
            self.error_label.setText(str(exc))
            self.error_label.show()
            self.export_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)

    def _request_preview(self):
        self._preview_configuration = self.configuration()
        if self.preview.apply_configuration(self._preview_configuration):
            self.preview.restart()
            return
        self.preview.begin(self._preview_configuration)
        self.preview_requested.emit(self._preview_configuration)

    def _preview_busy_changed(self, busy):
        self.form_content.setEnabled(not busy)
        self._update_preview()

    def _preview_idle(self):
        if self._pending_result is not None:
            result, self._pending_result = self._pending_result, None
            self.done(result)

    def done(self, result):
        if self.preview.working:
            self._pending_result = result
            self.preview.cancel_generation()
            return
        self.preview.dispose()
        super().done(result)

    def closeEvent(self, event):
        if self.preview.working:
            self.done(QDialog.Rejected)
            event.ignore()
        else:
            super().closeEvent(event)
