from __future__ import annotations

import traceback

import numpy as np
from matplotlib.figure import Figure

from megasweep_analysis import plot_line_cut_spectrogram, plot_map


from ui.widgets import PlotTab


class PlotResultsMixin:
    def _log_map_payload(
        self,
        stage_name: str,
        payload: dict,
        x_name: str,
        y_name: str,
        *,
        ratio: float | None = None,
    ) -> None:
        mapping = (
            f"Axis X={self.state.selected_x_col or 'X'}, "
            f"Axis Y={self.state.selected_y_col or 'Y'}"
        )
        summary = (
            f"{stage_name} payload: X{np.shape(payload['X2D'])}, Y{np.shape(payload['Y2D'])}, "
            f"Z{np.shape(payload['Z2D'])}"
        )
        missing_count = int(payload.get("missing_count", 0))
        if missing_count:
            measured_count = int(payload.get("measured_count", 0))
            expected_count = int(payload.get("expected_count", 0))
            missing_percent = (
                100.0 * missing_count / expected_count
                if expected_count
                else 0.0
            )
            summary += (
                f", measured {measured_count}/{expected_count}, "
                f"missing {missing_count} ({missing_percent:.2f}%)"
            )
        if ratio is not None:
            summary += f", ratio={ratio:.4f}"
        self._append_log(summary, "info")
        self._append_log(
            f"{x_name} range: {self._describe_range(payload['X2D'])}; "
            f"{y_name} range: {self._describe_range(payload['Y2D'])}; "
            f"Z range: {self._describe_range(payload['Z2D'])}; {mapping}",
            "info",
        )


    def _handle_plot_failure(self, stage_name: str, message: str, tb: str, tab: PlotTab, figure_key: str) -> None:
        self.state.figures.pop(figure_key, None)
        tab.clear()
        self._append_log(f"{stage_name} plotting failed: {message}", "error")
        self._append_log(tb, "error")


    def _current_map_payload(self) -> dict | None:
        view_key = self._current_view_key()
        mapping = {
            "intensity_original": self.state.original_map,
            "intensity_transformed": self.state.transformed_map,
            "peak_original": self.state.peak_map_original,
            "peak_transformed": self.state.peak_map_transformed,
            "fixed_original": self.state.rc_fixed_map_original,
            "fixed_transformed": self.state.rc_fixed_map_transformed,
            "ibias_original": self.state.ibias_map_original,
            "ibias_transformed": self.state.ibias_map_transformed,
            "resistance_original": self.state.resistance_map_original,
            "resistance_transformed": self.state.resistance_map_transformed,
        }
        return mapping.get(view_key)


    def _current_map_figure(self):
        view_key = self._current_view_key()
        key_map = {
            "intensity_original": "original_map",
            "intensity_transformed": "transformed_map",
            "peak_original": "peak_map_original",
            "peak_transformed": "peak_map_transformed",
            "fixed_original": "fixed_map_original",
            "fixed_transformed": "fixed_map_transformed",
            "ibias_original": "ibias_map_original",
            "ibias_transformed": "ibias_map_transformed",
            "resistance_original": "resistance_map_original",
            "resistance_transformed": "resistance_map_transformed",
        }
        return self.state.figures.get(key_map[view_key])


    def _show_current_map_view(self) -> None:
        figure = self._current_map_figure()
        if figure is None:
            self.map_plot_tab.clear()
        else:
            if hasattr(self, "_axis_ranges"):
                self._apply_axis_ranges(figure, self.map_axes_combo.currentText())
            self.map_plot_tab.set_figure(figure)
        self._sync_color_limit_controls()
        self._sync_axis_range_controls()
        self._update_map_colors()
        self._update_status_labels()


    def _on_analysis_refresh_ready(self, payload: dict) -> None:
        try:
            cmap = self.map_cmap_combo.currentText()
            vmin_val = None if self.map_auto_scale_check.isChecked() else self.map_vmin_spin.value()
            vmax_val = None if self.map_auto_scale_check.isChecked() else self.map_vmax_spin.value()
            is_rc = self.state.mode == "Reflection"
            for map_key, map_data in payload.items():
                if map_key not in [
                    "original_map",
                    "transformed_map",
                    "peak_map_original",
                    "peak_map_transformed",
                    "fixed_map_original",
                    "fixed_map_transformed",
                    "ibias_map_original",
                    "ibias_map_transformed",
                    "resistance_map_original",
                    "resistance_map_transformed",
                ]:
                    continue

                try:
                    target_axes = map_data.get("target_axes", "original")

                    if map_key == "original_map":
                        self.state.original_map = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = "RC Peak-to-Peak" if is_rc else "PL Intensity"
                        z_label = "RC Amplitude (a.u.)" if is_rc else "PL Intensity (a.u.)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["intensity_original"] = False
                        figure_key = "original_map"

                    elif map_key == "transformed_map":
                        self.state.transformed_map = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = "RC Peak-to-Peak" if is_rc else "PL Intensity"
                        z_label = "RC Amplitude (a.u.)" if is_rc else "PL Intensity (a.u.)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["intensity_transformed"] = False
                        figure_key = "transformed_map"

                    elif map_key == "peak_map_original":
                        self.state.peak_map_original = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = (
                            self._rc_feature_position_name()
                            if is_rc
                            else "Peak Energy"
                        )
                        z_label = f"{z_name} (eV)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["peak_original"] = False
                        figure_key = "peak_map_original"

                    elif map_key == "peak_map_transformed":
                        self.state.peak_map_transformed = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = (
                            self._rc_feature_position_name()
                            if is_rc
                            else "Peak Energy"
                        )
                        z_label = f"{z_name} (eV)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["peak_transformed"] = False
                        figure_key = "peak_map_transformed"

                    elif map_key == "fixed_map_original":
                        self.state.rc_fixed_map_original = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        fixed_energy = float(map_data["fixed_energy"])
                        z_name = "RC"
                        z_label = f"RC at {fixed_energy:.6f} eV"
                        title = self._compact_map_title(
                            z_name,
                            fixed_energy=fixed_energy,
                        )
                        self._dirty_views["fixed_original"] = False
                        figure_key = "fixed_map_original"

                    elif map_key == "fixed_map_transformed":
                        self.state.rc_fixed_map_transformed = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        fixed_energy = float(map_data["fixed_energy"])
                        z_name = "RC"
                        z_label = f"RC at {fixed_energy:.6f} eV"
                        title = self._compact_map_title(
                            z_name,
                            fixed_energy=fixed_energy,
                        )
                        self._dirty_views["fixed_transformed"] = False
                        figure_key = "fixed_map_transformed"

                    elif map_key == "ibias_map_original":
                        self.state.ibias_map_original = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = "Ibias"
                        z_label = "Ibias (A)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["ibias_original"] = False
                        figure_key = "ibias_map_original"

                    elif map_key == "ibias_map_transformed":
                        self.state.ibias_map_transformed = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = "Ibias"
                        z_label = "Ibias (A)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["ibias_transformed"] = False
                        figure_key = "ibias_map_transformed"

                    elif map_key == "resistance_map_original":
                        self.state.resistance_map_original = map_data
                        x_name = self.state.data.get("x_name", "x")
                        y_name = self.state.data.get("y_name", "y")
                        z_name = "Resistance"
                        z_label = "R = Vbias / Ibias (Ω)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["resistance_original"] = False
                        figure_key = "resistance_map_original"

                    elif map_key == "resistance_map_transformed":
                        self.state.resistance_map_transformed = map_data
                        if self.state.data.get("axis_space") == "transformed":
                            x_name = self.state.data.get("x_name", "doping")
                            y_name = self.state.data.get("y_name", "efield")
                        else:
                            x_name, y_name = self._axis_labels()
                        z_name = "Resistance"
                        z_label = "R = Vbias / Ibias (Ω)"
                        title = self._compact_map_title(z_name)
                        self._dirty_views["resistance_transformed"] = False
                        figure_key = "resistance_map_transformed"

                    else:
                        continue

                    # Annotate map_data with display metadata
                    map_data["x_name"] = x_name
                    map_data["y_name"] = y_name
                    map_data["z_name"] = z_name
                    map_data["target_axes"] = target_axes

                    # Render figure
                    fig, _ = plot_map(
                        map_data["X2D"], map_data["Y2D"], map_data["Z2D"],
                        x_label=x_name, y_label=y_name, z_label=z_label,
                        title=title,
                        cmap=cmap,
                        vmin=vmin_val,
                        vmax=vmax_val,
                    )
                    self.state.figures[figure_key] = fig
                    self._apply_axis_ranges(fig, "Original" if target_axes == "original" else "Transformed")
                    self._log_map_payload(z_name, map_data, x_name, y_name)

                except Exception:
                    self._append_log(traceback.format_exc(), "error")

            self._show_current_map_view()
            self._update_status_labels()

        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _on_intensity_ready(self, result: dict) -> None:
        try:
            self.state.original_map = result
            self.state.original_map["x_name"] = self.state.data.get("x_name", "x")
            self.state.original_map["y_name"] = self.state.data.get("y_name", "y")
            self.state.original_map["z_name"] = "PL Intensity"
            self._dirty_views["intensity_original"] = False
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=self.state.original_map["x_name"],
                y_label=self.state.original_map["y_name"],
                z_label="PL Intensity (a.u.)",
                title=self._compact_map_title("PL Intensity"),
                cmap=cmap,
            )
            self.state.figures["original_map"] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _on_transform_ready(self, result: dict) -> None:
        try:
            if self.state.data.get("axis_space") == "transformed":
                x_label = self.state.data.get("x_name", "doping")
                y_label = self.state.data.get("y_name", "efield")
            else:
                x_label, y_label = self._axis_labels()
            title = self._compact_map_title("PL Intensity")
            self.state.transformed_map = result
            self.state.transformed_map["x_name"] = x_label
            self.state.transformed_map["y_name"] = y_label
            self.state.transformed_map["z_name"] = "PL Intensity"
            self._dirty_views["intensity_transformed"] = False
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=x_label, y_label=y_label,
                z_label="PL Intensity (a.u.)",
                title=title,
                cmap=cmap,
            )
            self.state.figures["transformed_map"] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _on_peak_ready(self, result: dict) -> None:
        try:
            axes = result.get("target_axes", "original")
            if axes == "transformed":
                if self.state.data.get("axis_space") == "transformed":
                    x_label = self.state.data.get("x_name", "doping")
                    y_label = self.state.data.get("y_name", "efield")
                else:
                    x_label, y_label = self._axis_labels()
                self.state.peak_map_transformed = result
                self.state.peak_map_transformed["x_name"] = x_label
                self.state.peak_map_transformed["y_name"] = y_label
                self.state.peak_map_transformed["z_name"] = "Peak Energy"
                self._dirty_views["peak_transformed"] = False
                figure_key = "peak_map_transformed"
            else:
                self.state.peak_map_original = result
                self.state.peak_map_original["x_name"] = self.state.data.get("x_name", "x")
                self.state.peak_map_original["y_name"] = self.state.data.get("y_name", "y")
                self.state.peak_map_original["z_name"] = "Peak Energy"
                self._dirty_views["peak_original"] = False
                figure_key = "peak_map_original"
            title = self._compact_map_title("Peak Energy")
            cmap = self.map_cmap_combo.currentText()
            fig, _ = plot_map(
                result["X2D"], result["Y2D"], result["Z2D"],
                x_label=result.get("x_name", "x"),
                y_label=result.get("y_name", "y"),
                z_label="Peak Energy (eV)",
                title=title,
                cmap=cmap,
            )
            self.state.figures[figure_key] = fig
            self._show_current_map_view()
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _on_lines_ready(self, result: dict) -> None:
        try:
            line_cuts = result.get("line_cuts", [])
            if not line_cuts:
                self._append_log("No line cuts were extracted.", "warn")
                return

            self.state.line_cut_results = line_cuts
            self._dirty_views["line_cuts"] = False
            is_rc = self.state.mode == "Reflection"
            cmap = "RdBu_r" if is_rc else "jet"
            z_label = (
                "RC = (R - R_background) / R_background"
                if is_rc
                else "PL Intensity (a.u.)"
            )

            # Pick the first multi-row cut for the preview figure
            preview_cut = next(
                (lc for lc in line_cuts if np.asarray(lc["spectra"]).shape[0] >= 2),
                line_cuts[0],
            )
            c_used = preview_cut.get("c_value_used", 0.0)
            cut_type = preview_cut.get("cut_type", "cut")
            title = f"RC spectra near {cut_type} = {c_used:.3f} V" if is_rc else f"{cut_type} = {c_used:.3f} V"
            if np.asarray(preview_cut["spectra"]).shape[0] >= 2:
                fig, ax = plot_line_cut_spectrogram(
                    preview_cut, title=title, cmap=cmap, z_label=z_label
                )
            else:
                fig = Figure(figsize=(7, 4.8))
                ax = fig.add_subplot(111)
                s = np.asarray(preview_cut["spectra"], dtype=float).reshape(-1)
                ax.plot(preview_cut["energy"], s, color="#1d4ed8", linewidth=1.5)
                ax.set_xlabel("Energy (eV)")
                ax.set_ylabel(z_label)
                ax.set_title(title)
                fig.tight_layout()

            # Shade the analysis window
            e_lo = min(self.int_min_spin.value(), self.int_max_spin.value())
            e_hi = max(self.int_min_spin.value(), self.int_max_spin.value())
            ax.axvspan(e_lo, e_hi, color="#fef08a", alpha=0.15)

            self.state.figures["line_cuts"] = fig
            self.line_plot_tab.set_figure(fig)
            # Recompute legacy recipes for compatibility, but never overwrite
            # the user's newer processing/range recipe while restoring a file.
            if not self._restoring_session or not (self._pending_session or {}).get('spectral_slices'):
                self.spectral_slices_panel.show_existing_cut(preview_cut)
            self._append_log(f"Extracted {len(line_cuts)} line cut(s).", "success")
            self._update_status_labels()
        except Exception:
            self._append_log(traceback.format_exc(), "error")


    def _on_batch_lines_ready(self, result: dict) -> None:
        try:
            total = result.get("total_cuts", 0)
            n_files = len(result.get("saved_files", []))
            self._append_log(f"Batch line cut done: {total} cuts, {n_files} files saved.", "success")
        except Exception:
            self._append_log(traceback.format_exc(), "error")
