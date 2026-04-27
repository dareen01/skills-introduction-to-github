"""
plasma_guiding_fit.py
=====================
Non-linear curve fitting of oscilloscope waveform data to a plasma guiding
model, with automatic detection of the primary maximum (fmax) and secondary
maximum (2 fmax).

Usage (standalone):
    python plasma_guiding_fit.py --data waveform_data.csv [options]

Usage (as a module):
    from plasma_guiding_fit import fit_plasma_guiding, plot_results
    result = fit_plasma_guiding(time, voltage)
    plot_results(result)

Plasma guiding model
--------------------
The waveform is modelled as a damped sinusoid with a Gaussian envelope::

    V(t) = A * exp(-((t - t0) / sigma)^2) * sin(2π f (t - t0) + φ) + C

This captures:
  - A sharp principal peak at t0 ± 1/(2f) (fmax)
  - Decaying secondary oscillations at integer multiples (2 fmax, 3 fmax, …)
  - A DC offset C
  - A Gaussian amplitude envelope controlled by sigma

Dependencies:
    numpy, scipy, matplotlib, pandas
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit, OptimizeWarning
from scipy.signal import find_peaks

# ---- manual reference data (same as in the extractor) --------------------
from oscilloscope_waveform_extractor import MANUAL_REFERENCE_POINTS


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

def plasma_guiding_model(
    t: np.ndarray,
    A: float,
    t0: float,
    sigma: float,
    f: float,
    phi: float,
    C: float,
) -> np.ndarray:
    """Damped-Gaussian sinusoidal plasma guiding model.

    Parameters
    ----------
    t:    Time array (µs or same units as the data).
    A:    Peak amplitude (mV).
    t0:   Time of peak envelope centre (µs).
    sigma: Gaussian width (µs); controls decay rate.
    f:    Oscillation frequency (1/µs = MHz).
    phi:  Phase offset (radians).
    C:    DC offset (mV).

    Returns
    -------
    Voltage array (mV).
    """
    envelope = np.exp(-((t - t0) / sigma) ** 2)
    oscillation = np.sin(2.0 * np.pi * f * (t - t0) + phi)
    return A * envelope * oscillation + C


def _estimate_initial_params(
    t: np.ndarray, v: np.ndarray
) -> tuple[float, float, float, float, float, float]:
    """Heuristic initial parameter estimates from the data."""
    C0 = float(np.median(v))
    v_ac = v - C0

    # Peak amplitude and location
    idx_max = int(np.argmax(np.abs(v_ac)))
    A0 = float(v_ac[idx_max])
    t0_0 = float(t[idx_max])

    # Width: half-max of the envelope
    env = np.abs(v_ac)
    half = 0.5 * env.max()
    above = np.where(env > half)[0]
    sigma0 = float((t[above[-1]] - t[above[0]]) / 2.35) if len(above) > 1 else 1.0
    sigma0 = max(sigma0, 0.1)

    # Frequency: use the spacing between the two tallest peaks
    peaks_pos, _ = find_peaks(v_ac, height=0.2 * A0)
    peaks_neg, _ = find_peaks(-v_ac, height=0.2 * abs(A0))
    all_peaks = np.sort(np.concatenate([peaks_pos, peaks_neg]))
    if len(all_peaks) >= 2:
        spacings = np.diff(t[all_peaks])
        f0 = 1.0 / (2.0 * float(np.median(spacings)))
    else:
        f0 = 0.5  # fallback: 0.5 MHz

    phi0 = 0.0
    return A0, t0_0, sigma0, f0, phi0, C0


# ---------------------------------------------------------------------------
# Fit result container
# ---------------------------------------------------------------------------

@dataclass
class FitResult:
    """Container for fitting outputs."""
    t_data: np.ndarray
    v_data: np.ndarray
    t_fit: np.ndarray          # dense time grid for plotting
    v_fit: np.ndarray          # model evaluated on t_fit
    params: dict               # best-fit parameter dict
    param_errors: dict         # 1-σ uncertainties
    residuals: np.ndarray      # v_data - model(t_data)
    rmse: float
    r_squared: float
    fmax: float                # primary maximum frequency
    secondary_peaks: list[float] = field(default_factory=list)  # 2fmax, 3fmax, …
    converged: bool = True
    message: str = "OK"


# ---------------------------------------------------------------------------
# Core fitting function
# ---------------------------------------------------------------------------

def fit_plasma_guiding(
    time: np.ndarray,
    voltage: np.ndarray,
    maxfev: int = 20000,
    n_restarts: int = 5,
) -> FitResult:
    """Fit the plasma guiding model to waveform data.

    Parameters
    ----------
    time:
        1-D array of time values (µs).
    voltage:
        1-D array of voltage values (mV), same length as *time*.
    maxfev:
        Maximum number of function evaluations per optimisation run.
    n_restarts:
        Number of random restarts to avoid local minima.

    Returns
    -------
    :class:`FitResult`
    """
    t = np.asarray(time, dtype=float)
    v = np.asarray(voltage, dtype=float)

    # Sort by time
    order = np.argsort(t)
    t, v = t[order], v[order]

    p0 = _estimate_initial_params(t, v)
    A0, t0_0, sigma0, f0, phi0, C0 = p0

    # Parameter bounds:  A, t0, sigma, f, phi, C
    t_range = t.max() - t.min()
    v_range = v.max() - v.min()
    bounds = (
        [-5 * v_range, t.min(), 0.01, 0.01, -np.pi, v.min() - v_range],
        [+5 * v_range, t.max(), 10 * t_range, 100.0, np.pi, v.max() + v_range],
    )

    best_popt = None
    best_cost = np.inf
    best_pcov = None
    rng = np.random.default_rng(42)

    for i in range(n_restarts):
        if i == 0:
            p_try = list(p0)
        else:
            # Perturb initial guess
            p_try = [
                A0 * (1 + 0.3 * rng.standard_normal()),
                t0_0 + 0.1 * sigma0 * rng.standard_normal(),
                sigma0 * (1 + 0.3 * abs(rng.standard_normal())),
                f0 * (1 + 0.3 * rng.standard_normal()),
                phi0 + 0.5 * rng.standard_normal(),
                C0 * (1 + 0.1 * rng.standard_normal()),
            ]
            # Clip to bounds
            p_try = [
                float(np.clip(p_try[j], bounds[0][j], bounds[1][j]))
                for j in range(len(p_try))
            ]

        try:
            popt, pcov = curve_fit(
                plasma_guiding_model,
                t,
                v,
                p0=p_try,
                bounds=bounds,
                maxfev=maxfev,
                method="trf",
            )
        except (RuntimeError, OptimizeWarning):
            continue

        residuals = v - plasma_guiding_model(t, *popt)
        cost = float(np.sum(residuals ** 2))
        if cost < best_cost:
            best_cost = cost
            best_popt = popt
            best_pcov = pcov

    converged = best_popt is not None
    if not converged:
        # Fall back to initial estimates
        best_popt = np.array(p0, dtype=float)
        best_pcov = np.diag([1.0] * 6)
        message = "WARNING: curve_fit did not converge; showing initial estimate."
    else:
        message = "OK"

    A, t0, sigma, f, phi, C = best_popt
    try:
        perr = np.sqrt(np.diag(best_pcov))
    except Exception:
        perr = np.full(6, np.nan)

    param_names = ["A", "t0", "sigma", "f", "phi", "C"]
    params = dict(zip(param_names, best_popt.tolist()))
    param_errors = dict(zip(param_names, perr.tolist()))

    residuals = v - plasma_guiding_model(t, *best_popt)
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((v - v.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # Dense grid for smooth curve
    t_fit = np.linspace(t.min(), t.max(), 2000)
    v_fit = plasma_guiding_model(t_fit, *best_popt)

    # Identify peaks: fmax and secondary (2 fmax, 3 fmax, …)
    fmax = float(abs(f))
    secondary_peaks = _find_secondary_peaks(t_fit, v_fit, t0, sigma)

    return FitResult(
        t_data=t,
        v_data=v,
        t_fit=t_fit,
        v_fit=v_fit,
        params=params,
        param_errors=param_errors,
        residuals=residuals,
        rmse=rmse,
        r_squared=r2,
        fmax=fmax,
        secondary_peaks=secondary_peaks,
        converged=converged,
        message=message,
    )


def _find_secondary_peaks(
    t_fit: np.ndarray,
    v_fit: np.ndarray,
    t0: float,
    sigma: float,
) -> list[float]:
    """Return time positions of the secondary (post-main) peaks in the fitted curve."""
    # Only look to the right of the main peak
    mask = t_fit > t0 + 0.5 * sigma
    t_right = t_fit[mask]
    v_right = v_fit[mask]

    if len(v_right) < 5:
        return []

    v_norm = (v_right - v_right.min()) / (v_right.max() - v_right.min() + 1e-9)
    peak_idxs, props = find_peaks(v_norm, height=0.1, prominence=0.05)
    return [float(t_right[i]) for i in peak_idxs]


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_results(
    result: FitResult,
    title: str = "Plasma Guiding Model Fit",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Generate a three-panel figure: data+fit, residuals, frequency annotation.

    Parameters
    ----------
    result:
        :class:`FitResult` from :func:`fit_plasma_guiding`.
    title:
        Figure title.
    save_path:
        If given, the figure is saved to this path instead of (or in addition
        to) being displayed.

    Returns
    -------
    :class:`matplotlib.figure.Figure`
    """
    fig, axes = plt.subplots(
        2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )

    ax_main, ax_res = axes

    # ---- Main panel -------------------------------------------------------
    ax_main.scatter(
        result.t_data,
        result.v_data,
        s=15,
        color="steelblue",
        alpha=0.7,
        label="Extracted data",
        zorder=3,
    )
    ax_main.plot(
        result.t_fit,
        result.v_fit,
        "r-",
        lw=2,
        label="Plasma guiding fit",
        zorder=4,
    )

    # Mark fmax (main peak)
    t0 = result.params["t0"]
    A = result.params["A"]
    C = result.params["C"]
    peak_v = A + C
    ax_main.annotate(
        f"fmax\nt={t0:.3f} µs",
        xy=(t0, peak_v),
        xytext=(t0 + 0.3, peak_v + 5),
        fontsize=9,
        color="darkred",
        arrowprops=dict(arrowstyle="->", color="darkred"),
    )

    # Mark secondary peaks (2 fmax, …)
    for k, tp in enumerate(result.secondary_peaks, start=2):
        vp = plasma_guiding_model(np.array([tp]), **result.params)[0]
        ax_main.axvline(tp, color="orange", lw=1.2, ls="--", alpha=0.8)
        ax_main.text(
            tp,
            ax_main.get_ylim()[1] if ax_main.get_ylim()[1] != 1.0 else peak_v * 0.7,
            f"{k}fmax",
            fontsize=8,
            color="darkorange",
            rotation=90,
            va="bottom",
            ha="center",
        )

    ax_main.set_ylabel("Voltage (mV)", fontsize=11)
    ax_main.set_title(
        f"{title}\n"
        f"A={result.params['A']:.2f} mV, f={result.fmax:.4f} /µs, "
        f"σ={result.params['sigma']:.3f} µs, "
        f"RMSE={result.rmse:.2f} mV, R²={result.r_squared:.4f}",
        fontsize=10,
    )
    ax_main.legend(fontsize=10)
    ax_main.grid(True, alpha=0.3)

    # ---- Residuals panel --------------------------------------------------
    ax_res.scatter(result.t_data, result.residuals, s=8, color="gray", alpha=0.6)
    ax_res.axhline(0, color="black", lw=0.8)
    ax_res.set_xlabel("Time (µs)", fontsize=11)
    ax_res.set_ylabel("Residual (mV)", fontsize=10)
    ax_res.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"[INFO] Plot saved to: {save_path}")

    return fig


def print_fit_summary(result: FitResult) -> None:
    """Print a human-readable summary of the fit to stdout."""
    print("\n" + "=" * 60)
    print("PLASMA GUIDING MODEL FIT SUMMARY")
    print("=" * 60)
    print(f"  Converged    : {result.converged}  ({result.message})")
    print(f"  N data points: {len(result.t_data)}")
    print(f"  RMSE         : {result.rmse:.4f} mV")
    print(f"  R²           : {result.r_squared:.6f}")
    print()
    print("  Parameters (± 1σ):")
    for name, val in result.params.items():
        err = result.param_errors.get(name, float("nan"))
        unit = {"A": "mV", "t0": "µs", "sigma": "µs", "f": "/µs", "phi": "rad", "C": "mV"}.get(name, "")
        print(f"    {name:6s} = {val:+.6f}  ±  {err:.6f}  {unit}")
    print()
    print(f"  fmax (primary peak) : {result.fmax:.4f} /µs")
    if result.secondary_peaks:
        for k, tp in enumerate(result.secondary_peaks, start=2):
            print(f"  {k}·fmax position     : t = {tp:.4f} µs")
    else:
        print("  No secondary peaks identified in the fitted curve.")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fit a plasma guiding model to oscilloscope waveform data."
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--data", help="CSV file with 'time_us' and 'voltage_mv' columns.")
    group.add_argument(
        "--manual",
        action="store_true",
        help="Use the 87 manually extracted reference points embedded in the extractor.",
    )
    p.add_argument(
        "--output-plot",
        default=None,
        help="Save the result plot to this file (PNG/PDF).",
    )
    p.add_argument(
        "--output-csv",
        default=None,
        help="Save fitted curve to this CSV file.",
    )
    p.add_argument(
        "--no-plot",
        action="store_true",
        help="Do not display an interactive plot window.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.manual:
        df = pd.DataFrame(
            {
                "time_us": MANUAL_REFERENCE_POINTS["x"],
                "voltage_mv": MANUAL_REFERENCE_POINTS["y"],
            }
        )
        print(f"[INFO] Using {len(df)} manually extracted reference points.")
    else:
        if not os.path.isfile(args.data):
            print(f"[ERROR] Data file not found: {args.data}", file=sys.stderr)
            return 1
        df = pd.read_csv(args.data)
        if "time_us" not in df.columns or "voltage_mv" not in df.columns:
            print(
                "[ERROR] CSV must have 'time_us' and 'voltage_mv' columns.",
                file=sys.stderr,
            )
            return 1
        print(f"[INFO] Loaded {len(df)} data points from {args.data}")

    result = fit_plasma_guiding(df["time_us"].to_numpy(), df["voltage_mv"].to_numpy())
    print_fit_summary(result)

    if args.output_csv:
        out_df = pd.DataFrame({"time_us": result.t_fit, "voltage_mv_fit": result.v_fit})
        out_df.to_csv(args.output_csv, index=False)
        print(f"[INFO] Fitted curve saved to: {args.output_csv}")

    fig = plot_results(result, save_path=args.output_plot)
    if not args.no_plot:
        plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())
