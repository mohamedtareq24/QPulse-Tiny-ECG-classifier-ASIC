# MATLAB — ECG Preprocessing & Input Vector Generation

This directory contains the MATLAB simulation of the hardware ECG beat-detection and preprocessing pipeline used to generate CNN input vectors for the QPulse ASIC.

## Files

| File / Folder | Description |
|---|---|
| `ecg_algo.m` | Main script — runs the beat-detection algorithm and writes CNN input vectors |
| `mitbih_test.csv` | MIT-BIH Arrhythmia Database test-set rows (187 samples per beat, 8-bit ADC) |
| `nstdb/bw.csv` | NSTDB baseline wander noise record |
| `nstdb/ma.csv` | NSTDB muscle artifact noise record |
| `nstdb/em.csv` | NSTDB electrode motion noise record |

## What `ecg_algo.m` Does

1. **Data loading** — reads a single beat row from `mitbih_test.csv`, tiles it `num_repeats` times to form a continuous ADC stream (8-bit, 125 Hz).
2. **Noise injection** — optionally mixes NSTDB noise (`bw`, `ma`, `em`, or all three) into the stream at a configurable SNR (default 10 dB).
3. **Beat detection loop** — a hardware-faithful software model of the ASIC peak-pair detector:
   - **Slope trigger** — detects a rising edge exceeding `slope_thresh_knob` ADC counts/sample.
   - **Peak latch** — locks on the local maximum within a 5-sample look-ahead window (Peak 1).
   - **Rolling min/max tracking** — maintains a running minimum (RS-window guard) and a running maximum (hump / max-window guard) between peaks.
   - **Safety resets** — discards the candidate pair if the RS-window drop exceeds `rs_window_knob`, or if a hump is detected via the max-window check.
   - **Magnitude tolerance gate** — accepts Peak 2 only if its magnitude is within `tolerance` (fractional) of Peak 1.
4. **Preprocessing** — for each accepted beat window:
   - Subtracts `rolling_min` (the hardware normalization floor).
   - Right-shifts by `output_shift` bits to produce a 5-bit (0–31) value per sample.
5. **Output files** — writes three transaction files for UVM/cosim use:
   - `input_vectors.txt` — preprocessed, floor-subtracted, bit-shifted CNN inputs.
   - `input_vectors_raw_unscaled.txt` — raw ADC values for the accepted window.
   - `input_vectors_raw_scaled.txt` — reference beat scaled to 0–31 range.
   - `all_preprocessed_samples.mat` / `.csv` — concatenated accepted windows for offline analysis.
6. **Visualization** — live MATLAB figure showing detected peak pairs on the ADC stream and the preprocessed CNN window.

## Key Tunable Parameters

| Parameter | Default | Effect |
|---|---|---|
| `fs` | 125 | Sampling rate (Hz) |
| `tolerance` | 1 | Max fractional magnitude mismatch between Peak 1 and Peak 2 |
| `rs_window_knob` | 255 | Max Peak-1-to-rolling-min drop before reset |
| `slope_thresh_knob` | 15 | Minimum dy/sample to trigger slope detection |
| `refractory_delay` | 10 | Samples to skip after a peak or reset event |
| `max_window_knob` | -100 | Minimum Peak-1-minus-rolling-max gap (hump detector threshold) |
| `max_window_arm_samples` | 5 | Samples after Peak 1 before hump checking activates |
| `output_shift` | 2 | Right-shift applied to floor-subtracted samples (sets 5-bit range) |
| `window_floor_offset` | 5 | ADC units subtracted from pre-slope minimum to set normalization floor |
| `noise_profile` | `'mixed'` | `'none'` / `'bw'` / `'ma'` / `'em'` / `'mixed'` |
| `target_snr_db` | 10 | SNR at which NSTDB noise is injected |

## NSTDB Noise Files

The `nstdb/` folder holds CSV exports of the MIT Noise Stress Test Database:

- **bw** — baseline wander (respiration artifact)
- **ma** — muscle artifact (high-frequency EMG)
- **em** — electrode motion artifact

Each file is a single-column CSV at the original NSTDB sample rate; the script resamples to match the ECG stream length via `interp1`.

## Output Format

Transaction files follow the UVM/cosim `[[[runtime]]]` / `[[transaction]] N` / `[[/transaction]]` format expected by the testbenches under `fpga/testing/` and `verf/`.
