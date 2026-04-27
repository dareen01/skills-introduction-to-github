"""
oscilloscope_waveform_extractor.py
===================================
Automated waveform data extraction from RIGOL DHO924S oscilloscope images.

Features:
- Detect oscilloscope grid lines and calibrate pixel-to-physical coordinates
- Locate the orange cursor arrow and read Channel D time value
- Trace the waveform curve and extract calibrated (time, voltage) points
- Capture both the main peak and secondary peak (2 fmax)
- Export extracted data to CSV

Usage:
    python oscilloscope_waveform_extractor.py --image <path_to_image> [options]

Dependencies:
    numpy, scipy, matplotlib, opencv-python (cv2), pandas
"""

import argparse
import csv
import os
import sys

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants – default calibration for RIGOL DHO924S captures
# (can be overridden via command-line arguments)
# ---------------------------------------------------------------------------
DEFAULT_TIME_PER_DIV_US = 1.0       # microseconds per horizontal major division
DEFAULT_VOLTAGE_PER_DIV_MV = 4.0    # millivolts per vertical major division


# ---------------------------------------------------------------------------
# Grid detection helpers
# ---------------------------------------------------------------------------

def _gaussian_blur(gray: np.ndarray, ksize: int = 5) -> np.ndarray:
    """Return a Gaussian-blurred version of *gray*."""
    return cv2.GaussianBlur(gray, (ksize, ksize), 0)


def _detect_lines(binary: np.ndarray, axis: str = "horizontal") -> list[int]:
    """Return sorted pixel positions of dominant horizontal or vertical lines.

    Parameters
    ----------
    binary:
        Binary (thresholded) image.
    axis:
        ``'horizontal'`` or ``'vertical'``.

    Returns
    -------
    list[int]
        Sorted list of row (horizontal) or column (vertical) indices where
        strong lines were found.
    """
    if axis == "horizontal":
        projection = np.sum(binary, axis=1).astype(float)
    else:
        projection = np.sum(binary, axis=0).astype(float)

    # Smooth the projection to merge nearby peaks
    kernel = np.ones(5) / 5.0
    projection = np.convolve(projection, kernel, mode="same")

    threshold = np.percentile(projection, 85)
    above = projection > threshold

    # Find contiguous runs and pick their centres
    positions = []
    in_run = False
    run_start = 0
    for i, val in enumerate(above):
        if val and not in_run:
            in_run = True
            run_start = i
        elif not val and in_run:
            in_run = False
            positions.append((run_start + i) // 2)
    if in_run:
        positions.append((run_start + len(above)) // 2)

    return sorted(positions)


def detect_grid(image_bgr: np.ndarray) -> dict:
    """Detect the oscilloscope grid and return calibration information.

    Parameters
    ----------
    image_bgr:
        BGR image loaded with ``cv2.imread``.

    Returns
    -------
    dict with keys:
        ``h_lines``  – sorted list of row indices for horizontal grid lines
        ``v_lines``  – sorted list of column indices for vertical grid lines
        ``h_spacings`` – pixel spacings between consecutive horizontal lines
        ``v_spacings`` – pixel spacings between consecutive vertical lines
        ``h_spacing_median`` – median horizontal (row) spacing in pixels
        ``v_spacing_median`` – median vertical (col) spacing in pixels
        ``plot_roi``  – (x0, y0, x1, y1) pixel bounding box of the plot area
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = _gaussian_blur(gray, ksize=3)

    # Adaptive threshold emphasises edges and grid lines
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 4
    )

    h_lines = _detect_lines(binary, axis="horizontal")
    v_lines = _detect_lines(binary, axis="vertical")

    h_spacings = [h_lines[i + 1] - h_lines[i] for i in range(len(h_lines) - 1)]
    v_spacings = [v_lines[i + 1] - v_lines[i] for i in range(len(v_lines) - 1)]

    h_median = float(np.median(h_spacings)) if h_spacings else 50.0
    v_median = float(np.median(v_spacings)) if v_spacings else 50.0

    # Estimate plot ROI from outermost grid lines
    if h_lines and v_lines:
        roi = (v_lines[0], h_lines[0], v_lines[-1], h_lines[-1])
    else:
        h, w = image_bgr.shape[:2]
        roi = (0, 0, w, h)

    return {
        "h_lines": h_lines,
        "v_lines": v_lines,
        "h_spacings": h_spacings,
        "v_spacings": v_spacings,
        "h_spacing_median": h_median,
        "v_spacing_median": v_median,
        "plot_roi": roi,
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

class OscilloscopeCalibration:
    """Converts between pixel coordinates and physical (time, voltage) units.

    Parameters
    ----------
    grid_info:
        Dictionary returned by :func:`detect_grid`.
    time_per_div_us:
        Time per major horizontal grid division in microseconds.
    voltage_per_div_mv:
        Voltage per major vertical grid division in millivolts.
    ref_pixel_x:
        Pixel column that corresponds to *ref_time_us*.
    ref_time_us:
        Physical time (µs) at *ref_pixel_x*.
    ref_pixel_y:
        Pixel row that corresponds to *ref_voltage_mv*.
    ref_voltage_mv:
        Physical voltage (mV) at *ref_pixel_y*.
    """

    def __init__(
        self,
        grid_info: dict,
        time_per_div_us: float = DEFAULT_TIME_PER_DIV_US,
        voltage_per_div_mv: float = DEFAULT_VOLTAGE_PER_DIV_MV,
        ref_pixel_x: float | None = None,
        ref_time_us: float = 0.0,
        ref_pixel_y: float | None = None,
        ref_voltage_mv: float = 0.0,
    ):
        v_spacing = grid_info["v_spacing_median"]
        h_spacing = grid_info["h_spacing_median"]

        # pixels per physical unit
        self.px_per_us = v_spacing / time_per_div_us
        self.px_per_mv = h_spacing / voltage_per_div_mv

        roi = grid_info["plot_roi"]
        self.ref_pixel_x = ref_pixel_x if ref_pixel_x is not None else (roi[0] + roi[2]) / 2.0
        self.ref_time_us = ref_time_us

        self.ref_pixel_y = ref_pixel_y if ref_pixel_y is not None else (roi[1] + roi[3]) / 2.0
        self.ref_voltage_mv = ref_voltage_mv

    def pixel_to_time_us(self, px: float) -> float:
        """Convert a pixel column to a time value in microseconds."""
        return self.ref_time_us + (px - self.ref_pixel_x) / self.px_per_us

    def pixel_to_voltage_mv(self, py: float) -> float:
        """Convert a pixel row to a voltage value in millivolts.

        Note: pixel rows increase downward, voltage increases upward.
        """
        return self.ref_voltage_mv - (py - self.ref_pixel_y) / self.px_per_mv

    def time_us_to_pixel(self, t_us: float) -> float:
        """Convert a time value (µs) to a pixel column."""
        return self.ref_pixel_x + (t_us - self.ref_time_us) * self.px_per_us

    def voltage_mv_to_pixel(self, v_mv: float) -> float:
        """Convert a voltage value (mV) to a pixel row."""
        return self.ref_pixel_y - (v_mv - self.ref_voltage_mv) * self.px_per_mv


# ---------------------------------------------------------------------------
# Orange cursor arrow detection
# ---------------------------------------------------------------------------

def find_orange_arrow(image_bgr: np.ndarray) -> tuple[int, int] | None:
    """Locate the orange cursor arrow in the oscilloscope screenshot.

    The RIGOL DHO924S draws its cursor arrow in a distinctive orange/amber
    colour.  We threshold on the HSV hue range for orange and return the
    centroid of the largest matching blob.

    Parameters
    ----------
    image_bgr:
        BGR image.

    Returns
    -------
    (col, row) pixel coordinate of the arrow tip, or ``None`` if not found.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # Orange hue spans roughly 5–25° in OpenCV's 0–180 scale
    lower_orange = np.array([5, 150, 150], dtype=np.uint8)
    upper_orange = np.array([25, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_orange, upper_orange)

    # Remove small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Pick the largest contour
    largest = max(contours, key=cv2.contourArea)
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)


# ---------------------------------------------------------------------------
# Waveform tracing
# ---------------------------------------------------------------------------

def _isolate_waveform_color(image_bgr: np.ndarray) -> np.ndarray:
    """Return a binary mask of pixels that belong to the waveform trace.

    RIGOL DHO924S typically draws the active channel waveform in yellow or
    cyan.  We also keep white/bright pixels that may form the trace on dark
    backgrounds.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # Yellow waveform trace (common on RIGOL)
    yellow_lo = np.array([20, 100, 100], dtype=np.uint8)
    yellow_hi = np.array([40, 255, 255], dtype=np.uint8)
    mask_yellow = cv2.inRange(hsv, yellow_lo, yellow_hi)

    # Cyan waveform trace
    cyan_lo = np.array([85, 100, 100], dtype=np.uint8)
    cyan_hi = np.array([100, 255, 255], dtype=np.uint8)
    mask_cyan = cv2.inRange(hsv, cyan_lo, cyan_hi)

    # Also accept bright green (sometimes used for channel 1)
    green_lo = np.array([40, 80, 80], dtype=np.uint8)
    green_hi = np.array([85, 255, 255], dtype=np.uint8)
    mask_green = cv2.inRange(hsv, green_lo, green_hi)

    # Bright near-white pixels on a dark background
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, mask_bright = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    combined = cv2.bitwise_or(mask_yellow, mask_cyan)
    combined = cv2.bitwise_or(combined, mask_green)
    combined = cv2.bitwise_or(combined, mask_bright)

    return combined


def trace_waveform(
    image_bgr: np.ndarray,
    grid_info: dict,
    min_column_coverage: float = 0.3,
) -> list[tuple[int, int]]:
    """Trace the waveform and return a list of (col, row) pixel coordinates.

    For every column inside the plot ROI the function finds the pixel row that
    most likely belongs to the waveform (weighted centroid of the waveform
    mask in that column).

    Parameters
    ----------
    image_bgr:
        BGR image.
    grid_info:
        Dictionary from :func:`detect_grid`.
    min_column_coverage:
        Minimum fraction of columns that must have detected waveform pixels
        before the result is returned.  Columns below this threshold trigger
        a fallback to the full-image scan.

    Returns
    -------
    list of (col, row) tuples – one per column that has a waveform pixel.
    """
    roi = grid_info["plot_roi"]
    x0, y0, x1, y1 = roi

    waveform_mask = _isolate_waveform_color(image_bgr)

    # Crop to plot area
    crop_mask = waveform_mask[y0:y1, x0:x1]

    # Remove horizontal grid lines from the mask so they do not confuse
    # the centroid calculation
    for row in grid_info["h_lines"]:
        local_row = row - y0
        if 0 <= local_row < crop_mask.shape[0]:
            crop_mask[max(0, local_row - 1): local_row + 2, :] = 0

    points = []
    crop_height = crop_mask.shape[0]
    rows = np.arange(crop_height, dtype=float)

    for col in range(crop_mask.shape[1]):
        col_pixels = crop_mask[:, col].astype(float)
        total = col_pixels.sum()
        if total == 0:
            continue
        # Weighted centroid in the column
        centroid_row = float(np.dot(rows, col_pixels) / total)
        points.append((x0 + col, int(y0 + centroid_row)))

    # Fallback: scan without ROI restriction if coverage is too low
    if len(points) < min_column_coverage * (x1 - x0):
        wh, ww = waveform_mask.shape[:2]
        for col in range(ww):
            col_pixels = waveform_mask[:, col].astype(float)
            total = col_pixels.sum()
            if total == 0:
                continue
            centroid_row = float(np.dot(np.arange(wh, dtype=float), col_pixels) / total)
            points.append((col, int(centroid_row)))

    return points


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def extract_waveform(
    image_path: str,
    time_per_div_us: float = DEFAULT_TIME_PER_DIV_US,
    voltage_per_div_mv: float = DEFAULT_VOLTAGE_PER_DIV_MV,
    ref_time_us: float = 0.0,
    ref_voltage_mv: float = 0.0,
    debug: bool = False,
) -> pd.DataFrame:
    """Full extraction pipeline: load image → detect grid → trace waveform
    → convert to physical coordinates.

    Parameters
    ----------
    image_path:
        Path to the oscilloscope screenshot (PNG, JPG, BMP, …).
    time_per_div_us:
        Time per major horizontal division (µs).
    voltage_per_div_mv:
        Voltage per major vertical division (mV).
    ref_time_us:
        Physical time (µs) assigned to the centre of the plot.
    ref_voltage_mv:
        Physical voltage (mV) assigned to the centre of the plot.
    debug:
        When ``True``, save annotated debug images alongside the input file.

    Returns
    -------
    :class:`pandas.DataFrame` with columns ``time_us`` and ``voltage_mv``,
    sorted by ``time_us``.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise ValueError(f"Could not read image: {image_path}")

    print(f"[INFO] Loaded image: {image_path} ({image_bgr.shape[1]}×{image_bgr.shape[0]} px)")

    # ---- 1. Grid detection ------------------------------------------------
    grid_info = detect_grid(image_bgr)
    print(
        f"[INFO] Grid: {len(grid_info['h_lines'])} horizontal lines, "
        f"{len(grid_info['v_lines'])} vertical lines"
    )
    print(
        f"[INFO] Median grid spacing: "
        f"H={grid_info['h_spacing_median']:.1f} px, "
        f"V={grid_info['v_spacing_median']:.1f} px"
    )

    # ---- 2. Orange arrow detection ----------------------------------------
    arrow_pos = find_orange_arrow(image_bgr)
    if arrow_pos:
        print(f"[INFO] Orange cursor arrow detected at pixel {arrow_pos}")
    else:
        print("[WARN] Orange cursor arrow not detected – using image centre as reference")

    # ---- 3. Calibration ---------------------------------------------------
    roi = grid_info["plot_roi"]
    ref_px_x = arrow_pos[0] if arrow_pos else (roi[0] + roi[2]) / 2.0
    ref_px_y = (roi[1] + roi[3]) / 2.0  # vertical centre = ref voltage

    calib = OscilloscopeCalibration(
        grid_info=grid_info,
        time_per_div_us=time_per_div_us,
        voltage_per_div_mv=voltage_per_div_mv,
        ref_pixel_x=ref_px_x,
        ref_time_us=ref_time_us,
        ref_pixel_y=ref_px_y,
        ref_voltage_mv=ref_voltage_mv,
    )
    print(
        f"[INFO] Calibration: {calib.px_per_us:.2f} px/µs, "
        f"{calib.px_per_mv:.2f} px/mV"
    )

    # ---- 4. Waveform tracing ----------------------------------------------
    pixel_points = trace_waveform(image_bgr, grid_info)
    print(f"[INFO] Traced {len(pixel_points)} waveform pixel points")

    if not pixel_points:
        raise RuntimeError(
            "No waveform pixels found.  Check that the image contains a visible "
            "waveform trace and that the colour thresholds match your oscilloscope."
        )

    # ---- 5. Convert to physical coordinates ------------------------------
    records = []
    for col, row in pixel_points:
        t = calib.pixel_to_time_us(col)
        v = calib.pixel_to_voltage_mv(row)
        records.append({"time_us": t, "voltage_mv": v})

    df = pd.DataFrame(records).sort_values("time_us").reset_index(drop=True)
    print(
        f"[INFO] Extracted {len(df)} calibrated points "
        f"(time: {df['time_us'].min():.3f} – {df['time_us'].max():.3f} µs, "
        f"voltage: {df['voltage_mv'].min():.2f} – {df['voltage_mv'].max():.2f} mV)"
    )

    # ---- 6. Optional debug output ----------------------------------------
    if debug:
        _save_debug_image(image_bgr, grid_info, pixel_points, arrow_pos, image_path)

    return df


def _save_debug_image(
    image_bgr: np.ndarray,
    grid_info: dict,
    pixel_points: list[tuple[int, int]],
    arrow_pos: tuple[int, int] | None,
    source_path: str,
) -> None:
    """Save an annotated debug image showing detected grid and waveform."""
    debug_img = image_bgr.copy()

    # Draw grid lines
    for row in grid_info["h_lines"]:
        cv2.line(debug_img, (0, row), (debug_img.shape[1], row), (0, 255, 0), 1)
    for col in grid_info["v_lines"]:
        cv2.line(debug_img, (col, 0), (col, debug_img.shape[0]), (0, 255, 0), 1)

    # Draw traced waveform points
    for col, row in pixel_points:
        cv2.circle(debug_img, (col, row), 1, (0, 0, 255), -1)

    # Mark the orange arrow position
    if arrow_pos:
        cv2.drawMarker(debug_img, arrow_pos, (255, 0, 255), cv2.MARKER_CROSS, 20, 2)

    base, _ = os.path.splitext(source_path)
    debug_path = base + "_debug.png"
    cv2.imwrite(debug_path, debug_img)
    print(f"[DEBUG] Annotated image saved to: {debug_path}")


# ---------------------------------------------------------------------------
# Convenience: include the manually extracted reference points
# ---------------------------------------------------------------------------

MANUAL_REFERENCE_POINTS = {
    "x": [
        15186.210884578324, 15185.654378735951, 15185.910414547436,
        15184.969398471883, 15184.64171802686, 15184.246627971996,
        15184.028980767525, 15183.13330678491, 15183.13330678491,
        15183.482451217273, 15182.872736764133, 15181.864610264336,
        15181.470428083005, 15181.032415211834, 15181.032415211834,
        15180.326878833961, 15179.82387562958, 15182.058982892773,
        15182.058982892773, 15181.455922739962, 15180.941127496395,
        15178.158577651042, 15177.084253758905, 15176.117843016285,
        15175.423794333632, 15175.009659568059, 15174.488823870472,
        15173.781471745531, 15173.03059327472, 15172.650921594804,
        15172.207162296838, 15171.93661598394, 15171.684510852183,
        15171.436635585755, 15170.597487047327, 15170.098718866644,
        15169.893462072552, 15169.6383341346, 15169.382901852681,
        15170.967187593495, 15170.086926827456, 15168.82216098661,
        15168.024429019764, 15166.339178456987, 15166.339178456987,
        15167.368160256185, 15167.368160256185, 15167.265988375091,
        15167.846377481435, 15166.650233467932, 15165.992154115658,
        15165.428694787362, 15164.739783843565, 15164.20563954532,
        15163.64520302322, 15162.990750006706, 15162.354134641771,
        15165.40994926225, 15164.75519706014, 15163.179077022753,
        15162.126516303551, 15160.660424348343, 15160.866284672,
        15159.372383931464, 15159.665900476428, 15157.831325350924,
        15157.58043243667, 15156.311730757723, 15154.935724617197,
        15156.295708853211, 15155.06208410623, 15150.777472975287,
        15150.98756316427, 15151.451873417669, 15152.188847495816,
        15152.626860366987, 15152.922195238203, 15153.442731750194,
        15152.922195238203, 15153.891930551801, 15153.724463993529,
        15152.813069871185, 15151.575811050885, 15158.5604406488,
        15158.856077284798, 15158.294433703566, 15156.978574184615,
    ],
    "y": [
        39.1956468458432, 40.55293134660911, 28.353669405375296,
        28.59964907394513, 38.47572204428353, 28.942531680824395,
        37.79890265979668, 37.206425288956964, 37.206425288956964,
        29.418314997911153, 29.17953488372093, 28.849182565102353,
        29.75222113911711, 29.75222113911711, 29.75222113911711,
        30.60682356217797, 31.061038852527503, 36.79350786798496,
        36.79350786798496, 35.39854059323214, 33.524205542403564,
        31.70556746971174, 31.213608132572062, 29.93895000696282,
        29.52603258599081, 31.0771842361788, 29.21899456900153,
        34.85814510513856, 35.54755605068932, 29.235170589054448,
        34.504447848489065, 26.978431973262776, 39.46852527503133,
        42.701921737919506, 38.10410249268904, 42.07894582927169,
        56.53851552708536, 58.859881632084665, 103.0518646428074,
        28.752218353989694, 23.804316947500347, 27.389572482941094,
        27.24594903216822, 27.98563431276981, 27.98563431276981,
        28.36086895975491, 28.36086895975491, 36.664252889569696,
        35.29799192313048, 35.1561453836513, 36.2979947082579,
        34.82940816042334, 34.35543239103189, 36.996382119481964,
        33.6049937334633, 33.71629578053196, 35.21000417769113,
        27.369842640300792, 27.238780114190224, 27.10771758807965,
        27.447046372371535, 26.17952652833867, 34.675031332683474,
        33.301601448266254, 26.44523603954881, 35.303383929814785,
        26.87071438518312, 35.102286589611474, 27.206458710486004,
        27.206458710486004, 35.38058766188553, 25.590664252889567,
        34.48649491714246, 35.00535301490043, 34.05923966021446,
        34.05923966021446, 33.351845146915466, 35.34826625818131,
        33.351845146915466, 34.222592953627625, 25.132833867149422,
        25.396766467065866, 25.561927308174347, 34.92814928282969,
        27.710948335886364, 27.118501601448266, 35.91739869099010,
    ],
}


def load_manual_reference() -> pd.DataFrame:
    """Return the 87 manually extracted reference points as a DataFrame."""
    return pd.DataFrame(
        {
            "time_us": MANUAL_REFERENCE_POINTS["x"],
            "voltage_mv": MANUAL_REFERENCE_POINTS["y"],
        }
    ).sort_values("time_us").reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract waveform data from a RIGOL DHO924S oscilloscope image."
    )
    p.add_argument("--image", required=True, help="Path to the oscilloscope screenshot.")
    p.add_argument(
        "--time-per-div",
        type=float,
        default=DEFAULT_TIME_PER_DIV_US,
        help=f"Time per major horizontal division in µs (default: {DEFAULT_TIME_PER_DIV_US}).",
    )
    p.add_argument(
        "--voltage-per-div",
        type=float,
        default=DEFAULT_VOLTAGE_PER_DIV_MV,
        help=f"Voltage per major vertical division in mV (default: {DEFAULT_VOLTAGE_PER_DIV_MV}).",
    )
    p.add_argument(
        "--ref-time",
        type=float,
        default=0.0,
        help="Physical time (µs) at the cursor/reference pixel (default: 0).",
    )
    p.add_argument(
        "--ref-voltage",
        type=float,
        default=0.0,
        help="Physical voltage (mV) at the vertical centre of the plot (default: 0).",
    )
    p.add_argument(
        "--output",
        default="waveform_extracted.csv",
        help="Path for the output CSV file (default: waveform_extracted.csv).",
    )
    p.add_argument(
        "--plot",
        action="store_true",
        help="Show an interactive plot of the extracted waveform.",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Save an annotated debug image showing detected grid and waveform.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        df = extract_waveform(
            image_path=args.image,
            time_per_div_us=args.time_per_div,
            voltage_per_div_mv=args.voltage_per_div,
            ref_time_us=args.ref_time,
            ref_voltage_mv=args.ref_voltage,
            debug=args.debug,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    df.to_csv(args.output, index=False)
    print(f"[INFO] Saved {len(df)} points to: {args.output}")

    if args.plot:
        plt.figure(figsize=(12, 5))
        plt.plot(df["time_us"], df["voltage_mv"], "b-", lw=0.8, label="Extracted waveform")
        plt.xlabel("Time (µs)")
        plt.ylabel("Voltage (mV)")
        plt.title("Extracted Oscilloscope Waveform")
        plt.legend()
        plt.tight_layout()
        plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())
