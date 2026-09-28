"""Per-CSV analysis recipes; raw arrays and exported files are never persisted."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox


CONTROLS = (
    "mode_combo", "vbg_combo", "vtg_combo", "bg_average_mode_combo",
    "int_min_spin", "int_max_spin", "fixed_energy_spin", "baseline_spin",
    "auto_baseline_check", "ratio_spin", "convention_combo", "sg_window_spin",
    "sg_poly_spin", "rc_feature_combo", "background_scale_check",
    "scale_left_min_spin", "scale_left_max_spin", "scale_right_min_spin",
    "scale_right_max_spin", "reflection_preview_vbg_spin", "reflection_preview_vtg_spin",
    "map_type_combo", "map_axes_combo", "map_cmap_combo", "map_auto_scale_check",
    "map_vmin_spin", "map_vmax_spin", "batch_epsilon_spin",
)
MAP_TASKS = {
    "original_map": "intensity_original", "transformed_map": "intensity_transformed",
    "peak_map_original": "peak_original", "peak_map_transformed": "peak_transformed",
    "fixed_map_original": "fixed_original", "fixed_map_transformed": "fixed_transformed",
    "ibias_map_original": "ibias_original", "ibias_map_transformed": "ibias_transformed",
    "resistance_map_original": "resistance_original", "resistance_map_transformed": "resistance_transformed",
}


class SessionMemoryMixin:
    def _setup_session_memory(self, directory=None):
        base = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
        self._session_directory = Path(directory) if directory else Path(base) / "MegasweepAnalysis" / "sessions"
        self._session_path = ""
        self._session_ready = False
        self._pending_session = None
        self._restoring_session = False
        self._restore_steps = []
        self._remembered_views = set()
        self._remembered_preview = False
        self._remembered_lines = False
        self._session_defaults = self._capture_controls()
        self._session_save_timer = QTimer(self)
        self._session_save_timer.setSingleShot(True)
        self._session_save_timer.setInterval(500)
        self._session_save_timer.timeout.connect(self._save_session)
        for name in CONTROLS:
            widget = getattr(self, name)
            signal = (widget.currentTextChanged if isinstance(widget, QComboBox) else
                      widget.toggled if isinstance(widget, QCheckBox) else widget.valueChanged)
            signal.connect(self._schedule_session_save)
        self.bg_csv_edit.textChanged.connect(self._schedule_session_save)
        self.out_edit.textChanged.connect(self._schedule_session_save)
        self.cuts_table.itemChanged.connect(self._schedule_session_save)
        self.cuts_table.model().rowsRemoved.connect(self._schedule_session_save)
        self.workspace_tabs.currentChanged.connect(self._schedule_session_save)

    def _capture_controls(self):
        values = {}
        for name in CONTROLS:
            widget = getattr(self, name)
            values[name] = (widget.currentText() if isinstance(widget, QComboBox) else
                            widget.isChecked() if isinstance(widget, QCheckBox) else widget.value())
        return values

    def _session_file(self, csv_path):
        key = os.path.normcase(os.path.abspath(csv_path))
        return self._session_directory / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def _schedule_session_save(self, *_):
        if self._session_ready and not self._restoring_session:
            self._session_save_timer.start()

    def _save_session(self):
        if not self._session_ready or self._restoring_session or self._thread is not None:
            return
        self._remembered_views.update(MAP_TASKS[key] for key in self.state.figures if key in MAP_TASKS)
        self._remembered_lines |= bool(self.state.line_cut_results)
        self._remembered_preview |= self._reflection_preview_message is not None
        payload = {
            "version": 1, "csv_path": self._session_path,
            "controls": self._capture_controls(),
            "background_paths": self._get_background_paths(),
            "output_dir": self.out_edit.text(),
            "line_specs": self._collect_line_specs(),
            "views": sorted(self._remembered_views),
            "preview": self._remembered_preview, "lines": self._remembered_lines,
            "tab": self.workspace_tabs.currentIndex(),
            "axis_ranges": self._axis_ranges,
        }
        path = self._session_file(self._session_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
            self._pending_session = payload
        except (OSError, ValueError) as exc:
            self._append_log(f"Could not save analysis settings: {exc}", "warn")

    def _select_session(self, path):
        """Called before header controls change, so the old CSV is saved intact."""
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(self._session_path):
            return False
        self._save_session()
        self._session_save_timer.stop()
        self._session_ready = False
        self._axis_ranges = {}
        self._session_path = os.path.abspath(path)
        self._pending_session = None
        self._remembered_views = set()
        self._remembered_preview = self._remembered_lines = False
        try:
            file = self._session_file(path)
            if file.exists():
                payload = json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("controls"), dict):
                    raise ValueError("Unsupported analysis settings format")
                for name in ("background_paths", "views"):
                    if not isinstance(payload.get(name, []), list) or not all(isinstance(v, str) for v in payload.get(name, [])):
                        raise ValueError(f"Invalid {name}")
                if not isinstance(payload.get("output_dir", ""), str):
                    raise ValueError("Invalid output directory")
                specs = payload.get("line_specs", [])
                if not isinstance(specs, list):
                    raise ValueError("Invalid line cuts")
                for spec in specs:
                    if not isinstance(spec, dict) or spec.get("cut_type") not in {"doping", "efield"}:
                        raise ValueError("Invalid line cut")
                    for name in ("c_value", "epsilon"):
                        value = spec.get(name)
                        if not isinstance(value, (int, float)) or not math.isfinite(value):
                            raise ValueError("Invalid line cut value")
                    if spec["epsilon"] < 0:
                        raise ValueError("Invalid line cut tolerance")
                self._pending_session = payload
        except (OSError, ValueError) as exc:
            self._append_log(f"Saved settings could not be read; using defaults: {exc}", "warn")
        self._clear_background_state()
        self._set_background_paths([])
        return True

    def _apply_session_controls(self, values, names=CONTROLS):
        for name in names:
            if name not in values:
                continue
            widget, value = getattr(self, name), values[name]
            previous = widget.blockSignals(True)
            try:
                if isinstance(widget, QComboBox) and isinstance(value, str):
                    if widget.findText(value) >= 0:
                        widget.setCurrentText(value)
                elif isinstance(widget, QCheckBox) and isinstance(value, bool):
                    widget.setChecked(value)
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)) and isinstance(value, (int, float)) and math.isfinite(value):
                    widget.setValue(value)
            finally:
                widget.blockSignals(previous)

    def _prepare_session_headers(self):
        self._intensity_range_user_modified = False
        self._fixed_energy_user_modified = False
        self._baseline_user_modified = False
        values = (self._pending_session or {}).get("controls", self._session_defaults)
        # Mode changes rebuild map selectors and defaults; apply it first.
        self._apply_session_controls(values, ("mode_combo",))
        self._on_mode_changed(self.mode_combo.currentText())
        self._apply_session_controls(self._session_defaults,
                                     tuple(n for n in CONTROLS if n not in {"mode_combo", "vbg_combo", "vtg_combo"}))
        if self._pending_session:
            self._apply_session_controls(values, ("vbg_combo", "vtg_combo"))
        self.out_edit.setText((self._pending_session or {}).get("output_dir", os.path.dirname(self._session_path)))
        self._on_output_dir_changed()
        self.cuts_table.setRowCount(0)

    def _restore_session_loaded(self):
        self._session_ready = True
        saved = self._pending_session
        if saved:
            self._restoring_session = True
            self._axis_ranges = self._valid_axis_ranges(saved.get("axis_ranges", {}))
            self._apply_session_controls(saved["controls"])
        self.state.current_ratio = self.ratio_spin.value()
        self.state.transform_convention = self._current_convention()
        self.formula_label.setText(self._formula_text())
        if not saved:
            self._schedule_session_save()
            return
        self._intensity_range_user_modified = True
        self._fixed_energy_user_modified = True
        self._baseline_user_modified = True
        self.cuts_table.setRowCount(0)
        for spec in saved.get("line_specs", []):
            self._add_cut(spec["cut_type"], spec["c_value"], spec["epsilon"])
        paths = saved.get("background_paths", [])
        self._set_background_paths(paths)
        self._remembered_views = set(saved.get("views", [])) & set(MAP_TASKS.values())
        self._remembered_preview = bool(saved.get("preview"))
        self._remembered_lines = bool(saved.get("lines"))
        self._restore_steps = []
        self._append_log("Restored saved analysis parameters for this CSV.", "success")
        if self.state.mode == "Reflection" and paths:
            missing = [p for p in paths if not os.path.isfile(p)]
            if missing:
                self._append_log("Automatic plot restore stopped: background file missing: " + "; ".join(missing), "warn")
                self._restoring_session = False
                return
            self._restore_steps.append("background")
        elif self.state.mode == "Reflection" and (self._remembered_views or self._remembered_preview or self._remembered_lines):
            self._append_log("Saved plots need a background; select and load it to continue.", "warn")
            self._restoring_session = False
            return
        if self._remembered_preview and self.state.mode == "Reflection":
            self._restore_steps.append("preview")
        if self._remembered_views:
            self._restore_steps.append("maps")
        if self._remembered_lines and self._collect_line_specs():
            self._restore_steps.append("lines")
        # The next stage is dispatched only after QThread cleanup.

    def _advance_session_restore(self):
        if not self._restoring_session or self._thread is not None:
            return
        try:
            while self._restore_steps:
                step = self._restore_steps.pop(0)
                if step == "background":
                    self._start_background_load()
                elif step == "preview":
                    self._preview_reflection_spectra()
                elif step == "maps":
                    if not self._validate_reflection_background_ready():
                        raise ValueError("Background validation failed")
                    tasks = []
                    for view in sorted(self._remembered_views):
                        for task in self._required_tasks_for_view(view):
                            if task not in tasks:
                                tasks.append(task)
                    self._start_analysis_refresh(tasks, "Restoring saved maps")
                elif step == "lines":
                    self._start_line_stage()
                if self._thread is not None:
                    return
            self._show_current_map_view()
            tab = (self._pending_session or {}).get("tab", 0)
            if isinstance(tab, int) and 0 <= tab < self.workspace_tabs.count():
                self.workspace_tabs.setCurrentIndex(tab)
            self._append_log("Saved analysis restored. Export files were not rewritten.", "success")
        except Exception as exc:
            self._append_log(f"Automatic analysis restore stopped: {exc}", "error")
        self._restoring_session = False
        self._restore_steps = []
        self._schedule_session_save()

    def closeEvent(self, event):
        if self._thread is not None:
            self._append_log("Please wait for the analysis task to finish before closing.", "warn")
            event.ignore()
            return
        self._save_session()
        self._session_save_timer.stop()
        super().closeEvent(event)
