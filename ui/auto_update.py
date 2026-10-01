"""Shared automatic/manual plot updates with coalesced Qt scheduling."""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QPushButton, QWidget
from ui.map_display import WrapLayout


class AutoUpdateControls(QWidget):
    preference_changed = Signal()

    def __init__(self, callback, can_update, *, delay=300, parent=None, manual_callback=None):
        super().__init__(parent)
        self._callback = callback
        self._manual_callback = manual_callback or callback
        self._can_update = can_update
        self._pending = False
        self.checkbox = QCheckBox('Auto Update')
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip('Update this plot after parameter edits. Turn off to apply changes with Update Now.')
        self.button = QPushButton('Update Now')
        self.button.setProperty('class', 'primary')
        layout = WrapLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(delay)
        self.timer.timeout.connect(self._dispatch)
        self.checkbox.toggled.connect(self._toggled)
        self.button.clicked.connect(self.update_now)

    def request(self):
        if self.checkbox.isChecked():
            self._pending = True
            self.timer.start()

    def cancel(self):
        self.timer.stop()
        self._pending = False

    def resume(self):
        if self._pending and self.checkbox.isChecked() and not self.timer.isActive():
            self.timer.start()

    def _dispatch(self):
        if self._pending and self.checkbox.isChecked() and self._can_update():
            self._pending = False
            self._callback()

    def update_now(self):
        self.cancel()
        self._manual_callback()

    def _toggled(self, checked):
        if checked:
            self.request()
        else:
            self.cancel()
        self.preference_changed.emit()
