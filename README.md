# Megasweep Analysis

## Overview

Megasweep Analysis is a Python desktop application for analyzing megasweep photoluminescence (PL), reflection contrast, and scalar transport CSV data. It supports map views, spectral or scalar line cuts, and result exports. The optical workflow also transforms gate axes into doping/efield coordinates.

## Spectral slices (PL and Reflection)

Both optical workspaces use **Spectral Slices** for optical slices, including
D/E slices. It replaces the old optical Line Cuts sidebar section and tab;
Transport keeps its separate one-dimensional Line Cut view.
Choose **Follow map** (default), **Original X/Y**, or
**Transformed D/E**, then choose the fixed axis and a measured value.
**Extract Slice** displays energy horizontally and the other sweep coordinate
vertically. Color shows raw PL intensity, or RC using the current background
and background scale. Reflection requires a matching background; PL does not.

Typed fixed values snap to the nearest available coordinate. Original X/Y cuts
use the selected column names and units; zero tolerance selects the exact
setpoint, without a voltage-specific noise floor. D/E slices use the existing
gate transformation, also selecting actual coordinates with the entered tolerance.
Saved legacy line-cut recipes remain readable. At least two distinct varying-axis
points are required for a 2D spectral slice. A transformed map refresh is not
required before extracting from loaded spectra.

**Preview Counts**, **All fixed X**, **All fixed Y**, and **All Both** support
batch export (X/Y refer to the selected coordinate system). **Save CSV/PNG**
exports the displayed slice. Outputs go under the dataset results folder in
`spectral_slices/pl` or `spectral_slices/reflection`; existing exports are
preserved. Original-axis CSVs retain the full varying-axis label and a fixed
coordinate column. Slice controls are remembered per CSV and workspace; click
Extract Slice to regenerate the preview after reloading.

The fixed-value field names the actual coordinate being held constant.
**Display range** provides independent **Auto / Min / Max** for X (energy in eV)
and Y (the varying sweep coordinate). **Color scale** provides **Auto / V min /
V max** in the plotted signal's units. Scientific notation is accepted. Valid
changes update the preview and **Save PNG** immediately, without re-extraction;
invalid ranges retain the previous display. CSV exports retain every extracted
point, and batch plots use their full ranges. View settings are remembered with
the file; changing axes resets coordinate limits, and changing signal processing
resets color limits.

**Signal processing → Second derivative vs energy (d²/dE²)** differentiates PL
intensity or the background-normalized RC. **Derivative window (points)** selects
an odd number of energy channels (at least 3). Each channel uses a local cubic
least-squares fit on the actual energy coordinates (quadratic for 3 points), so
nonuniform and descending energy axes are supported. Larger windows smooth more
strongly; the endpoints use one-sided windows. The source spectra are preserved.
Single and batch derivative exports use a `_d2dE2_wN` filename suffix, and CSVs
record processing, window size, and signal units.

## Transport CSVs

Open the **Transport** tab and load a CSV. The optional second row
contains units, and a matching `<csv_stem>_metadata.json` is read when available.
No optical spectrum or reflection background is required.

1. Review the **suggested axes** and choose **Signal** from the actual numeric CSV
   headers. There is no hardcoded Doping/Vds/Ids_X default. Unit labels appear beside
   column names. All-empty columns are excluded; pass/direction are separate filters.
2. Select a direction and/or pass if needed, then click **Refresh Plot**. Snake
   scans are arranged by their coordinate values. Duplicate coordinate pairs
   require different coordinates or a pass/direction filter; they are never averaged.
3. In **Line Cut**, choose the fixed coordinate column and one of its measured
   values, then click **Plot Cut**. Either map coordinate can be fixed.
4. Use **Save Map/Cut PNG/CSV**. CSV exports contain the selected measured rows
   with all original columns, including pass/direction; the units row is omitted
   so exported values remain directly readable as numbers. PNG maps use the
   existing 3 × 3 inch inner-map export layout.

Axis suggestions first validate metadata `axis_fast` / `axis_slow` against the
available numeric columns. Valid `plot_x_resolved` or `plot_x_axis` determines
orientation; otherwise the slow axis goes on X. Metadata can retain the intended
two-dimensional coordinates even while only the first scan line has been measured.
Without usable metadata, the app excludes recognized signal/readback/recording
columns and constants, then looks for independent grid coordinates. Multiple
plausible grids (including equivalent gate representations) remain unselected.
The reason is shown above the selectors; **Use Suggested Axes** reapplies it.
Saved valid manual coordinates take priority when reloading a file.

One varying non-signal coordinate suggests **1D curve**. In this mode **X column**
is the scan variable and **Signal** is the vertical axis; no second coordinate is
required. Curves retain acquisition order and separate recorded passes/directions.
Use **Save Curve PNG/CSV** to export. The **Plot** selector can be changed manually
between 2D map and 1D curve. Signal selection is always explicit or restored from
saved settings; axis inference does not silently select a measurement channel.

Missing measurements remain blank, including the planned scan range when valid
metadata matches the selected headers. Missing interior cut points break the
plotted line. A stopped or still-running acquisition can be loaded; **Load CSV**
reads a fresh snapshot when more points have been acquired. There is no automatic
polling. A partial trailing CSV row is ignored with a warning.

Color limits accept scientific notation (for example `-2e-9` to `2e-9`) in the
selected channel's units. **Display range** provides independent X/Y **Auto**,
**Min**, and **Max** controls for maps/curves, and separately for line cuts.
Uncheck Auto and enter finite Min < Max; Enter or leaving the field applies the
view immediately. For curves, Y is the signal amplitude. Recheck Auto to recover
the full plotted extent. Scientific notation is accepted. Invalid limits keep
the previous valid view. PNG exports use the visible range; CSV keeps all selected
measurements. Ranges are restored with the file recipe and reset when coordinate,
signal, or plot-kind selections change.

Column choices, filters, color settings, display ranges, map and cut
recipes are remembered per CSV and workspace and restored on loading. Source files are never
modified. Transport displays recorded channels directly; no AC calibration,
resistance, or differential-conductance conversion is applied implicitly.

## Independent workspaces

App exports preserve existing files across all three tabs, including batch line
cuts. PNG exports use the base filename first, then `_002`, `_003`, and so on.
CSV exports compare their exact serialized content (including headers and row
order) with the base file and its numbered versions: identical content is reused
without rewriting, while changed content creates a new numbered file. Changing
only display limits or colors therefore creates new PNGs without duplicate CSVs.
The log reports the actual saved path or that an unchanged CSV was skipped.
The plot toolbar's Save button follows the same non-overwriting image rule,
including when a filename is chosen manually.

The top-level **PL**, **Reflection**, and **Transport** tabs each own their file
selection, sidebar, plots, analysis state and background worker. Switching tabs
keeps all loaded data and displayed results. The same CSV can be analyzed in PL
and Reflection with different saved settings. Compatible recipes from the older
single-mode UI are read as a fallback; new recipes are stored separately by mode.
Closing waits for active analysis work in any tab.

The bottom **Log** button expands processing messages; errors reveal the log
automatically. **Advanced Settings** groups optical coordinate transforms and
peak smoothing. Transport folds the Data section after loading, aligns its
header selectors, and hides map-only controls when **1D curve** is selected.
Plots adjust their margins when the window is resized.
Related sidebar values share rows (energy bounds, smoothing parameters,
preview coordinates and Transport axes). Numeric fields retain their native
preferred width and wrap together with their labels when space is limited.
Mouse wheels scroll panels and lists without changing numeric fields or combo
selections, even when an editor has focus. Use typing, arrow keys or clicks to
change parameters.

`ui/main_window.py` is the tab shell. `ui/measurement_workspace.py` coordinates
each independent workspace; `ui/optical_layout.py` builds its optical controls,
`ui/reflection_workflow.py` handles reflection previews/background processing,
and `ui/plot_results.py` handles optical plot results. Shared canvas/Qt controls
and styles live in `ui/widgets.py` and `ui/styles.py`. Transport analysis and
controls are in `transport_analysis.py` and `ui/transport.py`.

## Main Features

- PySide6 desktop GUI launched from `main.py`.
- Windows launcher (`Megasweep Analysis.bat`) that creates a local `.venv`, installs requirements, creates an icon-enabled shortcut, and starts the GUI without a second console taskbar button.
- Megasweep CSV loading with selectable X/Y sweep-axis columns.
- Axis-role validation for raw gate axes (`X=BG/Vbg`, `Y=TG/Vtg`) and transformed axes (`X=doping`, `Y=efield`).
- Integrated PL intensity maps over a configurable energy window.
- Automatic global baseline estimation for PL intensity maps.
- Peak-energy maps using Savitzky-Golay smoothing.
- Reflection mode with one or more background CSV files, averaged background spectra, RC spectra (`(I - I0) / I0`), RC peak-to-peak maps, fixed-energy RC maps, and RC peak-position maps.
- Coordinate transforms between raw gate axes and doping/efield axes using configurable lever-arm ratio and transform convention.
- Interactive Matplotlib map previews with colormap and color-scale controls.
- Constant-doping and constant-efield line-cut extraction.
- Batch line-cut extraction with preview counts and output subfolders.
- PNG and CSV exports for maps and line-cut results.
- Per-dataset output routing under the full CSV-stem folder, with concise result filenames to avoid repeating the long measurement name.
- Per-CSV analysis memory: parameters, background files, and previously generated views are saved locally and restored when that CSV is loaded again.
- Scriptable batch workflow in `megasweep_run.py`.

## Remembering an analysis

Map controls are grouped into view/refresh, color scale, and X/Y range rows;
groups wrap when the window is narrow. Each axis has an independent Auto toggle
and manual Min/Max. Range changes only adjust the view (Min must be below Max),
and Original/Transformed views remember separate ranges for each CSV. PNG export
uses the visible range; CSV export keeps the complete measured data. Colormap
and color-scale edits update the current plot immediately without recalculation.

Map refreshes reuse valid numerical results when only display settings change.
Peak positions are also reused when changing the coordinate transform or ratio;
only the map grid is rebuilt. Changes to the data, reference spectrum, or relevant
peak-analysis parameters invalidate the cached result. These numerical caches
last for the current process; reopening a saved analysis recalculates its views.

After loading a CSV, changes to analysis settings are saved automatically (also
when switching datasets or closing the app). Loading the same CSV restores its
PL/Reflection mode, X/Y columns, background files and averaging mode, energy and
background-scale windows, smoothing, coordinate transform, map colors/limits,
preview coordinates, and line-cut specifications. Previously generated maps,
RC previews, and individual line cuts are recalculated automatically after the
background has been loaded and validated. Exports and batch export operations
are not repeated.

Each absolute CSV path has its own configuration. On Windows the JSON files
live in `%LOCALAPPDATA%\MegasweepAnalysis\sessions`; the source CSVs are never
modified. Renaming or moving a CSV starts a separate configuration. Missing or
incompatible backgrounds stop automatic reconstruction with a message in the
Log; the saved parameters remain available. Settings from sessions before this
feature was installed cannot be recovered: configure the dataset once after
restarting the updated app.

## Project Structure

```text
.
+-- main.py                         # GUI entry point
+-- megasweep_analysis.py           # Core analysis, plotting, transform, and export functions
+-- megasweep_run.py                # Editable script workflow for batch-style analysis
+-- Megasweep Analysis.bat          # Windows launcher and environment bootstrapper
+-- Create_Megasweep_Shortcut.ps1   # Generates the icon-enabled Windows shortcut
+-- assets/
|   +-- megasweep.ico               # Window, taskbar, and shortcut icon
+-- requirements.txt                # Python package dependencies
+-- ui/
|   +-- __init__.py
|   +-- app_state.py                # GUI state container
|   +-- main_window.py              # Top-level PL / Reflection / Transport tab shell
|   +-- workers.py                  # Background worker classes for GUI tasks
+-- tests/
    +-- __init__.py
    +-- test_axis_role_validation.py
    +-- test_baseline_estimation.py
    +-- test_batch_linecut_values.py
```

## Requirements

- Python 3.10 or newer. The code uses modern type-hint syntax such as `QThread | None`.
- Python packages listed in `requirements.txt`:
  - `PySide6`
  - `numpy`
  - `pandas`
  - `matplotlib`
  - `Pillow`
  - `scipy`
- A megasweep CSV file with selectable sweep-axis columns and numeric spectral column headers.
- For Reflection mode: one or more matching background CSV files with the same spectral channels as the primary data.

Package versions are not pinned in this repository. Exact supported versions are To be confirmed.

## Installation

### Option 1: Windows Launcher

From the project folder, run:

```bat
Megasweep Analysis.bat
```

The launcher:

1. Checks that `main.py` and `requirements.txt` exist.
2. Creates `.venv` if it does not already exist.
3. Upgrades `pip`.
4. Installs packages from `requirements.txt`.
5. Creates `Megasweep Analysis.lnk` with the application icon.
6. Starts the GUI through `pythonw.exe`, avoiding a second console taskbar button.

The generated shortcut can be copied elsewhere or pinned to the taskbar. To
create an additional desktop shortcut, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Create_Megasweep_Shortcut.ps1 -Desktop
```

### Option 2: Manual Setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

On non-Windows systems, create and activate a Python virtual environment using the standard commands for your shell. Cross-platform support is To be confirmed.

## Usage

### GUI Workflow

Start the desktop app:

```powershell
python main.py
```

Basic workflow:

1. Open the `PL` or `Reflection` tab (use the workflow above for `Transport`).
2. Choose a primary megasweep CSV file.
3. Select the X/Y sweep-axis columns.
4. Click `Load CSV`.
5. Configure the six-decimal energy window, optional fixed RC energy, baseline, ratio, transform convention, and Savitzky-Golay settings.
6. In Reflection mode, select one or more background CSV files and click `Load Background`.
7. Use `Refresh Current View` or `Refresh All Maps` to generate map views.
8. Configure line cuts and click `Extract Line Cuts`, or use batch extraction for all doping/efield cuts.
9. Export generated maps and line cuts as PNG or CSV files.

The GUI writes uncaught crash details to `megasweep_crash.log` in the project folder.

### Script Workflow

`megasweep_run.py` provides an editable script workflow. Update the `CONFIG` block near the top of the file, then run:

```powershell
python megasweep_run.py
```

The script loads a configured CSV file, computes intensity and peak-energy maps, generates transformed-axis maps, extracts configured line cuts, and writes outputs under `OUTPUT_DIR`.

## Configuration

No environment variables or external config files were found.

GUI settings are controlled through the application sidebar:

- Workspace: `PL`, `Reflection`, or `Transport`, with independent controls
- Input CSV and output base directory; each CSV writes to its full CSV-stem dataset folder
- X/Y sweep-axis columns
- Energy integration window
- Fixed photon energy for interpolated `RC at Energy` maps
- RC feature-position selection: automatic, local peak, or local dip
- Measured `Ibias` maps on original or transformed axes
- Resistance maps calculated as `R = Vbias / Ibias`, with measured Vbias preferred
- PL baseline or automatic baseline estimation
- Lever-arm ratio
- Transform convention:
  - `D = TG + r*BG`, `E = TG - r*BG`
  - `D = r*TG + BG`, `E = r*TG - BG`
- Savitzky-Golay window and polynomial order
- Reflection background averaging mode:
  - average all frames
  - average first frame per CSV
  - average last frame per CSV
- Reflection-only `Raw / Background` tab overlays the selected unnormalized
  raw spectrum and averaged background against their matched wavelength channels
- Optional global background scaling estimated robustly from feature-free
  energy windows on the left and right sides of the RC feature
- Map type, axes, colormap, and optional color limits
- Skipped sweep points render as masked full-size cells without interpolation
- Fixed export-only inner map size: `3 × 3 in` at 300 DPI
- Manual and batch line-cut settings

Script settings in `megasweep_run.py` include:

- `CSV_PATH`
- `X_COL` / `Y_COL`
- `TG_IS_Y`
- `RATIO`
- `INT_MIN` / `INT_MAX`
- `BASELINE`
- `PEAK_SG_WINDOW` / `PEAK_SG_POLY`
- `OUTPUT_DIR`
- `LINE_CUTS`

## Input and Output

### Input CSV Format

The core loader expects:

- One row per sweep point.
- Two selected sweep-axis columns, usually raw gate columns such as `Vbg` and `Vtg`, or transformed columns such as `doping` and `efield`.
- Numeric spectral column headers representing wavelengths in nm.
- Spectral intensity values in the numeric wavelength columns.

Photon energy is computed internally as:

```text
energy_eV = 1240 / wavelength_nm
```

Map generation requires the selected X/Y axes to form a rectangular sweep grid. If the data do not form a rectangular grid, the application reports an error and asks the user to choose the true sweep axes or preprocess the data.

### Generated Outputs

The GUI saves outputs to the selected output directory. If no output directory is set, it creates one next to the input CSV using the pattern:

```text
<csv_stem>_outputs
```

Generated files can include:

- Map PNG files.
- Map CSV files with flattened `x`, `y`, and `z` columns.
- Line-cut PNG files.
- Line-cut CSV files with the line axis followed by energy columns.
- Batch line-cut subfolders such as `doping_fixed` and `efield_fixed`.

`megasweep_run.py` writes outputs under `OUTPUT_DIR`, including:

- `original_axes_maps/`
- `transformed_axes_maps/`
- `extracted_lines/`

## Testing

The repository includes `unittest` tests under `tests/`.

Run all tests:

```powershell
python -B -m unittest discover -s tests
```

The current regression suite covers optical analysis, Transport, and independent workspace/session behavior.

## Troubleshooting

- `Python was not found on PATH`: install Python 3 and ensure `py` or `python` is available from the terminal.
- `No spectral columns found`: confirm that spectral columns have numeric wavelength headers and that the selected X/Y columns are not spectral columns.
- Axis selection warning or error: raw gate sweeps should use `X=BG/Vbg` and `Y=TG/Vtg`; transformed-axis files should use `X=doping` and `Y=efield`.
- Rectangular grid error: the selected X/Y columns do not form a complete rectangular sweep grid. Choose the true sweep axes or preprocess the CSV.
- No energy points in window: adjust `E min` and `E max` so they fall inside the data energy range.
- Reflection background mismatch: reload background CSV files with the same wavelength/spectral channel headers as the primary CSV.
- PySide6 import or Qt startup failure: reinstall dependencies inside the active virtual environment with `python -m pip install -r requirements.txt`.
- GUI crash: check `megasweep_crash.log` in the project folder.

## Development Notes

- `megasweep_analysis.py` is the core library and keeps most computational functions independent of GUI state.
- `ui/main_window.py` owns the top-level workspace tabs and coordinated closing. Workspace state, UI builders, reflection handling and plot callbacks are split into the modules described above.
- `ui/workers.py` runs loading and analysis work in Qt worker objects to keep the GUI responsive.
- `ui/app_state.py` centralizes mutable application state for loaded data, generated maps, figures, line cuts, and reflection backgrounds.
- Tests currently cover axis-role validation, baseline estimation, and batch line-cut value discovery.
- The project does not include packaging metadata such as `pyproject.toml` or `setup.py`. Packaging and distribution strategy are To be confirmed.
- Dependency versions are unpinned; pinning known-good versions would make future installs more reproducible.

## License

To be confirmed.
