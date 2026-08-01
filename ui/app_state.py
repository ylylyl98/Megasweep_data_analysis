from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    csv_path: str = ""
    output_dir: str = ""  # User-selected base; exports use the full CSV-stem folder.
    header_columns: list[str] = field(default_factory=list)
    gate_columns: list[str] = field(default_factory=list)
    selected_x_col: str = ""
    selected_y_col: str = ""
    selected_tg_col: str = ""
    selected_bg_col: str = ""
    row_count: int = 0
    spectral_channel_count: int = 0
    energy_range: tuple[float, float] | None = None
    unique_x_count: int = 0
    unique_y_count: int = 0
    current_ratio: float = 1.0
    transform_convention: str = "TG+rBG"  # "TG+rBG": D=TG+r·BG  |  "rTG+BG": D=r·TG+BG

    data: dict[str, Any] | None = None

    intensity_settings: dict[str, float] | None = None
    original_map: dict[str, Any] | None = None
    transformed_map: dict[str, Any] | None = None

    peak_settings: dict[str, Any] | None = None
    peak_map_original: dict[str, Any] | None = None
    peak_map_transformed: dict[str, Any] | None = None
    rc_fixed_map_original: dict[str, Any] | None = None
    rc_fixed_map_transformed: dict[str, Any] | None = None
    ibias_map_original: dict[str, Any] | None = None
    ibias_map_transformed: dict[str, Any] | None = None
    resistance_map_original: dict[str, Any] | None = None
    resistance_map_transformed: dict[str, Any] | None = None

    line_cut_specs: list[dict[str, Any]] = field(default_factory=list)
    line_cut_results: list[dict[str, Any]] = field(default_factory=list)

    figures: dict[str, Any] = field(default_factory=dict)

    mode: str = "PL"
    background_spectra: Any | None = None
    background_wavelength: Any | None = None
    background_path: str = ""
    background_paths: list[str] = field(default_factory=list)
    background_average_mode: str = "all_frames"
    background_scale_factor: float | None = None
    background_scale_info: dict[str, Any] | None = None
    background_scale_frame_index: int | None = None

    def reset_from_stage(self, stage_number: int) -> None:
        if stage_number <= 1:
            self.data = None
            self.row_count = 0
            self.spectral_channel_count = 0
            self.energy_range = None
            self.unique_x_count = 0
            self.unique_y_count = 0
            self.background_scale_factor = None
            self.background_scale_info = None
            self.background_scale_frame_index = None

        if stage_number <= 2:
            self.intensity_settings = None
            self.original_map = None
            self.transformed_map = None
            self.peak_settings = None
            self.peak_map_original = None
            self.peak_map_transformed = None
            self.rc_fixed_map_original = None
            self.rc_fixed_map_transformed = None
            self.ibias_map_original = None
            self.ibias_map_transformed = None
            self.resistance_map_original = None
            self.resistance_map_transformed = None
            self.line_cut_specs = []
            self.line_cut_results = []
            self.figures.pop("original_map", None)
            self.figures.pop("transformed_map", None)
            self.figures.pop("peak_map_original", None)
            self.figures.pop("peak_map_transformed", None)
            self.figures.pop("fixed_map_original", None)
            self.figures.pop("fixed_map_transformed", None)
            self.figures.pop("ibias_map_original", None)
            self.figures.pop("ibias_map_transformed", None)
            self.figures.pop("resistance_map_original", None)
            self.figures.pop("resistance_map_transformed", None)
            self.figures.pop("raw_background", None)
            self.figures.pop("line_cuts", None)
            return

        if stage_number <= 3:
            self.transformed_map = None
            self.peak_map_transformed = None
            self.rc_fixed_map_transformed = None
            self.ibias_map_transformed = None
            self.resistance_map_transformed = None
            self.line_cut_specs = []
            self.line_cut_results = []
            self.figures.pop("transformed_map", None)
            self.figures.pop("peak_map_transformed", None)
            self.figures.pop("fixed_map_transformed", None)
            self.figures.pop("ibias_map_transformed", None)
            self.figures.pop("resistance_map_transformed", None)
            self.figures.pop("line_cuts", None)
            return

        if stage_number <= 4:
            self.peak_settings = None
            self.peak_map_original = None
            self.peak_map_transformed = None
            self.figures.pop("peak_map_original", None)
            self.figures.pop("peak_map_transformed", None)
            return

        if stage_number <= 5:
            self.line_cut_specs = []
            self.line_cut_results = []
            self.figures.pop("line_cuts", None)
            return
