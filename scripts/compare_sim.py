"""
compare_sim.py
==============
Keras float32  vs  HLS C++ fixed-point predictions side by side.
Runs on 20 randomly chosen samples from the MIT-BIH test set.
"""

import os, sys, traceback, warnings, json, h5py
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import numpy as np
import tensorflow as tf
from tensorflow import keras
tf.get_logger().setLevel("ERROR")


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

HLS_DIR   = os.environ.get("HLS_MODEL_DIR",   "hls4ml_tinyecg_8bit")
KERAS_H5  = os.environ.get("KERAS_MODEL",     "final_keras_model.h5")
TEST_CSV  = os.environ.get("TEST_CSV",        "mitbih_test.csv")
N        = 20000          # samples to compare
CLASSES  = ["N - Normal", "S - Supravent.", "V - Ventricular", "F - Fusion", "Q - Unknown"]
np.random.seed(42)

# ─────────────────────────────────────────────
# 1. Keras model
# ─────────────────────────────────────────────
print("=" * 60)
print("  Loading Keras model")
print("=" * 60)
model = load_model_compat(KERAS_H5)

# ─────────────────────────────────────────────
# 2. Load test data
# ─────────────────────────────────────────────
print(f"\n  Loading {TEST_CSV} ...")
data = np.loadtxt(TEST_CSV, delimiter=",", dtype="float32")
X_all = data[:, :-1].astype(np.float32)  # (N, 187)
y_all = data[:, -1].astype(int)

idx = np.random.choice(len(X_all), size=N, replace=False)
X   = X_all[idx].reshape(N, 187, 1)
y   = y_all[idx]
print(f"  Selected {N} samples  (classes: {np.bincount(y)})")

# ─────────────────────────────────────────────
# 3. Keras predictions
# ─────────────────────────────────────────────
print("\n  Running Keras (float32) ...")
keras_prob  = model.predict(X, verbose=0)
keras_preds = np.argmax(keras_prob, axis=1)

# ─────────────────────────────────────────────
# 4. HLS4ML C++ predictions via hls4ml.compile()
# ─────────────────────────────────────────────
print("\n  Loading HLS4ML project ...")
import hls4ml

print("  Parsing HLS4ML project from YAML ...")
try:
    # The project's hls4ml_config.yml stores KerasModel as a path relative
    # to the run directory (parent of HLS_DIR), so chdir there first.
    _orig_cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(HLS_DIR)))
    hls_model = hls4ml.converters.convert_from_config(
        f"{HLS_DIR}/hls4ml_config.yml"
    )
    os.chdir(_orig_cwd)
    print("  Compiling HLS C++ with g++ ...")
    hls_model.compile()
    print("  Running HLS inference ...")
    hls_prob  = hls_model.predict(np.ascontiguousarray(X))
    hls_preds = np.argmax(hls_prob, axis=1)
    hls_ok    = True
except Exception as e:
    os.chdir(_orig_cwd) if '_orig_cwd' in dir() else None
    print(f"\n  [WARN] HLS compile/predict failed: {e}")
    traceback.print_exc()
    hls_ok = False

# ─────────────────────────────────────────────
# 5. Side-by-side table
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Sample-by-sample comparison")
print("=" * 60)
header = f"{'#':>3}  {'True':>5}  {'Keras':>6}  "
if hls_ok:
    header += f"{'HLS':>5}  {'Match':>6}  "
header += "Keras probs"
print(header)
print("-" * 60)

matches = 0
for i in range(N):
    row = f"{idx[i]:>3}  {y[i]:>5}  {keras_preds[i]:>6}  "
    if hls_ok:
        m = "  ✓" if keras_preds[i] == hls_preds[i] else "  ✗"
        row += f"{hls_preds[i]:>5}{m:>7}  "
        matches += keras_preds[i] == hls_preds[i]
    row += "  ".join(f"{p:.3f}" for p in keras_prob[i])
    print(row)

print("-" * 60)

# ─────────────────────────────────────────────
# 6. Summary stats
# ─────────────────────────────────────────────
keras_acc = np.mean(keras_preds == y) * 100
print(f"\n  Keras accuracy  ({N} samples) : {keras_acc:.1f}%")

if hls_ok:
    hls_acc    = np.mean(hls_preds == y) * 100
    match_rate = matches / N * 100
    print(f"  HLS   accuracy  ({N} samples) : {hls_acc:.1f}%")
    print(f"  Prediction agreement          : {match_rate:.1f}%  ({matches}/{N} agree)")

    # Read actual precision from hls4ml_config.yml
    _cfg_path = os.path.join(HLS_DIR, "hls4ml_config.yml")
    _prec = "ap_fixed (see hls4ml_config.yml)"
    if os.path.exists(_cfg_path):
        with open(_cfg_path) as _f:
            for _line in _f:
                if "Precision:" in _line and "ap_fixed" in _line:
                    _prec = _line.split(":")[-1].strip()
                    break
    print(f"\n  Precision (HLS) : {_prec}")
    print(f"  Keras uses      : float32 (full precision)")
else:
    print("\n  HLS comparison skipped — compile() failed (see error above)")
    print("  Keras-only accuracy shown above for precision reference")

print("=" * 60)
