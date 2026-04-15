"""
Generate HLS testbench data for hls4ml_tinyecg_8bit.

Reads mitbih_test.csv, runs the Keras model, and writes:
  hls4ml_tinyecg_8bit/tb_data/tb_input_features.dat     -- raw signal (187 values per line)
  hls4ml_tinyecg_8bit/tb_data/tb_output_predictions.dat  -- float logits (5 values per line)
  hls4ml_tinyecg_8bit/tb_data/tb_labels_predictions.dat  -- true label (int per line)
"""

import sys
import os
import json
import h5py
import numpy as np
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
from tensorflow import keras


def _strip_keras3(obj):
    if isinstance(obj, dict):
        for k in ("module", "registered_name", "quantization_config", "optional"):
            obj.pop(k, None)
        for v in obj.values():
            _strip_keras3(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_keras3(item)


def load_model_compat(path):
    """Load a Keras model regardless of which Keras version saved it."""
    try:
        return keras.models.load_model(path)
    except TypeError:
        pass
    with h5py.File(path, "r") as f:
        raw = f.attrs["model_config"]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        config = json.loads(raw)
    for layer in config["config"]["layers"]:
        lc = layer["config"]
        if layer["class_name"] == "InputLayer":
            if "batch_shape" in lc:
                lc["batch_input_shape"] = lc.pop("batch_shape")
        if isinstance(lc.get("dtype"), dict):
            lc["dtype"] = lc["dtype"]["config"]["name"]
    _strip_keras3(config)
    model = keras.models.model_from_json(json.dumps(config))
    model.load_weights(path, by_name=True)
    return model

# ── Config ───────────────────────────────────────────────────
# Usage: python3 generate_tb_data.py <hls_output_dir> [n_samples]
# hls_output_dir: path to the generated HLS project (contains tb_data/)
# Paths to CSV and weights are relative to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_DIR    = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(SCRIPT_DIR, "hls4ml_tinyecg_8bit")
N_SAMPLES  = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
CSV_PATH   = os.environ.get("TEST_CSV",    os.path.join(SCRIPT_DIR, "mitbih_test.csv"))
WEIGHTS_H5 = os.environ.get("KERAS_MODEL", os.path.join(SCRIPT_DIR, "final_keras_model.h5"))
OUT_DIR    = os.path.join(HLS_DIR, "tb_data")
SEED       = 42

# ── Load data ─────────────────────────────────────────────────
print(f"Loading {CSV_PATH} ...")
raw = np.loadtxt(CSV_PATH, delimiter=",")
X   = raw[:, :187].astype(np.float32)   # (N, 187)
y   = raw[:, 187].astype(int)           # (N,)

# Stratified subsample if N_SAMPLES is set
if N_SAMPLES is not None and N_SAMPLES < len(X):
    rng     = np.random.default_rng(SEED)
    classes = np.unique(y)
    per_cls = N_SAMPLES // len(classes)
    idx     = []
    for c in classes:
        ci = np.where(y == c)[0]
        chosen = rng.choice(ci, size=min(per_cls, len(ci)), replace=False)
        idx.append(chosen)
    # top up to exactly N_SAMPLES from class 0 if needed
    idx = np.concatenate(idx)
    if len(idx) < N_SAMPLES:
        remaining = np.setdiff1d(np.where(y == classes[0])[0], idx)
        extra = rng.choice(remaining, size=N_SAMPLES - len(idx), replace=False)
        idx = np.concatenate([idx, extra])
    rng.shuffle(idx)
    X, y = X[idx], y[idx]

print(f"Samples: {len(X)}, class distribution: { {int(c): int((y==c).sum()) for c in np.unique(y)} }")

# ── Load model ────────────────────────────────────────────────
print(f"Loading model from {WEIGHTS_H5} ...")
model = load_model_compat(WEIGHTS_H5)

# ── Run inference ─────────────────────────────────────────────
X_in   = X.reshape(-1, 187, 1)                   # (N, 187, 1) for Conv1D
logits = model.predict(X_in, batch_size=256, verbose=0)   # (N, 5) softmax probs
preds  = np.argmax(logits, axis=1)
acc    = np.mean(preds == y) * 100
print(f"Keras model accuracy on selected samples: {acc:.2f}%")

# ── Write tb_data files ───────────────────────────────────────
os.makedirs(OUT_DIR, exist_ok=True)

# tb_input_features.dat — one sample per line, 187 space-separated floats
# hls4ml convention: input is channels-last flattened (already 187×1 → 187)
feat_path = os.path.join(OUT_DIR, "tb_input_features.dat")
with open(feat_path, "w") as f:
    for row in X:
        f.write(" ".join(f"{v:.8e}" for v in row) + "\n")
print(f"Written: {feat_path}")

# tb_output_predictions.dat — 5 float logits per line
pred_path = os.path.join(OUT_DIR, "tb_output_predictions.dat")
with open(pred_path, "w") as f:
    for row in logits:
        f.write(" ".join(f"{v:.8e}" for v in row) + "\n")
print(f"Written: {pred_path}")

# tb_labels_predictions.dat — two-column format matching hls4ml convention:
# col0 = true label, col1 = predicted label
lbl_path = os.path.join(OUT_DIR, "tb_labels_predictions.dat")
with open(lbl_path, "w") as f:
    for true, pred in zip(y, preds):
        f.write(f"{true} {pred}\n")
print(f"Written: {lbl_path}")

print("\nDone. tb_data is ready for HLS csim.")
