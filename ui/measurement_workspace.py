from __future__ import annotations

import os
import subprocess
import sys
import traceback

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QFileDialog, QMessageBox, QTableWidgetItem, QWidget

from megasweep_analysis import (
    estimate_global_baseline,
    find_all_cut_values,
    guess_sweep_axis_columns,
    resolve_dataset_output_dir,
    spectral_axes_match,
    validate_axis_selection,
)
from ui.exporting import save_line_csv, save_map_csv, save_figure, save_figure_with_axes_size
from ui.app_state import AppState
from ui.session_memory import SessionMemoryMixin
from ui.map_display import MapDisplayMixin
from ui.workers import (
    AnalysisRefreshWorker,
    BatchLineWorker,
    CsvLoadWorker,
    IntensityWorker,
    LineWorker,
    PeakWorker,
    TransformWorker,
)


from ui.styles import _LIGHT_STYLE
from ui.wheel_guard import install_editor_wheel_guard
from ui.transport import TransportLoadWorker
from ui.optical_layout import OpticalLayoutMixin
from ui.reflection_workflow import ReflectionWorkflowMixin
from ui.plot_results import PlotResultsMixin
from ui.automatic_workspace import AutomaticWorkspaceMixin


class MeasurementWorkspace(AutomaticWorkspaceMixin, OpticalLayoutMixin, ReflectionWorkflowMixin, PlotResultsMixin,
                           MapDisplayMixin, SessionMemoryMixin, QWidget):
    _EXPORT_MAP_AXES_SIZE = (3.0, 3.0)
    _LOG_COLORS = {
        "info": "#334155",
        "success": "#15803d",
        "error": "#b91c1c",
        "warn": "#b45309",
    }

    def __init__(self, *, mode=None, session_directory=None):
        super().__init__()
        install_editor_wheel_guard()
        if mode not in (None, "PL", "Reflection", "Transport"):
            raise ValueError(f"Unknown measurement mode: {mode}")
        self._fixed_mode = mode
        self.setWindowTitle("Megasweep Analysis")
        self.setMinimumSize(1100, 680)
        if not self._fixed_mode:
            self.setStyleSheet(_LIGHT_STYLE)

        self.state = AppState()
        self._thread: QThread | None = None
        self._worker = None
        self._worker_success_callback = None
        self._pending_context = ""
        self._map_cache_signatures = {}
        self._spectral_peak_cache = {}
        self._building_combos = False
        self._intensity_range_user_modified = False
        self._intensity_defaults_csv_signature: tuple[str, float, float, int] | None = None
        self._suppress_intensity_tracking = False
        self._fixed_energy_user_modified = False
        self._suppress_fixed_energy_tracking = False
        self._baseline_user_modified = False
        self._suppress_baseline_tracking = False
        self._background_paths: list[str] = []
        self._reflection_preview_message: str | None = None
        self._rc_span_selector = None
        self._dirty_views = {
            "intensity_original": True,
            "intensity_transformed": True,
            "peak_original": True,
            "peak_transformed": True,
            "fixed_original": True,
            "fixed_transformed": True,
            "ibias_original": True,
            "ibias_transformed": True,
            "resistance_original": True,
            "resistance_transformed": True,
            "line_cuts": True,
        }

        self._setup_ui()
        for spin in self.findChildren(QAbstractSpinBox):
            spin.setKeyboardTracking(False)
        self._setup_map_display()
        self._setup_session_memory(session_directory)
        self._setup_auto_updates()
        self.transport_panel.changed.connect(self._schedule_session_save)
        if self._fixed_mode:
            self._on_mode_changed(self._fixed_mode)
            self._session_defaults = self._capture_controls()
        self.setAcceptDrops(True)
        self._refresh_stage_states()

    @staticmethod
    def _describe_range(values: np.ndarray) -> str:
        array = np.asarray(values, dtype=float)
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            return "no finite values"
        return f"{float(np.min(finite)):.4f} to {float(np.max(finite)):.4f}"

    @staticmethod
    def _extract_csv_paths_from_mime(mime_data, *, allow_multiple: bool = True) -> list[str]:
        if not mime_data.hasUrls():
            return []
        paths = []
        for url in mime_data.urls():
            path = url.toLocalFile().strip()
            if path.lower().endswith(".csv"):
                paths.append(path)
        if not allow_multiple:
            return paths[:1]
        return paths

    @staticmethod
    def _widget_contains_global_pos(widget: QWidget, global_pos) -> bool:
        if widget is None or not widget.isVisible():
            return False
        local_pos = widget.mapFromGlobal(global_pos)
        return widget.rect().contains(local_pos)

    def _drop_target_from_global_pos(self, global_pos) -> str:
        if (
            hasattr(self, "bg_section")
            and self.bg_section.isVisible()
            and any(
                self._widget_contains_global_pos(widget, global_pos)
                for widget in (self.bg_section, self.bg_csv_edit, self.bg_average_mode_combo, self.load_bg_btn)
            )
        ):
            return "background"
        return "primary"


    def _mark_dirty(self, *keys: str) -> None:
        for key in keys:
            self._dirty_views[key] = True
        if self._current_view_key() in keys:
            self._request_map_update()

    def _mark_clean(self, *keys: str) -> None:
        for key in keys:
            self._dirty_views[key] = False

    def _current_view_key(self) -> str:
        map_label = self.map_type_combo.currentText()
        if map_label == "Resistance":
            map_kind = "resistance"
        elif map_label == "Ibias":
            map_kind = "ibias"
        elif map_label == "RC at Energy":
            map_kind = "fixed"
        elif map_label in {"Peak Energy", "RC Peak Position"}:
            map_kind = "peak"
        else:
            map_kind = "intensity"
        axes = "original" if self.map_axes_combo.currentText() == "Original" else "transformed"
        return f"{map_kind}_{axes}"

    def _current_view_description(self) -> str:
        label = self.map_type_combo.currentText()
        return f"{label} on {self.map_axes_combo.currentText().lower()} axes"

    def _compact_map_title(self, z_name: str, *, fixed_energy: float | None = None) -> str:
        """Return the approved concise title; source names stay in export filenames."""
        if z_name == "Ibias":
            return "Ibias"
        if z_name == "Resistance":
            return "R = Vbias / Ibias"
        if fixed_energy is not None:
            return f"{z_name} | E = {fixed_energy:.6f} eV"
        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
        return f"{z_name} | {e_lo:.6f}–{e_hi:.6f} eV"

    def _required_tasks_for_view(self, view_key: str) -> list[str]:
        match view_key:
            case "intensity_original":
                return ["intensity_original"]
            case "intensity_transformed":
                return ["intensity_original", "intensity_transformed"]
            case "peak_original":
                return ["peak_original"]
            case "peak_transformed":
                return ["peak_transformed"]
            case "fixed_original":
                return ["fixed_original"]
            case "fixed_transformed":
                return ["fixed_original", "fixed_transformed"]
            case "ibias_original":
                return ["ibias_original"]
            case "ibias_transformed":
                return ["ibias_transformed"]
            case "resistance_original":
                return ["resistance_original"]
            case "resistance_transformed":
                return ["resistance_transformed"]
        return ["intensity_original"]


    def _sync_color_limit_controls(self) -> None:
        """Show the current map's actual finite data range while auto-scale is on."""
        if not hasattr(self, "map_vmin_spin") or not self.map_auto_scale_check.isChecked():
            return
        payload = self._current_map_payload()
        if payload is None or "Z2D" not in payload:
            return
        z_data = np.asarray(payload["Z2D"], dtype=float)
        finite = z_data[np.isfinite(z_data)]
        if finite.size == 0:
            return
        vmin = float(np.min(finite))
        vmax = float(np.max(finite))
        old_vmin_block = self.map_vmin_spin.blockSignals(True)
        old_vmax_block = self.map_vmax_spin.blockSignals(True)
        self.map_vmin_spin.setValue(vmin)
        self.map_vmax_spin.setValue(vmax)
        self.map_vmin_spin.blockSignals(old_vmin_block)
        self.map_vmax_spin.blockSignals(old_vmax_block)


    def _on_map_selection_changed(self, _value: str) -> None:
        self._show_current_map_view()
        self.save_current_png_btn.setEnabled(self._current_map_figure() is not None)
        self.save_current_csv_btn.setEnabled(self._current_map_payload() is not None)
        self._refresh_stage_states()
        self._request_map_update()

    def _update_status_labels(self) -> None:
        if self.state.data is None:
            self.analysis_status_label.setToolTip("")
            self.analysis_status_label.setText("Load a CSV to start configuring the analysis.")
            if self.state.mode == "Reflection":
                self.map_status_label.setText("Load a reflection CSV and background, preview RC spectra, then refresh a map view.")
            else:
                self.map_status_label.setText("Load a CSV, choose settings, then refresh a map view.")
            self.linecuts_status_label.setText("Line cuts become available after a transformed map refresh.")
            return

        supports_de = self.state.data.get("axis_space") in {"gate", "transformed"}
        dirty_names = {
            "intensity_original": "intensity/original",
            "peak_original": "peak/original",
            "ibias_original": "Ibias/original",
            "resistance_original": "resistance/original",
        }
        if self.state.mode == "Reflection":
            dirty_names["fixed_original"] = "RC at energy/original"
        if supports_de:
            dirty_names.update({
                "intensity_transformed": "intensity/transformed",
                "peak_transformed": "peak/transformed",
                "ibias_transformed": "Ibias/transformed",
                "resistance_transformed": "resistance/transformed",
                "line_cuts": "line cuts",
            })
            if self.state.mode == "Reflection":
                dirty_names["fixed_transformed"] = "RC at energy/transformed"
        dirty_list = [label for key, label in dirty_names.items() if self._dirty_views.get(key, False)]
        if dirty_list:
            self.analysis_status_label.setText(f"{len(dirty_list)} views need updates. "
                                               + ('Only the visible plot updates automatically.' if self.map_auto_update_check.isChecked()
                                                  else 'Choose a map and click Update Now.'))
            self.analysis_status_label.setToolTip("Needs refresh: " + ", ".join(dirty_list) + ".")
        else:
            self.analysis_status_label.setText("All cached views are up to date with the current settings.")
            self.analysis_status_label.setToolTip("")

        current_key = self._current_view_key()
        if self._dirty_views.get(current_key, True):
            self.map_status_label.setText(
                f"{self._current_view_description()} is out of date. "
                + ('Updating… Previous plot remains visible.' if self._thread is not None
                   else 'Waiting to update; previous plot remains visible.' if self.map_auto_update_check.isChecked()
                   else 'Click Update Now to apply the current settings.')
            )
        elif self._current_map_figure() is None:
            self.map_status_label.setText(
                f"{self._current_view_description()} has not been generated yet."
            )
        else:
            self.map_status_label.setText(
                f"Showing {self._current_view_description()}."
            )

        if not supports_de:
            self.linecuts_status_label.setText(
                "D/E line cuts are unavailable for this sweep. Use Original maps with the loaded X/Y axes."
            )
        elif self._dirty_views.get("line_cuts", True):
            if self.state.data.get("axis_space") == "transformed":
                self.linecuts_status_label.setText(
                    "Line cuts are stale or not extracted yet. Loaded D/E axes are ready for extraction."
                )
            else:
                self.linecuts_status_label.setText(
                    "Line cuts are stale or not extracted yet. Refresh the transformed map first, then extract cuts."
                )
        else:
            self.linecuts_status_label.setText("Line cuts match the current transformed coordinate settings.")

    def _refresh_current_map_view(self) -> None:
        self.map_updates.cancel()
        if self.state.data is None:
            self._append_log("Load a CSV before refreshing map views.", "error")
            return
        view_key = self._current_view_key()
        is_electrical_view = view_key.startswith(
            ("ibias_", "resistance_")
        )
        if not is_electrical_view:
            if self.int_min_spin.value() >= self.int_max_spin.value():
                self._append_log(
                    "Intensity range is invalid: E min must be less than E max.",
                    "error",
                )
                return
            if not self._validate_reflection_background_ready():
                return
        if view_key.endswith("_transformed") and self.state.data.get("axis_space") == "generic":
            self._append_log(
                "D/E transformed views are unavailable for this sweep. Select Original axes.",
                "warn",
            )
            return
        tasks = self._required_tasks_for_view(view_key)
        self._start_analysis_refresh(tasks, f"Refreshing {self._current_view_description()}")

    def _refresh_all_maps(self) -> None:
        self.map_updates.cancel()
        if self.state.data is None:
            self._append_log("Load a CSV before refreshing map views.", "error")
            return
        if self.int_min_spin.value() >= self.int_max_spin.value():
            self._append_log("Intensity range is invalid: E min must be less than E max.", "error")
            return
        if not self._validate_reflection_background_ready():
            return
        tasks = ["intensity_original", "peak_original"]
        has_ibias = self.state.data.get("ibias_data") is not None
        has_resistance = (
            has_ibias and self.state.data.get("vbias_data") is not None
        )
        if has_ibias:
            tasks.append("ibias_original")
        if has_resistance:
            tasks.append("resistance_original")
        if self.state.mode == "Reflection":
            tasks.append("fixed_original")
        if self.state.data.get("axis_space") in {"gate", "transformed"}:
            tasks.extend(["intensity_transformed", "peak_transformed"])
            if has_ibias:
                tasks.append("ibias_transformed")
            if has_resistance:
                tasks.append("resistance_transformed")
            if self.state.mode == "Reflection":
                tasks.append("fixed_transformed")
        self._start_analysis_refresh(tasks, "Refreshing all map views")

    _MAP_CACHE_FIELDS = {
        "intensity_original": ("original_map", "original_map"),
        "intensity_transformed": ("transformed_map", "transformed_map"),
        "peak_original": ("peak_map_original", "peak_map_original"),
        "peak_transformed": ("peak_map_transformed", "peak_map_transformed"),
        "fixed_original": ("rc_fixed_map_original", "fixed_map_original"),
        "fixed_transformed": ("rc_fixed_map_transformed", "fixed_map_transformed"),
        "ibias_original": ("ibias_map_original", "ibias_map_original"),
        "ibias_transformed": ("ibias_map_transformed", "ibias_map_transformed"),
        "resistance_original": ("resistance_map_original", "resistance_map_original"),
        "resistance_transformed": ("resistance_map_transformed", "resistance_map_transformed"),
    }

    def _map_calculation_signature(self, task):
        signature = [id(self.state.data)]
        kind, axes = task.rsplit("_", 1)
        if axes == "transformed":
            signature.extend((self.ratio_spin.value(), self._current_convention()))
        if kind not in {"ibias", "resistance"}:
            signature.append(self.state.mode)
            if self.state.mode == "Reflection":
                scale = self.state.background_scale_factor if self.background_scale_check.isChecked() else 1.0
                signature.extend((id(self.state.background_spectra), scale))
            if kind == "intensity" or (kind == "peak" and self.state.mode == "Reflection"):
                signature.extend((self.int_min_spin.value(), self.int_max_spin.value()))
            if kind == "intensity" and self.state.mode == "PL":
                signature.append(self.baseline_spin.value())
            if kind == "peak":
                signature.extend((self.sg_window_spin.value(), self.sg_poly_spin.value()))
                if self.state.mode == "Reflection":
                    signature.append(self._current_rc_feature_mode())
            if kind == "fixed":
                signature.append(self.fixed_energy_spin.value())
        return tuple(signature)

    def _start_analysis_refresh(self, tasks: list[str], context: str) -> None:
        if self._thread is not None:
            self._append_log("An analysis task is already running. Please wait for it to finish.", "warn")
            return
        signatures = {task: self._map_calculation_signature(task) for task in tasks}
        cached, missing = {}, []
        for task in tasks:
            attribute, payload_key = self._MAP_CACHE_FIELDS[task]
            result = getattr(self.state, attribute)
            if (result is not None and not self._dirty_views.get(task, True)
                    and self._map_cache_signatures.get(task) == signatures[task]):
                cached[payload_key] = result
            else:
                missing.append(task)
        if cached:
            self._append_log(f"Reusing {len(cached)} cached map(s); updating display settings.", "info")
        if not missing:
            self._on_analysis_refresh_ready(cached)
            self._schedule_session_save()
            return

        def on_ready(payload):
            combined = {**cached, **payload}
            valid = {self._MAP_CACHE_FIELDS[task][1]: combined[self._MAP_CACHE_FIELDS[task][1]]
                     for task in tasks if signatures[task] == self._map_calculation_signature(task)
                     and self._MAP_CACHE_FIELDS[task][1] in combined}
            self._on_analysis_refresh_ready(valid)
            for task in tasks:
                attribute, payload_key = self._MAP_CACHE_FIELDS[task]
                if payload_key in valid:
                    self._map_cache_signatures[task] = signatures[task]
                    # Controls can change while the worker runs. Never label an
                    # old calculation as valid for those newly selected values.
                    self._dirty_views[task] = signatures[task] != self._map_calculation_signature(task)
                else:
                    self._dirty_views[task] = True

        worker = AnalysisRefreshWorker(
            self.state.data,
            self.int_min_spin.value(),
            self.int_max_spin.value(),
            self.baseline_spin.value(),
            self.ratio_spin.value(),
            self.sg_window_spin.value(),
            self.sg_poly_spin.value(),
            missing,
            tg_is_y=True,
            mode=self.state.mode,
            background_spectra=self.state.background_spectra,
            convention=self._current_convention(),
            fixed_energy=self.fixed_energy_spin.value(),
            background_scale=(
                self._effective_background_scale()
                if self.state.mode == "Reflection"
                else 1.0
            ),
            rc_feature_mode=self._current_rc_feature_mode(),
            peak_cache=self._spectral_peak_cache,
        )
        self._run_worker(worker, on_ready, context=context)

    def _export_map_axes_size(self) -> tuple[float, float]:
        return self._EXPORT_MAP_AXES_SIZE

    @staticmethod
    def _measured_map_arrays(payload: dict) -> tuple:
        """Return only acquired points so CSV exports never invent missing rows."""
        if all(key in payload for key in ("x_flat", "y_flat", "z_flat")):
            return (
                payload["x_flat"],
                payload["y_flat"],
                payload["z_flat"],
            )
        return payload["X2D"], payload["Y2D"], payload["Z2D"]

    def _map_export_stem(
        self,
        payload: dict,
        *,
        axes_override: str | None = None,
    ) -> str:
        axes = axes_override or payload.get("target_axes", "original")
        axes = str(axes).strip().lower() or "original"
        z_name = str(payload.get("z_name", "")).strip().lower()
        if z_name == "ibias":
            return f"Ibias_{axes}"
        if z_name == "resistance":
            return f"Resistance_{axes}"
        background_scale = float(payload.get("background_scale", 1.0))
        rc_prefix = (
            "RC_scaled"
            if not np.isclose(background_scale, 1.0)
            else "RC"
        )
        if "fixed_energy" in payload:
            return (
                f"{rc_prefix}_at_"
                f"{float(payload['fixed_energy']):.6f}eV_{axes}"
            )

        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
        energy_tag = f"{e_lo:.6f}-{e_hi:.6f}eV"
        if "peak-to-peak" in z_name:
            quantity = f"{rc_prefix}_P2P"
        elif z_name.startswith("rc") and "position" in z_name:
            feature_tag = {
                "dip": "dip",
                "peak": "peak",
            }.get(self._current_rc_feature_mode(), "feature")
            quantity = f"{rc_prefix}_{feature_tag}_position"
        elif "peak energy" in z_name:
            quantity = "PL_peak_energy"
        elif "intensity" in z_name:
            quantity = "PL_intensity"
        else:
            quantity = "map"
        return f"{quantity}_{energy_tag}_{axes}"

    def _export_file_path(self, filename: str) -> str:
        path = os.path.abspath(os.path.join(self._ensure_output_dir(), filename))
        if sys.platform == "win32" and len(path) >= 240:
            raise OSError(
                f"Export path is {len(path)} characters and may not open in "
                "PowerPoint. Choose a shorter Output dir. "
                f"Attempted path: {path}"
            )
        return path

    def _save_current_view(self, output_type: str) -> None:
        if self._thread is not None or self._dirty_views.get(self._current_view_key(), True) or not self._auto_file_matches():
            self._append_log('Update the selected plot before exporting.', 'warn')
            return
        payload = self._current_map_payload()
        figure = self._current_map_figure()
        if payload is None or figure is None:
            self._append_log("The selected map view has not been generated yet.", "warn")
            return
        path = ""
        try:
            path = self._export_file_path(
                f"{self._map_export_stem(payload)}.{output_type}"
            )
            if output_type == "png":
                exported = save_figure_with_axes_size(
                    figure,
                    path,
                    self._export_map_axes_size(),
                    dpi=300,
                )
            else:
                export_x, export_y, export_z = self._measured_map_arrays(payload)
                exported = save_map_csv(
                    export_x,
                    export_y,
                    export_z,
                    path,
                    x_name=payload["x_name"],
                    y_name=payload["y_name"],
                    z_name=payload["z_name"],
                )
        except Exception as exc:
            target = path or self.out_edit.text().strip() or "the selected output directory"
            self._append_log(f"Save failed for {target}: {exc}", "error")
            return
        self._append_log(exported.message, "success")

    def _save_all_maps(self) -> None:
        saved_any = False
        for kind in ("original", "transformed"):
            if (kind == "original" and self.state.original_map is not None) or (
                kind == "transformed" and self.state.transformed_map is not None
            ):
                self._save_map(kind, "png")
                self._save_map(kind, "csv")
                saved_any = True
        for axes in ("original", "transformed"):
            peak_map = self.state.peak_map_original if axes == "original" else self.state.peak_map_transformed
            if peak_map is not None:
                current_index = self.map_type_combo.currentIndex(), self.map_axes_combo.currentIndex()
                self.map_type_combo.setCurrentText(
                    "RC Peak Position" if self.state.mode == "Reflection" else "Peak Energy"
                )
                self.map_axes_combo.setCurrentText("Original" if axes == "original" else "Transformed")
                self._save_current_view("png")
                self._save_current_view("csv")
                self.map_type_combo.setCurrentIndex(current_index[0])
                self.map_axes_combo.setCurrentIndex(current_index[1])
                saved_any = True
        if self.state.mode == "Reflection":
            for axes in ("original", "transformed"):
                fixed_map = (
                    self.state.rc_fixed_map_original
                    if axes == "original"
                    else self.state.rc_fixed_map_transformed
                )
                if fixed_map is not None:
                    current_index = self.map_type_combo.currentIndex(), self.map_axes_combo.currentIndex()
                    self.map_type_combo.setCurrentText("RC at Energy")
                    self.map_axes_combo.setCurrentText(
                        "Original" if axes == "original" else "Transformed"
                    )
                    self._save_current_view("png")
                    self._save_current_view("csv")
                    self.map_type_combo.setCurrentIndex(current_index[0])
                    self.map_axes_combo.setCurrentIndex(current_index[1])
                    saved_any = True
        for axes in ("original", "transformed"):
            ibias_map = (
                self.state.ibias_map_original
                if axes == "original"
                else self.state.ibias_map_transformed
            )
            if ibias_map is not None:
                current_index = (
                    self.map_type_combo.currentIndex(),
                    self.map_axes_combo.currentIndex(),
                )
                self.map_type_combo.setCurrentText("Ibias")
                self.map_axes_combo.setCurrentText(
                    "Original" if axes == "original" else "Transformed"
                )
                self._save_current_view("png")
                self._save_current_view("csv")
                self.map_type_combo.setCurrentIndex(current_index[0])
                self.map_axes_combo.setCurrentIndex(current_index[1])
                saved_any = True
        for axes in ("original", "transformed"):
            resistance_map = (
                self.state.resistance_map_original
                if axes == "original"
                else self.state.resistance_map_transformed
            )
            if resistance_map is not None:
                current_index = (
                    self.map_type_combo.currentIndex(),
                    self.map_axes_combo.currentIndex(),
                )
                self.map_type_combo.setCurrentText("Resistance")
                self.map_axes_combo.setCurrentText(
                    "Original" if axes == "original" else "Transformed"
                )
                self._save_current_view("png")
                self._save_current_view("csv")
                self.map_type_combo.setCurrentIndex(current_index[0])
                self.map_axes_combo.setCurrentIndex(current_index[1])
                saved_any = True
        if not saved_any:
            self._append_log("No map views are available to save yet.", "warn")

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select megasweep CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self._set_primary_csv_path(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self.out_edit.text() or os.path.expanduser("~"),
        )
        if path:
            self.out_edit.setText(path)
            self._on_output_dir_changed()

    def _on_peak_preview_changed(self, index: int) -> None:
        if index == 1 and self.state.transformed_map is not None:
            self.peak_axes_combo.setCurrentText("transformed")
        else:
            self.peak_axes_combo.setCurrentText("original")

    def _on_peak_axes_requested(self, axes_mode: str) -> None:
        if axes_mode == "transformed" and self.state.transformed_map is not None:
            self.peak_plot_tabs.setCurrentWidget(self.peak_transformed_plot_tab)
        else:
            self.peak_plot_tabs.setCurrentWidget(self.peak_original_plot_tab)

    def _on_csv_path_changed(self) -> None:
        if self._thread is not None:
            self._append_log("Wait for the current task before changing CSV files.", "warn")
            return
        path = self.csv_edit.text().strip()
        self.csv_edit.setToolTip(path)
        if not path or not os.path.isfile(path):
            self._refresh_stage_states()
            return
        try:
            columns = pd.read_csv(path, nrows=0).columns.tolist()
        except Exception as exc:
            self._append_log(f"ERROR reading CSV headers: {exc}", "error")
            self._refresh_stage_states()
            return

        session_changed = self._select_session(path)
        if session_changed:
            self.transport_panel.clear()
        previous_axes = self._capture_controls()
        gate_columns = self._extract_gate_columns(columns)
        y_guess, x_guess = self._guess_gate_columns(gate_columns)

        self._building_combos = True
        self.vbg_combo.clear()
        self.vtg_combo.clear()
        self.vbg_combo.addItems(gate_columns)
        self.vtg_combo.addItems(gate_columns)
        if x_guess:
            self.vbg_combo.setCurrentText(x_guess)
        if y_guess:
            self.vtg_combo.setCurrentText(y_guess)
        self._building_combos = False
        if session_changed:
            self._prepare_session_headers()
            if not self._fixed_mode and not self._pending_session and not pd.to_numeric(pd.Series(columns), errors="coerce").notna().any():
                self.mode_combo.setCurrentText("Transport")
        else:
            self._apply_session_controls(previous_axes, ("vbg_combo", "vtg_combo"))
        self._update_axis_ui_text()

        self.state.header_columns = columns
        self.state.gate_columns = gate_columns
        if not self.out_edit.text().strip():
            self.out_edit.setText(os.path.dirname(path))
            self._on_output_dir_changed()
        else:
            self._update_output_destination_ui()

        if self.state.mode == "Transport":
            self._append_log("Transport headers detected. Load CSV, then choose coordinate and signal columns.")
        else:
            self._append_log(
                f"Headers detected. Auto-selected Axis X={self.vbg_combo.currentText()} and "
                f"Axis Y={self.vtg_combo.currentText()}. {self._axis_selection_status()['message']}",
                "info",
            )

        if self.state.data is not None and path != self.state.csv_path:
            self._invalidate_from_stage(1, "CSV path changed. Cached results were cleared.")
        else:
            self._refresh_stage_states()

    def _on_csv_text_changed(self, text: str) -> None:
        self.csv_edit.setToolTip(text.strip())
        self._update_output_destination_ui()
        self._refresh_stage_states()

    def _on_primary_csv_dropped(self, paths: list[str]) -> None:
        if not paths:
            return
        self._set_primary_csv_path(paths[0])

    def _on_output_dir_changed(self) -> None:
        requested = self.out_edit.text().strip()
        self.state.output_dir = (
            os.path.abspath(os.path.expanduser(requested)) if requested else ""
        )
        if requested and requested != self.state.output_dir:
            self.out_edit.setText(self.state.output_dir)
        self.out_edit.setToolTip(self.state.output_dir)
        self._update_output_destination_ui()

    @staticmethod
    def _normalize_csv_paths(paths: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for raw_path in paths:
            cleaned = str(raw_path).strip().strip('"')
            if not cleaned:
                continue
            path = os.path.abspath(os.path.expanduser(cleaned))
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(path)
        return normalized

    @classmethod
    def _parse_csv_path_text(cls, text: str) -> list[str]:
        parts = []
        for line in text.splitlines():
            for token in line.split(";"):
                cleaned = token.strip()
                if cleaned:
                    parts.append(cleaned)
        return cls._normalize_csv_paths(parts)

    def _set_primary_csv_path(self, path: str) -> None:
        normalized_paths = self._normalize_csv_paths([path])
        if not normalized_paths:
            return
        self.csv_edit.setText(normalized_paths[0])
        self.csv_edit.setToolTip(normalized_paths[0])
        self._on_csv_path_changed()

    def _set_background_paths(self, paths: list[str]) -> None:
        self._background_paths = self._normalize_csv_paths(paths)
        text = "; ".join(self._background_paths)
        self.bg_csv_edit.blockSignals(True)
        self.bg_csv_edit.setText(text)
        self.bg_csv_edit.blockSignals(False)
        self.bg_csv_edit.setToolTip("\n".join(self._background_paths))
        self._refresh_stage_states()

    def _get_background_paths(self) -> list[str]:
        typed_paths = self._parse_csv_path_text(self.bg_csv_edit.text())
        if typed_paths:
            self._background_paths = typed_paths
        return list(self._background_paths)

    def _on_background_text_changed(self, text: str) -> None:
        self._background_paths = self._parse_csv_path_text(text)
        self.bg_csv_edit.setToolTip("\n".join(self._background_paths))
        self._refresh_stage_states()

    def _on_background_csvs_dropped(self, paths: list[str]) -> None:
        self._set_background_paths(paths)


    # (legacy method removed – use _preview_reflection_spectra instead)

    def _axis_selection_status(self) -> dict:
        x_name = self.vbg_combo.currentText().strip() or self.state.selected_x_col or "X"
        y_name = self.vtg_combo.currentText().strip() or self.state.selected_y_col or "Y"
        return validate_axis_selection(x_name, y_name)

    def _update_axis_ui_text(self) -> None:
        x_name = self.vbg_combo.currentText().strip() or self.state.selected_x_col or "X"
        y_name = self.vtg_combo.currentText().strip() or self.state.selected_y_col or "Y"

        self._sweep_x_label.setText(f"Axis X column ({x_name}):")
        self._sweep_y_label.setText(f"Axis Y column ({y_name}):")
        self._rc_vbg_label.setText("X:")
        self._rc_vtg_label.setText("Y:")
        self._rc_vbg_label.setToolTip(f"Preview {x_name}")
        self._rc_vtg_label.setToolTip(f"Preview {y_name}")
        self.reflection_preview_vbg_spin.setAccessibleName(f"Preview {x_name}")
        self.reflection_preview_vtg_spin.setAccessibleName(f"Preview {y_name}")

        status = self._axis_selection_status()
        if status["mode"] == "raw_gate":
            mode_text = "Raw gates: X=BG/Vbg, Y=TG/Vtg"
        elif status["mode"] == "transformed":
            mode_text = "Transformed: X=doping, Y=efield"
        elif status["mode"] == "doping_bias":
            mode_text = "Sweep: X=doping, Y=Vbias"
        elif status["mode"] == "generic_sweep":
            mode_text = "Explicit acquisition sweep axes"
        elif status["mode"].startswith("swapped"):
            mode_text = "Axis selection looks swapped"
        else:
            mode_text = status["message"]
        current_summary = self.summary_label.text().strip() if hasattr(self, "summary_label") else ""
        if not current_summary or current_summary == "No CSV loaded." or current_summary.startswith("Axis selection:") or current_summary.startswith("Sweep selection:"):
            self.summary_label.setText(f"Axis selection: X={x_name}, Y={y_name} | {mode_text}")

    def _on_gate_columns_changed(self) -> None:
        if self._building_combos:
            return
        self._update_axis_ui_text()
        if self.state.data is not None:
            self._invalidate_from_stage(1, "Gate-column selection changed. Cached analysis results were cleared.")


    def _on_intensity_settings_changed(self) -> None:
        if self.state.data is None:
            return
        self.state.original_map = None
        self.state.transformed_map = None
        if self.state.mode == "Reflection":
            self.state.peak_map_original = None
            self.state.peak_map_transformed = None
            self._mark_dirty(
                "intensity_original",
                "intensity_transformed",
                "peak_original",
                "peak_transformed",
            )
            message = (
                "RC energy window changed. Peak-to-peak and peak-position views need refresh."
            )
        else:
            self._mark_dirty("intensity_original", "intensity_transformed")
            message = "Intensity settings changed. Intensity views need refresh."
        self._show_current_map_view()
        self._append_log(message, "warn")
        self._refresh_stage_states()

    def _on_energy_window_changed(self) -> None:
        if self._suppress_intensity_tracking:
            return
        self._intensity_range_user_modified = True
        if self.state.mode == "Reflection":
            if self._reflection_preview_message is not None:
                # A preview is already visible — refresh it in-place with the new energy window
                self._request_preview_update()
            else:
                self._clear_reflection_preview()
        elif self.auto_baseline_check.isChecked() and self.state.data is not None:
            self._estimate_and_apply_baseline(log=False, mark_dirty=False)
        self._on_intensity_settings_changed()
        if (
            self.state.mode == "Reflection"
            and self.state.background_spectra is not None
            and self._reflection_preview_message is None
        ):
            try:
                self._refresh_raw_background_plot()
            except Exception:
                pass

    def _on_fixed_energy_changed(self) -> None:
        if self._suppress_fixed_energy_tracking:
            return
        self._fixed_energy_user_modified = True
        if self.state.data is None:
            return
        self.state.rc_fixed_map_original = None
        self.state.rc_fixed_map_transformed = None
        self._mark_dirty("fixed_original", "fixed_transformed")
        if self.state.mode == "Reflection" and self._reflection_preview_message is not None:
            self._request_preview_update()
        self._show_current_map_view()
        self._append_log(
            f"Fixed RC energy changed to {self.fixed_energy_spin.value():.6f} eV. "
            "RC-at-energy views need refresh.",
            "warn",
        )
        self._refresh_stage_states()

    def _on_baseline_changed(self) -> None:
        if not self._suppress_baseline_tracking:
            self._baseline_user_modified = True
        self._on_intensity_settings_changed()

    def _on_auto_baseline_toggled(self, checked: bool) -> None:
        self.baseline_spin.setEnabled(not checked)
        if checked:
            self._baseline_user_modified = False
            self._estimate_and_apply_baseline()

    def _estimate_and_apply_baseline(self, log: bool = True, mark_dirty: bool = True) -> bool:
        if self.state.data is None:
            if log:
                self._append_log("Load a CSV before estimating the baseline.", "warn")
            return False
        if self.state.mode == "Reflection":
            return False

        try:
            baseline, info = estimate_global_baseline(
                self.state.data["Intensity"],
                self.state.data["energy"],
                self.int_min_spin.value(),
                self.int_max_spin.value(),
                return_info=True,
            )
        except Exception as exc:
            if log:
                self._append_log(f"Auto baseline estimate failed: {exc}", "error")
            return False

        self._suppress_baseline_tracking = True
        self.baseline_spin.setValue(baseline)
        self._suppress_baseline_tracking = False
        self._baseline_user_modified = not self.auto_baseline_check.isChecked()

        if log:
            level = "warn" if info.get("fallback") else "success"
            method = "full-spectrum fallback" if info.get("fallback") else "outside-window spectra"
            self._append_log(
                f"Baseline estimated: {baseline:.3f} counts/channel from {method} "
                f"({info.get('used_spectrum_count', info.get('spectrum_count'))} spectra, "
                f"{info.get('baseline_channels')} channels).",
                level,
            )
        if mark_dirty:
            self._on_intensity_settings_changed()
        return True

    def _on_ratio_changed(self) -> None:
        self.state.current_ratio = self.ratio_spin.value()
        if self.state.data is None:
            return
        self.state.transformed_map = None
        self.state.peak_map_transformed = None
        self.state.rc_fixed_map_transformed = None
        self.state.ibias_map_transformed = None
        self.state.resistance_map_transformed = None
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("transformed_map", None)
        self.state.figures.pop("peak_map_transformed", None)
        self.state.figures.pop("fixed_map_transformed", None)
        self.state.figures.pop("ibias_map_transformed", None)
        self.state.figures.pop("resistance_map_transformed", None)
        self.state.figures.pop("line_cuts", None)
        if self._reflection_preview_message is None:
            self.line_plot_tab.clear()
        self._mark_dirty(
            "intensity_transformed",
            "peak_transformed",
            "fixed_transformed",
            "ibias_transformed",
            "resistance_transformed",
            "line_cuts",
        )
        self._append_log(
            "Ratio changed. Transformed views and line cuts need refresh.",
            "warn",
        )
        self._refresh_stage_states()

    def _on_convention_changed(self) -> None:
        self.formula_label.setText(self._formula_text())
        convention = self._current_convention()
        self.state.transform_convention = convention
        if self.state.data is None:
            return
        self.state.transformed_map = None
        self.state.peak_map_transformed = None
        self.state.rc_fixed_map_transformed = None
        self.state.ibias_map_transformed = None
        self.state.resistance_map_transformed = None
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("transformed_map", None)
        self.state.figures.pop("peak_map_transformed", None)
        self.state.figures.pop("fixed_map_transformed", None)
        self.state.figures.pop("ibias_map_transformed", None)
        self.state.figures.pop("resistance_map_transformed", None)
        self.state.figures.pop("line_cuts", None)
        if self._reflection_preview_message is None:
            self.line_plot_tab.clear()
        self._mark_dirty(
            "intensity_transformed",
            "peak_transformed",
            "fixed_transformed",
            "ibias_transformed",
            "resistance_transformed",
            "line_cuts",
        )
        self._append_log(
            f"Axis convention changed to '{convention}'. Transformed views and line cuts need refresh.",
            "warn",
        )
        self._refresh_stage_states()

    def _current_convention(self) -> str:
        """Return the internal convention key for the current combo selection."""
        return "TG+rBG" if self.convention_combo.currentIndex() == 0 else "rTG+BG"

    def _current_rc_feature_mode(self) -> str:
        mode = self.rc_feature_combo.currentData()
        return str(mode or "auto")

    def _rc_feature_position_name(self) -> str:
        return {
            "auto": "RC Feature Position",
            "peak": "RC Peak Position",
            "dip": "RC Dip Position",
        }[self._current_rc_feature_mode()]

    def _formula_text(self) -> str:
        """Return the D/E definition text for the current convention."""
        idx = self.convention_combo.currentIndex() if hasattr(self, "convention_combo") else 0
        if idx == 0:
            return "D = TG + r·BG\nE = TG − r·BG"
        else:
            return "D = r·TG + BG\nE = r·TG − BG"

    def _axis_labels(self) -> tuple[str, str]:
        """Return (D label, E label) for the transformed map axes."""
        r = self.ratio_spin.value()
        if self._current_convention() == "TG+rBG":
            return f"TG + {r}·BG (V)", f"TG − {r}·BG (V)"
        else:
            return f"{r}·TG + BG (V)", f"{r}·TG − BG (V)"

    def _batch_cut_types(self, axes: list[str]) -> list[str]:
        """Map 'axis1' (D) / 'axis2' (E) to 'doping'/'efield' strings."""
        return [{"axis1": "doping", "axis2": "efield"}[a] for a in axes]

    def _batch_linecuts_ready(self) -> bool:
        """Return whether batch line cuts can be extracted from current axes."""
        if self.state.data is None:
            return False
        if self.state.data.get("axis_space") == "transformed":
            return True
        return self.state.transformed_map is not None and not self._dirty_views.get("intensity_transformed", True)

    def _on_peak_settings_changed(self) -> None:
        if self.state.data is None:
            return
        if self.state.mode == "Reflection" and self._reflection_preview_message is not None:
            self._request_preview_update()
        self.state.peak_map_original = None
        self.state.peak_map_transformed = None
        self._mark_dirty("peak_original", "peak_transformed")
        self._show_current_map_view()
        self._append_log("Peak settings changed. Peak views need refresh.", "warn")
        self._refresh_stage_states()

    def _on_linecut_settings_changed(self) -> None:
        if self.state.data is None:
            return
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        self.state.figures.pop("line_cuts", None)
        self.line_plot_tab.clear()
        self._mark_dirty("line_cuts")
        self._append_log("Line-cut settings changed. Re-extract cuts when ready.", "warn")
        self._refresh_stage_states()

    def _on_linecut_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 1:
            self._snap_linecut_row_value(item.row())
        else:
            self._on_linecut_settings_changed()

    def _on_linecut_type_changed(self, combo: QComboBox) -> None:
        self._schedule_session_save()
        for row in range(self.cuts_table.rowCount()):
            if self.cuts_table.cellWidget(row, 0) is combo:
                self._snap_linecut_row_value(row)
                return
        self._on_linecut_settings_changed()

    def _nearest_cut_value(self, cut_type: str, requested: float, epsilon: float) -> float | None:
        data = self.state.data
        if data is None:
            return None
        values = find_all_cut_values(
            data["x_data"],
            data["y_data"],
            cut_type,
            self.state.current_ratio,
            epsilon,
            convention=self._current_convention(),
            axis_space=data.get("axis_space", "gate"),
            x_axis_name=data.get("x_name", ""),
            y_axis_name=data.get("y_name", ""),
        )
        if not values:
            return None
        arr = np.asarray(values, dtype=float)
        distances = np.abs(arr - requested)
        min_dist = np.min(distances)
        return float(arr[distances == min_dist][0])

    def _snap_linecut_row_value(self, row: int) -> None:
        if self.state.data is None:
            self._on_linecut_settings_changed()
            return
        combo = self.cuts_table.cellWidget(row, 0)
        value_item = self.cuts_table.item(row, 1)
        eps_item = self.cuts_table.item(row, 2)
        if combo is None or value_item is None or eps_item is None:
            self._on_linecut_settings_changed()
            return

        try:
            requested = float(value_item.text())
            epsilon = float(eps_item.text())
        except ValueError:
            self._on_linecut_settings_changed()
            return

        snapped = self._nearest_cut_value(combo.currentText(), requested, epsilon)
        if snapped is None:
            self.linecuts_status_label.setText("No existing line-cut values are available for snapping.")
            self._on_linecut_settings_changed()
            return

        if not np.isclose(snapped, requested, rtol=0.0, atol=5e-7):
            self.cuts_table.blockSignals(True)
            value_item.setText(f"{snapped:.6g}")
            self.cuts_table.blockSignals(False)
            self.linecuts_status_label.setText(
                f"Snapped {combo.currentText()} cut from {requested:.4f} to {snapped:.4f} V."
            )

        self._on_linecut_settings_changed()

    def _extract_gate_columns(self, columns: list[str]) -> list[str]:
        gate_columns = []
        for column in columns:
            try:
                float(column)
            except ValueError:
                gate_columns.append(column)
        return gate_columns or columns[:2]

    def _guess_gate_columns(self, gate_columns: list[str]) -> tuple[str, str]:
        x_guess, y_guess = guess_sweep_axis_columns(gate_columns)
        # Historical return order is (Y, X) because the combo attributes retain
        # their original vtg/vbg names.
        return y_guess, x_guess

    def _collect_line_specs(self) -> list[dict]:
        specs = []
        for row in range(self.cuts_table.rowCount()):
            combo = self.cuts_table.cellWidget(row, 0)
            value_item = self.cuts_table.item(row, 1)
            eps_item = self.cuts_table.item(row, 2)
            if combo is None or value_item is None or eps_item is None:
                continue
            try:
                specs.append(
                    {
                        "cut_type": combo.currentText(),
                        "c_value": float(value_item.text()),
                        "epsilon": float(eps_item.text()),
                    }
                )
            except ValueError:
                self._append_log(f"Skipping invalid line cut row {row + 1}.", "warn")
        return specs

    def _add_cut(self, cut_type: str, c_value: float, epsilon: float) -> None:
        row = self.cuts_table.rowCount()
        self.cuts_table.insertRow(row)
        combo = QComboBox()
        combo.addItems(["doping", "efield"])
        combo.setCurrentText(cut_type)
        combo.currentTextChanged.connect(lambda _text, c=combo: self._on_linecut_type_changed(c))
        self.cuts_table.setCellWidget(row, 0, combo)
        self.cuts_table.setItem(row, 1, QTableWidgetItem(str(c_value)))
        self.cuts_table.setItem(row, 2, QTableWidgetItem(str(epsilon)))
        self._resize_linecuts_table()

    def _remove_selected_cut(self) -> None:
        rows = sorted({index.row() for index in self.cuts_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.cuts_table.removeRow(row)
        self._resize_linecuts_table()
        self._on_linecut_settings_changed()

    def _start_csv_load(self) -> None:
        if self._thread is not None:
            return
        path = self.csv_edit.text().strip()
        if path and os.path.normcase(os.path.abspath(path)) != os.path.normcase(self._session_path):
            self._on_csv_path_changed()
        self._save_session()
        if self.state.mode == "Transport":
            csv_path = self.csv_edit.text().strip()
            if not os.path.isfile(csv_path):
                self._append_log("Select a valid CSV file first.", "error")
                return
            self._run_worker(TransportLoadWorker(csv_path), self._on_transport_loaded, context="Loading Transport CSV")
            return
        csv_path = self.csv_edit.text().strip()
        if not csv_path or not os.path.isfile(csv_path):
            self._append_log("Select a valid CSV file first.", "error")
            return

        vbg = self.vbg_combo.currentText()
        vtg = self.vtg_combo.currentText()
        if not vbg or not vtg:
            self._append_log("Select both sweep-axis columns before loading.", "error")
            return

        axis_status = validate_axis_selection(vbg, vtg)
        if not axis_status["ok"]:
            self._append_log(axis_status["message"], "error")
            QMessageBox.warning(self, "Axis Selection", axis_status["message"])
            return
        if axis_status["mode"].startswith("unknown"):
            self._append_log(axis_status["message"], "warn")

        self.state.csv_path = csv_path
        requested_output_dir = self.out_edit.text().strip()
        if requested_output_dir:
            self.state.output_dir = os.path.abspath(
                os.path.expanduser(requested_output_dir)
            )
        else:
            self.state.output_dir = os.path.dirname(os.path.abspath(csv_path))
        self.out_edit.setText(self.state.output_dir)
        self.out_edit.setToolTip(self.state.output_dir)
        self._update_output_destination_ui()
        self.state.selected_x_col = vbg
        self.state.selected_y_col = vtg
        if axis_status["mode"] == "raw_gate":
            self.state.selected_bg_col = vbg
            self.state.selected_tg_col = vtg
        else:
            self.state.selected_bg_col = ""
            self.state.selected_tg_col = ""

        worker = CsvLoadWorker(csv_path, x_col=vbg, y_col=vtg)
        self._run_worker(worker, self._on_csv_loaded, context="Loading CSV")

    def _start_intensity_stage(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before plotting the original map.", "error")
            return
        if self.int_min_spin.value() >= self.int_max_spin.value():
            self._append_log("Intensity range is invalid: E min must be less than E max.", "error")
            return

        worker = IntensityWorker(
            self.state.data,
            self.int_min_spin.value(),
            self.int_max_spin.value(),
            self.baseline_spin.value(),
        )
        self._run_worker(worker, self._on_intensity_ready, context="Stage 2: building original map")

    def _start_transform_stage(self) -> None:
        if self.state.original_map is None:
            self._append_log("Plot the original intensity map first.", "error")
            return
        if self.state.data.get("axis_space") not in {"gate", "transformed"}:
            self._append_log(
                "D/E transformed views require BG/TG or Doping/Efield axes. "
                "Use the Original view for this sweep.",
                "warn",
            )
            return
        worker = TransformWorker(
            self.state.original_map,
            self.ratio_spin.value(),
            tg_is_y=True,
            convention=self._current_convention(),
        )
        self._run_worker(worker, self._on_transform_ready, context="Stage 3: building transformed map")

    def _start_peak_stage(self) -> None:
        if self.state.original_map is None:
            self._append_log("Plot the original map before computing the peak map.", "error")
            return
        axes_mode = self.peak_axes_combo.currentText()
        if axes_mode == "transformed" and self.state.transformed_map is None:
            self._append_log("Run Stage 3 before requesting a transformed-axis peak map.", "error")
            return

        worker = PeakWorker(
            self.state.data,
            self.sg_window_spin.value(),
            self.sg_poly_spin.value(),
            self.state.original_map,
            self.state.transformed_map,
            axes_mode,
        )
        self._run_worker(worker, self._on_peak_ready, context="Stage 4: computing peak map")

    def _start_line_stage(self) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before extracting line cuts.", "error")
            return
        if self.state.data.get("axis_space") not in {"gate", "transformed"}:
            self._append_log(
                "D/E line cuts are unavailable for this sweep. Use Original maps with the loaded X/Y axes.",
                "warn",
            )
            return
        if not self._validate_reflection_background_ready():
            return
        specs = self._collect_line_specs()
        if not specs:
            self._append_log("Add at least one valid line cut row.", "error")
            return
        worker = LineWorker(
            self.state.data,
            specs,
            self.state.current_ratio,
            tg_is_y=True,
            background_spectra=self.state.background_spectra if self.state.mode == "Reflection" else None,
            convention=self._current_convention(),
            background_scale=(
                self._effective_background_scale()
                if self.state.mode == "Reflection"
                else 1.0
            ),
        )
        self._run_worker(worker, self._on_lines_ready, context="Extracting line cuts")

    def _update_batch_preview(self) -> None:
        data = self.state.data
        if data is None:
            self.batch_preview_label.setText("No data loaded.")
            return
        x = data["x_data"]
        y = data["y_data"]
        ratio = self.state.current_ratio
        epsilon = self.batch_epsilon_spin.value()
        convention = self._current_convention()
        try:
            axis_space = data.get("axis_space", "gate")
            x_name = data.get("x_name", "")
            y_name = data.get("y_name", "")

            def _find_values(cut_type: str, *, dominant_lattice_only: bool = True):
                return find_all_cut_values(
                    x, y, cut_type, ratio, epsilon,
                    convention=convention,
                    axis_space=axis_space,
                    x_axis_name=x_name,
                    y_axis_name=y_name,
                    dominant_lattice_only=dominant_lattice_only,
                )

            doping_vals = _find_values("doping")
            efield_vals = _find_values("efield")
            if axis_space == "gate":
                doping_skipped = max(
                    0,
                    len(_find_values("doping", dominant_lattice_only=False)) - len(doping_vals),
                )
                efield_skipped = max(
                    0,
                    len(_find_values("efield", dominant_lattice_only=False)) - len(efield_vals),
                )
            else:
                doping_skipped = 0
                efield_skipped = 0
        except Exception as exc:
            self.batch_preview_label.setText(f"Preview error: {exc}")
            return

        def _range_str(vals):
            if not vals:
                return "(none)"
            if len(vals) == 1:
                return f"{vals[0]:.3f}"
            return f"{vals[0]:.3f} … {vals[-1]:.3f}"

        n_doping = len(doping_vals)
        n_efield = len(efield_vals)
        label_lines = [
            f"Doping : {n_doping} cuts   [{_range_str(doping_vals)}]",
            f"Efield : {n_efield} cuts   [{_range_str(efield_vals)}]",
            f"Both   : {n_doping + n_efield} cuts total  (see log for values)",
        ]
        if doping_skipped or efield_skipped:
            label_lines.append(
                f"Skipped off-lattice: Doping {doping_skipped}, Efield {efield_skipped}"
            )
        self.batch_preview_label.setText("\n".join(label_lines))

        def _log_vals(label, vals):
            if not vals:
                self._append_log(f"{label}: (none)", "info")
                return
            chunk_size = 10
            chunks = [vals[i:i + chunk_size] for i in range(0, len(vals), chunk_size)]
            self._append_log(f"{label} ({len(vals)} values):", "info")
            for chunk in chunks:
                self._append_log("  " + ",  ".join(f"{v:.3f}" for v in chunk), "info")

        self._append_log(f"── Batch preview  (epsilon={epsilon}) ──", "info")
        if doping_skipped or efield_skipped:
            self._append_log(
                f"Skipped off-lattice batch cuts: Doping {doping_skipped}, Efield {efield_skipped}",
                "info",
            )
        _log_vals("Doping", doping_vals)
        _log_vals("Efield", efield_vals)

    def _start_batch_line_stage(self, cut_types: list[str]) -> None:
        if self.state.data is None:
            self._append_log("Load a CSV before batch-extracting line cuts.", "error")
            return
        if not self._batch_linecuts_ready():
            self._append_log("Refresh the transformed map with the current settings before batch-extracting line cuts.", "error")
            return
        if not self._validate_reflection_background_ready():
            return

        epsilon = self.batch_epsilon_spin.value()
        if epsilon < 0:
            self._append_log("Batch epsilon must be zero or greater.", "error")
            return

        output_dir = self._ensure_output_dir()
        worker = BatchLineWorker(
            self.state.data,
            cut_types,
            epsilon,
            output_dir,
            self.state.current_ratio,
            tg_is_y=True,
            background_spectra=self.state.background_spectra if self.state.mode == "Reflection" else None,
            convention=self._current_convention(),
            background_scale=(
                self._effective_background_scale()
                if self.state.mode == "Reflection"
                else 1.0
            ),
        )
        context = f"Batch extracting {' + '.join(cut_types)} line cuts"
        self._run_worker(worker, self._on_batch_lines_ready, context=context)

    def _run_worker(self, worker, on_success, context: str, *, quiet=False) -> None:
        if self._thread is not None:
            self._append_log("An analysis task is already running. Please wait for it to finish.", "warn")
            return

        self._pending_context = context
        self.progress_label.setVisible(True)
        self._set_controls_enabled(False)

        self._thread = QThread(self)
        self._worker = worker
        self._worker_success_callback = on_success
        worker.moveToThread(self._thread)

        self._thread.started.connect(worker.run)
        worker.log.connect(self._log_worker_message)
        worker.progress.connect(self._on_worker_progress)
        # Plain Python callbacks/closures may run in the emitting worker thread.
        # Deliver every result through a QObject slot owned by the GUI thread.
        worker.finished.connect(self._dispatch_worker_result, Qt.QueuedConnection)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._thread.quit)
        worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()
        if not quiet:
            self._append_log(context, "info")

    @Slot(object)
    def _dispatch_worker_result(self, result) -> None:
        try:
            if self._worker_success_callback is not None:
                self._worker_success_callback(result)
        except Exception:
            self._on_worker_error(traceback.format_exc())

    def _log_worker_message(self, message: str) -> None:
        self._append_log(message, "info")

    def _on_worker_progress(self, current: int, total: int) -> None:
        if total <= 0:
            return
        self.batch_progress_bar.setMaximum(total)
        self.batch_progress_bar.setValue(current)
        self.batch_progress_bar.setFormat(f"{current} / {total}  (%p%)")
        self.batch_progress_bar.setVisible(True)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._worker_success_callback = None
        self._refresh_stage_states()
        self._advance_session_restore()
        self._schedule_session_save()
        self._resume_auto_updates()

    def _on_worker_finished(self, _result) -> None:
        try:
            self.progress_label.setVisible(False)
            self.batch_progress_bar.setVisible(False)
            self.batch_progress_bar.setValue(0)
            self._set_controls_enabled(True)
            self._refresh_stage_states()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _on_worker_error(self, tb: str) -> None:
        self._restore_steps = []
        self._restoring_session = False
        try:
            self._append_log(tb, "error")
            self._set_controls_enabled(True)
            self.progress_label.setVisible(False)
            self.batch_progress_bar.setVisible(False)
            self.batch_progress_bar.setValue(0)
            context = f" ({self._pending_context})" if self._pending_context else ""
            self._append_log(f"Worker failed{context}.", "error")
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _append_log(self, message: str, level: str = "info") -> None:
        msg = message.strip()
        if not msg:
            return
        color = {"info": "#334155", "success": "#15803d", "error": "#b91c1c", "warn": "#b45309"}.get(level, "#334155")
        html_msg = f'<span style="color: {color};">{msg}</span>'
        self.log_text.append(html_msg)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
        self.log_summary.setText(msg.splitlines()[0])
        self.log_summary.setToolTip(msg)
        if level == "error":
            self.log_toggle.setChecked(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.spectral_slices_panel.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        self.csv_edit.setEnabled(enabled)
        self.transport_panel.setEnabled(enabled)
        for section in (self.transport_settings_section, self.transport_cuts_section, self.transport_export_section):
            section.setEnabled(enabled)
        self.load_csv_btn.setEnabled(enabled)
        self.load_bg_btn.setEnabled(enabled)
        self.preview_rc_btn.setEnabled(enabled)
        self.estimate_background_scale_btn.setEnabled(
            enabled and self.background_scale_check.isChecked()
        )
        self.refresh_current_btn.setEnabled(enabled)
        self.refresh_all_maps_btn.setEnabled(enabled)
        self.plot_lines_btn.setEnabled(enabled)
        self.extract_all_doping_btn.setEnabled(enabled)
        self.extract_all_efield_btn.setEnabled(enabled)
        self.extract_all_both_btn.setEnabled(enabled)

    def _dataset_output_dir(self) -> str:
        """Return the active full-condition per-CSV folder without creating it."""
        csv_path = self.csv_edit.text().strip() or self.state.csv_path
        base_dir = self.state.output_dir or self.out_edit.text().strip()
        if not base_dir and csv_path:
            base_dir = os.path.dirname(os.path.abspath(csv_path))
        if not base_dir:
            return ""

        base_dir = os.path.abspath(os.path.expanduser(base_dir))
        if not csv_path:
            return base_dir
        return resolve_dataset_output_dir(base_dir, csv_path)

    def _update_output_destination_ui(self) -> None:
        if not hasattr(self, "active_output_label"):
            return
        output_dir = self._dataset_output_dir()
        if output_dir:
            display_path = os.path.normpath(output_dir)
            self.active_output_label.setText(display_path)
            self.active_output_label.setToolTip(display_path)
            self.open_folder_btn.setToolTip(f"Open {display_path}")
            self.open_folder_btn.setEnabled(True)
        else:
            message = "Select a CSV to determine its results subfolder."
            self.active_output_label.setText(message)
            self.active_output_label.setToolTip("")
            self.open_folder_btn.setToolTip("")
            self.open_folder_btn.setEnabled(False)

    def _ensure_output_dir(self) -> str:
        output_dir = self._dataset_output_dir()
        if not output_dir:
            raise ValueError("Select an output base folder and load a CSV first.")
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Could not create dataset output folder '{output_dir}'. "
                f"Choose a shorter writable Output dir. {exc}"
            ) from exc
        self._update_output_destination_ui()
        return output_dir

    def _open_output_folder(self) -> None:
        try:
            output_dir = self._ensure_output_dir()
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", output_dir])
            else:
                subprocess.Popen(["xdg-open", output_dir])
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    def _invalidate_from_stage(self, stage_number: int, message: str) -> None:
        self.map_updates.cancel()
        self.preview_updates.cancel()
        self.spectral_slices_panel.updates.cancel()
        self.state.reset_from_stage(stage_number)
        if stage_number <= 1:
            x_name = self.vbg_combo.currentText().strip() or "X"
            y_name = self.vtg_combo.currentText().strip() or "Y"
            self.summary_label.setText(
                f"Axis selection: X={x_name}, Y={y_name} | Reload the CSV to apply this selection."
            )
        self._dirty_views = {k: True for k in self._dirty_views.keys()}
        if stage_number <= 1:
            self._clear_reflection_preview()
            for plot_tab in (self.map_plot_tab, self.line_plot_tab, self.raw_background_plot_tab):
                plot_tab.clear()
        else:
            self._request_preview_update()
        self._append_log(message, "warn")
        self._refresh_stage_states()
        if stage_number > 1:
            self._request_map_update()

    def _on_csv_loaded(self, result: dict) -> None:
        try:
            data = result["data"]
            self._map_cache_signatures.clear()
            self._spectral_peak_cache.clear()
            self.state.data = data
            self.state.csv_path = data.get("source_path", self.state.csv_path)

            x_data = data["x_data"]
            y_data = data["y_data"]
            energy = data["energy"]
            intensity = data["Intensity"]

            self.state.row_count = len(x_data)
            self.state.spectral_channel_count = intensity.shape[1]
            self.state.energy_range = (float(np.min(energy)), float(np.max(energy)))
            self.state.unique_x_count = len(np.unique(x_data))
            self.state.unique_y_count = len(np.unique(y_data))
            self._configure_reflection_preview_coordinates()

            energy_sorted = np.sort(energy[np.isfinite(energy)])
            fixed_min = float(energy_sorted[0])
            fixed_max = float(energy_sorted[-1])
            requested_fixed_energy = self.fixed_energy_spin.value()
            use_fixed_default = (
                not self._fixed_energy_user_modified
                or not fixed_min <= requested_fixed_energy <= fixed_max
            )
            self._suppress_fixed_energy_tracking = True
            self.fixed_energy_spin.setRange(fixed_min, fixed_max)
            if use_fixed_default:
                self.fixed_energy_spin.setValue(float(np.median(energy_sorted)))
            self._suppress_fixed_energy_tracking = False

            if not self._intensity_range_user_modified:
                if len(energy_sorted) >= 10:
                    e_lo = float(np.percentile(energy_sorted, 10))
                    e_hi = float(np.percentile(energy_sorted, 90))
                else:
                    e_lo, e_hi = float(energy_sorted[0]), float(energy_sorted[-1])
                self._suppress_intensity_tracking = True
                self.int_min_spin.setValue(e_lo)
                self.int_max_spin.setValue(e_hi)
                self._suppress_intensity_tracking = False
                self._intensity_defaults_csv_signature = (data.get("source_name", ""), e_lo, e_hi, self.state.spectral_channel_count)

            scale_min = float(energy_sorted[0])
            scale_max = float(energy_sorted[-1])
            feature_lo = max(scale_min, self.int_min_spin.value())
            feature_hi = min(scale_max, self.int_max_spin.value())
            if feature_lo <= scale_min:
                feature_lo = float(np.percentile(energy_sorted, 20))
            if feature_hi >= scale_max:
                feature_hi = float(np.percentile(energy_sorted, 80))
            scale_defaults = (
                (self.scale_left_min_spin, scale_min),
                (self.scale_left_max_spin, feature_lo),
                (self.scale_right_min_spin, feature_hi),
                (self.scale_right_max_spin, scale_max),
            )
            for spin, value in scale_defaults:
                was_blocked = spin.blockSignals(True)
                spin.setRange(scale_min, scale_max)
                spin.setValue(value)
                spin.blockSignals(was_blocked)
            self.state.background_scale_factor = None
            self.state.background_scale_info = None
            self.state.background_scale_frame_index = None
            self.background_scale_status_label.setText(
                "Scale α: estimate from the left + right side windows"
            )

            if self.auto_baseline_check.isChecked() and self.state.mode != "Reflection":
                self._estimate_and_apply_baseline(log=True, mark_dirty=False)
            elif not self._baseline_user_modified:
                self._suppress_baseline_tracking = True
                self.baseline_spin.setValue(595.0)
                self._suppress_baseline_tracking = False

            summary_text = (
                f"{self.state.row_count} rows × {self.state.spectral_channel_count} channels | "
                f"E: {self.state.energy_range[0]:.6f}–{self.state.energy_range[1]:.6f} eV | "
                f"Grid: {self.state.unique_x_count}×{self.state.unique_y_count}"
            )
            if data.get("ibias_name"):
                summary_text += f" | Ibias: {data['ibias_name']}"
            if data.get("ibias_name") and data.get("vbias_name"):
                summary_text += f" | R uses: {data['vbias_name']}/Ibias"
            axis_status = validate_axis_selection(data.get("x_name", ""), data.get("y_name", ""))
            if axis_status["mode"] == "raw_gate":
                summary_text += " | Axes: X=BG/Vbg, Y=TG/Vtg"
            elif axis_status["mode"] == "transformed":
                summary_text += " | Axes: X=doping, Y=efield"
            elif axis_status["mode"] == "doping_bias":
                summary_text += " | Axes: X=doping, Y=Vbias"
            elif axis_status["mode"] == "generic_sweep":
                summary_text += (
                    f" | Axes: X={data.get('x_name', 'X')}, Y={data.get('y_name', 'Y')}"
                )
            self.summary_label.setText(summary_text)
            self.summary_label.setToolTip(summary_text)
            known_axis_modes = {"raw_gate", "transformed", "doping_bias", "generic_sweep"}
            self._append_log(
                axis_status["message"],
                "info" if axis_status["mode"] in known_axis_modes else "warn",
            )

            supports_de = data.get("axis_space") in {"gate", "transformed"}
            transformed_index = self.map_axes_combo.findText("Transformed")
            if transformed_index >= 0:
                transformed_item = self.map_axes_combo.model().item(transformed_index)
                if transformed_item is not None:
                    transformed_item.setEnabled(supports_de)
                    transformed_item.setToolTip(
                        "" if supports_de
                        else "D/E transformed views require BG/TG or Doping/Efield axes."
                    )
            if not supports_de:
                self.map_axes_combo.setCurrentText("Original")

            if self.state.background_spectra is not None:
                bg_wavelength = None if self.state.background_wavelength is None else np.asarray(self.state.background_wavelength, dtype=float)
                data_wavelength = np.asarray(data["wavelength"], dtype=float)
                if (
                    bg_wavelength is None
                    or not spectral_axes_match(bg_wavelength, data_wavelength)
                ):
                    self._clear_background_state("Background cleared: reload a matching background for this dataset.")
                    self._append_log(
                        "The previously loaded background does not match this CSV's spectral channels and was cleared.",
                        "warn",
                    )

            self._clear_reflection_preview()
            self._dirty_views = {k: True for k in self._dirty_views.keys()}
            self._refresh_stage_states()
            self._append_log(f"CSV loaded: {data.get('source_name', 'unknown')}", "success")
            self._update_output_destination_ui()
            self._append_log(
                f"Dataset outputs will be saved to: {self._dataset_output_dir()}",
                "info",
            )
            self.data_section.set_expanded(False)
            if self.state.mode == "Reflection":
                self.bg_section.set_expanded(True)
                self.sidebar_scroll.ensureWidgetVisible(self.bg_section, 0, 16)
            else:
                self.analysis_section.set_expanded(True)
                self.sidebar_scroll.ensureWidgetVisible(self.analysis_section, 0, 16)
            self._restore_session_loaded()
            self._request_map_update()
            self._visible_view_changed()
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    # ── Background loading ────────────────────────────────────────────────


    # ── Mode switching ────────────────────────────────────────────────────

    def _on_transport_loaded(self, data: dict) -> None:
        self.state.csv_path = data["source_path"]
        self.state.output_dir = self.out_edit.text().strip() or os.path.dirname(self.state.csv_path)
        self.state.data = None
        self.state.row_count = len(data["df"])
        saved = self._pending_session or {}
        self.transport_panel.set_data(data, saved.get("transport"))
        self.data_section.set_expanded(False)
        self.transport_settings_section.set_expanded(True)
        self.transport_cuts_section.setVisible(self.transport_panel.plot_kind_combo.currentData() == "map")
        self.summary_label.setText(
            f"Transport: {len(data['df'])} rows, {len(data['columns'])} numeric columns. "
            "Review the suggested axes and choose a Signal in the Transport workspace."
        )
        self._session_ready = True
        self._restoring_session = False
        self._restore_steps = []
        self._update_output_destination_ui()
        self._append_log(f"Loaded Transport CSV: {len(data['df'])} rows.", "success")
        self._schedule_session_save()

    def _on_mode_changed(self, mode: str) -> None:
        if self._fixed_mode and mode != self._fixed_mode:
            return
        was_transport = self.state.mode == "Transport"
        is_transport = mode == "Transport"
        if was_transport != is_transport:
            self._invalidate_from_stage(1, "Measurement mode changed. Reload CSV for this mode.")
            self.transport_panel.clear()
        for section in (self.analysis_section, self.export_section):
            section.setVisible(not is_transport)
        self.linecuts_section.hide()
        for section in (self.transport_settings_section, self.transport_cuts_section, self.transport_export_section):
            section.setVisible(is_transport)
        for widget in (self.vbg_combo, self.vtg_combo, self._sweep_x_label, self._sweep_y_label):
            widget.setVisible(not is_transport)
        self.workspace_tabs.setTabVisible(0, not is_transport)
        self.workspace_tabs.setTabVisible(1, False)
        self.workspace_tabs.setTabVisible(self.transport_tab_index, is_transport)
        self.workspace_tabs.setTabVisible(self.spectral_slices_tab_index, not is_transport)
        self.workspace_tabs.tabBar().setVisible(not is_transport)
        if hasattr(self, "_remembered_views") and self.state.mode != mode:
            self._remembered_views.clear()
            self._remembered_preview = self._remembered_lines = False
        self.state.mode = mode
        if is_transport:
            self.bg_section.hide()
            self.workspace_tabs.setTabVisible(self.raw_background_tab_index, False)
            self.workspace_tabs.setCurrentIndex(self.transport_tab_index)
            self.workflow_hint_label.setText("Load CSV → Review axes and choose Signal → View / Update Now → Export")
            self._refresh_stage_states()
            return
        is_rc = mode == "Reflection"
        self.workspace_tabs.setTabVisible(
            self.raw_background_tab_index,
            is_rc,
        )

        previous_map_type = self.map_type_combo.currentText()
        was_blocked = self.map_type_combo.blockSignals(True)
        self.map_type_combo.clear()
        if is_rc:
            self.map_type_combo.addItems(
                [
                    "RC Peak-to-Peak",
                    "RC at Energy",
                    "RC Peak Position",
                    "Ibias",
                    "Resistance",
                ]
            )
            if previous_map_type in {
                "RC Peak-to-Peak",
                "RC at Energy",
                "RC Peak Position",
                "Ibias",
                "Resistance",
            }:
                self.map_type_combo.setCurrentText(previous_map_type)
        else:
            self.map_type_combo.addItems(
                ["Intensity", "Peak Energy", "Ibias", "Resistance"]
            )
            if previous_map_type in {
                "Intensity",
                "Peak Energy",
                "Ibias",
                "Resistance",
            }:
                self.map_type_combo.setCurrentText(previous_map_type)
        self.map_type_combo.blockSignals(was_blocked)

        # Show/hide background section
        self.bg_section.setVisible(is_rc)
        if is_rc:
            self.bg_section.toggle.setText("2  Background")
            self.bg_section.set_expanded(True)
            self.analysis_section.toggle.setText("3  Analysis Settings")
            self.linecuts_section.toggle.setText("4  Line Cuts")
            self.export_section.toggle.setText("4  Export")
            self.workflow_hint_label.setText(
                "1. Load data  →  2. Load background  →  3. Preview one RC frame "
                "and select a window or fixed energy  →  4. View / Update Now"
            )
            self.sidebar_scroll.ensureWidgetVisible(self.bg_section, 0, 16)
        else:
            self.analysis_section.toggle.setText("2  Analysis Settings")
            self.linecuts_section.toggle.setText("3  Line Cuts")
            self.export_section.toggle.setText("3  Export")
            self.workflow_hint_label.setText(
                "1. Load data  →  2. Choose analysis settings  →  3. View / Update Now"
            )

        # Show/hide baseline
        self.baseline_form_label.setVisible(not is_rc)
        self.baseline_row_widget.setVisible(not is_rc)

        # Show/hide RC preview sidebar controls
        for w in self._rc_sidebar_widgets:
            w.setVisible(is_rc)

        # Set sensible default colormap
        self.map_cmap_combo.setCurrentText("RdBu_r" if is_rc else "jet")
        self._show_current_map_view()

        if is_rc:
            self.reflection_preview_status_label.setText(
                "Load CSV + background, choose X/Y, then preview one RC frame. "
                "Drag to set the peak window or enter Fixed E for an RC-at-energy map."
            )

        if not is_rc and self.state.data is not None and self.auto_baseline_check.isChecked():
            self._estimate_and_apply_baseline(log=True, mark_dirty=False)

        if self.state.data is not None:
            self._invalidate_from_stage(2, f"Mode switched to {mode} – maps need refresh.")
        else:
            self._refresh_stage_states()

    # ── Stage-state refresh ───────────────────────────────────────────────

    def _refresh_stage_states(self) -> None:
        try:
            self.spectral_slices_panel.refresh()
            if self.state.mode == "Transport":
                self.load_csv_btn.setEnabled(self._thread is None and os.path.isfile(self.csv_edit.text().strip()))
                data = self.transport_panel.data
                matches_loaded = data is None or os.path.normcase(os.path.abspath(self.csv_edit.text().strip())) == os.path.normcase(data['source_path'])
                enabled = self._thread is None and matches_loaded
                self.transport_panel.setEnabled(enabled)
                for section in (self.transport_settings_section, self.transport_cuts_section, self.transport_export_section):
                    section.setEnabled(enabled)
                return
            has_csv_path = bool(self.csv_edit.text().strip())
            csv_is_file = has_csv_path and os.path.isfile(self.csv_edit.text().strip())
            has_data = self.state.data is not None
            is_rc = self.state.mode == "Reflection"
            has_background = self.state.background_spectra is not None
            electrical_selected = self.map_type_combo.currentText() in {
                "Ibias",
                "Resistance",
            }
            has_transformed_map = self.state.transformed_map is not None and not self._dirty_views.get("intensity_transformed", True)
            supports_de = bool(
                has_data and self.state.data.get("axis_space") in {"gate", "transformed"}
            )
            batch_linecuts_ready = self._batch_linecuts_ready()

            self.load_csv_btn.setEnabled(bool(csv_is_file))
            self.load_bg_btn.setEnabled(bool(has_data and is_rc))
            self.preview_rc_btn.setEnabled(bool(has_data and is_rc and has_background))
            self.estimate_background_scale_btn.setEnabled(
                bool(
                    has_data
                    and is_rc
                    and has_background
                    and self.background_scale_check.isChecked()
                )
            )
            self.refresh_current_btn.setEnabled(
                bool(
                    has_data
                    and (electrical_selected or not is_rc or has_background)
                )
            )
            self.refresh_all_maps_btn.setEnabled(bool(has_data and (not is_rc or has_background)))
            self.plot_lines_btn.setEnabled(supports_de)
            self.batch_preview_btn.setEnabled(supports_de)
            self.extract_all_doping_btn.setEnabled(bool(batch_linecuts_ready))
            self.extract_all_efield_btn.setEnabled(bool(batch_linecuts_ready))
            self.extract_all_both_btn.setEnabled(bool(batch_linecuts_ready))

            current_valid = not self._dirty_views.get(self._current_view_key(), True) and self._thread is None and self._auto_file_matches()
            save_enabled = bool(self._current_map_figure() is not None and current_valid)
            self.save_current_png_btn.setEnabled(save_enabled)
            self.save_current_csv_btn.setEnabled(bool(self._current_map_payload() is not None and current_valid))
            self.map_plot_tab.set_export_enabled(save_enabled)
            has_any_map = any(
                map_data is not None
                for map_data in (
                    self.state.original_map,
                    self.state.transformed_map,
                    self.state.peak_map_original,
                    self.state.peak_map_transformed,
                    self.state.rc_fixed_map_original,
                    self.state.rc_fixed_map_transformed,
                    self.state.ibias_map_original,
                    self.state.ibias_map_transformed,
                    self.state.resistance_map_original,
                    self.state.resistance_map_transformed,
                )
            )
            self.save_all_maps_btn.setEnabled(has_any_map)
            has_lines = self.state.figures.get("line_cuts") is not None
            self.save_lines_png_btn.setEnabled(has_lines)
            self.save_lines_csv_btn.setEnabled(bool(self.state.line_cut_results))
            line_valid = (self._thread is None and self._auto_file_matches()
                          and (not self._preview_stale if self._reflection_preview_message is not None
                               else not self._dirty_views.get('line_cuts', True)))
            self.line_plot_tab.set_export_enabled(line_valid)
            self.raw_background_plot_tab.set_export_enabled(self._thread is None and self._auto_file_matches())
            self._resume_auto_updates()
        except Exception:
            self._append_log(traceback.format_exc(), "error")

    # ── Legacy per-stage callbacks (kept for compat) ──────────────────────


    # ── Save helpers ──────────────────────────────────────────────────────

    def _save_map(self, kind: str, output_type: str) -> None:
        if self._dirty_views.get('intensity_' + kind, True) or self._thread is not None or not self._auto_file_matches():
            self._append_log('Update the map before exporting.', 'warn')
            return
        map_payload = self.state.original_map if kind == "original" else self.state.transformed_map
        figure_key = "original_map" if kind == "original" else "transformed_map"
        figure = self.state.figures.get(figure_key)
        if map_payload is None or figure is None:
            self._append_log(f"No {kind} map available to save.", "warn")
            return
        path = ""
        try:
            z_name = map_payload.get("z_name", kind)
            path = self._export_file_path(
                f"{self._map_export_stem(map_payload, axes_override=kind)}.{output_type}"
            )
            if output_type == "png":
                exported = save_figure_with_axes_size(
                    figure,
                    path,
                    self._export_map_axes_size(),
                    dpi=300,
                )
            else:
                export_x, export_y, export_z = self._measured_map_arrays(
                    map_payload
                )
                exported = save_map_csv(
                    export_x, export_y, export_z,
                    path,
                    x_name=map_payload.get("x_name", "x"),
                    y_name=map_payload.get("y_name", "y"),
                    z_name=z_name,
                )
        except Exception as exc:
            target = path or self.out_edit.text().strip() or "the selected output directory"
            self._append_log(f"Save failed for {target}: {exc}", "error")
            return
        self._append_log(exported.message, "success")

    def _save_peak_png(self) -> None:
        axes = "original"
        for a, fig_key in [("original", "peak_map_original"), ("transformed", "peak_map_transformed")]:
            if self.state.figures.get(fig_key) is not None:
                axes = a
                break
        fig_key = f"peak_map_{axes}"
        figure = self.state.figures.get(fig_key)
        map_data = self.state.peak_map_original if axes == "original" else self.state.peak_map_transformed
        if figure is None or map_data is None:
            self._append_log("No peak map available to save.", "warn")
            return
        export_payload = dict(map_data)
        export_payload.setdefault("target_axes", axes)
        export_payload.setdefault(
            "z_name",
            "RC Peak Position" if self.state.mode == "Reflection" else "Peak Energy",
        )
        path = self._export_file_path(
            f"{self._map_export_stem(export_payload, axes_override=axes)}.png"
        )
        exported = save_figure_with_axes_size(
            figure,
            path,
            self._export_map_axes_size(),
            dpi=300,
        )
        self._append_log(exported.message, "success")

    def _save_peak_csv(self) -> None:
        for axes, attr, fig_key in [
            ("original", "peak_map_original", "peak_map_original"),
            ("transformed", "peak_map_transformed", "peak_map_transformed"),
        ]:
            map_data = getattr(self.state, attr)
            if map_data is None:
                continue
            export_payload = dict(map_data)
            export_payload.setdefault("target_axes", axes)
            export_payload.setdefault(
                "z_name",
                "RC Peak Position" if self.state.mode == "Reflection" else "Peak Energy",
            )
            path = self._export_file_path(
                f"{self._map_export_stem(export_payload, axes_override=axes)}.csv"
            )
            export_x, export_y, export_z = self._measured_map_arrays(map_data)
            exported = save_map_csv(
                export_x, export_y, export_z,
                path,
                x_name=map_data.get("x_name", "x"),
                y_name=map_data.get("y_name", "y"),
                z_name=map_data.get("z_name", "Peak Energy"),
            )
            self._append_log(exported.message, "success")

    def _save_lines_png(self) -> None:
        figure = self.state.figures.get("line_cuts")
        if figure is None:
            self._append_log("No line-cut figure available to save.", "warn")
            return
        path = self._export_file_path("linecuts.png")
        exported = save_figure(figure, path, dpi=300)
        self._append_log(exported.message, "success")

    def _save_lines_csvs(self) -> None:
        if not self.state.line_cut_results:
            self._append_log("No line cuts available to save.", "warn")
            return
        saved = 0
        for lc in self.state.line_cut_results:
            cut_type = lc.get("cut_type", "cut")
            c_val = lc.get("c_value_used", 0.0)
            sign = "n" if c_val < 0 else "p"
            path = self._export_file_path(
                f"linecut_{cut_type}_{sign}{abs(c_val):.4f}.csv"
            )
            exported = save_line_csv(lc, path)
            saved += int(exported.created)
            self._append_log(exported.message, "success")
        self._append_log(f"Created {saved} new line-cut CSV(s).", "success")

    # ── Browse background ─────────────────────────────────────────────────


    # ── Drag-and-drop for main window ─────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        try:
            gpos = event.pos()
            target = self._drop_target_from_global_pos(self.mapToGlobal(gpos))
        except Exception:
            target = "primary"

        paths = self._extract_csv_paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return

        if target == "background":
            self._set_background_paths(paths)
        else:
            self._set_primary_csv_path(paths[0])
        event.acceptProposedAction()
