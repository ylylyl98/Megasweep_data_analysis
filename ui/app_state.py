from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    csv_path: str = ""
    output_dir: str = ""
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

    data: dict[str, Any] | None = None

    intensity_settings: dict[str, float] | None = None
    original_map: dict[str, Any] | None = None
    transformed_map: dict[str, Any] | None = None

    peak_settings: dict[str, Any] | None = None
    peak_map_original: dict[str, Any] | None = None
    peak_map_transformed: dict[str, Any] | None = None

    line_cut_specs: list[dict[str, Any]] = field(default_factory=list)
    line_cut_results: list[dict[str, Any]] = field(default_factory=list)

    figures: dict[str, Any] = field(default_factory=dict)

    mode: str = "PL"
    background_spectra: Any | None = None
    background_wavelength: Any | None = None
    background_path: str = ""
    background_paths: list[str] = field(default_factory=list)
    background_average_mode: str = "all_frames"

    def reset_from_stage(self, stage_number: int) -> None:
        if stage_number <= 1:
            self.data = None
            self.row_count = 0
            self.spectral_channel_count = 0
            self.energy_range = None
            self.unique_x_count = 0
            self.unique_y_count = 0

        if stage_number <= 2:
            self.intensity_settings = None
            self.original_map = None
            self.transformed_map = None
            self.peak_settings = None
            self.peak_map_original = None
            self.peak_map_transformed = None
            self.line_cut_specs = []
            self.line_cut_results = []
            self.figures.pop("original_map", None)
            self.figures.pop("transformed_map", None)
            self.figures.pop("peak_map_original", None)
            self.figures.pop("peak_map_transformed", None)
            self.figures.pop("line_cuts", None)
            return

        if stage_number <= 3:
            self.transformed_map = None
            self.peak_map_transformed = None
            self.line_cut_specs = []
            self.line_cut_results = []
            self.figures.pop("transformed_map", None)
            self.figures.pop("peak_map_transformed", None)
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