from __future__ import annotations

import os
import traceback

import numpy as np
from PySide6.QtCore import QObject, Signal

from megasweep_analysis import (
    build_map_payload,
    compute_intensity_map,
    compute_peak_energy_map,
    compute_peak_energy,
    compute_rc_at_energy_map,
    compute_rc_spectra,
    compute_rc_peak_position_map,
    compute_rc_peak_to_peak_map,
    compute_transformed_coords,
    extract_line_cut,
    find_all_cut_values,
    load_megasweep_csv,
    load_spectral_csv,
    plot_line_cut_spectrogram,
    save_figure,
    save_line_csv,
    spectral_axes_match,
)


def _compute_reflection_spectra(
    data: dict,
    background_spectra,
    background_scale: float = 1.0,
) -> np.ndarray:
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
    return compute_rc_spectra(
        intensity,
        background,
        background_scale=background_scale,
    )


def _build_transformed_map_payload(
    data: dict,
    quantity_flat,
    ratio: float,
    tg_is_y: bool,
    convention: str,
) -> dict:
    """Preserve the original sweep-cell topology in transformed coordinates."""
    payload = build_map_payload(
        data["x_data"],
        data["y_data"],
        quantity_flat,
    )
    axis1_flat, axis2_flat = compute_transformed_coords(
        data["x_data"],
        data["y_data"],
        ratio,
        tg_is_y=tg_is_y,
        convention=convention,
    )
    payload["x_flat"] = np.asarray(axis1_flat, dtype=float)[
        payload["idx_flat"]
    ]
    payload["y_flat"] = np.asarray(axis2_flat, dtype=float)[
        payload["idx_flat"]
    ]

    if np.asarray(payload["X2D"]).ndim == 2:
        axis1_grid, axis2_grid = compute_transformed_coords(
            payload["X2D"],
            payload["Y2D"],
            ratio,
            tg_is_y=tg_is_y,
            convention=convention,
        )
        payload["X2D"] = axis1_grid
        payload["Y2D"] = axis2_grid
    else:
        payload["X2D"] = payload["x_flat"]
        payload["Y2D"] = payload["y_flat"]
    return payload


class BaseWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    log = Signal(str)
    progress = Signal(int, int)   # (current, total)

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
        average_mode: str = "all_frames",
        expected_wavelength=None,
    ):
        super().__init__()
        self.csv_paths = list(csv_paths)
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
            # Background metadata often differs from the primary sweep. Only
            # its numeric wavelength channels and spectra are relevant.
            data = load_spectral_csv(csv_path)
            wavelength = np.asarray(data["wavelength"], dtype=float)
            energy = np.asarray(data["energy"], dtype=float)

            if reference_wavelength is None:
                reference_wavelength = wavelength
                reference_energy = energy
                if self.expected_wavelength is not None:
                    if not spectral_axes_match(wavelength, self.expected_wavelength):
                        raise ValueError(
                            "Background spectral channels do not match the loaded megasweep data. "
                            f"Background has {wavelength.size} channels spanning "
                            f"{wavelength.min():.4f}-{wavelength.max():.4f} nm; primary data has "
                            f"{self.expected_wavelength.size} channels spanning "
                            f"{self.expected_wavelength.min():.4f}-{self.expected_wavelength.max():.4f} nm."
                        )
            elif not spectral_axes_match(wavelength, reference_wavelength):
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
        convention: str = "TG+rBG",
        fixed_energy: float | None = None,
        background_scale: float = 1.0,
        rc_feature_mode: str = "auto",
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
        self.convention = convention
        self.fixed_energy = fixed_energy
        self.background_scale = background_scale
        self.rc_feature_mode = rc_feature_mode

    def process(self) -> dict:
        tasks = set(self.tasks)
        payload: dict[str, dict] = {}

        if not tasks:
            return payload

        self.log.emit("Refreshing map analysis...")

        ibias_tasks = {"ibias_original", "ibias_transformed"} & tasks
        if ibias_tasks:
            ibias_values = self.data.get("ibias_data")
            ibias_name = self.data.get("ibias_name")
            if ibias_values is None or not ibias_name:
                raise ValueError(
                    "No measured Ibias column was found. Expected a column such "
                    "as 'Ibias_A', 'Ibias_meas', or 'Ibias'."
                )
            ibias_values = np.asarray(ibias_values, dtype=float).reshape(-1)
            if ibias_values.size != np.asarray(self.data["x_data"]).size:
                raise ValueError(
                    "The measured Ibias column does not match the number of sweep rows."
                )
            if not np.any(np.isfinite(ibias_values)):
                raise ValueError("The measured Ibias column contains no finite values.")

            self.log.emit(f"Building Ibias map from column '{ibias_name}'...")
            if "ibias_original" in tasks:
                ibias_original = build_map_payload(
                    self.data["x_data"],
                    self.data["y_data"],
                    ibias_values,
                )
                ibias_original["target_axes"] = "original"
                ibias_original["source_column"] = ibias_name
                payload["ibias_map_original"] = ibias_original

            if "ibias_transformed" in tasks:
                axis_space = self.data.get("axis_space", "gate")
                if axis_space == "transformed":
                    ibias_transformed = build_map_payload(
                        self.data["x_data"],
                        self.data["y_data"],
                        ibias_values,
                    )
                elif axis_space == "gate":
                    ibias_transformed = _build_transformed_map_payload(
                        self.data,
                        ibias_values,
                        self.ratio,
                        self.tg_is_y,
                        self.convention,
                    )
                else:
                    raise ValueError(
                        "D/E transformed views require BG/TG gate axes or loaded "
                        "Doping/Efield axes. Use the Original view for this sweep."
                    )
                ibias_transformed["target_axes"] = "transformed"
                ibias_transformed["source_column"] = ibias_name
                ibias_transformed["ratio"] = self.ratio
                ibias_transformed["convention"] = self.convention
                payload["ibias_map_transformed"] = ibias_transformed

        resistance_tasks = {"resistance_original", "resistance_transformed"} & tasks
        if resistance_tasks:
            ibias_values = self.data.get("ibias_data")
            vbias_values = self.data.get("vbias_data")
            ibias_name = self.data.get("ibias_name")
            vbias_name = self.data.get("vbias_name")
            if ibias_values is None or not ibias_name:
                raise ValueError(
                    "Resistance requires a measured Ibias column such as "
                    "'Ibias_A', 'Ibias_meas', or 'Ibias'."
                )
            if vbias_values is None or not vbias_name:
                raise ValueError(
                    "Resistance requires Vbias. Expected a measured column such "
                    "as 'Vbias_meas', or a selected Vbias sweep axis."
                )

            ibias_values = np.asarray(ibias_values, dtype=float).reshape(-1)
            vbias_values = np.asarray(vbias_values, dtype=float).reshape(-1)
            row_count = np.asarray(self.data["x_data"]).size
            if ibias_values.size != row_count or vbias_values.size != row_count:
                raise ValueError(
                    "The Vbias/Ibias columns do not match the number of sweep rows."
                )

            valid = (
                np.isfinite(vbias_values)
                & np.isfinite(ibias_values)
                & (ibias_values != 0.0)
            )
            resistance_values = np.full(row_count, np.nan, dtype=float)
            np.divide(
                vbias_values,
                ibias_values,
                out=resistance_values,
                where=valid,
            )
            finite_resistance = np.isfinite(resistance_values)
            if not np.any(finite_resistance):
                raise ValueError(
                    "Resistance could not be calculated: all Vbias/Ibias rows "
                    "are invalid or have zero current."
                )
            invalid_count = int(row_count - np.count_nonzero(finite_resistance))
            self.log.emit(
                f"Building resistance map as {vbias_name} / {ibias_name}"
                + (
                    f"; {invalid_count} zero-current or invalid row(s) are blank."
                    if invalid_count
                    else "."
                )
            )

            if "resistance_original" in tasks:
                resistance_original = build_map_payload(
                    self.data["x_data"],
                    self.data["y_data"],
                    resistance_values,
                )
                resistance_original["target_axes"] = "original"
                resistance_original["vbias_column"] = vbias_name
                resistance_original["ibias_column"] = ibias_name
                payload["resistance_map_original"] = resistance_original

            if "resistance_transformed" in tasks:
                axis_space = self.data.get("axis_space", "gate")
                if axis_space == "transformed":
                    resistance_transformed = build_map_payload(
                        self.data["x_data"],
                        self.data["y_data"],
                        resistance_values,
                    )
                elif axis_space == "gate":
                    resistance_transformed = _build_transformed_map_payload(
                        self.data,
                        resistance_values,
                        self.ratio,
                        self.tg_is_y,
                        self.convention,
                    )
                else:
                    raise ValueError(
                        "D/E transformed views require BG/TG gate axes or loaded "
                        "Doping/Efield axes. Use the Original view for this sweep."
                    )
                resistance_transformed["target_axes"] = "transformed"
                resistance_transformed["vbias_column"] = vbias_name
                resistance_transformed["ibias_column"] = ibias_name
                resistance_transformed["ratio"] = self.ratio
                resistance_transformed["convention"] = self.convention
                payload["resistance_map_transformed"] = resistance_transformed

        spectral_tasks = tasks - {
            "ibias_original",
            "ibias_transformed",
            "resistance_original",
            "resistance_transformed",
        }
        if not spectral_tasks:
            return payload

        # Determine effective intensity matrix and map values based on mode
        if self.mode == "Reflection":
            self.log.emit("Computing RC spectra from the loaded background...")
            rc = _compute_reflection_spectra(
                self.data,
                self.background_spectra,
                self.background_scale,
            )
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

        original_map = build_map_payload(
            self.data["x_data"],
            self.data["y_data"],
            intensity_flat,
        )
        if {"intensity_original", "intensity_transformed", "peak_original", "peak_transformed"} & tasks:
            payload["original_map"] = original_map

        transformed_map = None
        if {"intensity_transformed", "peak_transformed", "fixed_transformed"} & tasks:
            axis_space = self.data.get("axis_space", "gate")
            if axis_space == "transformed":
                self.log.emit("Loaded axes are already transformed; reusing them for transformed view...")
                transformed_map = dict(original_map)
                transformed_map["already_transformed"] = True
            elif axis_space == "gate":
                self.log.emit("Computing transformed coordinate view...")
                transformed_map = _build_transformed_map_payload(
                    self.data,
                    intensity_flat,
                    self.ratio,
                    self.tg_is_y,
                    self.convention,
                )
            else:
                raise ValueError(
                    "D/E transformed views require BG/TG gate axes or loaded "
                    "Doping/Efield axes. Use the Original view for this sweep."
                )
            transformed_map["ratio"] = self.ratio
            transformed_map["convention"] = self.convention
            if "intensity_transformed" in tasks:
                payload["transformed_map"] = transformed_map

        if {"fixed_original", "fixed_transformed"} & tasks:
            if self.mode != "Reflection":
                raise ValueError("Fixed-energy RC maps are available only in Reflection mode.")
            if self.fixed_energy is None:
                raise ValueError("Choose a fixed energy before generating an RC-at-energy map.")
            self.log.emit(f"Interpolating RC at {self.fixed_energy:.6f} eV...")
            fixed_flat = compute_rc_at_energy_map(
                working_intensity,
                self.data["energy"],
                self.fixed_energy,
            )
            if "fixed_original" in tasks:
                fixed_original = build_map_payload(
                    self.data["x_data"],
                    self.data["y_data"],
                    fixed_flat,
                )
                fixed_original["target_axes"] = "original"
                fixed_original["fixed_energy"] = self.fixed_energy
                payload["fixed_map_original"] = fixed_original
            if "fixed_transformed" in tasks:
                if transformed_map is None:
                    raise ValueError("Transformed coordinates were not available for the fixed-energy map.")
                if self.data.get("axis_space", "gate") == "transformed":
                    fixed_transformed = build_map_payload(
                        self.data["x_data"],
                        self.data["y_data"],
                        fixed_flat,
                    )
                else:
                    fixed_transformed = _build_transformed_map_payload(
                        self.data,
                        fixed_flat,
                        self.ratio,
                        self.tg_is_y,
                        self.convention,
                    )
                fixed_transformed["target_axes"] = "transformed"
                fixed_transformed["fixed_energy"] = self.fixed_energy
                fixed_transformed["ratio"] = self.ratio
                fixed_transformed["convention"] = self.convention
                payload["fixed_map_transformed"] = fixed_transformed

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
                    feature_mode=self.rc_feature_mode,
                )
            else:
                self.log.emit("Computing peak-energy map...")
                peak_flat = compute_peak_energy(working_intensity, self.data['energy'], self.sg_window, self.sg_poly)
            if "peak_original" in tasks:
                peak_original = build_map_payload(
                    self.data["x_data"],
                    self.data["y_data"],
                    peak_flat,
                )
                peak_original["target_axes"] = "original"
                payload["peak_map_original"] = peak_original
            if "peak_transformed" in tasks:
                if transformed_map is None:
                    raise ValueError("Transformed coordinates were not available for the peak map.")
                axis_space = self.data.get("axis_space", "gate")
                if axis_space == "transformed":
                    peak_transformed = build_map_payload(
                        self.data["x_data"],
                        self.data["y_data"],
                        peak_flat,
                    )
                else:
                    peak_transformed = _build_transformed_map_payload(
                        self.data,
                        peak_flat,
                        self.ratio,
                        self.tg_is_y,
                        self.convention,
                    )
                peak_transformed["target_axes"] = "transformed"
                peak_transformed["ratio"] = self.ratio
                peak_transformed["convention"] = self.convention
                payload["peak_map_transformed"] = peak_transformed

        if self.mode == "Reflection":
            for map_data in payload.values():
                if isinstance(map_data, dict) and "Z2D" in map_data:
                    map_data["background_scale"] = float(self.background_scale)
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
        return build_map_payload(
            self.data["x_data"],
            self.data["y_data"],
            intensity_flat,
        )


class TransformWorker(BaseWorker):
    def __init__(self, original_map: dict, ratio: float, tg_is_y: bool, convention: str = "TG+rBG"):
        super().__init__()
        self.original_map = original_map
        self.ratio = ratio
        self.tg_is_y = tg_is_y
        self.convention = convention

    def process(self) -> dict:
        self.log.emit("Computing transformed coordinates...")
        axis1, axis2 = compute_transformed_coords(
            self.original_map["x_flat"],
            self.original_map["y_flat"],
            self.ratio,
            tg_is_y=self.tg_is_y,
            convention=self.convention,
        )
        payload = build_map_payload(axis1, axis2, self.original_map["z_flat"])
        payload["ratio"] = self.ratio
        payload["convention"] = self.convention
        return payload


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
        if self.target_axes == "transformed" and self.transformed_map is not None:
            payload = build_map_payload(
                self.transformed_map["x_flat"],
                self.transformed_map["y_flat"],
                peak_flat[self.transformed_map["idx_flat"]],
            )
            target = "transformed"
        else:
            payload = build_map_payload(
                self.original_map["x_flat"],
                self.original_map["y_flat"],
                peak_flat[self.original_map["idx_flat"]],
            )
            target = "original"

        payload["target_axes"] = target
        return payload


class LineWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        specs: list[dict],
        ratio: float,
        tg_is_y: bool = True,
        background_spectra=None,
        convention: str = "TG+rBG",
        background_scale: float = 1.0,
    ):
        super().__init__()
        self.data = data
        self.specs = specs
        self.ratio = ratio
        self.tg_is_y = tg_is_y
        self.background_spectra = background_spectra
        self.convention = convention
        self.background_scale = background_scale

    def process(self) -> dict:
        if self.background_spectra is not None:
            self.log.emit("Computing RC spectra for line cuts...")
            working_intensity = _compute_reflection_spectra(
                self.data,
                self.background_spectra,
                self.background_scale,
            )
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
                convention=self.convention,
                axis_space=self.data.get("axis_space", "gate"),
                x_axis_name=self.data.get("x_name", ""),
                y_axis_name=self.data.get("y_name", ""),
            )
            n_pts = len(line_cut['axis_values'])
            if n_pts == 0:
                self.log.emit(
                    f"  → 0 points found within epsilon={spec['epsilon']:.4f} V — "
                    f"no data returned for this cut"
                )
            else:
                results.append(line_cut)
                self.log.emit(f"  → {n_pts} points selected")

        return {"line_cuts": results}


class BatchLineWorker(BaseWorker):
    def __init__(
        self,
        data: dict,
        cut_types: list[str],
        epsilon: float,
        output_dir: str,
        ratio: float,
        tg_is_y: bool = True,
        background_spectra=None,
        convention: str = "TG+rBG",
        background_scale: float = 1.0,
    ):
        super().__init__()
        self.data = data
        self.cut_types = cut_types
        self.epsilon = epsilon
        self.output_dir = output_dir
        self.ratio = ratio
        self.tg_is_y = tg_is_y
        self.background_spectra = background_spectra
        self.convention = convention
        self.background_scale = background_scale

    def process(self) -> dict:
        os.makedirs(self.output_dir, exist_ok=True)

        if self.background_spectra is not None:
            self.log.emit("Computing RC spectra for batch line cuts...")
            working_intensity = _compute_reflection_spectra(
                self.data,
                self.background_spectra,
                self.background_scale,
            )
            is_rc = True
        else:
            working_intensity = self.data["Intensity"]
            is_rc = False

        raw_data = np.column_stack([
            self.data["x_data"], self.data["y_data"], working_intensity
        ])

        saved_files: list[str] = []
        total_cuts = 0

        _subfolder = {"doping": "doping_fixed", "efield": "efield_fixed"}

        # Build per-cut-type work lists and compute global y ranges in one scan
        cut_type_values: dict[str, list[float]] = {}
        for cut_type in self.cut_types:
            self.log.emit(f"Finding all {cut_type} cut values...")
            cut_values = find_all_cut_values(
                self.data["x_data"],
                self.data["y_data"],
                cut_type,
                self.ratio,
                self.epsilon,
                tg_is_y=self.tg_is_y,
                convention=self.convention,
                axis_space=self.data.get("axis_space", "gate"),
                x_axis_name=self.data.get("x_name", ""),
                y_axis_name=self.data.get("y_name", ""),
            )
            self.log.emit(f"Found {len(cut_values)} {cut_type} line cuts to extract.")
            cut_type_values[cut_type] = cut_values

        # Pass 1 — scan axis_values across every cut to get the global y range per type
        global_ylim: dict[str, tuple[float, float]] = {}
        for cut_type, cut_values in cut_type_values.items():
            y_min, y_max = float("inf"), float("-inf")
            for c_value in cut_values:
                lc = extract_line_cut(
                    raw_data,
                    self.data["x_data"],
                    self.data["y_data"],
                    self.data["energy"],
                    cut_type=cut_type,
                    c_value=c_value,
                    ratio=self.ratio,
                    epsilon=self.epsilon,
                    tg_is_y=self.tg_is_y,
                    convention=self.convention,
                    axis_space=self.data.get("axis_space", "gate"),
                    x_axis_name=self.data.get("x_name", ""),
                    y_axis_name=self.data.get("y_name", ""),
                )
                av = lc["axis_values"]
                if len(av):
                    y_min = min(y_min, float(np.min(av)))
                    y_max = max(y_max, float(np.max(av)))
            if y_min < y_max:
                global_ylim[cut_type] = (y_min, y_max)
                self.log.emit(f"  {cut_type} y range: [{y_min:.3f}, {y_max:.3f}]")

        # Pass 2 — extract, save CSV, and plot using the shared y range
        work_items: list[tuple[str, float]] = [
            (ct, cv) for ct, cvs in cut_type_values.items() for cv in cvs
        ]
        total_work = len(work_items)
        self.progress.emit(0, total_work)

        for done, (cut_type, c_value) in enumerate(work_items, start=1):
            subfolder = os.path.join(self.output_dir, _subfolder.get(cut_type, cut_type))
            os.makedirs(subfolder, exist_ok=True)

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
                convention=self.convention,
                axis_space=self.data.get("axis_space", "gate"),
                x_axis_name=self.data.get("x_name", ""),
                y_axis_name=self.data.get("y_name", ""),
            )

            self.progress.emit(done, total_work)

            if len(line_cut["axis_values"]) == 0:
                continue

            # Use 'n'/'p' prefix instead of '+'/'-' — '+' is invalid in Windows filenames
            sign = "n" if c_value < 0 else "p"
            stem = f"{cut_type}_{sign}{abs(c_value):.4f}"
            csv_path = os.path.join(subfolder, f"{stem}.csv")
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
                    ylim=global_ylim.get(cut_type),
                )
                png_path = os.path.join(subfolder, f"{stem}.png")
                save_figure(fig, png_path)
                saved_files.append(png_path)

            total_cuts += 1

        self.log.emit(f"Batch extraction done: {total_cuts} cuts, {len(saved_files)} files saved.")
        return {"saved_files": saved_files, "total_cuts": total_cuts}
