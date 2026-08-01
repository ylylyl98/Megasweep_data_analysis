# Megasweep PL Analysis

## Overview

Megasweep PL Analysis is a Python desktop application and script workflow for analyzing megasweep photoluminescence (PL) and reflection contrast CSV data. It is intended for users who need to load sweep data, generate map views, transform gate axes into doping/efield coordinates, extract spectral line cuts, and export analysis results.

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
- Scriptable batch workflow in `megasweep_run.py`.

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
|   +-- main_window.py              # Main PySide6 window and UI workflow
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

1. Select `PL` or `Reflection` mode.
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

- Mode: `PL` or `Reflection`
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

During inspection, this command ran 11 tests successfully.

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
- `ui/main_window.py` owns the PySide6 interface, user workflow, plotting controls, export actions, and validation messages.
- `ui/workers.py` runs loading and analysis work in Qt worker objects to keep the GUI responsive.
- `ui/app_state.py` centralizes mutable application state for loaded data, generated maps, figures, line cuts, and reflection backgrounds.
- Tests currently cover axis-role validation, baseline estimation, and batch line-cut value discovery.
- The project does not include packaging metadata such as `pyproject.toml` or `setup.py`. Packaging and distribution strategy are To be confirmed.
- Dependency versions are unpinned; pinning known-good versions would make future installs more reproducible.

## License

To be confirmed.
