"""Header-driven scalar transport workspace."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton,
    QCheckBox, QTabWidget, QSizePolicy,
)

from megasweep_analysis import plot_map, update_map_colors
from ui.exporting import save_dataframe, save_figure, save_figure_with_axes_size
from transport_analysis import load_transport_csv, transport_map, transport_cut, transport_curve
from ui.workers import BaseWorker
from ui.plot_ranges import PlotRangeControls
from ui.widgets import NumericLineEdit
from ui.auto_update import AutoUpdateControls


class TransportLoadWorker(BaseWorker):
    def __init__(self, path):
        super().__init__()
        self.path = path

    def process(self):
        return load_transport_csv(self.path)


class TransportPanel(QWidget):
    changed = Signal()

    def __init__(self, plot_factory, output_directory, log, parent=None):
        super().__init__(parent)
        self.output_directory = output_directory
        self.log = log
        self.data = self.result = self.cut = None
        self._updating = False
        self._map_stale = self._cut_stale = True
        self.active = lambda: True
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        self.settings_widget = QWidget()
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.setSpacing(4)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self.x_combo, self.y_combo, self.channel_combo = QComboBox(), QComboBox(), QComboBox()
        self.plot_kind_combo = QComboBox()
        self.plot_kind_combo.addItem('2D map', 'map')
        self.plot_kind_combo.addItem('1D curve', 'curve')
        self.axis_hint = QLabel()
        self.axis_hint.setWordWrap(True)
        self.axis_hint.setTextFormat(Qt.PlainText)
        self.axis_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.suggest_button = QPushButton('Use Suggested Axes')
        self.suggest_button.clicked.connect(self.apply_suggested_axes)
        self._restored_axes = False
        self.direction_combo, self.pass_combo = QComboBox(), QComboBox()
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(['RdBu_r', 'viridis', 'jet', 'plasma', 'inferno', 'seismic'])
        self.auto_scale = QCheckBox('Auto color scale')
        self.auto_scale.setChecked(True)
        self.min_edit, self.max_edit = NumericLineEdit('0'), NumericLineEdit('1e-9')
        for widget in (self.min_edit, self.max_edit):
            widget.setEnabled(False)
            widget.setToolTip('Signal units; scientific notation is accepted, e.g. -2e-9.')
        self.map_updates = AutoUpdateControls(lambda: self.refresh_map(automatic=True),
                                             self._can_auto_map, parent=self, manual_callback=self.refresh_map)
        self.refresh_button = self.map_updates.button
        self.map_updates.preference_changed.connect(self.changed.emit)
        settings_layout.addWidget(self.axis_hint)
        settings_layout.addWidget(self.suggest_button)
        self._row(settings_layout, [('Plot', self.plot_kind_combo)])
        self._row(settings_layout, [('X', self.x_combo), ('Y', self.y_combo)])
        self.y_row = self.y_combo.parentWidget()
        self.x_combo.setAccessibleName('X column')
        self.y_combo.setAccessibleName('Y column')
        self._row(settings_layout, [('Signal', self.channel_combo)])
        self._row(settings_layout, [('Direction', self.direction_combo), ('Pass', self.pass_combo)])
        self.color_controls = QWidget()
        color_layout = QVBoxLayout(self.color_controls)
        color_layout.setSpacing(4)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self._row(color_layout, [('Color', self.cmap_combo), ('', self.auto_scale)])
        self._row(color_layout, [('Min', self.min_edit), ('Max', self.max_edit)])
        settings_layout.addWidget(self.color_controls)
        self.map_ranges = PlotRangeControls()
        self.map_ranges.changed.connect(self.changed.emit)
        settings_layout.addWidget(self.map_ranges)
        settings_layout.addWidget(self.map_updates)
        layout.addWidget(self.settings_widget)
        self.status = QLabel('Load a Transport CSV, then select X, Y and signal from its headers.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.map_plot = plot_factory('Transport map')
        self.cut_plot = plot_factory('Transport line cut')
        self.tabs.addTab(self.map_plot, 'Map')
        cut_workspace = QWidget()
        cut_layout = QVBoxLayout(cut_workspace)
        cut_layout.setSpacing(4)
        self.fixed_combo, self.cut_value_combo = QComboBox(), QComboBox()
        self.cut_updates = AutoUpdateControls(lambda: self.refresh_cut(automatic=True),
                                             self._can_auto_cut, parent=self, manual_callback=self.refresh_cut)
        self.cut_button = self.cut_updates.button
        self.cut_updates.preference_changed.connect(self.changed.emit)
        self.cut_controls_widget = QWidget()
        cut_controls_layout = QVBoxLayout(self.cut_controls_widget)
        cut_controls_layout.setSpacing(4)
        cut_controls_layout.setContentsMargins(0, 0, 0, 0)
        self._row(cut_controls_layout, [('Fixed column', self.fixed_combo)])
        self._row(cut_controls_layout, [('Value', self.cut_value_combo)])
        cut_controls_layout.addWidget(self.cut_updates)
        self.cut_ranges = PlotRangeControls()
        self.cut_ranges.changed.connect(self.changed.emit)
        cut_controls_layout.addWidget(self.cut_ranges)
        cut_layout.addWidget(self.cut_controls_widget)
        cut_layout.addWidget(self.cut_plot, 1)
        self.tabs.addTab(cut_workspace, 'Line Cut')
        layout.addWidget(self.tabs, 1)
        self.export_buttons = {}
        self.export_widget = QWidget()
        export_layout = QVBoxLayout(self.export_widget)
        export_layout.setSpacing(4)
        export_layout.setContentsMargins(0, 0, 0, 0)
        for kind in ('map', 'cut'):
            row = QHBoxLayout()
            for extension in ('png', 'csv'):
                button = QPushButton(f'Save {kind.title()} {extension.upper()}')
                button.clicked.connect(lambda checked=False, k=kind, e=extension: self.export(k, e))
                row.addWidget(button)
                self.export_buttons[(kind, extension)] = button
            export_layout.addLayout(row)
        layout.addWidget(self.export_widget)
        for combo in (self.x_combo, self.y_combo, self.channel_combo, self.direction_combo, self.pass_combo):
            combo.currentIndexChanged.connect(self._selection_changed)
        self.plot_kind_combo.currentIndexChanged.connect(self._selection_changed)
        self.fixed_combo.currentIndexChanged.connect(self._cut_axis_changed)
        self.cut_value_combo.currentIndexChanged.connect(self._clear_cut)
        self.cmap_combo.currentTextChanged.connect(self._color_changed)
        self.auto_scale.toggled.connect(self._color_changed)
        self.min_edit.editingFinished.connect(self._color_changed)
        self.max_edit.editingFinished.connect(self._color_changed)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.clear()

    def _selection_valid(self):
        names = [self.x_combo.currentData(), self.channel_combo.currentData()]
        if self.plot_kind_combo.currentData() == 'map':
            names.append(self.y_combo.currentData())
        return self.data is not None and all(name in self.data['columns'] for name in names) and len(set(names)) == len(names)

    def _can_auto_map(self):
        return self.isEnabled() and self.active() and self._map_stale and self._selection_valid() and not self._updating

    def _can_auto_cut(self):
        return (self.isEnabled() and self.active() and self.tabs.currentIndex() == 1
                and not self._map_stale and self.result is not None and self.result['kind'] == 'map'
                and self._cut_stale and self.cut_value_combo.currentData() is not None and not self._updating)

    def _tab_changed(self, *_):
        if self.tabs.currentIndex() == 1:
            self.cut_updates.request()
        self.map_updates.resume()

    def cancel_updates(self):
        self.map_updates.cancel()
        self.cut_updates.cancel()

    @staticmethod
    def _row(layout, items):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        for label, control in items:
            group = QWidget()
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            if label:
                text = QLabel(label)
                text.setBuddy(control)
                if len(items) == 1:
                    text.setMinimumWidth(76)
                group_layout.addWidget(text)
                control.setAccessibleName(label)
            if isinstance(control, QComboBox):
                control.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                control.setMinimumContentsLength(6)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            group_layout.addWidget(control, 1)
            row.addWidget(group, 1)
        layout.addWidget(container)
        return container

    def clear(self):
        self.cancel_updates()
        self._updating = True
        self._map_stale = self._cut_stale = True
        self.data = self.result = self.cut = None
        self.map_ranges.reset()
        self.cut_ranges.reset()
        self._restored_axes = False
        self.plot_kind_combo.setCurrentIndex(0)
        self.axis_hint.setText('Load a CSV to suggest its scan coordinates.')
        for combo in (self.x_combo, self.y_combo, self.channel_combo):
            combo.clear()
            combo.addItem('Select column…', None)
        for combo in (self.direction_combo, self.pass_combo):
            combo.clear()
            combo.addItem('All', None)
        self.fixed_combo.clear()
        self.cut_value_combo.clear()
        self.map_plot.clear()
        self.cut_plot.clear()
        self.status.setText('Load a Transport CSV, then select X, Y and signal from its headers.')
        self._updating = False
        self._update_actions()

    def set_data(self, data, recipe=None):
        self.clear()
        self._updating = True
        self.data = data
        self.map_updates.checkbox.setChecked(not isinstance(recipe, dict) or recipe.get('auto_update', True) is not False)
        self.cut_updates.checkbox.setChecked(not isinstance(recipe, dict) or recipe.get('auto_cut_update', True) is not False)
        for combo in (self.x_combo, self.y_combo, self.channel_combo):
            for name in data['columns']:
                combo.addItem(self._label(name), name)
        frame = data['df']
        if 'FastDirection' in frame:
            for value in frame['FastDirection'].dropna().unique():
                if value:
                    self.direction_combo.addItem(value, value)
        if 'PassIndex' in frame:
            for value in sorted(frame['PassIndex'].dropna().unique()):
                self.pass_combo.addItem(f'{value:g}', float(value))
        self.cmap_combo.setCurrentText('RdBu_r')
        self.auto_scale.setChecked(True)
        self.min_edit.setText('0')
        self.max_edit.setText('1e-9')
        saved_kind = recipe.get('kind', 'map') if isinstance(recipe, dict) else 'map'
        saved_axes_valid = isinstance(recipe, dict) and recipe.get('x') in data['columns'] and (
            saved_kind == 'curve' or (saved_kind == 'map' and recipe.get('y') in data['columns'] and recipe.get('x') != recipe.get('y')))
        if saved_axes_valid:
            self.plot_kind_combo.setCurrentIndex(self.plot_kind_combo.findData(saved_kind))
            self._restored_axes = True
        else:
            self._set_suggested_axes()
        if isinstance(recipe, dict):
            for name, combo in self._selection_controls().items():
                if name in ('x', 'y') and not saved_axes_valid:
                    continue
                index = combo.findData(recipe.get(name))
                combo.setCurrentIndex(max(0, index))
            if self.cmap_combo.findText(str(recipe.get('cmap'))) >= 0:
                self.cmap_combo.setCurrentText(recipe['cmap'])
            self.auto_scale.setChecked(recipe.get('auto_scale', True) is not False)
            self.min_edit.setText(str(recipe.get('min', '0')))
            self.max_edit.setText(str(recipe.get('max', '1e-9')))
        self._updating = False
        scan_status = data['metadata'].get('status', 'not recorded')
        self.status.setText(f'{len(frame)} rows loaded; acquisition status: {scan_status}. Select columns from the CSV headers.')
        for warning in data['warnings']:
            self.log(warning, 'warn')
        self._update_actions()
        self._update_axis_hint()
        if saved_axes_valid and recipe.get('channel') in data['columns']:
            self.map_ranges.restore(recipe.get('map_ranges'))
        if saved_axes_valid and recipe.get('map'):
            self.refresh_map()
            self.fixed_combo.setCurrentText(str(recipe.get('fixed_axis', '')))
            index = self.cut_value_combo.findData(recipe.get('cut_value'))
            if index >= 0:
                self.cut_value_combo.setCurrentIndex(index)
            if recipe.get('cut') and index >= 0:
                self.cut_ranges.restore(recipe.get('cut_ranges'))
                self.refresh_cut()
        if self.result is None:
            self.map_updates.request()

    def _selection_controls(self):
        return dict(x=self.x_combo, y=self.y_combo, channel=self.channel_combo,
                    direction=self.direction_combo, pass_index=self.pass_combo)

    def _set_suggested_axes(self):
        suggestion = (self.data or {}).get('axis_suggestion', {})
        if suggestion.get('x') is None:
            return
        self.plot_kind_combo.setCurrentIndex(self.plot_kind_combo.findData(suggestion['kind']))
        for combo, key in ((self.x_combo, 'x'), (self.y_combo, 'y')):
            combo.setCurrentIndex(max(0, combo.findData(suggestion[key])))
        self._restored_axes = False

    def apply_suggested_axes(self):
        if not self.data or not self.data['axis_suggestion']['x']:
            return
        self.map_ranges.reset()
        self.cut_ranges.reset()
        self._updating = True
        self._set_suggested_axes()
        self._updating = False
        self._selection_changed()

    def _update_axis_hint(self):
        if self.data is None:
            return
        suggestion = self.data['axis_suggestion']
        current = (self.plot_kind_combo.currentData(), self.x_combo.currentData(),
                   self.y_combo.currentData() if self.plot_kind_combo.currentData() == 'map' else None)
        expected = (suggestion['kind'], suggestion['x'], suggestion['y'])
        prefix = 'Saved axes restored. ' if self._restored_axes else (
            'Manual selection. ' if current != expected else '')
        self.axis_hint.setText(prefix + suggestion['reason'])

    def recipe(self):
        return {**{key: combo.currentData() for key, combo in self._selection_controls().items()},
                'kind': self.plot_kind_combo.currentData(),
                'auto_update': self.map_updates.checkbox.isChecked(),
                'auto_cut_update': self.cut_updates.checkbox.isChecked(),
                'cmap': self.cmap_combo.currentText(), 'auto_scale': self.auto_scale.isChecked(),
                'min': self.min_edit.text(), 'max': self.max_edit.text(),
                'map_ranges': self.map_ranges.recipe(), 'cut_ranges': self.cut_ranges.recipe(),
                'map': self.result is not None, 'cut': self.cut is not None,
                'fixed_axis': self.fixed_combo.currentText(), 'cut_value': self.cut_value_combo.currentData()}

    def _label(self, name):
        unit = self.data['units'].get(name, '').strip() if self.data else ''
        return f'{name} ({unit})' if unit else name

    def _update_actions(self):
        is_map = self.plot_kind_combo.currentData() == 'map'
        self.y_row.setVisible(is_map)
        self.color_controls.setVisible(is_map)
        self.y_combo.setEnabled(is_map)
        self.y_combo.setToolTip('Map coordinate. For a 1D curve, Signal is the vertical axis.')
        self.cmap_combo.setEnabled(is_map)
        self.auto_scale.setEnabled(is_map)
        self.min_edit.setEnabled(is_map and not self.auto_scale.isChecked())
        self.max_edit.setEnabled(is_map and not self.auto_scale.isChecked())
        suggestion = (self.data or {}).get('axis_suggestion', {})
        self.suggest_button.setEnabled(suggestion.get('x') is not None)
        self.tabs.setTabText(0, 'Map' if is_map else 'Curve')
        self.tabs.setTabEnabled(1, is_map)
        self.tabs.setTabVisible(1, is_map)
        self.refresh_button.setEnabled(self.data is not None)
        self.cut_button.setEnabled(is_map and self.result is not None and not self._map_stale and self.cut_value_combo.count() > 0)
        self.fixed_combo.setEnabled(is_map)
        self.cut_value_combo.setEnabled(is_map)
        for (kind, _), button in self.export_buttons.items():
            button.setEnabled(self.result is not None and not self._map_stale if kind == 'map'
                              else self.cut is not None and not self._cut_stale and not self._map_stale)
            button.setVisible(kind == 'map' or is_map)
        self.map_plot.set_export_enabled(self.result is not None and not self._map_stale and self.isEnabled())
        self.cut_plot.set_export_enabled(self.cut is not None and not self._cut_stale and not self._map_stale and self.isEnabled())
        for extension in ('png', 'csv'):
            self.export_buttons[('map', extension)].setText(f"Save {'Map' if is_map else 'Curve'} {extension.upper()}")

    def _selection_changed(self, *_):
        if self._updating:
            return
        self._map_stale = True
        if self.sender() in (self.x_combo, self.y_combo, self.channel_combo, self.plot_kind_combo, self.suggest_button):
            self.map_ranges.reset()
            self.cut_ranges.reset()
        if self.sender() in (self.x_combo, self.y_combo, self.plot_kind_combo):
            self._restored_axes = False
        self._clear_cut()
        self.status.setText('Selection changed; previous plot is out of date. '
                            + ('Waiting to update…' if self.map_updates.checkbox.isChecked() else 'Click Update Now.'))
        self._update_actions()
        self._update_axis_hint()
        self.changed.emit()
        self.map_updates.request()

    def _clear_cut(self, *_):
        if self._updating:
            return
        self._cut_stale = True
        self._update_actions()
        self.changed.emit()
        self.cut_updates.request()

    def _cut_axis_changed(self, *_):
        if self._updating:
            return
        self.cut_ranges.reset()
        self.cut_value_combo.clear()
        if self.result is not None and self.result['kind'] == 'map':
            name = self.fixed_combo.currentText()
            if name in self.result['samples']:
                for value in sorted(self.result['samples'][name].unique()):
                    self.cut_value_combo.addItem(f'{value:.12g}', float(value))
        self._clear_cut()

    def _limits(self):
        if self.auto_scale.isChecked():
            return None, None
        low, high = float(self.min_edit.text()), float(self.max_edit.text())
        if not np.isfinite([low, high]).all() or low >= high:
            raise ValueError('Color limits must be finite and Min must be below Max.')
        return low, high

    def _draw_map(self):
        r = self.result
        if r['kind'] == 'curve':
            fig = Figure(figsize=(6, 4.8), layout='constrained')
            ax = fig.add_subplot(111)
            frame = r['samples']
            keys = [key for key in ('PassIndex', 'FastDirection') if key in frame]
            groups = list(frame.groupby(keys, sort=False, dropna=False)) if keys else [(None, frame)]
            for key, rows in groups:
                label = str(key) if key is not None else r['channel']
                ax.plot(rows[r['x_name']], rows[r['channel']], '.-', label=label)
            if 1 < len(groups) <= 12:
                ax.legend(title=' / '.join(keys), fontsize='small')
            ax.set_xlabel(self._label(r['x_name']))
            ax.set_ylabel(self._label(r['channel']))
            ax.set_title(self._title())
            self.map_plot.set_figure(fig)
            self.map_ranges.attach(fig)
            return
        low, high = self._limits()
        fig, _ = plot_map(r['X2D'], r['Y2D'], r['Z2D'],
                          x_label=self._label(r['x_name']), y_label=self._label(r['y_name']),
                          z_label=self._label(r['channel']), title=self._title(),
                          cmap=self.cmap_combo.currentText(), vmin=low, vmax=high)
        self.map_plot.set_figure(fig)
        self.map_ranges.attach(fig)

    def _title(self):
        r = self.result
        parts = [r['channel']]
        if r['direction'] is not None:
            parts.append(r['direction'])
        if r['pass_index'] is not None:
            parts.append(f"pass {r['pass_index']:g}")
        return ' | '.join(parts)

    def _color_changed(self, *_):
        if self._updating:
            return
        self._update_actions()
        try:
            if self.result is not None:
                if self.result['kind'] == 'map':
                    low, high = self._limits()
                    figure = self.map_plot.current_figure
                    if update_map_colors(figure, self.result['Z2D'], self.cmap_combo.currentText(), low, high):
                        figure.canvas.draw_idle()
        except ValueError as exc:
            self.status.setText(str(exc))
        self.changed.emit()

    def refresh_map(self, *, automatic=False):
        self.map_updates.cancel()
        if self.data is None:
            return
        fixed, value = self.fixed_combo.currentText(), self.cut_value_combo.currentData()
        selected_tab = self.tabs.currentIndex()
        previous = self.result
        try:
            if self.plot_kind_combo.currentData() == 'curve':
                self.result = transport_curve(self.data, self.x_combo.currentData(), self.channel_combo.currentData(),
                                              direction=self.direction_combo.currentData(), pass_index=self.pass_combo.currentData())
            else:
                self.result = transport_map(self.data, self.x_combo.currentData(), self.y_combo.currentData(),
                                        self.channel_combo.currentData(), direction=self.direction_combo.currentData(),
                                        pass_index=self.pass_combo.currentData())
            self._draw_map()
            self._map_stale = False
            self._updating = True
            self.fixed_combo.clear()
            if self.result['kind'] == 'map':
                self.fixed_combo.addItems([self.result['x_name'], self.result['y_name']])
                if self.fixed_combo.findText(fixed) >= 0:
                    self.fixed_combo.setCurrentText(fixed)
            self._updating = False
            self._cut_axis_changed()
            index = self.cut_value_combo.findData(value)
            if index >= 0:
                self.cut_value_combo.setCurrentIndex(index)
            if not automatic:
                self.tabs.setCurrentIndex(0)
            elif selected_tab == 1 and self.cut_updates.checkbox.isChecked():
                self.refresh_cut(automatic=True)
            r = self.result
            if r['kind'] == 'map':
                self.status.setText(f"{len(r['samples'])} measured points; {np.isnan(r['Z2D']).sum()} blank cells. "
                                    'Missing or invalid values are not interpolated. Reload CSV to read new measurements.')
            else:
                self.status.setText(f"{len(r['samples'])} measured points. Signal is the vertical axis. "
                                    'Scan order is preserved; passes/directions are plotted separately.')
        except (ValueError, KeyError) as exc:
            self.result = previous
            self._map_stale = True
            self._clear_cut()
            self.status.setText(str(exc))
            self.log(str(exc), 'warn')
        self._update_actions()
        self.changed.emit()

    def refresh_cut(self, *, automatic=False):
        self.cut_updates.cancel()
        if self._map_stale or self.result is None or self.result['kind'] != 'map' or self.cut_value_combo.currentData() is None:
            return
        try:
            self.cut = transport_cut(self.result, self.fixed_combo.currentText(), self.cut_value_combo.currentData())
            fig = Figure(figsize=(6, 4.8), layout='constrained')
            ax = fig.add_subplot(111)
            # Reindex on the map axis so missing interior points break the line.
            c = self.cut
            coordinate_grid = self.result['X2D'][:, 0] if c['axis'] == self.result['x_name'] else self.result['Y2D'][0, :]
            signal = c['samples'].set_index(c['axis'])[c['channel']].reindex(coordinate_grid)
            ax.plot(coordinate_grid, signal, '.-')
            ax.set_xlabel(self._label(c['axis']))
            ax.set_ylabel(self._label(c['channel']))
            ax.set_title(f"{self._title()} | {self._label(c['fixed_axis'])} = {c['fixed_value']:.12g}")
            self.cut_plot.set_figure(fig)
            self.cut_ranges.attach(fig)
            self._cut_stale = False
            if not automatic:
                self.tabs.setCurrentIndex(1)
        except ValueError as exc:
            self._clear_cut()
            self.status.setText(str(exc))
        self._update_actions()
        self.changed.emit()

    def export(self, kind, extension):
        r = self.result if kind == 'map' else self.cut
        if r is None or self._map_stale or (kind == 'cut' and self._cut_stale) or not self.isEnabled():
            return
        try:
            names = [self.result['kind'] if kind == 'map' else kind, self.result['channel'], self.result['x_name'],
                     self.result['y_name'] or 'signal',
                     self.result['direction'] or 'all-directions',
                     'all-passes' if self.result['pass_index'] is None else f"pass-{self.result['pass_index']:g}"]
            if kind == 'cut':
                names += [r['fixed_axis'], f"{r['fixed_value']:.12g}"]
            filename = '_'.join(re.sub(r'[^A-Za-z0-9_.-]+', '-', name) for name in names) + '.' + extension
            path = Path(self.output_directory()) / filename
            if extension == 'csv':
                # Preserve all measured columns, units are in the original CSV;
                # unmeasured grid cells are deliberately absent from this table.
                exported = save_dataframe(r['samples'], path)
            elif kind == 'map' and self.result['kind'] == 'map':
                exported = save_figure_with_axes_size(self.map_plot.current_figure, str(path), axes_size=(3, 3), dpi=300)
            else:
                exported = save_figure(self.map_plot.current_figure if kind == 'map' else self.cut_plot.current_figure, str(path))
            self.log(exported.message, 'success')
        except Exception as exc:
            self.status.setText(f'Export failed: {exc}')
            self.log(f'Export failed: {exc}', 'error')
