"""Compact, view-only scientific axis limits for a single plot."""
import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QSizePolicy


class PlotRangeControls(QWidget):
    changed = Signal()

    def __init__(self, *, title='Display range'):
        super().__init__()
        self._figure = None
        self._full_limits = {}
        self._ranges = {}
        self._syncing = False
        self.controls, self.labels = {}, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title))
        for axis in ('x', 'y'):
            row = QHBoxLayout()
            row.setSpacing(4)
            label, auto = QLabel(axis.upper()), QCheckBox('Auto')
            auto.setChecked(True)
            lower, upper = QLineEdit('0'), QLineEdit('1')
            row.addWidget(label)
            row.addWidget(auto)
            for name, edit in (('Min', lower), ('Max', upper)):
                caption = QLabel(name)
                caption.setBuddy(edit)
                edit.setAccessibleName(f'{axis.upper()} range {name}')
                edit.setToolTip('Display only. Scientific notation is accepted, e.g. -2e-9.')
                edit.setMinimumWidth(45)
                edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                row.addWidget(caption)
                row.addWidget(edit, 1)
                edit.editingFinished.connect(lambda a=axis: self._edited(a))
            auto.toggled.connect(lambda checked, a=axis: self._edited(a))
            layout.addLayout(row)
            self.controls[axis] = auto, lower, upper
            self.labels[axis] = label
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color:#b91c1c;')
        layout.addWidget(self.error)
        self.reset()

    def reset(self):
        self._figure = None
        self._full_limits = {}
        self._ranges = {a: {'auto': True, 'min': 0.0, 'max': 1.0} for a in ('x', 'y')}
        self.error.clear()
        self.error.hide()
        for axis, label in self.labels.items():
            label.setToolTip(f'{axis.upper()} display range')
        self._sync()

    def recipe(self):
        return {axis: dict(spec) for axis, spec in self._ranges.items()}

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
        self._apply()
        self._sync()
        self.changed.emit()

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
                limits = self._full_limits.get(axis, (spec['min'], spec['max'])) if spec['auto'] else (spec['min'], spec['max'])
                for edit, value in zip((lower, upper), limits):
                    edit.setText(f'{value:.12g}')
                    edit.setEnabled(not spec['auto'])
        finally:
            self._syncing = False
