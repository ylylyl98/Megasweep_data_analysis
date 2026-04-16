from __future__ import annotations

import os
import traceback

import numpy as np
from PySide6.QtCore import QObject, Signal

from megasweep_analysis import (
    build_grid,
    compute_intensity_map,
    compute_peak_energy_map,
    compute_peak_energy,
    compute_rc_spectra,
    compute_rc_peak_position_map,
    compute_rc_peak_to_peak_map,
    compute_transformed_coords,
    extract_line_cut,
    find_all_cut_values,
    load_megasweep_csv,
    plot_line_cut_spectrogram,
    save_figure,
    save_line_csv,
)


def _compute_reflection_spectra(data: dict, background_spectra) -> np.ndarray:
    if background_spectra is None:
        raise ValueError("Reflection mode requires a loaded background spectrum before RC can be computed.")

    intensity = np.asarray(data["Intensity"], dtype=float)
    background = np.asarray(background_spectra, dtype=float).reshape(-1)
    n_channels = intensity.shape[1]
    if background.shape[0] != n_channels:
        raise ValueError(
            "Background spectrum does not match the loaded CSV spectral channels. "
            f"Data has {n_channels} channels, background has {background.shape[0]}. "
            "Reload a matching background CSV for this dataset."
        )
    return compute_rc_spectra(intensity, background)


class BaseWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    log = Signal(str)

    def run(self) -> None:
        try:
            result = self.process()
            self.finished.emit(result)
        except Exception:
            self.error.emit(traceback.format_exc())

    def process(self):
        raise NotImplementedError


class CsvLoadWorker(BaseWorker):
    def __init__(self, csv_path: str, x_col: str, y_col: str):
        super().__init__()
        self.csv_path = csv_path
        self.x_col = x_col
        self.y_col = y_col

    def process(self) -> dict:
        self.log.emit("Loading CSV data...")
        data = load_megasweep_csv(self.csv_path, x_col=self.x_col, y_col=self.y_col)
        return {"data": data}


class BackgroundLoadWorker(BaseWorker):
    _MODE_LABELS = {
        "all_frames": "all frames from each CSV",
        "first_frame": "the first frame from each CSV",
        "last_frame": "the last frame from each CSV",
    }

    def __init__(
        self,
        csv_paths: list[str],
        x_col: str,
        y_col: str,
        average_mode: str = "all_frames",
        expected_wavelength=None,
    ):
        super().__init__()
        self.csv_paths = list(csv_paths)
        self.x_col = x_col
        self.y_col = y_col
        self.average_mode = average_mode
        self.expected_wavelength = None if expected_wavelength is None else np.asarray(expected_wavelength, dtype=float)

    def _select_background_frames(self, intensity: np.ndarray) -> np.ndarray:
        if self.average_mode == "all_frames":
            return intensity
        if self.average_mode == "first_frame":
            return intensity[:1]
        if self.average_mode == "last_frame":
            return intensity[-1:]
        raise ValueError(f"Unknown background averaging mode: {self.average_mode}")

    def process(self) -> dict:
        if not self.csv_paths:
            raise ValueError("No background CSV files were selected.")

        mode_label = self._MODE_LABELS.get(self.average_mode, self.average_mode)
        self.log.emit(f"Loading {len(self.csv_paths)} background CSV file(s) using {mode_label}...")

        selected_spectra = []
        reference_wavelength = None
        reference_energy = None
        total_spectra = 0
        for index, csv_path in enumerate(self.csv_paths, start=1):
            data = load_megasweep_csv(csv_path, x_col=self.x_col, y_col=self.y_col)
            wavelength = np.asarray(data["wavelength"], dtype=float)
            energy = np.asarray(data["energy"], dtype=float)

            if reference_wavelength is None:
                reference_wavelength = wavelength
                reference_energy = energy
                if self.expected_wavelength is not None:
                    if (
                        wavelength.shape != self.expected_wavelength.shape
                        or not np.allclose(wavelength, self.expected_wavelength, rtol=1e-9, atol=1e-9)
                    ):
                        raise ValueError(
                            "Background spectral channels do not match the loaded megasweep data."
                        )
            elif wavelength.shape != reference_wavelength.shape or not np.allclose(
                wavelength, reference_wavelength, rtol=1e-9, atol=1e-9
            ):
                raise ValueError(
                    "Selected background CSV files do not share the same spectral channels."
                )

            frames = self._select_background_frames(np.asarray(data["Intensity"], dtype=float))
            if frames.ndim != 2 or frames.shape[0] == 0:
                raise ValueError(f"No usable spectra were found in background CSV: {csv_path}")
            selected_spectra.append(frames)
            total_spectra += frames.shape[0]
            self.log.emit(
                f"Background file {index}/{len(self.csv_paths)}: {os.path.basename(csv_path)} -> "
                f"{frames.shape[0]} frame(s) selected."
            )

        bg = np.mean(np.vstack(selected_spectra), axis=0)
        self.log.emit(
            f"Background averaged from {total_spectra} selected spectra across "
            f"{len(self.csv_paths)} file(s) ({bg.shape[0]} spectral channels)."
        )
        return {
            "background_spectra": bg,
            "background_path": self.csv_paths[0] if len(self.csv_paths) == 1 else f"{len(self.csv_paths)} CSV files",
            "background_paths": self.csv_paths,
            "average_mode": self.average_mode,
            "wavelength": reference_wavelength,
            "energy": reference_energy,
            "spectrum_count": total_spectra,
        }


class AnalysisRefreshWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        min_energy: float,
        max_energy: float,
        baseline: float,
        ratio: float,
        sg_window: int,
        sg_poly: int,
        tasks: list[str],
        tg_is_y: bool,
        mode: str = "PL",
        background_spectra=None,
    ):
        super().__init__()
        self.data = data
        self.min_energy = min_energy
        self.max_energy = max_energy
        self.baseline = baseline
        self.ratio = ratio
        self.sg_window = sg_window
        self.sg_poly = sg_poly
        self.tasks = tasks
        self.tg_is_y = tg_is_y
        self.mode = mode
        self.background_spectra = background_spectra

    def process(self) -> dict:
        tasks = set(self.tasks)
        payload: dict[str, dict] = {}

        if not tasks:
            return payload

        self.log.emit("Refreshing map analysis...")

        # Determine effective intensity matrix and map values based on mode
        if self.mode == "Reflection":
            self.log.emit("Computing RC spectra from the loaded background...")
            rc = _compute_reflection_spectra(self.data, self.background_spectra)
            intensity_flat = compute_rc_peak_to_peak_map(rc, self.data['energy'], self.min_energy, self.max_energy)
            working_intensity = rc  # for peak energy computation
        else:
            intensity_flat = compute_intensity_map(
                self.data,
                self.min_energy,
                self.max_energy,
                self.baseline,
            )
            working_intensity = self.data['Intensity']

        x2d, y2d, z2d, idx_flat, n_x, n_y = build_grid(
            self.data["x_data"],
            self.data["y_data"],
            intensity_flat,
        )
        original_map = {
            "flat": intensity_flat,
            "X2D": x2d,
            "Y2D": y2d,
            "Z2D": z2d,
            "idx_flat": idx_flat,
            "n_x": n_x,
            "n_y": n_y,
        }
        payload["original_map"] = original_map

        transformed_map = None
        if {"intensity_transformed", "peak_transformed"} & tasks:
            self.log.emit("Computing transformed coordinate view...")
            doping2d, efield2d = compute_transformed_coords(
                original_map["X2D"],
                original_map["Y2D"],
                self.ratio,
                tg_is_y=self.tg_is_y,
            )
            transformed_map = {
                "X2D": doping2d,
                "Y2D": efield2d,
                "Z2D": original_map["Z2D"],
                "ratio": self.ratio,
            }
            payload["transformed_map"] = transformed_map

        if {"peak_original", "peak_transformed"} & tasks:
            if self.mode == "Reflection":
                self.log.emit("Computing RC peak-position map...")
                peak_flat = compute_rc_peak_position_map(
                    working_intensity,
                    self.data['energy'],
                    self.min_energy,
                    self.max_energy,
                    self.sg_window,
                    self.sg_poly,
                )
            else:
                self.log.emit("Computing peak-energy map...")
                peak_flat = compute_peak_energy(working_intensity, self.data['energy'], self.sg_window, self.sg_poly)
            z_peak = peak_flat[original_map["idx_flat"]].reshape(
                original_map["n_x"],
                original_map["n_y"],
            )
            if "peak_original" in tasks:
                payload["peak_map_original"] = {
                    "flat": peak_flat,
                    "X2D": original_map["X2D"],
                    "Y2D": original_map["Y2D"],
                    "Z2D": z_peak,
                    "target_axes": "original",
                }
            if "peak_transformed" in tasks:
                if transformed_map is None:
                    raise ValueError("Transformed coordinates were not available for the peak map.")
                payload["peak_map_transformed"] = {
                    "flat": peak_flat,
                    "X2D": transformed_map["X2D"],
                    "Y2D": transformed_map["Y2D"],
                    "Z2D": z_peak,
                    "target_axes": "transformed",
                }

        return payload


class IntensityWorker(BaseWorker):
    def __init__(self, data: dict, min_energy: float, max_energy: float, baseline: float):
        super().__init__()
        self.data = data
        self.min_energy = min_energy
        self.max_energy = max_energy
        self.baseline = baseline

    def process(self) -> dict:
        self.log.emit("Computing original intensity map...")
        intensity_flat = compute_intensity_map(
            self.data,
            self.min_energy,
            self.max_energy,
            self.baseline,
        )
        x2d, y2d, z2d, idx_flat, n_x, n_y = build_grid(
            self.data["x_data"],
            self.data["y_data"],
            intensity_flat,
        )
        return {
            "flat": intensity_flat,
            "X2D": x2d,
            "Y2D": y2d,
            "Z2D": z2d,
            "idx_flat": idx_flat,
            "n_x": n_x,
            "n_y": n_y,
        }


class TransformWorker(BaseWorker):
    def __init__(self, original_map: dict, ratio: float, tg_is_y: bool):
        super().__init__()
        self.original_map = original_map
        self.ratio = ratio
        self.tg_is_y = tg_is_y

    def process(self) -> dict:
        self.log.emit("Computing transformed coordinates...")
        doping2d, efield2d = compute_transformed_coords(
            self.original_map["X2D"],
            self.original_map["Y2D"],
            self.ratio,
            tg_is_y=self.tg_is_y,
        )
        return {
            "X2D": doping2d,
            "Y2D": efield2d,
            "Z2D": self.original_map["Z2D"],
            "ratio": self.ratio,
        }


class PeakWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        sg_window: int,
        sg_poly: int,
        original_map: dict,
        transformed_map: dict | None,
        target_axes: str,
    ):
        super().__init__()
        self.data = data
        self.sg_window = sg_window
        self.sg_poly = sg_poly
        self.original_map = original_map
        self.transformed_map = transformed_map
        self.target_axes = target_axes

    def process(self) -> dict:
        self.log.emit("Computing peak map...")
        peak_flat = compute_peak_energy_map(self.data, self.sg_window, self.sg_poly)
        z2d = peak_flat[self.original_map["idx_flat"]].reshape(
            self.original_map["n_x"], self.original_map["n_y"]
        )

        if self.target_axes == "transformed" and self.transformed_map is not None:
            x2d = self.transformed_map["X2D"]
            y2d = self.transformed_map["Y2D"]
            target = "transformed"
        else:
            x2d = self.original_map["X2D"]
            y2d = self.original_map["Y2D"]
            target = "original"

        return {
            "flat": peak_flat,
            "X2D": x2d,
            "Y2D": y2d,
            "Z2D": z2d,
            "target_axes": target,
            "idx_flat": self.original_map["idx_flat"],
            "n_x": self.original_map["n_x"],
            "n_y": self.original_map["n_y"],
        }


class LineWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        specs: list[dict],
        ratio: float,
        tg_is_y: bool = True,
        background_spectra=None,
    ):
        super().__init__()
        self.data = data
        self.specs = specs
        self.ratio = ratio
        self.tg_is_y = tg_is_y
        self.background_spectra = background_spectra

    def process(self) -> dict:
        if self.background_spectra is not None:
            self.log.emit("Computing RC spectra for line cuts...")
            working_intensity = _compute_reflection_spectra(self.data, self.background_spectra)
        else:
            working_intensity = self.data["Intensity"]

        raw_data = np.column_stack([
            self.data["x_data"], self.data["y_data"], working_intensity
        ])

        results = []
        for spec in self.specs:
            self.log.emit(
                f"Extracting {spec['cut_type']} line cut at {spec['c_value']:.4f} V "
                f"(epsilon={spec['epsilon']:.4f})..."
            )
            line_cut = extract_line_cut(
                raw_data,
                self.data["x_data"],
                self.data["y_data"],
                self.data["energy"],
                cut_type=spec["cut_type"],
                c_value=spec["c_value"],
                ratio=self.ratio,
                epsilon=spec["epsilon"],
                tg_is_y=self.tg_is_y,
            )
            results.append(line_cut)
            self.log.emit(
                f"  → {len(line_cut['axis_values'])} points selected "
                f"(actual value: {line_cut['c_value_used']:.4f} V)"
            )

        return {"line_cuts": results}


class BatchLineWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        cut_types: list[str],
        epsilon: float,
        output_dir: str,
        source_name: str,
        ratio: float,
        tg_is_y: bool = True,
        background_spectra=None,
    ):
        super().__init__()
        self.data = data
        self.cut_types = cut_types
        self.epsilon = epsilon
        self.output_dir = output_dir
        self.source_name = source_name
        self.ratio = ratio
        self.tg_is_y = tg_is_y
        self.background_spectra = background_spectra

    def process(self) -> dict:
        os.makedirs(self.output_dir, exist_ok=True)

        if self.background_spectra is not None:
            self.log.emit("Computing RC spectra for batch line cuts...")
            working_intensity = _compute_reflection_spectra(self.data, self.background_spectra)
            is_rc = True
        else:
            working_intensity = self.data["Intensity"]
            is_rc = False

        raw_data = np.column_stack([
            self.data["x_data"], self.data["y_data"], working_intensity
        ])

        saved_files: list[str] = []
        total_cuts = 0

        for cut_type in self.cut_types:
            self.log.emit(f"Finding all {cut_type} cut values...")
            cut_values = find_all_cut_values(
                self.data["x_data"],
                self.data["y_data"],
                cut_type,
                self.ratio,
                self.epsilon,
                tg_is_y=self.tg_is_y,
            )
            self.log.emit(f"Found {len(cut_values)} {cut_type} line cuts to extract.")

            for c_value in cut_values:
                line_cut = extract_line_cut(
                    raw_data,
                    self.data["x_data"],
                    self.data["y_data"],
                    self.data["energy"],
                    cut_type=cut_type,
                    c_value=c_value,
                    ratio=self.ratio,
                    epsilon=self.epsilon,
                    tg_is_y=self.tg_is_y,
                )
                if len(line_cut["axis_values"]) == 0:
                    continue

                csv_path = os.path.join(
                    self.output_dir,
                    f"{self.source_name}_{cut_type}_{c_value:+.4f}.csv",
                )
                save_line_csv(line_cut, csv_path)
                saved_files.append(csv_path)

                spectra_array = np.asarray(line_cut["spectra"])
                if spectra_array.shape[0] >= 2:
                    cmap = "RdBu_r" if is_rc else "jet"
                    z_label = "RC (ΔI/I₀)" if is_rc else "PL Intensity (a.u.)"
                    fig, _ = plot_line_cut_spectrogram(
                        line_cut,
                        title=f"{cut_type.capitalize()} = {c_value:.3f} V",
                        cmap=cmap,
                        z_label=z_label,
                    )
                    png_path = csv_path.replace(".csv", ".png")
                    save_figure(fig, png_path)
                    saved_files.append(png_path)

                total_cuts += 1

        self.log.emit(f"Batch extraction done: {total_cuts} cuts, {len(saved_files)} files saved.")
        return {"saved_files": saved_files, "total_cuts": total_cuts}
