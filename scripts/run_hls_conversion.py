# =============================================================
# HLS4ML Conversion Script — TinyECG
# Loads the saved Keras model from the run directory and
# converts it to an HLS project using the run's hls4ml_config.yml.
# =============================================================

import sys
import os
import subprocess
import json
import h5py
import yaml
import hls4ml
from tensorflow import keras

# Allow !keras_model tags written by hls4ml to parse without error
yaml.add_multi_constructor("", lambda loader, tag, node: loader.construct_yaml_str(node),
                           Loader=yaml.SafeLoader)


def _strip_keras3(obj):
    """Recursively remove Keras 3 fields that older Keras doesn't accept."""
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

    print(f"  [compat] Patching Keras 3 config for older Keras runtime ...")
    with h5py.File(path, "r") as f:
        raw = f.attrs["model_config"]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        config = json.loads(raw)

    for layer in config["config"]["layers"]:
        lc = layer["config"]
        # InputLayer: batch_shape -> batch_input_shape
        if layer["class_name"] == "InputLayer":
            if "batch_shape" in lc:
                lc["batch_input_shape"] = lc.pop("batch_shape")
        # dtype dict -> plain string
        if isinstance(lc.get("dtype"), dict):
            lc["dtype"] = lc["dtype"]["config"]["name"]

    _strip_keras3(config)

    model = keras.models.model_from_json(json.dumps(config))
    model.load_weights(path, by_name=True)
    return model

# ── 1. Load YAML config ──────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
config_path = sys.argv[1] if len(sys.argv) > 1 else "hls4ml_config.yml"
config_path = os.path.abspath(config_path)
# Run from the directory containing the config so relative paths resolve
os.chdir(os.path.dirname(config_path))
with open(config_path, "r") as f:
    cfg = yaml.safe_load(f)

print("=== Config sanity check ===")
print(f"  Backend       : {cfg['Backend']}")
print(f"  Part          : {cfg['Part']}")
print(f"  ClockPeriod   : {cfg['ClockPeriod']} ns  ({1000/cfg['ClockPeriod']:.0f} MHz)")
print(f"  IOType        : {cfg['IOType']}")
print(f"  Strategy      : {cfg['HLSConfig']['Model']['Strategy']}")
print(f"  ReuseFactor   : {cfg['HLSConfig']['Model']['ReuseFactor']}")
print(f"  Precision     : {cfg['HLSConfig']['Model']['Precision']}")
print(f"  OutputDir     : {cfg['OutputDir']}")
print()

# ── 2. Load the saved Keras model ──────────────────────────────
# KERAS_MODEL env var is set by the Makefile; fall back to local file.
weights_path = os.environ.get("KERAS_MODEL",
                               os.path.join(os.path.dirname(config_path),
                                            "final_keras_model.h5"))
model = load_model_compat(weights_path)
print(f"Model loaded from    : {weights_path}")
model.summary()
print()

# ── 4. Convert to HLS ────────────────────────────────────────
hls_config = cfg["HLSConfig"]
# Extract Flows before passing to convert — hls4ml 0.8.1 does not register
# vitis:fifo_depth_optimization as a flow, so passing it causes "Unknown flow".
flows = hls_config.pop("Flows", [])
fifo_opt = any("fifo_depth_optimization" in str(f) for f in flows)

if fifo_opt:
    backend_prefix = cfg["Backend"].lower()
    opt_name = f"{backend_prefix}:fifo_depth_optimization"
    fifo_opt_pass = hls4ml.model.optimizer.get_optimizer(opt_name)
    fifo_opt_pass.configure(profiling_fifo_depth=100_000)
    print(f"  FIFO depth optimization ENABLED (profiling_fifo_depth=100,000)")

hls_model = hls4ml.converters.convert_from_keras_model(
    model,
    hls_config=hls_config,
    output_dir=cfg["OutputDir"],
    project_name=cfg["ProjectName"],
    backend=cfg["Backend"],
    part=cfg["Part"],
    clock_period=cfg["ClockPeriod"],
    io_type=cfg["IOType"],
)

# ── 5. Write HLS project ──────────────────────────────────────
hls_model.write()
print(f"\nHLS project written to: {cfg['OutputDir']}/")

if fifo_opt:
    print("\n>>> Generating tb_data for co-simulation (required by FIFO depth optimization)...")
    tb_samples = os.environ.get("TB_SAMPLES", "500")
    hls_dir_abs = os.path.abspath(cfg["OutputDir"])
    subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "generate_tb_data.py"), hls_dir_abs, tb_samples],
        check=True,
        env=os.environ,
    )
    print(">>> tb_data generated.")
    print("\n>>> Running FIFO depth optimization (csim -> profile -> synth -> cosim)...")
    print("    This will take a while — co-simulation is required to profile FIFO occupancy.")
    # Call the pass directly — the flow is not registered in hls4ml 0.8.1
    fifo_opt_pass.transform(hls_model)
    # Re-write project with updated FIFO depths, then synthesise
    hls_model.write()
    hls_model.build(reset=False, csim=False, synth=True, cosim=False)
    print(">>> FIFO optimization complete. FIFO depths updated to minimum required.")
else:
    print("Done. Run Vitis HLS synthesis from that directory.")
