"""Consolidated optical slices, processing, and independent display controls."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from megasweep_analysis import (classify_axis_role, find_all_cut_values,
                               plot_line_cut_spectrogram, spectral_slice_stem)
from ui.exporting import save_figure, save_line_csv
from ui.widgets import PlotTab
from ui.plot_ranges import PlotRangeControls
from ui.plot_colors import ColorScaleControls
from ui.workers import BatchLineWorker, LineWorker


class SpectralSlicesPanel(QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.result = None
        self._signature = None
        self._request_signature = None
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.coordinates_combo = QComboBox()
        self.coordinates_combo.addItems(['Follow map', 'Original X/Y', 'Transformed D/E'])
        self.fixed_combo = QComboBox()
        self.value_combo = QComboBox()
        self.value_combo.setEditable(True)
        self.value_combo.setInsertPolicy(QComboBox.NoInsert)
        self.value_combo.setToolTip('Choose a measured coordinate or enter a value to snap to the nearest one.')
        self.epsilon_spin = QDoubleSpinBox()
        self.epsilon_spin.setDecimals(12)
        self.epsilon_spin.setRange(0, 1e9)
        self.epsilon_spin.setSingleStep(.001)
        self.epsilon_spin.setToolTip('Tolerance in the fixed axis units. Original axes: 0 selects the exact setpoint.')
        self.extract_btn = QPushButton('Extract Slice')
        self.extract_btn.setProperty('class', 'primary')
        selection = QGroupBox('1. Choose the fixed sweep coordinate')
        fields = QGridLayout(selection)
        fields.addWidget(QLabel('Coordinate system'), 0, 0)
        fields.addWidget(self.coordinates_combo, 0, 1)
        fields.addWidget(QLabel('Axis to hold fixed'), 0, 2)
        fields.addWidget(self.fixed_combo, 0, 3)
        self.value_label = QLabel('Fixed coordinate value')
        self.value_label.setWordWrap(True)
        self.value_label.setBuddy(self.value_combo)
        fields.addWidget(self.value_label, 1, 0)
        fields.addWidget(self.value_combo, 1, 1)
        fields.addWidget(QLabel('Selection tolerance (±)'), 1, 2)
        fields.addWidget(self.epsilon_spin, 1, 3)
        fields.addWidget(self.extract_btn, 0, 4, 2, 1)
        fields.setColumnStretch(1, 1)
        fields.setColumnStretch(3, 1)
        layout.addWidget(selection)
        self.processing_combo = QComboBox()
        self.processing_combo.addItem('Spectrum', 'spectrum')
        self.processing_combo.addItem('Second derivative vs energy (d²/dE²)', 'second_derivative')
        self.derivative_window_spin = QSpinBox()
        self.derivative_window_spin.setRange(3, 10001)
        self.derivative_window_spin.setSingleStep(2)
        self.derivative_window_spin.setValue(9)
        self.derivative_window_spin.setEnabled(False)
        self.derivative_window_spin.setToolTip('Odd number of energy channels for the local polynomial fit. Larger windows smooth more strongly.')
        fields.addWidget(QLabel('Signal processing'), 2, 0)
        fields.addWidget(self.processing_combo, 2, 1)
        fields.addWidget(QLabel('Derivative window (points)'), 2, 2)
        fields.addWidget(self.derivative_window_spin, 2, 3)
        self.axis_label = QLabel('Energy × varying sweep axis; color = spectrum intensity.')
        self.axis_label.setWordWrap(True)
        fields.addWidget(self.axis_label, 3, 0, 1, 5)
        self.ranges = PlotRangeControls(title='2. Display range — preview and Save PNG only; CSV keeps all points')
        self.ranges.changed.connect(workspace._schedule_session_save)
        layout.addWidget(self.ranges)
        self.colors = ColorScaleControls()
        self.colors.changed.connect(workspace._schedule_session_save)
        layout.addWidget(self.colors)
        self.preview_btn = QPushButton('Preview Counts')
        self.batch_x_btn = QPushButton('All fixed X')
        self.batch_y_btn = QPushButton('All fixed Y')
        self.batch_both_btn = QPushButton('All Both')
        self.save_csv_btn = QPushButton('Save CSV')
        self.save_png_btn = QPushButton('Save PNG')
        self._row(layout, [('', button) for button in (self.preview_btn, self.batch_x_btn,
                   self.batch_y_btn, self.batch_both_btn, self.save_csv_btn, self.save_png_btn)])
        self.status_label = QLabel('Load a spectral CSV to extract a slice.')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.plot = PlotTab('Spectral Slices')
        layout.addWidget(self.plot, 1)
        self.plot.export_message.connect(workspace._append_log)
        self.coordinates_combo.currentTextChanged.connect(self._coordinates_changed)
        self.fixed_combo.currentIndexChanged.connect(self._fixed_changed)
        self.value_combo.currentTextChanged.connect(self._settings_changed)
        self.epsilon_spin.valueChanged.connect(self._settings_changed)
        self.processing_combo.currentIndexChanged.connect(self._processing_changed)
        self.derivative_window_spin.valueChanged.connect(self._processing_changed)
        self.extract_btn.clicked.connect(self.extract)
        self.preview_btn.clicked.connect(self.preview)
        self.batch_x_btn.clicked.connect(lambda: self.batch([self._kinds()[0]]))
        self.batch_y_btn.clicked.connect(lambda: self.batch([self._kinds()[1]]))
        self.batch_both_btn.clicked.connect(lambda: self.batch(self._kinds()))
        self.save_csv_btn.clicked.connect(lambda: self.save('csv'))
        self.save_png_btn.clicked.connect(lambda: self.save('png'))

    @staticmethod
    def _row(layout, pairs):
        row = QHBoxLayout()
        for text, widget in pairs:
            if text:
                row.addWidget(QLabel(text))
            row.addWidget(widget)
        layout.addLayout(row)

    def _transformed(self):
        data = self.workspace.state.data or {}
        if data.get('axis_space') not in {'gate', 'transformed'}:
            return False
        choice = self.coordinates_combo.currentText()
        return choice == 'Transformed D/E' or (
            choice == 'Follow map' and self.workspace.map_axes_combo.currentText() == 'Transformed')

    def _kinds(self):
        return ['doping', 'efield'] if self._transformed() else ['x', 'y']

    def _names(self):
        data = self.workspace.state.data or {}
        if self._transformed() and data.get('axis_space') == 'gate':
            d, e = self.workspace._axis_labels()
            return f'Doping: {d}', f'Efield: {e}'
        if self._transformed() and classify_axis_role(data.get('x_name', '')) == 'efield':
            return data.get('y_name', 'Doping'), data.get('x_name', 'Efield')
        return data.get('x_name', 'X'), data.get('y_name', 'Y')

    def _values(self, kind, min_points=1):
        data = self.workspace.state.data
        if data is None:
            return []
        return find_all_cut_values(data['x_data'], data['y_data'], kind,
                                  self.workspace.ratio_spin.value(), self.epsilon_spin.value(),
                                  min_points=min_points, convention=self.workspace._current_convention(),
                                  axis_space=data.get('axis_space', 'gate'),
                                  x_axis_name=data.get('x_name', ''), y_axis_name=data.get('y_name', ''),
                                  exact_coordinates=True)

    def _populate_values(self):
        previous = self.value_combo.currentText()
        blocked = self.value_combo.blockSignals(True)
        self.value_combo.clear()
        values = self._values(self.fixed_combo.currentData())
        for value in values:
            self.value_combo.addItem(f'{value:.12g}', value)
        try:
            requested = float(previous)
            if values:
                self.value_combo.setCurrentIndex(int(np.argmin(np.abs(np.asarray(values) - requested))))
        except ValueError:
            pass
        self.value_combo.blockSignals(blocked)
        names = self._names()
        index = max(0, self.fixed_combo.currentIndex())
        self.value_label.setText(f'Fixed {names[index]} value')
        self.value_combo.setAccessibleName(f'Fixed {names[index]} value')
        self.epsilon_spin.setToolTip(f'Allowed distance from the fixed {names[index]} value, in that axis’s units. 0 selects the exact coordinate.')
        self.ranges.labels['x'].setText('X — Energy (eV)')
        self.ranges.labels['y'].setText(f'Y — {names[1-index]}')
        for label in self.ranges.labels.values():
            label.setWordWrap(True)
            label.setFixedWidth(210)
        signal = 'RC' if self.workspace.state.mode == 'Reflection' else 'PL intensity'
        if self.processing_combo.currentData() == 'second_derivative':
            signal = 'd²RC/dE²' if self.workspace.state.mode == 'Reflection' else 'd²PL/dE²'
        self.axis_label.setText(f'Hold {names[index]} at the value above; scan all {names[1-index]} points. Color shows {signal}. Typed values snap to the nearest measured coordinate.')

    def _clear(self):
        self.ranges.detach()
        self.colors.detach()
        self.result = None
        self.plot.clear()
        self.save_csv_btn.setEnabled(False)
        self.save_png_btn.setEnabled(False)

    def _settings_changed(self, *_):
        if self._updating:
            return
        self._clear()
        self.status_label.setText('Settings changed. Extract a slice to update the plot.')
        self.workspace._schedule_session_save()

    def _coordinates_changed(self, *_):
        self.refresh()
        self._settings_changed()

    def _fixed_changed(self, *_):
        if self._updating:
            return
        self.ranges.reset()
        self._populate_values()
        self._settings_changed()

    def _processing_changed(self, *_):
        if self._updating:
            return
        self.derivative_window_spin.setEnabled(self.processing_combo.currentData() == 'second_derivative')
        self.colors.reset()
        self.refresh()
        self._settings_changed()

    def refresh(self):
        w = self.workspace
        data = w.state.data
        is_rc = w.state.mode == 'Reflection'
        if data is not None:
            channels = len(data['energy'])
            blocked = self.derivative_window_spin.blockSignals(True)
            self.derivative_window_spin.setMaximum(max(3, channels if channels % 2 else channels - 1))
            self.derivative_window_spin.blockSignals(blocked)
        supports_de = data is not None and data.get('axis_space') in {'gate', 'transformed'}
        self.coordinates_combo.model().item(2).setEnabled(supports_de)
        signature = (id(data), w.state.mode, self._transformed(),
                     w.ratio_spin.value() if self._transformed() else None,
                     w._current_convention() if self._transformed() else None,
                     id(w.state.background_spectra) if is_rc else None,
                     w.background_scale_check.isChecked() if is_rc else None,
                     w.state.background_scale_factor if is_rc and w.background_scale_check.isChecked() else None,
                     self.processing_combo.currentData(),
                     self.derivative_window_spin.value() if self.processing_combo.currentData() == 'second_derivative' else None)
        if signature != self._signature:
            if self._signature is None or signature[:5] != self._signature[:5]:
                self.ranges.reset()
                self.colors.reset()
            self._signature = signature
            self._updating = True
            try:
                self._clear()
                index = max(0, self.fixed_combo.currentIndex())
                self.fixed_combo.clear()
                for kind, name in zip(self._kinds(), self._names()):
                    self.fixed_combo.addItem(f'Fixed {name}', kind)
                self.fixed_combo.setCurrentIndex(index)
                self._populate_values()
                self.status_label.setText('Choose a fixed coordinate, then Extract Slice. Batch exports CSV and PNG.')
            finally:
                self._updating = False
        ready = data is not None and w.state.mode in {'PL', 'Reflection'}
        if is_rc:
            ready = ready and w.state.background_spectra is not None
            if ready:
                try:
                    w._effective_background_scale()
                except ValueError as exc:
                    ready = False
                    self.status_label.setText(str(exc))
            elif data is not None:
                self.status_label.setText('Load a matching background spectrum before extracting RC slices.')
        if data is None:
            self.status_label.setText('Load a spectral CSV to extract a slice.')
        for button in (self.extract_btn, self.batch_x_btn, self.batch_y_btn, self.batch_both_btn):
            button.setEnabled(bool(ready))
        self.preview_btn.setEnabled(data is not None)
        self.setEnabled(w._thread is None)

    def _worker_options(self):
        w = self.workspace
        is_rc = w.state.mode == 'Reflection'
        return dict(convention=w._current_convention(), exact_coordinates=True,
                    spectral_processing=self.processing_combo.currentData(),
                    derivative_window=self.derivative_window_spin.value(),
                    background_spectra=w.state.background_spectra if is_rc else None,
                    background_scale=w._effective_background_scale() if is_rc else 1.)

    def extract(self):
        w = self.workspace
        try:
            self.refresh()
            if not self.extract_btn.isEnabled() or w._thread is not None:
                return
            if not w._validate_reflection_background_ready():
                return
            requested = float(self.value_combo.currentText())
            if not np.isfinite(requested):
                raise ValueError('Enter a finite fixed coordinate.')
            kind = self.fixed_combo.currentData()
            values = self._values(kind)
            if not values:
                raise ValueError('No finite measured coordinates are available.')
            actual = values[int(np.argmin(np.abs(np.asarray(values) - requested)))]
            self.value_combo.setEditText(f'{actual:.12g}')
            specs = [dict(cut_type=kind, c_value=actual, epsilon=self.epsilon_spin.value())]
            self._request_signature = self._signature
            self.status_label.setText(f'Extracting at {actual:.12g} (requested {requested:.12g})…')
            worker = LineWorker(w.state.data, specs, w.ratio_spin.value(), **self._worker_options())
            w._run_worker(worker, self._show_result, context='Extracting spectral slice')
        except (ValueError, RuntimeError) as exc:
            self.status_label.setText(str(exc))
            w._append_log(str(exc), 'error')

    def _show_result(self, payload):
        self.refresh()
        if self._request_signature != self._signature:
            self.status_label.setText('Source settings changed during extraction. Extract again.')
            return
        cuts = payload.get('line_cuts', [])
        if not cuts or len(cuts[0]['axis_values']) < 2:
            self._clear()
            self.status_label.setText('A 2D spectral slice needs at least two distinct points on the varying axis.')
            return
        result = cuts[0]
        is_rc = self.workspace.state.mode == 'Reflection'
        title = f"Fixed {result['fixed_axis_label']} = {result['c_value_used']:.12g}"
        derivative = result.get('processing') == 'second_derivative'
        if derivative:
            title += f" | d²/dE², window {result['derivative_window']}"
        figure, _ = plot_line_cut_spectrogram(result, title=title,
                     cmap='RdBu_r' if is_rc or derivative else 'jet',
                     z_label=result.get('signal_label', 'RC (ΔI/I₀)' if is_rc else 'PL Intensity (a.u.)'))
        self.plot.set_figure(figure)
        self.ranges.attach(figure)
        self.colors.attach(figure)
        self.result = result
        self.save_csv_btn.setEnabled(True)
        self.save_png_btn.setEnabled(True)
        self.status_label.setText(f"{title}; {len(result['axis_values'])} scan points × {len(result['energy'])} energy channels.")
        self.workspace.workspace_tabs.setCurrentWidget(self)
        self.workspace._schedule_session_save()

    def show_existing_cut(self, cut):
        """Display a restored legacy recipe in the consolidated optical view."""
        self.processing_combo.setCurrentIndex(0)
        self.coordinates_combo.setCurrentText('Transformed D/E' if cut['cut_type'] in {'doping', 'efield'} else 'Original X/Y')
        index = self.fixed_combo.findData(cut['cut_type'])
        if index >= 0:
            self.fixed_combo.setCurrentIndex(index)
        self.value_combo.setEditText(str(cut['c_value_used']))
        self._request_signature = self._signature
        self._show_result({'line_cuts': [cut]})

    def preview(self):
        try:
            counts = [len(self._values(kind, min_points=2)) for kind in self._kinds()]
            self.status_label.setText(' | '.join(f'Fixed {name}: {count} slices' for name, count in zip(self._names(), counts)))
        except ValueError as exc:
            self.status_label.setText(str(exc))

    def batch(self, kinds):
        w = self.workspace
        try:
            self.refresh()
            if not self.batch_both_btn.isEnabled() or w._thread is not None:
                return
            if not w._validate_reflection_background_ready():
                return
            output = os.path.join(w._ensure_output_dir(), 'spectral_slices', w.state.mode.lower())
            worker = BatchLineWorker(w.state.data, kinds, self.epsilon_spin.value(), output,
                                     w.ratio_spin.value(), **self._worker_options())
            w._run_worker(worker, self._batch_finished, context='Exporting spectral slices')
        except (ValueError, OSError) as exc:
            self.status_label.setText(str(exc))
            w._append_log(str(exc), 'error')

    def _batch_finished(self, payload):
        self.status_label.setText(f"Exported {payload['total_cuts']} slices; {len(payload['saved_files'])} new files.")
        self.workspace._on_batch_lines_ready(payload)

    def save(self, kind):
        if self.result is None:
            return
        try:
            directory = os.path.join(self.workspace._ensure_output_dir(), 'spectral_slices', self.workspace.state.mode.lower())
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, spectral_slice_stem(self.result) + '.' + kind)
            exported = save_line_csv(self.result, path) if kind == 'csv' else save_figure(self.plot.current_figure, path)
            self.workspace._append_log(exported.message, 'success')
        except (OSError, ValueError) as exc:
            self.workspace._append_log(f'Slice export failed: {exc}', 'error')

    def recipe(self):
        return dict(coordinates=self.coordinates_combo.currentText(), fixed=self.fixed_combo.currentData(),
                    value=self.value_combo.currentText(), epsilon=self.epsilon_spin.value(),
                    ranges=self.ranges.recipe(), colors=self.colors.recipe(),
                    processing=self.processing_combo.currentData(), derivative_window=self.derivative_window_spin.value())

    def restore(self, recipe):
        recipe = recipe if isinstance(recipe, dict) else {}
        index = self.processing_combo.findData(recipe.get('processing', 'spectrum'))
        self.processing_combo.setCurrentIndex(max(0, index))
        window = recipe.get('derivative_window', 9)
        if isinstance(window, int) and window >= 3 and window % 2:
            self.derivative_window_spin.setValue(window)
        self.coordinates_combo.setCurrentText(recipe.get('coordinates', 'Follow map'))
        self.refresh()
        index = self.fixed_combo.findData(recipe.get('fixed', self._kinds()[0]))
        if index >= 0:
            self.fixed_combo.setCurrentIndex(index)
        value = recipe.get('value', '')
        if isinstance(value, str) and value:
            self.value_combo.setEditText(value)
        epsilon = recipe.get('epsilon', 0.)
        if isinstance(epsilon, (float, int)) and np.isfinite(epsilon) and epsilon >= 0:
            self.epsilon_spin.setValue(epsilon)
        self.ranges.restore(recipe.get('ranges'))
        self.colors.restore(recipe.get('colors'))
