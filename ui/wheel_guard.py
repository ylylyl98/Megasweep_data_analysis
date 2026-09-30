"""Treat wheels over editors as scrolling, never as parameter edits."""
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QAbstractSpinBox, QComboBox, QWidget


class EditorWheelGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, QWidget):
            return False
        control = watched
        while control is not None:
            # Popup lists and other scrollable views retain normal scrolling.
            if isinstance(control, QAbstractScrollArea):
                return False
            if isinstance(control, (QAbstractSpinBox, QComboBox)):
                break
            control = control.parentWidget()
        if control is None:
            return False

        parent = control.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            viewport = parent.viewport()
            forwarded = QWheelEvent(
                QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                event.source(), event.pointingDevice(),
            )
            QApplication.sendEvent(viewport, forwarded)
        event.accept()
        return True


def install_editor_wheel_guard():
    """Install once for all workspaces and dynamically created dialogs."""
    app = QApplication.instance()
    if not hasattr(app, '_editor_wheel_guard'):
        app._editor_wheel_guard = EditorWheelGuard(app)
        app.installEventFilter(app._editor_wheel_guard)
