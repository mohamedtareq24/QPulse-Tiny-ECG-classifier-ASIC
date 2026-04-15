import json
import h5py

with h5py.File("../models/tiny_ecg_qat/ecg_clean_for_hls4ml.h5", "r") as f:
    model_config = f.attrs.get("model_config")
    if model_config is None:
        raise ValueError("No model_config found in HDF5 file.")
    if isinstance(model_config, bytes):
        model_config = model_config.decode("utf-8")

parsed = json.loads(model_config)

with open("../models/tiny_ecg_qat/ecg_clean_for_hls4ml.json", "w") as f:
    json.dump(parsed, f, indent=2)

print("Model architecture saved to ecg_clean_for_hls4ml.json")
