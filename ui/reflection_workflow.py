from __future__ import annotations

import os
import traceback

import numpy as np
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtWidgets import QFileDialog

from megasweep_analysis import (
    compute_rc_at_energy_map,
    compute_rc_spectra,
    estimate_background_scale,
    spectral_axes_match,
)
from ui.workers import BackgroundLoadWorker


class ReflectionWorkflowMixin:
    def _clear_background_state(self, status_text: str = "No background loaded.") -> None:
        self.state.background_spectra = None
        self.state.background_wavelength = None
        self.state.background_path = ""
        self.state.background_paths = []
        self.state.background_scale_factor = None
        self.state.background_scale_info = None
        self.state.background_scale_frame_index = None
        self.state.figures.pop("raw_background", None)
        if hasattr(self, "raw_background_plot_tab"):
            self.raw_background_plot_tab.clear()
        self.bg_status_label.setText(status_text)


    def _validate_reflection_background_ready(self) -> bool:
        if self.state.mode != "Reflection":
            return True
        if self.state.background_spectra is None:
            self._append_log("Reflection mode requires a loaded background before RC maps or line cuts can be computed.", "error")
            return False
        if self.state.data is None:
            self._append_log("Load the reflection CSV before validating the background spectrum.", "error")
            return False
        background = np.asarray(self.state.background_spectra, dtype=float).reshape(-1)
        expected = int(self.state.data["Intensity"].shape[1])
        if background.shape[0] != expected:
            self._append_log(
                "Loaded background does not match the current reflection dataset. "
                f"Data has {expected} channels while the background has {background.shape[0]}. Reload a matching background CSV.",
                "error",
            )
            return False
        if (
            self.background_scale_check.isChecked()
            and self.state.background_scale_factor is None
        ):
            if not self._estimate_and_apply_background_scale(
                log=True,
                refresh_preview=False,
            ):
                return False
        return True


    def _background_scale_windows(self) -> list[tuple[float, float]]:
        return [
            (
                self.scale_left_min_spin.value(),
                self.scale_left_max_spin.value(),
            ),
            (
                self.scale_right_min_spin.value(),
                self.scale_right_max_spin.value(),
            ),
        ]


    def _effective_background_scale(self) -> float:
        if not self.background_scale_check.isChecked():
            return 1.0
        scale = self.state.background_scale_factor
        if scale is None or not np.isfinite(scale) or scale <= 0:
            raise ValueError(
                "Estimate the background scale before calculating RC."
            )
        return float(scale)


    def _clear_rc_results_for_scale_change(self) -> None:
        """Invalidate only results that depend on the reflection background."""
        self.state.original_map = None
        self.state.transformed_map = None
        self.state.peak_map_original = None
        self.state.peak_map_transformed = None
        self.state.rc_fixed_map_original = None
        self.state.rc_fixed_map_transformed = None
        self.state.line_cut_specs = []
        self.state.line_cut_results = []
        for figure_key in (
            "original_map",
            "transformed_map",
            "peak_map_original",
            "peak_map_transformed",
            "fixed_map_original",
            "fixed_map_transformed",
            "line_cuts",
        ):
            self.state.figures.pop(figure_key, None)
        self._mark_dirty(
            "intensity_original",
            "intensity_transformed",
            "peak_original",
            "peak_transformed",
            "fixed_original",
            "fixed_transformed",
            "line_cuts",
        )
        self.line_plot_tab.clear()


    def _on_background_scale_enabled_changed(self, enabled: bool) -> None:
        for widget in (
            self.scale_left_min_spin,
            self.scale_left_max_spin,
            self.scale_right_min_spin,
            self.scale_right_max_spin,
            self.estimate_background_scale_btn,
        ):
            widget.setEnabled(enabled)
        if self.state.data is None:
            return
        self._clear_rc_results_for_scale_change()
        if enabled and self.state.background_spectra is not None:
            self._estimate_and_apply_background_scale(
                log=True,
                refresh_preview=False,
            )
        else:
            self.background_scale_status_label.setText(
                "Scale correction off; α = 1"
            )
        try:
            self._refresh_raw_background_plot()
        except Exception as exc:
            self._append_log(f"Raw/background refresh failed: {exc}", "error")
        self._show_current_map_view()
        self._refresh_stage_states()


    def _on_background_scale_window_changed(self, _value: float) -> None:
        self.state.background_scale_factor = None
        self.state.background_scale_info = None
        self.state.background_scale_frame_index = None
        self.background_scale_status_label.setText(
            "Scale α: window changed; estimate again"
        )
        if self.state.data is None:
            return
        self._clear_rc_results_for_scale_change()
        try:
            self._refresh_raw_background_plot()
        except Exception:
            pass
        self._show_current_map_view()
        self._refresh_stage_states()


    def _estimate_and_apply_background_scale(
        self,
        _checked: bool = False,
        *,
        log: bool = True,
        refresh_preview: bool = True,
    ) -> bool:
        if not self.background_scale_check.isChecked():
            self.background_scale_status_label.setText(
                "Scale correction off; α = 1"
            )
            return True
        if self.state.data is None or self.state.background_spectra is None:
            if log:
                self._append_log(
                    "Load the reflection CSV and background before estimating scale.",
                    "error",
                )
            return False
        try:
            row_index, actual_x, actual_y = self._selected_reflection_frame()
            scale, info = estimate_background_scale(
                self.state.data["Intensity"][row_index],
                self.state.background_spectra,
                self.state.data["energy"],
                self._background_scale_windows(),
            )
            self.state.background_scale_factor = scale
            self.state.background_scale_info = info
            self.state.background_scale_frame_index = row_index
            relative_mad_percent = 100.0 * float(info["relative_mad"])
            self.background_scale_status_label.setText(
                f"α = {scale:.6g} | {info['channel_count']} channels | "
                f"relative MAD {relative_mad_percent:.2f}%"
            )
            self._clear_rc_results_for_scale_change()
            self._refresh_raw_background_plot(row_index, actual_x, actual_y)
            if log:
                left, right = info["windows"]
                self._append_log(
                    f"Background scale estimated: α={scale:.8g} from "
                    f"{info['channel_count']} channels in left "
                    f"{left[0]:.6f}-{left[1]:.6f} eV and right "
                    f"{right[0]:.6f}-{right[1]:.6f} eV windows "
                    f"(relative MAD {relative_mad_percent:.2f}%).",
                    "success",
                )
                if relative_mad_percent > 10.0:
                    self._append_log(
                        "Raw/background scaling varies by more than 10% in the "
                        "side windows. Check that both windows are feature-free.",
                        "warn",
                    )
            if refresh_preview and self._reflection_preview_message is not None:
                self._preview_reflection_spectra()
            self._show_current_map_view()
            self._refresh_stage_states()
            return True
        except Exception as exc:
            self.state.background_scale_factor = None
            self.state.background_scale_info = None
            self.state.background_scale_frame_index = None
            self.background_scale_status_label.setText(
                f"Scale estimate failed: {exc}"
            )
            if log:
                self._append_log(f"Background scale estimate failed: {exc}", "error")
            return False


    def _clear_reflection_preview(self) -> None:
        self._reflection_preview_message = None
        self._rc_span_selector = None
        if self.state.figures.get("line_cuts") is None:
            self.line_plot_tab.clear()


    def _configure_reflection_preview_coordinates(self) -> None:
        """Set useful coordinate ranges/defaults for selecting one RC frame."""
        if self.state.data is None:
            return
        for values, spin in (
            (self.state.data["x_data"], self.reflection_preview_vbg_spin),
            (self.state.data["y_data"], self.reflection_preview_vtg_spin),
        ):
            array = np.asarray(values, dtype=float).reshape(-1)
            finite = array[np.isfinite(array)]
            if finite.size == 0:
                continue
            spin.setRange(float(np.min(finite)), float(np.max(finite)))
            unique = np.unique(finite)
            if unique.size > 1:
                positive_steps = np.diff(unique)
                positive_steps = positive_steps[positive_steps > 0]
                if positive_steps.size:
                    spin.setSingleStep(float(np.median(positive_steps)))
            spin.setValue(float(finite[0]))


    def _selected_reflection_frame(self) -> tuple[int, float, float]:
        """Return the row nearest the requested reflection-preview coordinates."""
        if self.state.data is None:
            raise ValueError("Load a reflection CSV first.")
        x_data = np.asarray(self.state.data["x_data"], dtype=float).reshape(-1)
        y_data = np.asarray(self.state.data["y_data"], dtype=float).reshape(-1)
        if x_data.size == 0 or y_data.size == 0 or x_data.size != y_data.size:
            raise ValueError("No valid reflection sweep coordinates are available.")

        finite_mask = np.isfinite(x_data) & np.isfinite(y_data)
        if not np.any(finite_mask):
            raise ValueError(
                "Reflection dataset does not contain finite sweep-coordinate points."
            )
        target_x = float(self.reflection_preview_vbg_spin.value())
        target_y = float(self.reflection_preview_vtg_spin.value())
        finite_indices = np.flatnonzero(finite_mask)
        distances = (
            (x_data[finite_mask] - target_x) ** 2
            + (y_data[finite_mask] - target_y) ** 2
        )
        row_index = int(finite_indices[int(np.argmin(distances))])
        return row_index, float(x_data[row_index]), float(y_data[row_index])


    def _refresh_raw_background_plot(
        self,
        row_index: int | None = None,
        actual_x: float | None = None,
        actual_y: float | None = None,
    ) -> None:
        """Plot one unnormalized raw spectrum with the averaged background."""
        if (
            self.state.data is None
            or self.state.background_spectra is None
            or self.state.background_wavelength is None
        ):
            self.state.figures.pop("raw_background", None)
            self.raw_background_plot_tab.clear()
            return

        if row_index is None or actual_x is None or actual_y is None:
            row_index, actual_x, actual_y = self._selected_reflection_frame()

        wavelength = np.asarray(
            self.state.data["wavelength"],
            dtype=float,
        ).reshape(-1)
        background_wavelength = np.asarray(
            self.state.background_wavelength,
            dtype=float,
        ).reshape(-1)
        raw_spectrum = np.asarray(
            self.state.data["Intensity"][row_index],
            dtype=float,
        ).reshape(-1)
        averaged_background = np.asarray(
            self.state.background_spectra,
            dtype=float,
        ).reshape(-1)
        if not spectral_axes_match(wavelength, background_wavelength):
            raise ValueError(
                "Cannot plot raw/background comparison because their wavelength "
                "channels do not match."
            )
        if (
            raw_spectrum.size != wavelength.size
            or averaged_background.size != wavelength.size
        ):
            raise ValueError(
                "Raw spectrum, background, and wavelength arrays must have the "
                "same number of channels."
            )

        order = np.argsort(wavelength)
        wavelength_sorted = wavelength[order]
        raw_sorted = raw_spectrum[order]
        background_sorted = averaged_background[order]
        max_delta = float(
            np.max(np.abs(wavelength - background_wavelength))
        )

        fig = Figure(figsize=(7, 4.8))
        ax = fig.add_subplot(111)
        ax.plot(
            wavelength_sorted,
            raw_sorted,
            color="#2563eb",
            linewidth=1.5,
            label="Selected raw spectrum",
        )
        ax.plot(
            wavelength_sorted,
            background_sorted,
            color="#dc2626",
            linewidth=1.5,
            label="Averaged background",
        )
        scale = self.state.background_scale_factor
        if (
            self.background_scale_check.isChecked()
            and scale is not None
            and np.isfinite(scale)
            and scale > 0
        ):
            ax.plot(
                wavelength_sorted,
                background_sorted * float(scale),
                color="#16a34a",
                linewidth=1.5,
                linestyle="--",
                label=f"Scaled background (α={float(scale):.5g})",
            )

        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
        if e_lo > 0 and e_hi > 0:
            wavelength_lo = 1240.0 / e_hi
            wavelength_hi = 1240.0 / e_lo
            ax.axvspan(
                wavelength_lo,
                wavelength_hi,
                color="#fef08a",
                alpha=0.18,
                label="RC analysis window",
            )
        if self.background_scale_check.isChecked():
            for index, (scale_lo, scale_hi) in enumerate(
                self._background_scale_windows()
            ):
                if scale_lo > 0 and scale_hi > 0:
                    ax.axvspan(
                        1240.0 / max(scale_lo, scale_hi),
                        1240.0 / min(scale_lo, scale_hi),
                        color="#bbf7d0",
                        alpha=0.20,
                        label=(
                            "Scale side windows"
                            if index == 0
                            else "_nolegend_"
                        ),
                    )

        x_name = self.state.data.get("x_name", "X")
        y_name = self.state.data.get("y_name", "Y")
        ax.set_title(
            f"Raw vs averaged background  "
            f"{x_name} = {actual_x:.3f},  {y_name} = {actual_y:.3f}"
        )
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Raw detector signal")
        ax.grid(True, alpha=0.18)
        ax.legend(loc="best")
        ax.text(
            0.01,
            0.02,
            f"{wavelength.size} matched channels; max |Δλ| = {max_delta:.6f} nm",
            transform=ax.transAxes,
            fontsize=9,
            color="#475569",
            verticalalignment="bottom",
        )
        fig.tight_layout()
        self.state.figures["raw_background"] = fig
        self.raw_background_plot_tab.set_figure(fig)


    def _on_rc_energy_span_selected(self, e_min: float, e_max: float) -> None:
        """Apply a dragged RC-preview span as the shared map energy window."""
        if self.state.data is None or not np.isfinite(e_min) or not np.isfinite(e_max):
            return
        lo, hi = sorted((float(e_min), float(e_max)))
        energy = np.asarray(self.state.data["energy"], dtype=float)
        finite = energy[np.isfinite(energy)]
        if finite.size == 0:
            return
        lo = max(lo, float(np.min(finite)))
        hi = min(hi, float(np.max(finite)))
        if hi <= lo:
            return

        self._suppress_intensity_tracking = True
        self.int_min_spin.setValue(lo)
        self.int_max_spin.setValue(hi)
        self._suppress_intensity_tracking = False
        self._intensity_range_user_modified = True
        self._on_energy_window_changed()
        self._append_log(
            f"RC analysis window selected from preview: {lo:.4f}-{hi:.4f} eV. "
            "Peak-to-peak and peak-position maps will use this range.",
            "success",
        )


    def _preview_reflection_spectra(self) -> None:
        if self.state.mode != "Reflection":
            self._append_log("RC spectra preview is only available in Reflection mode.", "warn")
            return
        if self.state.data is None:
            self._append_log("Load a reflection CSV before previewing RC spectra.", "error")
            return
        if not self._validate_reflection_background_ready():
            return

        try:
            from scipy.signal import savgol_filter as _sgf
            from megasweep_analysis import compute_rc_peak_position as _rc_peak_pos

            rc_spectra = compute_rc_spectra(
                self.state.data["Intensity"],
                self.state.background_spectra,
                background_scale=self._effective_background_scale(),
            )
            energy = np.asarray(self.state.data["energy"], dtype=float).reshape(-1)
            if rc_spectra.shape[0] == 0:
                raise ValueError("No reflection points are available for RC preview.")
            row_index, actual_x, actual_y = self._selected_reflection_frame()
            spectrum = np.asarray(rc_spectra[row_index], dtype=float).reshape(-1)
            self._refresh_raw_background_plot(row_index, actual_x, actual_y)
        except Exception:
            self._append_log(traceback.format_exc(), "error")
            return

        e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
        e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())

        # ── Smoothed spectrum ─────────────────────────────────────────────
        n_pts = spectrum.size
        win = min(
            int(self.sg_window_spin.value()),
            n_pts if n_pts % 2 == 1 else n_pts - 1,
        )
        if win % 2 == 0:
            win -= 1
        poly = min(int(self.sg_poly_spin.value()), max(0, win - 1))
        try:
            if win < 3:
                raise ValueError("Not enough spectral channels for smoothing.")
            spectrum_smooth = _sgf(
                spectrum,
                window_length=win,
                polyorder=poly,
                mode="interp",
            )
        except Exception:
            spectrum_smooth = spectrum.copy()

        # ── RC statistics inside the analysis window ──────────────────────
        win_mask = (energy >= e_lo) & (energy <= e_hi)
        if np.any(win_mask):
            rc_win = spectrum[win_mask]
            rc_max = float(np.nanmax(rc_win))
            rc_min = float(np.nanmin(rc_win))
            rc_p2p = rc_max - rc_min
            e_arr = energy[win_mask]
            e_max = float(e_arr[np.nanargmax(rc_win)])
            e_min_pt = float(e_arr[np.nanargmin(rc_win)])
        else:
            rc_max = rc_min = rc_p2p = float("nan")
            e_max = e_min_pt = float("nan")

        # ── Peak position (dominant feature) ─────────────────────────────
        try:
            pk_energy, pk_value = _rc_peak_pos(
                energy,
                spectrum,
                e_lo,
                e_hi,
                sg_window=self.sg_window_spin.value(),
                sg_poly=self.sg_poly_spin.value(),
                feature_mode=self._current_rc_feature_mode(),
            )
        except Exception:
            pk_energy, pk_value = float("nan"), float("nan")

        # ── Plot ──────────────────────────────────────────────────────────
        fig = Figure(figsize=(7, 4.8))
        ax = fig.add_subplot(111)

        ax.plot(energy, spectrum, color="#93c5fd", linewidth=1.0, alpha=0.7, label="Raw RC")
        ax.plot(energy, spectrum_smooth, color="#1d4ed8", linewidth=1.8, label="Smoothed")
        ax.axvspan(
            e_lo,
            e_hi,
            color="#fef08a",
            alpha=0.25,
            label=f"Window [{e_lo:.6f}–{e_hi:.6f} eV]",
        )
        fixed_energy = self.fixed_energy_spin.value()
        try:
            fixed_rc = float(
                compute_rc_at_energy_map(
                    spectrum.reshape(1, -1),
                    energy,
                    fixed_energy,
                )[0]
            )
        except ValueError:
            fixed_rc = float("nan")
        if np.isfinite(fixed_rc):
            ax.axvline(
                fixed_energy,
                color="#7c3aed",
                linestyle="-.",
                linewidth=1.5,
                label=f"Fixed E = {fixed_energy:.6f} eV",
            )
            ax.scatter([fixed_energy], [fixed_rc], color="#7c3aed", zorder=6, s=42)

        if np.isfinite(rc_max) and np.isfinite(e_max):
            ax.scatter([e_max], [rc_max], color="#dc2626", zorder=5, s=50, label=f"Max {rc_max:.4f}")
        if np.isfinite(rc_min) and np.isfinite(e_min_pt):
            ax.scatter([e_min_pt], [rc_min], color="#2563eb", zorder=5, s=50, label=f"Min {rc_min:.4f}")
        if np.isfinite(rc_p2p):
            if np.isfinite(e_min_pt) and np.isfinite(rc_min) and np.isfinite(rc_max):
                ax.plot(
                    [e_min_pt, e_min_pt], [rc_min, rc_max],
                    color="black", linestyle="--", linewidth=1.2,
                    label=f"P2P = {rc_p2p:.4f}",
                )
        if np.isfinite(pk_energy) and np.isfinite(pk_value):
            feature_label = {
                "peak": "Peak",
                "dip": "Dip",
                "auto": "Feature",
            }[self._current_rc_feature_mode()]
            ax.axvline(pk_energy, color="#16a34a", linestyle=":", linewidth=1.4)
            ax.annotate(
                f"{feature_label}\n{pk_energy:.4f} eV",
                xy=(pk_energy, pk_value),
                xytext=(6, 6),
                textcoords="offset points",
                color="#15803d",
                fontsize=8,
            )

        ax.set_xlabel("Energy (eV)")
        ax.set_ylabel("RC = (R - R_background) / R_background")
        x_label = self.state.data.get("x_name", "X")
        y_label = self.state.data.get("y_name", "Y")
        ax.set_title(f"RC spectrum  {x_label} = {actual_x:.3f},  {y_label} = {actual_y:.3f}")
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()

        self.line_plot_tab.set_figure(fig)
        self._rc_span_selector = SpanSelector(
            ax,
            self._on_rc_energy_span_selected,
            "horizontal",
            useblit=True,
            props={"facecolor": "#f59e0b", "alpha": 0.2},
            minspan=1e-6,
            interactive=True,
        )
        self.workspace_tabs.setCurrentIndex(1)

        p2p_str = f"{rc_p2p:.4f}" if np.isfinite(rc_p2p) else "n/a"
        pk_str = f"{pk_energy:.4f} eV" if np.isfinite(pk_energy) else "n/a"
        fixed_str = f"{fixed_rc:.6g}" if np.isfinite(fixed_rc) else "out of range"
        scale_str = (
            f"{self._effective_background_scale():.6g}"
            if self.background_scale_check.isChecked()
            else "1 (off)"
        )
        self._reflection_preview_message = (
            f"RC preview: {x_label}={actual_x:.3f}, {y_label}={actual_y:.3f} | "
            f"BG scale α={scale_str} | "
            f"Window={e_lo:.6f}-{e_hi:.6f} eV | P2P={p2p_str} | "
            f"{self.rc_feature_combo.currentText()}={pk_str} | "
            f"RC({fixed_energy:.6f} eV)={fixed_str}. "
            "Drag horizontally to change the window."
        )
        self.reflection_preview_status_label.setText(self._reflection_preview_message)
        self._schedule_session_save()


    def _start_background_load(self) -> None:
        paths = self._get_background_paths()
        if not paths:
            self._append_log("Select at least one background CSV file first.", "error")
            return

        for p in paths:
            if not os.path.isfile(p):
                self._append_log(f"Background file not found: {p}", "error")
                return

        if self.state.data is None:
            self._append_log(
                "Load the primary reflection CSV first so the background channels can be validated.",
                "error",
            )
            return

        mode = self.bg_average_mode_combo.currentData() or "all_frames"
        worker = BackgroundLoadWorker(
            paths,
            average_mode=mode,
            expected_wavelength=self.state.data["wavelength"],
        )
        self._run_worker(worker, self._on_background_loaded, context="Loading background CSV")


    def _on_background_loaded(self, result: dict) -> None:
        try:
            self.state.background_spectra = result["background_spectra"]
            self.state.background_wavelength = result.get("wavelength")
            self.state.background_path = result.get("background_path", "")
            self.state.background_paths = result.get("background_paths", [])
            self.state.background_average_mode = result.get("average_mode", "all_frames")
            self.state.background_scale_factor = None
            self.state.background_scale_info = None
            self.state.background_scale_frame_index = None
            n_spectra = result.get("spectrum_count", "?")
            n_channels = np.asarray(self.state.background_spectra).shape[0]
            self.bg_status_label.setText(
                f"Background: {n_channels} ch, averaged from {n_spectra} spectra. "
                f"({os.path.basename(self.state.background_path)})"
            )
            self.bg_status_label.setToolTip("\n".join(self.state.background_paths))
            self._append_log(
                f"Background loaded: {n_channels} channels, {n_spectra} spectra averaged.",
                "success",
            )
            self._append_log(
                "Reflection contrast is computed wavelength-by-wavelength as "
                "RC = (R - R_background) / R_background.",
                "info",
            )
            self.reflection_preview_status_label.setText(
                "Background ready. Preview one RC frame; drag to set the peak "
                "window or enter Fixed E for the RC-at-energy map."
            )
            # Invalidate any previously computed maps since background changed
            self._invalidate_from_stage(2, "Background updated – RC maps need refresh.")
            if self.background_scale_check.isChecked():
                self._estimate_and_apply_background_scale(
                    log=True,
                    refresh_preview=False,
                )
            else:
                self._refresh_raw_background_plot()
            self.bg_section.set_expanded(False)
            self.analysis_section.set_expanded(True)
            self.sidebar_scroll.ensureWidgetVisible(self.analysis_section, 0, 16)
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _browse_background_csv(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select background CSV file(s)",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if paths:
            self._set_background_paths(paths)
