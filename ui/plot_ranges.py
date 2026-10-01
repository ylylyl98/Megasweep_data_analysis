"""Compact, view-only scientific axis limits for a single plot."""
import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox
from ui.widgets import NumericLineEdit


class PlotRangeControls(QWidget):
    changed = Signal()

    def __init__(self, *, title='Display range', show_mode_selector=False):
        super().__init__()
        self._figure = None
        self._full_limits = {}
        self._ranges = {}
        self._syncing = False
        self.controls, self.labels = {}, {}
        self.modes = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title))
        for axis in ('x', 'y'):
            row = QHBoxLayout()
            row.setSpacing(4)
            label, auto = QLabel(axis.upper()), QCheckBox('Auto')
            auto.setChecked(True)
            lower, upper = NumericLineEdit('0'), NumericLineEdit('1')
            row.addWidget(label)
            if show_mode_selector:
                mode = QComboBox()
                mode.addItem('Auto', True)
                mode.addItem('Fixed', False)
                mode.setAccessibleName(f'{axis.upper()} range mode')
                mode.setToolTip('Auto: use the full coordinate range. Fixed: keep Min/Max across slices and exports.')
                row.addWidget(mode)
                self.modes[axis] = mode
                # Keep the established boolean control/recipe interface for
                # existing callers; the visible selector makes both modes clear.
                auto.setParent(self)
                auto.hide()
                mode.currentIndexChanged.connect(lambda _index, a=axis: self._mode_changed(a))
            else:
                row.addWidget(auto)
            for name, edit in (('Min', lower), ('Max', upper)):
                caption = QLabel(name)
                caption.setBuddy(edit)
                edit.setAccessibleName(f'{axis.upper()} range {name}')
                edit.setToolTip('Display only. Scientific notation is accepted, e.g. -2e-9.')
                row.addWidget(caption)
                row.addWidget(edit)
                edit.editingFinished.connect(lambda a=axis: self._edited(a))
            row.addStretch(1)
            auto.toggled.connect(lambda checked, a=axis: self._edited(a))
            layout.addLayout(row)
            self.controls[axis] = auto, lower, upper
            self.labels[axis] = label
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty('fluentSeverity', 'danger')
        layout.addWidget(self.error)
        self.reset()

    def reset(self):
        self._figure = None
        self._full_limits = {}
        self._fixed_limits = {}
        self._ranges = {a: {'auto': True, 'min': 0.0, 'max': 1.0} for a in ('x', 'y')}
        self.error.clear()
        self.error.hide()
        for axis, label in self.labels.items():
            label.setToolTip(f'{axis.upper()} display range')
        self._sync()

    def recipe(self):
        result = {axis: dict(spec) for axis, spec in self._ranges.items()}
        for axis, limits in self._fixed_limits.items():
            if result[axis]['auto']:
                result[axis].update(fixed_min=limits[0], fixed_max=limits[1])
        return result

    def restore(self, value):
        self.reset()
        if isinstance(value, dict):
            for axis in ('x', 'y'):
                spec = value.get(axis)
                if not isinstance(spec, dict) or not isinstance(spec.get('auto'), bool):
                    continue
                try:
                    low, high = float(spec['min']), float(spec['max'])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(low) and math.isfinite(high) and low < high:
                    self._ranges[axis] = {'auto': spec['auto'], 'min': low, 'max': high}
                    if not spec['auto']:
                        self._fixed_limits[axis] = (low, high)
                    else:
                        try:
                            saved = float(spec['fixed_min']), float(spec['fixed_max'])
                            if all(math.isfinite(v) for v in saved) and saved[0] < saved[1]:
                                self._fixed_limits[axis] = saved
                        except (KeyError, TypeError, ValueError, OverflowError):
                            pass
        self._sync()

    def attach(self, figure):
        self._figure = figure
        self.error.clear()
        self.error.hide()
        axes = figure.axes[0]
        self._full_limits = {a: getattr(axes, f'get_{a}lim')() for a in ('x', 'y')}
        for axis in ('x', 'y'):
            self.labels[axis].setToolTip(f'{axis.upper()}: {getattr(axes, f"get_{axis}label")()}')
        self._apply()
        self._sync()

    def set_full_limits(self, limits):
        """Provide Auto bounds for controls without an attached plot."""
        self._full_limits = {axis: tuple(bounds) for axis, bounds in limits.items()
                             if axis in self.controls and len(bounds) == 2
                             and all(math.isfinite(v) for v in bounds) and bounds[0] < bounds[1]}
        self._apply()
        self._sync()

    def detach(self):
        self._figure = None
        self._full_limits = {}

    def _edited(self, axis):
        if self._syncing:
            return
        auto, lower, upper = self.controls[axis]
        lower.setEnabled(not auto.isChecked())
        upper.setEnabled(not auto.isChecked())
        try:
            low, high = (self._full_limits.get(axis, (0, 1)) if auto.isChecked()
                         else (float(lower.text()), float(upper.text())))
            if not math.isfinite(low) or not math.isfinite(high) or low >= high:
                raise ValueError()
        except (ValueError, OverflowError):
            self.error.setText(f'{axis.upper()}: enter finite Min < Max. Previous range kept.')
            self.error.show()
            return
        self.error.clear()
        self.error.hide()
        self._ranges[axis] = {'auto': auto.isChecked(), 'min': low, 'max': high}
        if not auto.isChecked():
            self._fixed_limits[axis] = (low, high)
        self._apply()
        self._sync()
        self.changed.emit()

    def _mode_changed(self, axis):
        if not self._syncing:
            if not self.modes[axis].currentData() and axis in self._fixed_limits:
                for edit, value in zip(self.controls[axis][1:], self._fixed_limits[axis]):
                    edit.setText(f'{value:.12g}')
            self.controls[axis][0].setChecked(self.modes[axis].currentData())

    def _apply(self):
        if self._figure is None:
            return
        axes = self._figure.axes[0]
        for axis, spec in self._ranges.items():
            limits = self._full_limits[axis] if spec['auto'] else (spec['min'], spec['max'])
            getattr(axes, f'set_{axis}lim')(*limits)
        self._figure.canvas.draw_idle()

    def _sync(self):
        self._syncing = True
        try:
            for axis, spec in self._ranges.items():
                auto, lower, upper = self.controls[axis]
                auto.setChecked(spec['auto'])
                if axis in self.modes:
                    mode = self.modes[axis]
                    mode.setCurrentIndex(mode.findData(spec['auto']))
                limits = self._full_limits.get(axis, (spec['min'], spec['max'])) if spec['auto'] else (spec['min'], spec['max'])
                for edit, value in zip((lower, upper), limits):
                    edit.setText(f'{value:.12g}')
                    edit.setEnabled(not spec['auto'])
        finally:
            self._syncing = False
