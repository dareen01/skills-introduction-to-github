# Oscilloscope Waveform Extraction & Plasma Guiding Fit

This project provides two Python scripts for automated extraction of waveform
data from a RIGOL DHO924S oscilloscope screenshot and fitting a plasma guiding
model to the resulting dataset.

---

## Contents

| File | Description |
|------|-------------|
| `oscilloscope_waveform_extractor.py` | Image processing: grid detection, orange-arrow location, waveform tracing, pixel→physical calibration |
| `plasma_guiding_fit.py` | Non-linear curve fitting of the plasma guiding model (damped Gaussian sinusoid) with peak identification |
| `waveform_data.csv` | 87 manually extracted reference points (time in µs, voltage in mV) |
| `requirements.txt` | Python dependencies |

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Quick Start

### 1. Fit the plasma guiding model to the included reference data

```bash
python plasma_guiding_fit.py --manual
```

### 2. Extract waveform from your oscilloscope image and then fit

```bash
# Step 1 – extract
python oscilloscope_waveform_extractor.py \
    --image your_scope_image.png \
    --time-per-div 1.0 \
    --voltage-per-div 4.0 \
    --output waveform_extracted.csv \
    --plot

# Step 2 – fit
python plasma_guiding_fit.py \
    --data waveform_extracted.csv \
    --output-plot fit_result.png
```

### 3. Fit the included CSV directly

```bash
python plasma_guiding_fit.py \
    --data waveform_data.csv \
    --output-plot fit_result.png \
    --output-csv fit_curve.csv
```

---

## Calibration Methodology

### Grid detection

`oscilloscope_waveform_extractor.py` converts the screenshot to greyscale,
applies adaptive thresholding, and projects pixel intensities along both axes
to find the dominant horizontal and vertical grid lines.  The median spacing
between adjacent lines gives the pixels-per-division scale.

### Physical unit conversion

Two scale factors link pixel coordinates to physical units:

| Direction | Formula |
|-----------|---------|
| Horizontal (time) | `px_per_µs = pixel_spacing_per_div / time_per_div_µs` |
| Vertical (voltage) | `px_per_mV = pixel_spacing_per_div / voltage_per_div_mV` |

Default values for the RIGOL DHO924S screenshots used in this study:

- **Time per division** : 1 µs  
- **Voltage per division** : 4 mV  

The orange cursor arrow (detected via HSV colour thresholding) provides the
reference pixel column; its physical time value is read from Channel D's
digital readout and passed in via `--ref-time`.

### Waveform tracing

For every pixel column inside the detected plot ROI the script computes the
weighted centroid of the waveform mask (pixels matching the trace colour) to
produce one (time, voltage) point per column.  Grid-line pixels are masked out
before the centroid calculation to avoid bias.

---

## Plasma Guiding Model

The waveform is described by a **damped Gaussian sinusoid**:

```
V(t) = A · exp(−((t − t₀) / σ)²) · sin(2π f (t − t₀) + φ) + C
```

| Parameter | Unit | Interpretation |
|-----------|------|----------------|
| `A`       | mV   | Peak amplitude |
| `t₀`      | µs   | Time of peak envelope (primary maximum = fmax) |
| `σ`       | µs   | Gaussian width / decay constant |
| `f`       | 1/µs | Oscillation frequency |
| `φ`       | rad  | Phase offset |
| `C`       | mV   | DC offset |

`scipy.optimize.curve_fit` with the Trust Region Reflective (`trf`) method and
multiple random restarts is used to minimise the residual sum of squares.

Peak locations:

- **fmax** – position of the primary envelope maximum at `t₀`  
- **2 fmax, 3 fmax, …** – secondary oscillation maxima detected automatically
  in the fitted curve to the right of `t₀`

---

## CLI Reference

### `oscilloscope_waveform_extractor.py`

```
usage: oscilloscope_waveform_extractor.py
       --image PATH
       [--time-per-div FLOAT]   (µs, default 1.0)
       [--voltage-per-div FLOAT] (mV, default 4.0)
       [--ref-time FLOAT]       (µs at cursor arrow, default 0.0)
       [--ref-voltage FLOAT]    (mV at plot centre, default 0.0)
       [--output PATH]          (CSV output, default waveform_extracted.csv)
       [--plot]                 (show interactive plot)
       [--debug]                (save annotated debug image)
```

### `plasma_guiding_fit.py`

```
usage: plasma_guiding_fit.py
       (--data PATH | --manual)
       [--output-plot PATH]     (save figure to PNG/PDF)
       [--output-csv PATH]      (save fitted curve to CSV)
       [--no-plot]              (suppress interactive window)
```

---

## Output Files

| File | Description |
|------|-------------|
| `waveform_extracted.csv` | Extracted waveform: `time_us`, `voltage_mv` |
| `fit_result.png` | Two-panel figure: data + fitted curve (top) and residuals (bottom) |
| `fit_curve.csv` | Dense fitted curve: `time_us`, `voltage_mv_fit` |
| `*_debug.png` | Annotated screenshot showing detected grid and waveform (with `--debug`) |

---

## Notes

- The extractor uses colour thresholding tuned for RIGOL oscilloscope colour
  schemes (yellow / cyan waveform on dark background, orange cursor arrow).
  Adjust the HSV ranges in `_isolate_waveform_color` and `find_orange_arrow`
  if your scope uses different colours.
- For best results supply the full-resolution screenshot without JPEG
  artefacts.
- The 87 reference points embedded in `waveform_data.csv` were manually
  digitised from the original image; the automated extractor can capture
  significantly more points including the secondary maxima (2 fmax) that
  are difficult to mark by hand.
