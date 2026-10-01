"""Live color limits with validated scientific-notation input."""
import math

from matplotlib.colors import Normalize
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from ui.widgets import NumericLineEdit


class ColorScaleControls(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._figure = None
        self._full_limits = (0., 1.)
        self._spec = dict(auto=True, min=0., max=1.)
        self._syncing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel('3. Color scale'))
        self.auto = QCheckBox('Auto')
        row.addWidget(self.auto)
        self.lower, self.upper = NumericLineEdit(), NumericLineEdit()
        for name, edit in (('V min', self.lower), ('V max', self.upper)):
            label = QLabel(name)
            label.setBuddy(edit)
            edit.setAccessibleName(f'Color {name}')
            edit.setToolTip('Color-bar limit in the plotted signal units. Scientific notation is accepted.')
            row.addWidget(label)
            row.addWidget(edit)
            edit.editingFinished.connect(self._edited)
        row.addStretch(1)
        self.auto.toggled.connect(self._edited)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty('fluentSeverity', 'danger')
        layout.addWidget(self.error)
        self.reset()

    def reset(self):
        self.detach()
        self._spec = dict(auto=True, min=0., max=1.)
        self.error.clear()
        self.error.hide()
        self._sync()

    def detach(self):
        self._figure = None
        self._full_limits = (0., 1.)

    def attach(self, figure):
        self._figure = figure
        self._full_limits = figure.axes[0].collections[0].get_clim()
        self._apply()
        self._sync()

    def recipe(self):
        return dict(self._spec)

    def restore(self, value):
        self.reset()
        if isinstance(value, dict) and isinstance(value.get('auto'), bool):
            try:
                low, high = float(value['min']), float(value['max'])
                if math.isfinite(low) and math.isfinite(high) and low < high:
                    self._spec = dict(auto=value['auto'], min=low, max=high)
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
        self._sync()

    def _edited(self, *_):
        if self._syncing:
            return
        self.lower.setEnabled(not self.auto.isChecked())
        self.upper.setEnabled(not self.auto.isChecked())
        try:
            low, high = self._full_limits if self.auto.isChecked() else (float(self.lower.text()), float(self.upper.text()))
            if not math.isfinite(low) or not math.isfinite(high) or low >= high:
                raise ValueError()
        except (ValueError, OverflowError):
            self.error.setText('Color scale: enter finite V min < V max. Previous limits kept.')
            self.error.show()
            return
        self._spec = dict(auto=self.auto.isChecked(), min=low, max=high)
        self.error.clear()
        self.error.hide()
        self._apply()
        self._sync()
        self.changed.emit()

    def _apply(self):
        if self._figure is None:
            return
        low, high = self._full_limits if self._spec['auto'] else (self._spec['min'], self._spec['max'])
        # Replace both bounds together so colorbar callbacks never see an
        # intermediate inverted range when switching to disjoint limits.
        self._figure.axes[0].collections[0].set_norm(Normalize(low, high))
        self._figure.canvas.draw_idle()

    def _sync(self):
        self._syncing = True
        try:
            self.auto.setChecked(self._spec['auto'])
            values = self._full_limits if self._spec['auto'] else (self._spec['min'], self._spec['max'])
            for edit, value in zip((self.lower, self.upper), values):
                edit.setText(f'{value:.12g}')
                edit.setEnabled(not self._spec['auto'])
        finally:
            self._syncing = False
