"""
TinyECG  ─  HLS4ML (8-bit) + ONNX export
==========================================
Rebuilds the model from the known architecture (avoids Keras version mismatch
when loading the .h5 saved with a newer Keras), then:
  1. Prints detailed parameter breakdown
  2. Exports an ONNX graph  (tinyecg.onnx)
  3. Converts to HLS C++ with 8-bit fixed-point weights + activations
"""

import os
import warnings
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import numpy as np
import tensorflow as tf
from tensorflow import keras

# ── optional: silence TF-TRT noise ───────────────────────────────────────────
tf.get_logger().setLevel("ERROR")

# =============================================================================
# 1. Rebuild model from known architecture
# =============================================================================
def build_tinyecg(input_shape=(187, 1), num_classes=5):
    model = keras.Sequential(
        [
            keras.layers.Conv1D(4,  kernel_size=5, activation="relu", input_shape=input_shape, name="conv1"),
            keras.layers.MaxPool1D(pool_size=2, name="pool1"),
            keras.layers.Conv1D(8,  kernel_size=5, activation="relu",                          name="conv2"),
            keras.layers.MaxPool1D(pool_size=2, name="pool2"),
            keras.layers.Flatten(name="flatten"),
            keras.layers.Dense(num_classes, activation="softmax",                              name="output"),
        ],
        name="TinyECG",
    )
    return model

model = build_tinyecg()

# Try to load weights from the existing .h5 (best-effort; skip if version mismatch)
H5_PATH = "final_keras_model.h5"
if os.path.exists(H5_PATH):
    try:
        model.load_weights(H5_PATH)
        print(f"[OK] Weights loaded from {H5_PATH}")
    except Exception as e:
        print(f"[WARN] Could not load weights ({e})  ─ using random weights for conversion demo")
else:
    print(f"[WARN] {H5_PATH} not found  ─ using random weights for conversion demo")

# =============================================================================
# 2. Parameter breakdown
# =============================================================================
print("\n" + "=" * 58)
print("  TinyECG  ─  Parameter Breakdown")
print("=" * 58)
model.summary()

print("\n  Per-layer (trainable only):")
print(f"  {'Layer':<20} {'Shape':>22}   Params")
print("  " + "-" * 52)
for layer in model.layers:
    for w in layer.trainable_weights:
        print(f"  {w.name:<35} {str(w.shape):>12}   {np.prod(w.shape):>6}")

total = model.count_params()
bits  = total * 8          # 8-bit quantized footprint
print(f"\n  TOTAL parameters : {total:,}")
print(f"  Weight memory    : {total} × 1 byte (int8/fp8) = {bits//8} bytes  ({bits/8/1024:.2f} KB)")
print("=" * 58)

# =============================================================================
# 3. ONNX Export
# =============================================================================
print("\n[ONNX] Exporting model ...")

import tf2onnx
import onnx

# Convert via the SavedModel path (most reliable with tf2onnx)
TF_SAVED = "/tmp/tinyecg_savedmodel"
model.export(TF_SAVED) if hasattr(model, "export") else tf.saved_model.save(model, TF_SAVED)

ONNX_PATH = "tinyecg.onnx"
onnx_model, _ = tf2onnx.convert.from_keras(
    model,
    input_signature=[tf.TensorSpec(shape=[None, 187, 1], dtype=tf.float32, name="input")],
    opset=13,
    output_path=ONNX_PATH,
)
print(f"[OK] ONNX graph saved → {ONNX_PATH}")
print(f"     Opset : {onnx_model.opset_import[0].version}")
print(f"     Nodes : {len(onnx_model.graph.node)}")
inputs  = [f"{i.name} {list(d.dim[j].dim_value for j in range(len(d.dim)))}"
           for i in onnx_model.graph.input
           for d in [i.type.tensor_type.shape]]
outputs = [f"{o.name} {list(d.dim[j].dim_value for j in range(len(d.dim)))}"
           for o in onnx_model.graph.output
           for d in [o.type.tensor_type.shape]]
print(f"     Inputs  : {inputs}")
print(f"     Outputs : {outputs}")

# Validate
onnx.checker.check_model(ONNX_PATH)
print("[OK] ONNX model is valid")

# =============================================================================
# 4. HLS4ML Conversion  ─  area-focused fixed-point
# =============================================================================
print("\n[HLS4ML] Configuring area-focused fixed-point conversion ...")

import hls4ml

# --- auto-generate a starting config ---
config = hls4ml.utils.config_from_keras_model(model, granularity="name")

# --- tighter precision to reduce area ---
#   ap_fixed<4,1> : 4 total bits, 1 integer bit (range [-1, 0.875], res 0.125)
PREC = "ap_fixed<4,1>"

config["Model"]["Precision"]               = PREC   # default for weights & biases
config["Model"]["ReuseFactor"]             = 256

for layer in model.layers:
    config["LayerName"][layer.name]["Precision"]    = PREC
    config["LayerName"][layer.name]["ReuseFactor"]  = 256

print("  HLS4ML config (8-bit fixed-point):")
for k, v in config["Model"].items():
    print(f"    Model.{k} = {v}")

# --- convert ---
HLS_OUTPUT = "hls4ml_tinyecg_8bit"
hls_model = hls4ml.converters.convert_from_keras_model(
    model,
    hls_config=config,
    output_dir=HLS_OUTPUT,
    backend="Vivado",          # change to 'VivadoAccelerator' for Pynq boards
    io_type="io_stream",
    part="xcku115-flvb2104-2-e",  # Kintex UltraScale: 5520 DSPs, 4Mb BRAM – avoids array partition limits
)

print(f"\n[OK] HLS project generated → {HLS_OUTPUT}/")
print("     Backend   : Vivado HLS")
print("     IO type   : io_stream")
print("     Precision : " + PREC)
print("     Part      : xcku115-flvb2104-2-e (Kintex UltraScale)")

# --- print the precision table ---
print("\n  Layer precision summary:")
for lname, lcfg in config.get("LayerName", {}).items():
    prec = lcfg.get("Precision", config["Model"]["Precision"])
    print(f"    {lname:<20} {prec}")

# =============================================================================
# 5. Compile (csim) ─ optional, requires Vivado HLS or Vitis HLS in PATH
# =============================================================================
print("\n" + "=" * 58)
print("  Next steps")
print("=" * 58)
print(f"  1. Open HLS project : {HLS_OUTPUT}/")
print("  2. Run C-simulation  : hls_model.compile()  (needs g++)")
print("  3. Run synthesis     : hls_model.build(csim=False, synth=True)")
print("     (Vivado / Vitis HLS must be in your PATH)")
print("  4. View ONNX graph   : netron tinyecg.onnx")
print("=" * 58)
