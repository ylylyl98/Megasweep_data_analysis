"""
megasweep_analysis.py
=====================
Core library for megasweep PL data analysis.

Functions are pure (no side-effects on global state) so they can be called
from a script, notebook, or GUI without modification.

Sections
--------
1.  I/O          – load_megasweep_csv
2.  Physics      – sum_select_region, compute_peak_energy, peak_filter
3.  Grid         – build_grid
4.  Maps         – compute_intensity_map, compute_peak_energy_map
5.  Reflection   – compute_rc_spectra, compute_rc_peak_to_peak_map
6.  Transforms   – compute_transformed_coords
7.  Line cuts    – extract_line_cut
8.  Plotting     – plot_map, plot_line_cut_spectrogram
9.  Export       – save_map_csv, save_line_csv, save_figure
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import optimize
from scipy.signal import find_peaks, savgol_filter, medfilt2d


def _finite_min_max(values, label='values'):
    """Return finite min/max for plotting or raise a clear error."""
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ValueError(f"Cannot plot {label}: array contains no finite values.")
    return float(np.min(finite)), float(np.max(finite))


def _resolve_color_limits(values, vmin=None, vmax=None):
    """Return stable color limits and whether the data are effectively flat."""
    data_min, data_max = _finite_min_max(values, label='map data')
    v0 = data_min if vmin is None else float(vmin)
    v1 = data_max if vmax is None else float(vmax)

    if not np.isfinite(v0) or not np.isfinite(v1):
        raise ValueError("Color limits must be finite numbers.")

    if v0 > v1:
        v0, v1 = v1, v0

    is_flat = np.isclose(v0, v1)
    if is_flat:
        pad = max(abs(v0) * 1e-6, 1e-9)
        v0 -= pad
        v1 += pad

    return v0, v1, is_flat


def _is_rectilinear_grid(X2D, Y2D):
    """Return True when X/Y describe a standard rectangular meshgrid."""
    x_grid = np.asarray(X2D, dtype=float)
    y_grid = np.asarray(Y2D, dtype=float)
    if x_grid.ndim != 2 or y_grid.ndim != 2 or x_grid.shape != y_grid.shape:
        return False

    x_rect = np.allclose(x_grid, x_grid[:, :1], equal_nan=True)
    y_rect = np.allclose(y_grid, y_grid[:1, :], equal_nan=True)
    return bool(x_rect and y_rect)


def _split_numeric_spectral_columns(columns, excluded=None):
    """Separate numeric wavelength headers from non-spectral metadata columns."""
    excluded = set(excluded or ())
    metadata_cols = []
    spectral_cols = []
    for column in columns:
        if column in excluded:
            metadata_cols.append(column)
            continue
        try:
            float(column)
        except (TypeError, ValueError):
            metadata_cols.append(column)
        else:
            spectral_cols.append(column)
    return metadata_cols, spectral_cols


# ─────────────────────────────────────────────────────────────────────────────
# 1.  I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_megasweep_csv(csv_path, x_col=None, y_col=None):
    """
    Load a megasweep CSV file.

    Expected format
    ---------------
    Row layout  : each row is one (x, y) gate-voltage sweep point.
    Columns 0,1 : gate voltages (Vbg / Vtg or similar).
    Columns 2+  : spectral intensity values.
    Column headers for the spectral part must be numeric wavelength values
    (in nm).  The first two column headers name the gate axes.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file.
    x_col : str or None
        Override the name of the x-axis column (e.g. 'Vbg').
        If None, the first column is used.
    y_col : str or None
        Override the name of the y-axis column (e.g. 'Vtg').
        If None, the second column is used.

    Returns
    -------
    dict with keys:
        'df'         : raw pandas DataFrame
        'x_name'     : detected/override x-axis column name
        'y_name'     : detected/override y-axis column name
        'x_data'     : 1-D array of x values (shape: matrix_size)
        'y_data'     : 1-D array of y values
        'wavelength' : 1-D array of wavelength values (nm)
        'energy'     : 1-D array of photon energy values (eV)
        'Intensity'  : 2-D array, shape (matrix_size, n_wavelengths)
        'raw_data'   : numpy array of the full DataFrame
        'source_name': file stem (used in output filenames)
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    cols = list(df.columns)

    # --- axis column detection ---
    if x_col is None:
        x_col = cols[0]
    elif x_col not in cols:
        raise ValueError(f"x_col '{x_col}' not found in columns: {cols}")

    if y_col is None:
        y_col = cols[1]
    elif y_col not in cols:
        raise ValueError(f"y_col '{y_col}' not found in columns: {cols}")

    # --- spectral columns (numeric wavelength headers only) ---
    metadata_cols, spec_cols = _split_numeric_spectral_columns(cols, excluded=(x_col, y_col))
    if len(spec_cols) == 0:
        extra = f" Non-spectral columns seen: {metadata_cols[:5]}" if metadata_cols else ""
        raise ValueError(
            "No spectral columns found after removing x/y columns."
            + extra
        )

    wavelength = np.array(spec_cols, dtype=float)

    energy = 1240.0 / wavelength  # eV

    raw_data = df.values  # shape: (matrix_size, 2 + n_wavelengths) if x,y are first two cols
    # build a clean matrix with x, y, then spectra in that order
    x_data = df[x_col].values.astype(float)
    y_data = df[y_col].values.astype(float)
    Intensity = df[spec_cols].values.astype(float)  # (matrix_size, n_wl)

    source_name = os.path.splitext(os.path.basename(csv_path))[0]

    return {
        'df': df,
        'x_name': x_col,
        'y_name': y_col,
        'x_data': x_data,
        'y_data': y_data,
        'wavelength': wavelength,
        'energy': energy,
        'Intensity': Intensity,
        'raw_data': np.column_stack([x_data, y_data, Intensity]),
        'source_name': source_name,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Physics
# ─────────────────────────────────────────────────────────────────────────────

def sum_select_region(Intensity, energy, min_energy, max_energy, baseline=595):
    """
    Integrate PL intensity between min_energy and max_energy.

    Subtracts a flat background: baseline * number_of_channels_in_window.

    Parameters
    ----------
    Intensity : (N, n_wl) array
    energy    : (n_wl,) array in eV
    min_energy, max_energy : float, integration window in eV
    baseline  : float, background counts per spectral channel

    Returns
    -------
    (N,) array of integrated intensities
    """
    mask = (energy > min_energy) & (energy < max_energy)
    n_channels = np.count_nonzero(mask)
    if n_channels == 0:
        raise ValueError(
            f"No spectral channels found in energy window [{min_energy}, {max_energy}] eV. "
            f"Energy range of data: [{energy.min():.3f}, {energy.max():.3f}] eV."
        )
    result = np.nansum(Intensity[:, mask], axis=1) - baseline * n_channels
    return result


def compute_peak_energy(Intensity, energy, sg_window=25, sg_poly=1):
    """
    Find the energy of peak PL intensity for each spectrum, with
    Savitzky-Golay smoothing.

    Parameters
    ----------
    Intensity  : (N, n_wl) array
    energy     : (n_wl,) array in eV
    sg_window  : int, Savitzky-Golay window length (odd, ≤ n_wl)
    sg_poly    : int, polynomial order for SG filter

    Returns
    -------
    (N,) array of peak energies in eV
    """
    npts = Intensity.shape[1]
    # ensure odd window, capped at npts
    win = min(sg_window, npts if npts % 2 == 1 else npts - 1)
    if win < 3:
        win = 3 if npts >= 3 else npts
    if win % 2 == 0:
        win -= 1
    poly = min(sg_poly, win - 1)

    Yf = savgol_filter(Intensity, window_length=win, polyorder=poly, axis=1, mode='interp')
    Yf_safe = np.where(np.isfinite(Yf), Yf, -np.inf)
    max_idx = np.nanargmax(Yf_safe, axis=1)
    return energy[max_idx]


def peak_filter(results, minmax=(1.65, 1.75)):
    """
    Replace peak-position values outside [minmax[0], minmax[1]] with NaN.

    Parameters
    ----------
    results : (N, M) array of peak positions
    minmax  : (low, high) tuple

    Returns
    -------
    filtered array (same shape, NaN where out-of-range)
    """
    raw = np.array(results, dtype=float)
    mask = (raw < minmax[0]) | (raw > minmax[1])
    raw[mask] = np.nan
    return raw


# Two-level model (preserved from original notebook)
def twolevel_LE(x, X1, X2, p1, p2, D):
    """Lower eigenvalue of a 2-level Hamiltonian with linear coupling."""
    return (
        (X2 + X1 + p2*x - p1*x) / 2
        - np.sqrt((X2 + X1 + p2*x - p1*x)**2 - 4*(X2 + p2*x)*(X1 - p1*x) + 4*D**2) / 2
    )


def twolevel_fitting(inputX, inputY, title='2LevelFitting'):
    """Fit two-level model to data and return figure + params."""
    params, covariance = optimize.curve_fit(twolevel_LE, inputX, inputY, nan_policy='omit')
    perr = np.sqrt(np.diag(covariance))
    residual = inputY - twolevel_LE(inputX, *params)
    ss_res = np.nansum(residual**2)
    ss_tot = np.nansum((inputY - np.nanmean(inputY))**2)
    r_squared = 1 - (ss_res / ss_tot)

    fig = Figure(figsize=(6.4, 4.8))
    ax = fig.add_subplot(111)
    ax.scatter(inputX, inputY, label='Data', s=5)
    ax.plot(inputX, twolevel_LE(inputX, *params), label='2Level_LE', color='red')
    stats = (
        f'X1 = {params[0]:.4f} +/- {perr[0]:.4f}\n'
        f'X2 = {params[1]:.4f} +/- {perr[1]:.4f}\n'
        f'p1 = {params[2]:.4f} +/- {perr[2]:.4f}\n'
        f'p2 = {params[3]:.4f} +/- {perr[3]:.4f}\n'
        f'Delta = {params[4]:.4f} +/- {perr[4]:.4f}\n'
        f'R^2 = {r_squared:.4f}'
    )
    bbox = dict(boxstyle='round', fc='#99FF99', ec='orange', alpha=0.5)
    ax.text(0.02, 0.97, stats, transform=ax.transAxes, fontsize=8,
            verticalalignment='top', bbox=bbox)
    ax.legend()
    ax.set_xlabel('TG-BG (V)')
    ax.set_ylabel('Photon Energy (eV)')
    ax.set_title(title)
    return fig, params, perr


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Grid
# ─────────────────────────────────────────────────────────────────────────────

def build_grid(x_data, y_data, quantity_flat):
    """
    Sort flat (x, y, quantity) data onto a rectangular 2-D grid.

    Automatically infers grid dimensions from the number of unique
    x and y values — no hardcoding needed.

    Parameters
    ----------
    x_data        : (N,) array  – e.g. Vbg values
    y_data        : (N,) array  – e.g. Vtg values
    quantity_flat : (N,) array  – the quantity to grid (intensity, peak E, …)

    Returns
    -------
    X2D : (n_x, n_y) grid of x values
    Y2D : (n_x, n_y) grid of y values
    Z2D : (n_x, n_y) grid of the quantity
    idx_flat : sorting index (for reuse when gridding multiple quantities)
    n_x, n_y : grid dimensions
    """
    n_x = len(np.unique(x_data))
    n_y = len(np.unique(y_data))

    if n_x * n_y != len(x_data):
        # Grid is not perfectly rectangular — warn and use closest estimate
        import warnings
        warnings.warn(
            f"Data length ({len(x_data)}) ≠ n_x×n_y ({n_x}×{n_y}={n_x*n_y}). "
            "Grid may be incomplete. Results may look wrong near edges."
        )

    # Sort: primary key = x (rows), secondary key = y (cols)
    idx_flat = np.lexsort((y_data, x_data))
    X2D = x_data[idx_flat].reshape(n_x, n_y)
    Y2D = y_data[idx_flat].reshape(n_x, n_y)
    Z2D = quantity_flat[idx_flat].reshape(n_x, n_y)

    return X2D, Y2D, Z2D, idx_flat, n_x, n_y


def build_grid_multi(x_data, y_data, *quantities):
    """
    Like build_grid but grids multiple quantities with the same sort index.

    Returns (X2D, Y2D, [Z2D_q1, Z2D_q2, ...], idx_flat, n_x, n_y)
    """
    X2D, Y2D, Z0, idx_flat, n_x, n_y = build_grid(x_data, y_data, quantities[0])
    grids = [Z0]
    for q in quantities[1:]:
        grids.append(q[idx_flat].reshape(n_x, n_y))
    return X2D, Y2D, grids, idx_flat, n_x, n_y


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Maps  (compute scalar maps from Intensity matrix)
# ─────────────────────────────────────────────────────────────────────────────

def compute_intensity_map(data, min_energy, max_energy, baseline=595):
    """
    Compute integrated-intensity map from loaded data dict.

    Returns (N,) flat array ready for build_grid.
    """
    return sum_select_region(
        data['Intensity'], data['energy'],
        min_energy, max_energy, baseline
    )


def compute_peak_energy_map(data, sg_window=25, sg_poly=1):
    """
    Compute peak-energy map from loaded data dict.

    Returns (N,) flat array ready for build_grid.
    """
    return compute_peak_energy(data['Intensity'], data['energy'], sg_window, sg_poly)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Reflection Mode (RC spectra and maps)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rc_spectra(intensity: np.ndarray, background: np.ndarray) -> np.ndarray:
    """
    Compute Reflectance Contrast spectra: RC = (I - I0) / I0.

    Parameters
    ----------
    intensity  : (N, n_wl) float array — raw spectral data from megasweep
    background : (n_wl,) float array — averaged reference spectrum

    Returns
    -------
    (N, n_wl) array of RC values (can be negative)
    """
    bg = np.asarray(background, dtype=float)
    bg_safe = np.where(np.abs(bg) < 1e-12, np.nan, bg)
    return (np.asarray(intensity, dtype=float) - bg_safe) / bg_safe


def compute_rc_peak_to_peak_map(rc_spectra: np.ndarray, energy: np.ndarray,
                                 e_lo: float, e_hi: float) -> np.ndarray:
    """
    Compute RC peak-to-peak amplitude within [e_lo, e_hi] for each sweep point.

    Parameters
    ----------
    rc_spectra : (N, n_wl) array of RC = (I - I0) / I0
    energy     : (n_wl,) array in eV
    e_lo, e_hi : energy window boundaries in eV (inclusive)

    Returns
    -------
    (N,) flat array of peak-to-peak amplitudes, ready for build_grid
    """
    mask = (energy >= e_lo) & (energy <= e_hi)
    if not np.any(mask):
        raise ValueError(
            f"No energy points in RC window [{e_lo:.3f}, {e_hi:.3f}] eV. "
            f"Data energy range: [{float(energy.min()):.3f}, {float(energy.max()):.3f}] eV."
        )
    window = rc_spectra[:, mask]
    return np.nanmax(window, axis=1) - np.nanmin(window, axis=1)


def compute_rc_peak_position(energy: np.ndarray, rc_spectrum: np.ndarray,
                             e_lo: float, e_hi: float) -> tuple[float, float]:
    """
    Find the dominant RC feature position within [e_lo, e_hi].

    This follows the notebook workflow: search for a strong maximum first and,
    if none is found, fall back to a strong minimum in the selected window.
    """
    x = np.asarray(energy, dtype=float)
    y = np.asarray(rc_spectrum, dtype=float)
    finite_mask = np.isfinite(x) & np.isfinite(y)
    if not np.any(finite_mask):
        return np.nan, np.nan

    x = x[finite_mask]
    y = y[finite_mask]
    lo, hi = (e_lo, e_hi) if e_lo <= e_hi else (e_hi, e_lo)
    window_mask = (x >= lo) & (x <= hi)
    if not np.any(window_mask):
        return np.nan, np.nan

    xw = x[window_mask]
    yw = y[window_mask]
    n_points = xw.size
    if n_points < 3:
        return np.nan, np.nan

    window_length = min(n_points if n_points % 2 == 1 else n_points - 1, 21)
    window_length = max(5, window_length)
    if window_length >= n_points:
        window_length = n_points if n_points % 2 == 1 else n_points - 1
    if window_length < 3:
        return np.nan, np.nan

    yw_smooth = savgol_filter(yw, window_length=window_length, polyorder=2, mode="interp")

    def _best_feature(invert: bool = False):
        target = -yw_smooth if invert else yw_smooth
        dynamic_range = float(np.nanmax(target) - np.nanmin(target))
        prominence = max(1e-12, 0.02 * dynamic_range)
        peaks, _ = find_peaks(target, prominence=prominence)
        if peaks.size == 0:
            peaks, _ = find_peaks(target, prominence=max(1e-12, 0.005 * dynamic_range))
            if peaks.size == 0:
                return None

        if invert:
            candidate_index = peaks[np.argmin(yw_smooth[peaks])]
        else:
            candidate_index = peaks[np.argmax(yw_smooth[peaks])]

        if 0 < candidate_index < len(yw_smooth) - 1:
            y0, y1, y2 = yw_smooth[candidate_index - 1], yw_smooth[candidate_index], yw_smooth[candidate_index + 1]
            denom = (y0 - 2 * y1 + y2)
            if denom != 0:
                dx = 0.5 * (y0 - y2) / denom
                x_refined = xw[candidate_index] + dx * (xw[candidate_index + 1] - xw[candidate_index - 1]) / 2.0
                nearest_index = int(np.argmin(np.abs(xw - x_refined)))
                return float(xw[nearest_index]), float(yw[nearest_index])
        return float(xw[candidate_index]), float(yw[candidate_index])

    result = _best_feature(invert=False)
    if result is not None:
        return result

    result = _best_feature(invert=True)
    if result is not None:
        return result

    return np.nan, np.nan


def compute_rc_peak_position_map(rc_spectra: np.ndarray, energy: np.ndarray,
                                 e_lo: float, e_hi: float) -> np.ndarray:
    """Compute the dominant RC feature position for each sweep point."""
    rc_matrix = np.asarray(rc_spectra, dtype=float)
    positions = np.full(rc_matrix.shape[0], np.nan, dtype=float)
    for index, spectrum in enumerate(rc_matrix):
        positions[index], _ = compute_rc_peak_position(energy, spectrum, e_lo, e_hi)
    return positions


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Transforms
# ─────────────────────────────────────────────────────────────────────────────

def compute_transformed_coords(X2D, Y2D, ratio, tg_is_y=True):
    """
    Compute Efield / Doping from original gate grids.

    Convention:
        Doping = TG + ratio * BG
        Efield = TG - ratio * BG

    Parameters
    ----------
    X2D, Y2D : 2-D grids from build_grid (rows = x_col, cols = y_col)
    ratio    : float, lever-arm ratio (notebook used 0.9)
    tg_is_y  : bool
        True  → TG = Y2D (second column), BG = X2D (first column)
        False → TG = X2D, BG = Y2D

    Returns
    -------
    Doping2D, Efield2D : same shape as X2D/Y2D
    """
    if tg_is_y:
        TG, BG = Y2D, X2D
    else:
        TG, BG = X2D, Y2D

    Doping = TG + ratio * BG
    Efield = TG - ratio * BG
    return Doping, Efield


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Line cuts
# ─────────────────────────────────────────────────────────────────────────────

def extract_line_cut(raw_data, x_data, y_data, energy,
                     cut_type='doping', c_value=0.0,
                     ratio=0.9, epsilon=0.03,
                     tg_is_y=True):
    """
    Extract a line cut at constant Doping or constant Efield.

    Parameters
    ----------
    raw_data  : (N, 2+n_wl) array  [x, y, spectrum…]
    x_data, y_data : (N,) arrays
    energy    : (n_wl,) array in eV
    cut_type  : 'doping' or 'efield'
    c_value   : float, the constant value to cut along
    ratio     : float, lever-arm ratio
    epsilon   : float, tolerance window around c_value
    tg_is_y   : bool, if True TG=y_data, BG=x_data; else reversed

    Returns
    -------
    dict with keys:
        'axis_values'   : (n_sel,) values along the varying axis
        'axis_label'    : str label for the varying axis
        'spectra'       : (n_sel, n_wl) spectral intensity
        'energy'        : (n_wl,) energy array
        'x_sel'         : (n_sel,) x values of selected points
        'y_sel'         : (n_sel,) y values of selected points
        'cut_type'      : 'doping' or 'efield'
        'c_value_used'  : actual c_value that was matched
    """
    if tg_is_y:
        TG, BG = y_data, x_data
    else:
        TG, BG = x_data, y_data

    doping_flat = TG + ratio * BG
    efield_flat = TG - ratio * BG

    if cut_type == 'doping':
        line_values = doping_flat      # the constant axis
        vary_values = efield_flat      # the varying axis
        vary_label = f'Efield = TG - {ratio}·BG (V)'
    elif cut_type == 'efield':
        line_values = efield_flat
        vary_values = doping_flat
        vary_label = f'Doping = TG + {ratio}·BG (V)'
    else:
        raise ValueError("cut_type must be 'doping' or 'efield'")

    # find points within epsilon of c_value
    dist = np.abs(line_values - c_value)
    mask = dist <= epsilon

    if not np.any(mask):
        # snap to nearest achievable value
        nearest_idx = np.argmin(dist)
        c_actual = line_values[nearest_idx]
        import warnings
        warnings.warn(
            f"No points within epsilon={epsilon} of {cut_type}={c_value:.4f}. "
            f"Snapping to nearest: {c_actual:.4f}"
        )
        mask = np.abs(line_values - c_actual) <= 1e-10
    else:
        c_actual = c_value

    # de-duplicate: for each unique vary_value bucket keep closest point
    sel_idx = np.where(mask)[0]
    unique_vary = np.unique(np.round(vary_values[sel_idx], 6))
    keep = []
    for uv in unique_vary:
        candidates = sel_idx[np.argmin(dist[sel_idx])]  # fallback
        bucket = sel_idx[np.abs(vary_values[sel_idx] - uv) < 1e-6]
        if len(bucket) > 0:
            keep.append(bucket[np.argmin(dist[bucket])])
    keep = np.array(keep, dtype=int)

    # sort by vary_values
    order = np.argsort(vary_values[keep])
    keep = keep[order]

    spectra = raw_data[keep, 2:]
    axis_values = vary_values[keep]

    return {
        'axis_values': axis_values,
        'axis_label': vary_label,
        'spectra': spectra,
        'energy': energy,
        'x_sel': x_data[keep],
        'y_sel': y_data[keep],
        'cut_type': cut_type,
        'c_value_used': c_actual,
        'ratio': ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8.  Plotting
# ─────────────────────────────────────────────────────────────────────────────

def find_all_cut_values(x_data, y_data, cut_type, ratio, epsilon, min_points=2, tg_is_y=True):
    """
    Find representative constant-axis values for batch line-cut extraction.

    Parameters
    ----------
    x_data, y_data : (N,) arrays
    cut_type       : 'doping' or 'efield'
    ratio          : float, lever-arm ratio
    epsilon        : float, half-width tolerance used by extract_line_cut
    min_points     : int, minimum points required to keep a cut
    tg_is_y        : bool, if True TG=y_data and BG=x_data

    Returns
    -------
    list of float
        Sorted representative cut centers suitable for extract_line_cut().
    """
    if epsilon <= 0:
        raise ValueError("epsilon must be positive.")
    if min_points < 1:
        raise ValueError("min_points must be at least 1.")

    x_vals = np.asarray(x_data, dtype=float)
    y_vals = np.asarray(y_data, dtype=float)
    if x_vals.size == 0 or y_vals.size == 0:
        return []

    if tg_is_y:
        TG, BG = y_vals, x_vals
    else:
        TG, BG = x_vals, y_vals

    if cut_type == 'doping':
        line_values = TG + ratio * BG
    elif cut_type == 'efield':
        line_values = TG - ratio * BG
    else:
        raise ValueError("cut_type must be 'doping' or 'efield'")

    finite_values = np.sort(line_values[np.isfinite(line_values)])
    if finite_values.size == 0:
        return []

    clusters = []
    current_cluster = [float(finite_values[0])]
    current_center = float(finite_values[0])
    gap_threshold = 2.0 * float(epsilon)

    for value in finite_values[1:]:
        value = float(value)
        if value - current_center > gap_threshold:
            clusters.append(current_cluster)
            current_cluster = [value]
        else:
            current_cluster.append(value)
        current_center = float(np.mean(current_cluster))
    clusters.append(current_cluster)

    cut_values = []
    for cluster in clusters:
        c_value = float(np.mean(cluster))
        count = int(np.count_nonzero(np.abs(line_values - c_value) <= epsilon))
        if count >= min_points:
            cut_values.append(c_value)

    return sorted(cut_values)


def plot_map(X2D, Y2D, Z2D,
             x_label='x', y_label='y', z_label='quantity',
             title='', cmap='jet', n_levels=200,
             vmin=None, vmax=None,
             figsize=(6, 4.8)):
    """
    Plot a 2-D map as a filled-contour plot.

    Returns
    -------
    fig, ax
    """
    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    v0, v1, is_flat = _resolve_color_limits(Z2D, vmin=vmin, vmax=vmax)

    if _is_rectilinear_grid(X2D, Y2D) and not is_flat:
        levels = np.linspace(v0, v1, n_levels)
        artist = ax.contourf(X2D, Y2D, Z2D, levels=levels, cmap=cmap, vmin=v0, vmax=v1)
    else:
        artist = ax.pcolormesh(X2D, Y2D, Z2D, cmap=cmap, shading='auto', vmin=v0, vmax=v1)

    fig.colorbar(artist, ax=ax, label=z_label)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return fig, ax


def plot_line_cut_spectrogram(line_cut: dict,
                               title: str = '',
                               cmap: str = 'RdBu_r',
                               z_label: str = 'Intensity',
                               figsize: tuple = (7, 4.8),
                               vmin=None, vmax=None) -> tuple:
    """
    Plot a line-cut spectrogram (energy vs. axis value, colour = intensity).

    Parameters
    ----------
    line_cut : dict returned by extract_line_cut
    title    : figure title
    cmap     : matplotlib colormap name
    z_label  : colorbar label
    figsize  : figure size tuple
    vmin, vmax : optional color limits

    Returns
    -------
    fig, ax
    """
    energy = np.asarray(line_cut['energy'], dtype=float)
    axis_values = np.asarray(line_cut['axis_values'], dtype=float)
    spectra = np.asarray(line_cut['spectra'], dtype=float)

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)

    v0, v1, _ = _resolve_color_limits(spectra, vmin=vmin, vmax=vmax)

    E_grid, Y_grid = np.meshgrid(energy, axis_values)
    artist = ax.pcolormesh(E_grid, Y_grid, spectra,
                           cmap=cmap, shading='auto',
                           vmin=v0, vmax=v1)
    fig.colorbar(artist, ax=ax, label=z_label)
    ax.set_xlabel('Energy (eV)')
    ax.set_ylabel(line_cut.get('axis_label', 'Axis'))
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return fig, ax


# ─────────────────────────────────────────────────────────────────────────────
# 9.  Export
# ─────────────────────────────────────────────────────────────────────────────

def save_map_csv(X2D, Y2D, Z2D, path,
                 x_name='x', y_name='y', z_name='z') -> None:
    """Save a 2-D map as a three-column CSV (flattened)."""
    x_flat = np.asarray(X2D, dtype=float).ravel()
    y_flat = np.asarray(Y2D, dtype=float).ravel()
    z_flat = np.asarray(Z2D, dtype=float).ravel()
    df = pd.DataFrame({x_name: x_flat, y_name: y_flat, z_name: z_flat})
    df.to_csv(path, index=False)


def save_line_csv(line_cut: dict, path: str) -> None:
    """Save a line-cut result as a CSV with energy columns."""
    energy = np.asarray(line_cut['energy'], dtype=float)
    axis_values = np.asarray(line_cut['axis_values'], dtype=float)
    spectra = np.asarray(line_cut['spectra'], dtype=float)
    axis_label = line_cut.get('axis_label', 'axis').split(' ')[0]

    # header: axis_value, then each energy as column header
    col_headers = [axis_label] + [f'{e:.6f}' for e in energy]
    data_rows = np.column_stack([axis_values, spectra])
    df = pd.DataFrame(data_rows, columns=col_headers)
    df.to_csv(path, index=False)


def save_figure(fig, path: str, dpi: int = 300) -> None:
    """Save a matplotlib Figure to *path* (PNG, PDF, SVG, …)."""
    fig.savefig(path, dpi=dpi, bbox_inches='tight', transparent=True)