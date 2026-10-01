"""Consolidated optical slices, processing, and independent display controls."""
from __future__ import annotations

import os
from collections import OrderedDict
from copy import deepcopy

import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QProgressDialog,
                               QPushButton, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from megasweep_analysis import (classify_axis_role, compute_transformed_coords, find_all_cut_values,
                               plot_line_cut_spectrogram, spectral_slice_stem,
                               spectral_slice_title, spectral_title_precision)
from ui.exporting import save_figure, save_line_csv
from ui.widgets import PlotTab
from ui.plot_ranges import PlotRangeControls
from ui.plot_colors import ColorScaleControls
from ui.map_display import WrapLayout
from ui.workers import (BatchLineWorker, LineWorker, SpectralMovieWorker,
                        SpectralPreviewWorker, SpectralPreviewFrameWorker)
from ui.spectral_movie import SpectralMovieDialog
from ui.auto_update import AutoUpdateControls


class SpectralSlicesPanel(QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self._movie_recipe = {}
        self._movie_progress = None
        self._values_source = None
        self._values_cache = OrderedDict()
        self.result = None
        self._signature = None
        self._request_signature = None
        self._updating = False
        self._stale = True
        self._selection_revision = 0
        self._navigate_after_extract = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.coordinates_combo = QComboBox()
        self.coordinates_combo.addItems(['Follow map', 'Original X/Y', 'Transformed D/E'])
        self.fixed_combo = QComboBox()
        self.value_combo = QComboBox()
        self.value_combo.setEditable(True)
        self.value_combo.setInsertPolicy(QComboBox.NoInsert)
        self.value_combo.setToolTip('Choose a measured coordinate or enter a value to snap to the nearest one.')
        self.previous_value_btn = QToolButton()
        self.next_value_btn = QToolButton()
        for button, arrow, label, direction in (
            (self.previous_value_btn, Qt.LeftArrow, 'Previous measured fixed value', -1),
            (self.next_value_btn, Qt.RightArrow, 'Next measured fixed value', 1),
        ):
            button.setArrowType(arrow)
            button.setAccessibleName(label)
            button.setToolTip(label + '. Refreshes the slice when a plot is already displayed.')
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, step=direction: self._step_value(step))
        self.epsilon_spin = QDoubleSpinBox()
        self.epsilon_spin.setDecimals(12)
        self.epsilon_spin.setKeyboardTracking(False)
        self.epsilon_spin.setRange(0, 1e9)
        self.epsilon_spin.setSingleStep(.001)
        self.epsilon_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.epsilon_spin.setToolTip('Tolerance in the fixed axis units. Original axes: 0 selects the exact setpoint.')
        self.updates = AutoUpdateControls(lambda: self.extract(automatic=True), self._can_auto_update,
                                         parent=self, manual_callback=self.extract)
        self.updates.preference_changed.connect(workspace._schedule_session_save)
        self.extract_btn = self.updates.button
        selection = QGroupBox('1. Choose the fixed sweep coordinate')
        fields = QGridLayout(selection)
        self.coordinates_label = QLabel('Coordinate system')
        fields.addWidget(self.coordinates_label, 0, 0)
        fields.addWidget(self.coordinates_combo, 0, 1)
        fields.addWidget(QLabel('Axis to hold fixed'), 0, 2)
        fields.addWidget(self.fixed_combo, 0, 3)
        self.value_label = QLabel('Fixed coordinate value')
        self.value_label.setWordWrap(True)
        self.value_label.setBuddy(self.value_combo)
        fields.addWidget(self.value_label, 1, 0)
        value_row = QHBoxLayout()
        value_row.setSpacing(4)
        value_row.addWidget(self.previous_value_btn)
        value_row.addWidget(self.value_combo, 1)
        value_row.addWidget(self.next_value_btn)
        fields.addLayout(value_row, 1, 1)
        fields.addWidget(QLabel('Selection tolerance (±)'), 1, 2)
        fields.addWidget(self.epsilon_spin, 1, 3)
        fields.addWidget(self.updates, 0, 4, 2, 1)
        fields.setColumnStretch(1, 1)
        fields.setColumnStretch(3, 1)
        layout.addWidget(selection)
        self.processing_combo = QComboBox()
        self.processing_combo.addItem('Spectrum', 'spectrum')
        self.processing_combo.addItem('Second derivative vs energy (d²/dE²)', 'second_derivative')
        self.derivative_window_spin = QSpinBox()
        self.derivative_window_spin.setRange(3, 10001)
        self.derivative_window_spin.setKeyboardTracking(False)
        self.derivative_window_spin.setSingleStep(2)
        self.derivative_window_spin.setValue(9)
        self.derivative_window_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.derivative_window_spin.setEnabled(False)
        self.derivative_window_spin.setToolTip('Odd number of energy channels for the local polynomial fit. Larger windows smooth more strongly.')
        fields.addWidget(QLabel('Signal processing'), 2, 0)
        fields.addWidget(self.processing_combo, 2, 1)
        fields.addWidget(QLabel('Derivative window (points)'), 2, 2)
        fields.addWidget(self.derivative_window_spin, 2, 3)
        self.axis_label = QLabel('Energy × varying sweep axis; color = spectrum intensity.')
        self.axis_label.setWordWrap(True)
        fields.addWidget(self.axis_label, 3, 0, 1, 5)
        self.ranges = PlotRangeControls(title='2. Slice / PNG display range — MP4 has separate controls; CSV keeps all points',
                                        show_mode_selector=True)
        self.ranges.changed.connect(workspace._schedule_session_save)
        self.ranges.modes['x'].setItemText(0, 'Full (Auto)')
        self.ranges.modes['x'].setItemText(1, 'Zoom (Fixed)')
        self.ranges.modes['x'].setToolTip('Full: all measured energy channels. Zoom: remember your Min/Max across slices and exports.')
        self.ranges.modes['y'].setToolTip('Auto: the same full sweep range for every slice. Fixed: your chosen shared Min/Max.')
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
        self.movie_btn = QPushButton('Create MP4…')
        self.movie_btn.setToolTip('Animate 2D slices by sweeping the measured fixed coordinate.')
        actions = WrapLayout()
        for button in (self.preview_btn, self.batch_x_btn, self.batch_y_btn,
                       self.batch_both_btn, self.save_csv_btn, self.save_png_btn, self.movie_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status_label = QLabel('Load a spectral CSV to extract a slice.')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.plot = PlotTab('Spectral Slices')
        layout.addWidget(self.plot, 1)
        self.plot.export_message.connect(workspace._append_log)
        self.coordinates_combo.currentTextChanged.connect(self._coordinates_changed)
        self.fixed_combo.currentIndexChanged.connect(self._fixed_changed)
        self.value_combo.currentIndexChanged.connect(self._settings_changed)
        self.value_combo.currentTextChanged.connect(self._update_value_navigation)
        self.value_combo.lineEdit().textEdited.connect(self._value_edited)
        self.value_combo.lineEdit().editingFinished.connect(self._settings_changed)
        self.epsilon_spin.valueChanged.connect(self._settings_changed)
        self.processing_combo.currentIndexChanged.connect(self._processing_changed)
        self.derivative_window_spin.valueChanged.connect(self._processing_changed)
        self.preview_btn.clicked.connect(self.preview)
        self.batch_x_btn.clicked.connect(lambda: self.batch([self._kinds()[0]]))
        self.batch_y_btn.clicked.connect(lambda: self.batch([self._kinds()[1]]))
        self.batch_both_btn.clicked.connect(lambda: self.batch(self._kinds()))
        self.save_csv_btn.clicked.connect(lambda: self.save('csv'))
        self.save_png_btn.clicked.connect(lambda: self.save('png'))
        self.movie_btn.clicked.connect(self.create_movie)
        self.movie_btn.setEnabled(False)

    def _can_auto_update(self):
        w = self.workspace
        if not w._auto_update_allowed() or w.workspace_tabs.currentWidget() is not self or not self._stale:
            return False
        try:
            return (np.isfinite(float(self.value_combo.currentText())) and self.extract_btn.isEnabled()
                    and w._background_ready_for_auto() and not self._updating)
        except ValueError:
            return False

    def _invalidate_result(self):
        self._stale = True
        self._selection_revision += 1
        self.save_csv_btn.setEnabled(False)
        self.save_png_btn.setEnabled(False)
        self.movie_btn.setEnabled(False)
        self.plot.set_export_enabled(False)

    def _value_edited(self, *_):
        # Typing invalidates exports immediately but calculation waits for commit.
        self.updates.cancel()
        self._invalidate_result()

    def _transformed(self):
        data = self.workspace.state.data or {}
        if data.get('axis_space') != 'gate':
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
        if data is not self._values_source:
            self._values_source = data
            self._values_cache.clear()
        if data is None:
            return []
        transformed = kind in {'doping', 'efield'}
        key = (kind, min_points, self.epsilon_spin.value(),
               self.workspace.ratio_spin.value() if transformed else None,
               self.workspace._current_convention() if transformed else None)
        if key not in self._values_cache:
            self._values_cache[key] = find_all_cut_values(data['x_data'], data['y_data'], kind,
                                  self.workspace.ratio_spin.value(), self.epsilon_spin.value(),
                                  min_points=min_points, convention=self.workspace._current_convention(),
                                  axis_space=data.get('axis_space', 'gate'),
                                  x_axis_name=data.get('x_name', ''), y_axis_name=data.get('y_name', ''),
                                  exact_coordinates=True)
            while len(self._values_cache) > 8:
                self._values_cache.popitem(last=False)
        self._values_cache.move_to_end(key)
        return list(self._values_cache[key])

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
        self._update_value_navigation()
        names = self._names()
        for index, button in enumerate((self.batch_x_btn, self.batch_y_btn)):
            button.setText(f'All fixed {names[index]}')
            button.setToolTip(f'Export a spectral slice for every measured {names[index]} value; vary {names[1-index]}.')
        self.batch_both_btn.setText('All fixed axes')
        self.batch_both_btn.setToolTip(f'Export all fixed {names[0]} slices and all fixed {names[1]} slices.')
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
        self.updates.cancel()
        self._invalidate_result()
        self.ranges.detach()
        self.colors.detach()
        self.result = None
        self.plot.clear()
        self.save_csv_btn.setEnabled(False)
        self.save_png_btn.setEnabled(False)
        self.movie_btn.setEnabled(False)

    def _settings_changed(self, *_):
        if self._updating:
            return
        self._update_value_navigation()
        self._invalidate_result()
        self.status_label.setText('Settings changed; previous slice is out of date. '
                                 + ('Waiting to update…' if self.updates.checkbox.isChecked() else 'Click Update Now.'))
        try:
            if not np.isfinite(float(self.value_combo.currentText())):
                raise ValueError
        except ValueError:
            self.status_label.setText('Enter a finite fixed coordinate; previous slice is kept.')
        self.updates.request()
        self.workspace._schedule_session_save()

    def _value_neighbors(self):
        """Find strictly lower/higher measured coordinates, also for typed input."""
        try:
            current = float(self.value_combo.currentText())
        except ValueError:
            return None, None
        if not np.isfinite(current):
            return None, None
        values = np.array([self.value_combo.itemData(i) for i in range(self.value_combo.count())], dtype=float)
        # Compare the displayed numbers so rounding of an exact selected item
        # cannot make the same item appear to be its own neighbour.
        index = self.value_combo.currentIndex()
        if index >= 0 and self.value_combo.currentText() == self.value_combo.itemText(index):
            return (index - 1 if index > 0 else None,
                    index + 1 if index + 1 < len(values) else None)
        previous = int(np.searchsorted(values, current, side='left')) - 1
        following = int(np.searchsorted(values, current, side='right'))
        return previous if previous >= 0 else None, following if following < len(values) else None

    def _update_value_navigation(self):
        previous, following = self._value_neighbors()
        idle = self.workspace._thread is None
        self.previous_value_btn.setEnabled(idle and previous is not None)
        self.next_value_btn.setEnabled(idle and following is not None)

    def _step_value(self, direction):
        if self.workspace._thread is not None:
            return
        neighbors = self._value_neighbors()
        index = neighbors[0 if direction < 0 else 1]
        if index is None:
            return
        had_result = self.result is not None
        self.value_combo.setCurrentIndex(index)
        if had_result and self._can_auto_update() and self.updates.checkbox.isChecked():
            self.extract(automatic=True)

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
        if data is None:
            self._values_source = None
            self._values_cache.clear()
        is_rc = w.state.mode == 'Reflection'
        if data is not None:
            channels = len(data['energy'])
            blocked = self.derivative_window_spin.blockSignals(True)
            self.derivative_window_spin.setMaximum(max(3, channels if channels % 2 else channels - 1))
            self.derivative_window_spin.blockSignals(blocked)
        supports_de = data is not None and data.get('axis_space') in {'gate', 'transformed'}
        self.coordinates_combo.model().item(2).setEnabled(supports_de)
        loaded_de = data is not None and data.get('axis_space') == 'transformed'
        self.coordinates_combo.setVisible(not loaded_de)
        self.coordinates_label.setVisible(not loaded_de)
        signature = (id(data), w.state.mode, self._transformed(),
                     w.ratio_spin.value() if self._transformed() else None,
                     w._current_convention() if self._transformed() else None,
                     id(w.state.background_spectra) if is_rc else None,
                     w.background_scale_check.isChecked() if is_rc else None,
                     w.state.background_scale_factor if is_rc and w.background_scale_check.isChecked() else None,
                     self.processing_combo.currentData(),
                     self.derivative_window_spin.value() if self.processing_combo.currentData() == 'second_derivative' else None)
        if signature != self._signature:
            new_source = self._signature is None or signature[:2] != self._signature[:2]
            if self._signature is None or signature[:5] != self._signature[:5]:
                self.ranges.reset()
                self.colors.reset()
            self._signature = signature
            self._updating = True
            try:
                if new_source:
                    self._clear()
                else:
                    self._invalidate_result()
                index = max(0, self.fixed_combo.currentIndex())
                self.fixed_combo.clear()
                for kind, name in zip(self._kinds(), self._names()):
                    self.fixed_combo.addItem(f'Fixed {name}', kind)
                self.fixed_combo.setCurrentIndex(index)
                self._populate_values()
                self.status_label.setText('Choose a fixed coordinate, then Extract Slice. Batch exports CSV and PNG.')
            finally:
                self._updating = False
            if not new_source:
                self.updates.request()
        ready = data is not None and w.state.mode in {'PL', 'Reflection'} and w._auto_file_matches()
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
        self._update_value_navigation()
        self.setEnabled(w._thread is None)
        export_ready = (self.result is not None and not self._stale and w._thread is None
                        and w._auto_file_matches() and w.state.mode in {'PL', 'Reflection'})
        for button in (self.save_csv_btn, self.save_png_btn, self.movie_btn):
            button.setEnabled(export_ready)
        self.plot.set_export_enabled(export_ready)

    def _worker_options(self):
        w = self.workspace
        is_rc = w.state.mode == 'Reflection'
        return dict(convention=w._current_convention(), exact_coordinates=True,
                    spectral_processing=self.processing_combo.currentData(),
                    derivative_window=self.derivative_window_spin.value(),
                    background_spectra=w.state.background_spectra if is_rc else None,
                    background_scale=w._effective_background_scale() if is_rc else 1.)

    def _global_limits(self, kind=None):
        """Coordinate bounds need no spectrum extraction or processing."""
        data = self.workspace.state.data
        if data is None:
            return {}
        kind = kind or self.fixed_combo.currentData()
        first, second = np.asarray(data['x_data']), np.asarray(data['y_data'])
        if kind in {'doping', 'efield'} and data.get('axis_space') == 'gate':
            first, second = compute_transformed_coords(first, second, self.workspace.ratio_spin.value(),
                                                      convention=self.workspace._current_convention())
        varying = second if kind in {'x', 'doping'} else first
        varying = varying[np.isfinite(first) & np.isfinite(second)]
        result = {}
        for axis, values in (('x', np.asarray(data['energy'])), ('y', varying)):
            finite = values[np.isfinite(values)]
            if finite.size and finite.min() < finite.max():
                result[axis] = (float(finite.min()), float(finite.max()))
        return result

    def _display_ranges(self, kind=None, ranges=None):
        # Resolve Auto to the whole source sweep, also for a movie subset.
        ranges = deepcopy(self.ranges.recipe() if ranges is None else ranges)
        current = self.fixed_combo.currentData()
        kind = kind or current
        full = self._global_limits(kind)
        if kind != current:
            ranges['y'] = dict(auto=True)
        for axis, spec in ranges.items():
            if spec['auto'] and axis in full:
                spec.update(auto=False, min=full[axis][0], max=full[axis][1])
        return ranges

    def extract(self, *, automatic=False):
        self.updates.cancel()
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
            blocked = self.value_combo.blockSignals(True)
            self.value_combo.setEditText(f'{actual:.12g}')
            self.value_combo.blockSignals(blocked)
            specs = [dict(cut_type=kind, c_value=actual, epsilon=self.epsilon_spin.value())]
            self._invalidate_result()
            self._request_signature = (self._signature, self._selection_revision)
            self._navigate_after_extract = not automatic
            self.status_label.setText(f'Extracting at {actual:.12g} (requested {requested:.12g})…')
            worker = LineWorker(w.state.data, specs, w.ratio_spin.value(), **self._worker_options())
            w._run_worker(worker, self._show_result, context='Extracting spectral slice')
        except (ValueError, RuntimeError) as exc:
            self.status_label.setText(str(exc))
            w._append_log(str(exc), 'error')

    def _show_result(self, payload):
        self.refresh()
        if self._request_signature != (self._signature, self._selection_revision):
            self.status_label.setText('Settings changed during extraction. Waiting for the latest update.')
            self.updates.request()
            return
        cuts = payload.get('line_cuts', [])
        if not cuts or len(cuts[0]['axis_values']) < 2:
            self._clear()
            self.updates.cancel()
            self.status_label.setText('A 2D spectral slice needs at least two distinct points on the varying axis.')
            return
        result = cuts[0]
        is_rc = self.workspace.state.mode == 'Reflection'
        title = spectral_slice_title(result, spectral_title_precision(self._values(self.fixed_combo.currentData())))
        derivative = result.get('processing') == 'second_derivative'
        figure, _ = plot_line_cut_spectrogram(result, title=title,
                     cmap='RdBu_r' if is_rc or derivative else 'jet',
                     z_label=result.get('signal_label', 'RC (ΔI/I₀)' if is_rc else 'PL Intensity (a.u.)'))
        for axis, limits in self._global_limits().items():
            getattr(figure.axes[0], f'set_{axis}lim')(*limits)
        self.plot.set_figure(figure)
        self.ranges.attach(figure)
        self.colors.attach(figure)
        self.result = result
        self._stale = False
        self.plot.set_export_enabled(True)
        self.save_csv_btn.setEnabled(True)
        self.save_png_btn.setEnabled(True)
        self.movie_btn.setEnabled(True)
        self.status_label.setText(f"{title}; {len(result['axis_values'])} scan points × {len(result['energy'])} energy channels.")
        if self._navigate_after_extract:
            self.workspace.workspace_tabs.setCurrentWidget(self)
        self.workspace._schedule_session_save()

    def show_existing_cut(self, cut):
        """Display a restored legacy recipe in the consolidated optical view."""
        self._navigate_after_extract = True
        data = self.workspace.state.data or {}
        if data.get('axis_space') == 'transformed' and cut['cut_type'] in {'doping', 'efield'}:
            # Legacy recipes name semantic D/E axes; the unified controls name
            # actual loaded X/Y columns, which may be ordered either way.
            x_is_fixed = classify_axis_role(data.get('x_name', '')) == cut['cut_type']
            fixed_key, varying_key = ('x', 'y') if x_is_fixed else ('y', 'x')
            cut = dict(cut, cut_type=fixed_key, coordinate_space='original',
                       fixed_axis_label=data.get(f'{fixed_key}_name', fixed_key.upper()),
                       axis_label=data.get(f'{varying_key}_name', varying_key.upper()))
        self.processing_combo.setCurrentIndex(0)
        self.coordinates_combo.setCurrentText('Transformed D/E' if cut['cut_type'] in {'doping', 'efield'} else 'Original X/Y')
        index = self.fixed_combo.findData(cut['cut_type'])
        if index >= 0:
            self.fixed_combo.setCurrentIndex(index)
        self.value_combo.setEditText(str(cut['c_value_used']))
        self._request_signature = (self._signature, self._selection_revision)
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
            display_ranges = {kind: self._display_ranges(kind) for kind in kinds}
            worker = BatchLineWorker(w.state.data, kinds, self.epsilon_spin.value(), output,
                                     w.ratio_spin.value(), display_ranges=display_ranges,
                                     color_settings=self.colors.recipe(), **self._worker_options())
            w._run_worker(worker, self._batch_finished, context='Exporting spectral slices')
        except (ValueError, OSError) as exc:
            self.status_label.setText(str(exc))
            w._append_log(str(exc), 'error')

    def _batch_finished(self, payload):
        self.status_label.setText(f"Exported {payload['total_cuts']} slices; {len(payload['saved_files'])} new files.")
        self.workspace._on_batch_lines_ready(payload)

    def save(self, kind):
        if self.result is None or self._stale or self.workspace._thread is not None or not self.workspace._auto_file_matches():
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
                    processing=self.processing_combo.currentData(), derivative_window=self.derivative_window_spin.value(),
                    auto_update=self.updates.checkbox.isChecked(),
                    movie=self._movie_recipe)

    def restore(self, recipe):
        recipe = recipe if isinstance(recipe, dict) else {}
        self.updates.cancel()
        self.updates.checkbox.setChecked(recipe.get('auto_update', True) is not False)
        self._movie_recipe = recipe.get('movie', {}) if isinstance(recipe.get('movie'), dict) else {}
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
        self.updates.cancel()

    def create_movie(self):
        if self.result is None or self._stale or not self.workspace._auto_file_matches():
            return
        if self.result is None or self.workspace._thread is not None:
            return
        try:
            colors = self.colors.recipe()
            low, high = self.plot.current_figure.axes[0].collections[0].get_clim()
            colors.update(min=low, max=high)
            self.plot.canvas.draw()
            pixels = np.asarray(self.plot.canvas.buffer_rgba())
            height, width, _ = pixels.shape
            poster = QImage(pixels.data, width, height, pixels.strides[0], QImage.Format_RGBA8888).copy()
            recipe = dict(self._movie_recipe)
            if recipe.get('range_axis', self.fixed_combo.currentData()) != self.fixed_combo.currentData():
                recipe.pop('ranges', None)
            dialog = SpectralMovieDialog(self._values(self.fixed_combo.currentData(), min_points=2),
                       self.result['fixed_axis_label'], self.ranges.recipe(), colors,
                       recipe, self.workspace, poster=poster, full_ranges=self._global_limits())
            dialog.preview_requested.connect(lambda configuration: self.start_movie_preview(dialog.preview, configuration))
            dialog.preview.frame_requested.connect(lambda request: self._preview_frame(dialog.preview, request))
            accepted = dialog.exec() == QDialog.Accepted
            try:
                configuration = dialog.configuration()
                self._remember_movie_configuration(configuration)
            except (ValueError, TypeError):
                configuration = None
            if accepted and configuration is not None:
                self.start_movie(configuration)
            dialog.deleteLater()
        except (ValueError, RuntimeError) as exc:
            self.workspace._append_log(str(exc), 'error')

    def start_movie(self, configuration):
        w = self.workspace
        if self.result is None or self._stale or w._thread is not None or not w._auto_file_matches():
            return
        try:
            if not w._validate_reflection_background_ready():
                return
            directory = os.path.join(w._ensure_output_dir(), 'spectral_slices', w.state.mode.lower(), 'movies')
            kind = self.fixed_combo.currentData()
            processing = self.processing_combo.currentData()
            stem = f'{kind}_sequence'
            if processing == 'second_derivative':
                stem += f'_d2dE2_w{self.derivative_window_spin.value()}'
            worker = self._movie_worker(configuration, os.path.join(directory, stem + '.mp4'))
            self._remember_movie_configuration(configuration)
            progress = QProgressDialog('Preparing slice sequence…', 'Cancel', 0, 0, w)
            progress.setWindowTitle('Export spectral slice MP4')
            progress.setWindowModality(Qt.NonModal)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setMinimumDuration(0)
            progress.canceled.connect(worker.cancel.set)
            self._movie_progress = progress
            worker.movie_progress.connect(self._on_movie_progress, Qt.QueuedConnection)
            worker.error.connect(self._close_movie_progress, Qt.QueuedConnection)
            w._run_worker(worker, self._movie_finished, context='Exporting spectral slice MP4')
            progress.show()
        except (ValueError, RuntimeError, OSError) as exc:
            self._close_movie_progress()
            w._append_log(f'Movie export failed: {exc}', 'error')

    def _remember_movie_configuration(self, configuration):
        self._movie_recipe = deepcopy({key: value for key, value in configuration.items() if key != 'values'})
        self._movie_recipe['range_axis'] = self.fixed_combo.currentData()
        self.workspace._schedule_session_save()

    def _movie_worker(self, configuration, destination, worker_type=SpectralMovieWorker, **extra):
        w = self.workspace
        kind = self.fixed_combo.currentData()
        processing = self.processing_combo.currentData()
        metadata = dict(source_csv=w.state.csv_path, mode=w.state.mode,
                        x_name=w.state.data.get('x_name'), y_name=w.state.data.get('y_name'),
                        coordinate_space=self.result['coordinate_space'], cut_type=kind,
                        fixed_axis_label=self.result['fixed_axis_label'], axis_label=self.result['axis_label'],
                        ratio=w.ratio_spin.value(), convention=w._current_convention(),
                        epsilon=self.epsilon_spin.value(), processing=processing,
                        derivative_window=self.derivative_window_spin.value(),
                        background_paths=list(w.state.background_paths) if w.state.mode == 'Reflection' else [],
                        background_average_mode=w.state.background_average_mode,
                        background_scale=w._effective_background_scale() if w.state.mode == 'Reflection' else 1.)
        return worker_type(w.state.data, kind, configuration['values'],
                     destination, configuration['options'],
                     self._display_ranges(ranges=configuration.get('ranges')), configuration['colors'], metadata,
                     w.ratio_spin.value(), self.epsilon_spin.value(), **self._worker_options(), **extra)

    def start_movie_preview(self, preview, configuration):
        w = self.workspace
        if self.result is None or w._thread is not None:
            preview.status.setText('Extract a slice and wait for the current task before previewing.')
            preview.generation_finished()
            return
        try:
            if not w._validate_reflection_background_ready():
                preview.status.setText('Load a matching background before previewing Reflection movies.')
                preview.generation_finished()
                return
            if not preview.generating:
                preview.begin(configuration)
            worker = self._movie_worker(configuration, None, SpectralPreviewWorker, session=preview.session)
            w._run_worker(worker, preview.movie_ready, context='Preparing spectral MP4 preview')
            preview.bind_worker(worker, w._thread)
        except (ValueError, RuntimeError, OSError) as exc:
            preview.generation_error(str(exc))
            preview.generation_finished()

    def _preview_frame(self, preview, request):
        w = self.workspace
        if w._thread is not None:
            return
        worker = SpectralPreviewFrameWorker(request)
        w._run_worker(worker, preview.frame_ready, context='Rendering preview slice', quiet=True)
        preview.bind_frame_worker(worker, w._thread)

    @Slot(int, int, str)
    def _on_movie_progress(self, current, total, message):
        if self._movie_progress is not None:
            self._movie_progress.setRange(0, total)
            self._movie_progress.setValue(current)
            self._movie_progress.setLabelText(message)

    @Slot(str)
    def _close_movie_progress(self, *_):
        if self._movie_progress is not None:
            self._movie_progress.close()
            self._movie_progress.deleteLater()
            self._movie_progress = None

    def _movie_finished(self, payload):
        self._close_movie_progress()
        if payload.get('cancelled'):
            self.status_label.setText('Movie export cancelled.')
            return
        info = payload['info']
        self.status_label.setText(f"Saved MP4: {info['duration_s']:.2f} s; {len(info['values'])} slices.")
        self.workspace._append_log('Saved MP4: ' + payload['path'], 'success')
        self.workspace._append_log('Saved movie settings: ' + payload['sidecar'], 'success')
        for skipped in info['skipped']:
            self.workspace._append_log(f"Skipped fixed value {skipped['value']:.12g}: {skipped['reason']}", 'warn')
