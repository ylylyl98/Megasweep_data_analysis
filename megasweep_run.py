"""
megasweep_run.py
================
Main workflow script for megasweep PL analysis.

HOW TO USE
----------
1. Edit the CONFIG block below.
2. Run:  python megasweep_run.py

All outputs go into OUTPUT_DIR, organised in sub-folders.

WHERE TO EDIT
─────────────
  CSV_PATH          → path to your megasweep CSV file
  X_COL / Y_COL     → column names for x/y axes (None = auto-detect from first two columns)
  TG_IS_Y           → True  if TG = second column (y), BG = first column (x)  [default]
                      False if TG = first column (x), BG = second column (y)
  RATIO             → lever-arm ratio for Efield/Doping transform (notebook used 0.9)
  INT_MIN / INT_MAX → energy integration window for intensity map (eV)
  BASELINE          → flat background counts per spectral channel for intensity map
  PEAK_SG_WINDOW    → Savitzky-Golay window for peak-energy smoothing
  OUTPUT_DIR        → root folder for all saved outputs
  LINE_CUTS         → list of line-cut specs (see format below)
"""

import os
import sys

# Add the app folder to path so megasweep_analysis can be imported
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import matplotlib
matplotlib.use('Agg')   # non-interactive backend (change to 'TkAgg' if you want pop-up windows)
import matplotlib.pyplot as plt

from megasweep_analysis import (
    load_megasweep_csv,
    compute_intensity_map,
    compute_peak_energy_map,
    build_grid,
    compute_transformed_coords,
    extract_line_cut,
    plot_map,
    plot_line_cut_spectrogram,
    save_figure,
    save_map_csv,
    save_line_csv,
)


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG  ←  Edit this block
# ═══════════════════════════════════════════════════════════════════════════

# --- Input ---
CSV_PATH = r'./megasweep/$YZD303$~$pen1$~$0T1.688K$~$PL660nm0.447uw1500msx1c932nm$~.csv'

# Column selection
# Set to None to auto-detect from the first two columns of the CSV
X_COL = None   # e.g. 'Vbg'  or  None
Y_COL = None   # e.g. 'Vtg'  or  None

# If you need to manually specify which column is TG and which is BG, edit here:
# TG_IS_Y = True  means: TG = Y_COL (second column), BG = X_COL (first column)
TG_IS_Y = True

# --- Transformed-axis ratio ---
# Doping = TG + RATIO * BG
# Efield  = TG - RATIO * BG
RATIO = 0.9

# --- Intensity map energy window (eV) ---
INT_MIN    = 1.25     # lower bound of integration window
INT_MAX    = 1.425    # upper bound of integration window
BASELINE   = 595      # background counts per spectral channel

# --- Peak-energy map smoothing ---
PEAK_SG_WINDOW = 25   # Savitzky-Golay window (odd integer, ≤ number of spectral points)
PEAK_SG_POLY   = 1    # Savitzky-Golay polynomial order

# --- Output ---
OUTPUT_DIR = './megasweep_output'

# --- Line cuts ---
# Each entry is a dict with:
#   cut_type : 'doping' or 'efield'
#   c_value  : float, the constant value to cut at
#   epsilon  : float, tolerance window around c_value (V)
#
LINE_CUTS = [
    {'cut_type': 'doping', 'c_value':  0.0, 'epsilon': 0.03},
    {'cut_type': 'doping', 'c_value': -5.0, 'epsilon': 0.03},
    {'cut_type': 'efield', 'c_value':  0.0, 'epsilon': 0.03},
]

# ═══════════════════════════════════════════════════════════════════════════
#  END CONFIG
# ═══════════════════════════════════════════════════════════════════════════


def make_output_dirs(base):
    dirs = {
        'orig':  os.path.join(base, 'original_axes_maps'),
        'trans': os.path.join(base, 'transformed_axes_maps'),
        'lines': os.path.join(base, 'extracted_lines'),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def run():
    print("=" * 60)
    print("Megasweep analysis")
    print("=" * 60)

    # ── 1. Load data ──────────────────────────────────────────────
    print(f"\n[1/5] Loading CSV: {CSV_PATH}")
    data = load_megasweep_csv(CSV_PATH, x_col=X_COL, y_col=Y_COL)
    src  = data['source_name']
    x_name = data['x_name']
    y_name = data['y_name']
    print(f"      x-axis : {x_name}  ({len(np.unique(data['x_data']))} unique values)")
    print(f"      y-axis : {y_name}  ({len(np.unique(data['y_data']))} unique values)")
    print(f"      spectra: {data['Intensity'].shape[0]} points × {data['Intensity'].shape[1]} channels")
    print(f"      energy : {data['energy'].min():.3f} – {data['energy'].max():.3f} eV")

    dirs = make_output_dirs(OUTPUT_DIR)

    # ── 2. Compute scalar maps ────────────────────────────────────
    print(f"\n[2/5] Computing maps")
    print(f"      Intensity sum  [{INT_MIN}, {INT_MAX}] eV, baseline={BASELINE}")
    intensity_flat = compute_intensity_map(data, INT_MIN, INT_MAX, BASELINE)

    print(f"      Peak energy  (SG window={PEAK_SG_WINDOW})")
    peak_e_flat = compute_peak_energy_map(data, PEAK_SG_WINDOW, PEAK_SG_POLY)

    # ── 3. Original-axis maps ─────────────────────────────────────
    print(f"\n[3/5] Original-axis maps  ({x_name} × {y_name})")

    maps_orig = {}
    for qty_name, qty_flat in [('intensity', intensity_flat), ('peak_energy', peak_e_flat)]:
        X2D, Y2D, Z2D, idx_flat, n_x, n_y = build_grid(
            data['x_data'], data['y_data'], qty_flat
        )
        maps_orig[qty_name] = (X2D, Y2D, Z2D)

        z_labels = {'intensity': 'Integrated PL (a.u.)', 'peak_energy': 'Peak energy (eV)'}
        z_label = z_labels[qty_name]
        title   = f'{qty_name}  |  {src}'

        fig, _ = plot_map(X2D, Y2D, Z2D,
                          x_label=f'{x_name} (V)', y_label=f'{y_name} (V)',
                          z_label=z_label, title=title)
        png_path = os.path.join(dirs['orig'], f'{src}_{qty_name}_original.png')
        csv_path = os.path.join(dirs['orig'], f'{src}_{qty_name}_original.csv')
        save_figure(fig, png_path)
        save_map_csv(X2D, Y2D, Z2D, csv_path,
                     x_name=x_name, y_name=y_name, z_name=qty_name)

    # ── 4. Transformed-axis maps ──────────────────────────────────
    print(f"\n[4/5] Transformed-axis maps  (Doping × Efield, ratio={RATIO})")

    # Use the grid from the last build_grid call (both quantities share the same x/y grid)
    X2D, Y2D, _ = maps_orig['intensity']
    Doping2D, Efield2D = compute_transformed_coords(X2D, Y2D, RATIO, tg_is_y=TG_IS_Y)

    for qty_name in ('intensity', 'peak_energy'):
        _, _, Z2D = maps_orig[qty_name]
        z_labels = {'intensity': 'Integrated PL (a.u.)', 'peak_energy': 'Peak energy (eV)'}
        z_label = z_labels[qty_name]
        title   = f'{qty_name} (transformed)  |  {src}'

        fig, _ = plot_map(Doping2D, Efield2D, Z2D,
                          x_label='Doping (V)', y_label='Efield (V)',
                          z_label=z_label, title=title)
        png_path = os.path.join(dirs['trans'], f'{src}_{qty_name}_transformed.png')
        csv_path = os.path.join(dirs['trans'], f'{src}_{qty_name}_transformed.csv')
        save_figure(fig, png_path)
        save_map_csv(Doping2D, Efield2D, Z2D, csv_path,
                     x_name='Doping_V', y_name='Efield_V', z_name=qty_name)

    # ── 5. Line cuts ──────────────────────────────────────────────
    print(f"\n[5/5] Line cuts  ({len(LINE_CUTS)} cuts)")

    raw_data = data['raw_data']
    x_data   = data['x_data']
    y_data   = data['y_data']
    energy   = data['energy']

    for lc_spec in LINE_CUTS:
        cut_type = lc_spec['cut_type']
        c_value  = lc_spec['c_value']
        epsilon  = lc_spec.get('epsilon', 0.03)

        print(f"      {cut_type} = {c_value:.3f}  (epsilon={epsilon})")

        lc = extract_line_cut(
            raw_data, x_data, y_data, energy,
            cut_type=cut_type, c_value=c_value,
            ratio=RATIO, epsilon=epsilon,
            tg_is_y=TG_IS_Y,
        )

        if lc['spectra'].shape[0] == 0:
            print(f"        WARNING: no points found – skipping")
            continue

        c_str = f'{lc["c_value_used"]:.3f}'.replace('.', 'p').replace('-', 'm')
        stem  = f'{src}_{cut_type}{c_str}'

        fig, _ = plot_line_cut_spectrogram(lc)
        png_path = os.path.join(dirs['lines'], f'{stem}.png')
        csv_path = os.path.join(dirs['lines'], f'{stem}.csv')
        save_figure(fig, png_path)
        save_line_csv(lc, csv_path)

    print(f"\nDone.  All outputs in: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 60)


if __name__ == '__main__':
    run()
