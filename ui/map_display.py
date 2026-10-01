"""Responsive map controls and view-only axis limits."""
from __future__ import annotations

import math
from megasweep_analysis import update_map_colors
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLayout, QSizePolicy, QWidget


class WrapLayout(QLayout):
    """Wrap whole control groups instead of squeezing their individual fields."""
    def __init__(self):
        super().__init__()
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return QSize(sum(i.sizeHint().width() for i in self.items) + self.spacing() * max(0, len(self.items) - 1), self.minimumSize().height())

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, min(size.width(), rect.width()), size.height()))
            x += size.width() + self.spacing()
            height = max(height, size.height())
        return y + height - rect.y()


class MapDisplayMixin:
    def _build_axis_range_group(self, axis):
        group = QWidget()
        row = QHBoxLayout(group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        label = QLabel(f"{axis.upper()} range")
        label.setMaximumWidth(110)
        auto = QCheckBox("Auto")
        auto.setChecked(True)
        lower = self._dspin(-1e12, 1e12, .1, 6, 0)
        upper = self._dspin(-1e12, 1e12, .1, 6, 1)
        for widget in (lower, upper):
            widget.setFixedWidth(118)
            widget.setKeyboardTracking(False)
            widget.setEnabled(False)
        for widget in (label, auto, QLabel("Min"), lower, QLabel("Max"), upper):
            row.addWidget(widget)
        setattr(self, f"{axis}_range_label", label)
        setattr(self, f"{axis}_range_auto_check", auto)
        setattr(self, f"{axis}_range_min_spin", lower)
        setattr(self, f"{axis}_range_max_spin", upper)
        group.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return group

    def _setup_map_display(self):
        self._axis_ranges = {}
        self._syncing_display = False
        for axis in ("x", "y"):
            for suffix, signal in (("auto_check", "toggled"), ("min_spin", "valueChanged"), ("max_spin", "valueChanged")):
                widget = getattr(self, f"{axis}_range_{suffix}")
                getattr(widget, signal).connect(lambda _, a=axis: self._on_axis_range_changed(a))
        self.map_cmap_combo.currentTextChanged.connect(self._update_map_colors)
        self.map_auto_scale_check.toggled.connect(self._update_map_colors)
        self.map_vmin_spin.valueChanged.connect(self._update_map_colors)
        self.map_vmax_spin.valueChanged.connect(self._update_map_colors)

    def _on_axis_range_changed(self, axis):
        if self._syncing_display:
            return
        auto = getattr(self, f"{axis}_range_auto_check").isChecked()
        lower = getattr(self, f"{axis}_range_min_spin")
        upper = getattr(self, f"{axis}_range_max_spin")
        lower.setEnabled(not auto)
        upper.setEnabled(not auto)
        if not auto and lower.value() >= upper.value():
            self.map_status_label.setText(f"{axis.upper()} range: Min must be less than Max; previous range kept.")
            return
        space = self.map_axes_combo.currentText()
        self._axis_ranges.setdefault(space, {})[axis] = {"auto": auto, "min": lower.value(), "max": upper.value()}
        for task, (_, figure_key) in self._MAP_CACHE_FIELDS.items():
            if task.endswith("_original") == (space == "Original"):
                figure = self.state.figures.get(figure_key)
                if figure is not None:
                    self._apply_axis_ranges(figure, space)
        self._sync_axis_range_controls()
        if self.map_plot_tab.canvas is not None:
            self.map_plot_tab.canvas.draw_idle()
        self._update_status_labels()
        self._schedule_session_save()

    def _apply_axis_ranges(self, figure, space):
        if not figure.axes:
            return
        axes = figure.axes[0]
        if not hasattr(figure, "_full_map_limits"):
            figure._full_map_limits = {"x": axes.get_xlim(), "y": axes.get_ylim()}
        settings = self._axis_ranges.get(space, {})
        for axis in ("x", "y"):
            spec = settings.get(axis, {"auto": True})
            limits = figure._full_map_limits[axis] if spec["auto"] else (spec["min"], spec["max"])
            getattr(axes, f"set_{axis}lim")(*limits)

    def _sync_axis_range_controls(self):
        if not hasattr(self, "_axis_ranges"):
            return
        figure = self._current_map_figure()
        space = self.map_axes_combo.currentText()
        self._syncing_display = True
        try:
            for axis in ("x", "y"):
                spec = self._axis_ranges.get(space, {}).get(axis, {"auto": True, "min": 0, "max": 1})
                limits = (spec["min"], spec["max"])
                label = f"{axis.upper()} range"
                if figure is not None:
                    if spec["auto"]:
                        limits = figure._full_map_limits[axis]
                    label = f"{axis.upper()}: " + getattr(figure.axes[0], f"get_{axis}label")()
                range_label = getattr(self, f"{axis}_range_label")
                range_label.setText(range_label.fontMetrics().elidedText(label, Qt.ElideRight, 110))
                range_label.setToolTip(label)
                getattr(self, f"{axis}_range_auto_check").setChecked(spec["auto"])
                for suffix, value in zip(("min", "max"), limits):
                    widget = getattr(self, f"{axis}_range_{suffix}_spin")
                    widget.setValue(value)
                    widget.setEnabled(not spec["auto"])
                    widget.setToolTip(label)
        finally:
            self._syncing_display = False

    def _update_map_colors(self, *_):
        if not hasattr(self, "_axis_ranges"):
            return
        manual = not self.map_auto_scale_check.isChecked()
        self.map_vmin_spin.setEnabled(manual)
        self.map_vmax_spin.setEnabled(manual)
        figure = self._current_map_figure()
        payload = self._current_map_payload()
        if figure is None or payload is None:
            return
        lower, upper = None, None
        if manual:
            lower, upper = self.map_vmin_spin.value(), self.map_vmax_spin.value()
            if lower >= upper:
                self.map_status_label.setText("Color range: Min must be less than Max; previous range kept.")
                return
        if update_map_colors(figure, payload['Z2D'], self.map_cmap_combo.currentText(), lower, upper):
            figure.canvas.draw_idle()
        self._update_status_labels()

    @staticmethod
    def _valid_axis_ranges(value):
        if not isinstance(value, dict):
            return {}
        clean = {}
        for space in ("Original", "Transformed"):
            if not isinstance(value.get(space), dict):
                continue
            for axis in ("x", "y"):
                spec = value[space].get(axis)
                if not isinstance(spec, dict) or not isinstance(spec.get("auto"), bool):
                    continue
                if not all(isinstance(spec.get(k), (int, float)) and math.isfinite(spec[k]) for k in ("min", "max")):
                    continue
                if not spec["auto"] and spec["min"] >= spec["max"]:
                    continue
                clean.setdefault(space, {})[axis] = dict(spec)
        return clean
