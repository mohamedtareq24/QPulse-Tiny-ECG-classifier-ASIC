#!/usr/bin/env python3
"""
fifo_depth_search.py — Find the minimum FIFO depth that passes RTL co-simulation.

Strategy (simple and reliable):
  For each candidate depth (1, 2, 4, 8, …):
    1. Patch the depth pragma in firmware/<project>.cpp
    2. Run vitis_hls with synth=1 cosim=1  (re-synthesise + cosim — proven reliable)
    3. Check the cosim report for Pass/Fail
  First passing depth is the answer.

Why not csim?
  hls::stream is unbounded in Vitis HLS C sim; depth pragmas have no effect.
  Deadlocks only appear in RTL co-simulation.

Sample count:
  The number of transactions simulated equals the number of rows in
  tb_data/tb_input_features.dat.  Run 'make tbdata TB_SAMPLES=5' before
  this script to keep each cosim fast.

Usage:
    python3 fifo_depth_search.py <hls_project_dir> [--max-depth N] [--vitis-hls PATH]

Example:
    make tbdata TB_SAMPLES=5
    python3 fifo_depth_search.py ../tiny_ecg_clip_reluf3s_run1/hls4ml_prj
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

# ── Args ─────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("hls_dir",     help="HLS project dir (contains build_prj.tcl + firmware/)")
parser.add_argument("--max-depth", type=int, default=256, help="Max depth to probe (default: 256)")
parser.add_argument("--vitis-hls", default=None,          help="Path to vitis_hls binary")
args = parser.parse_args()

HLS_DIR = os.path.abspath(args.hls_dir)

# ── Locate vitis_hls ──────────────────────────────────────────────────────────
VITIS_HLS = args.vitis_hls or shutil.which("vitis_hls") or os.path.join(
    os.environ.get("XILINX_HLS", "/home/zkp_egy2/tools/xilinx23/Vitis_HLS/2023.1"),
    "bin", "vitis_hls"
)
if not os.path.isfile(VITIS_HLS):
    sys.exit(f"ERROR: vitis_hls not found at {VITIS_HLS}")

# ── Find project name ─────────────────────────────────────────────────────────
PRJ_NAME = None
for tcl_name in ("project.tcl", "build_prj.tcl"):
    p = os.path.join(HLS_DIR, tcl_name)
    if not os.path.exists(p):
        continue
    with open(p) as fh:
        for line in fh:
            m = re.search(r'set project_name\s+"(\S+)"', line)
            if m:
                PRJ_NAME = m.group(1)
                break
    if PRJ_NAME:
        break
if not PRJ_NAME:
    sys.exit("ERROR: Could not find 'set project_name' in project.tcl or build_prj.tcl")

COSIM_RPT = os.path.join(HLS_DIR, f"{PRJ_NAME}_prj", "solution1",
                          "sim", "report", f"{PRJ_NAME}_cosim.rpt")

# ── Find firmware .cpp with depth pragmas ─────────────────────────────────────
fw_dir  = os.path.join(HLS_DIR, "firmware")
top_cpp = None
for fname in os.listdir(fw_dir):
    if fname.endswith(".cpp") and not fname.startswith("nnet_"):
        fpath = os.path.join(fw_dir, fname)
        with open(fpath) as fh:
            if "HLS STREAM" in fh.read():
                top_cpp = fpath
                break
if not top_cpp:
    sys.exit(f"ERROR: No .cpp with '#pragma HLS STREAM' found under {fw_dir}")

with open(top_cpp) as fh:
    original_cpp = fh.read()

n_pragmas = len(re.findall(r"#pragma HLS STREAM variable=\w+ depth=\d+", original_cpp))

# ── Inform the user about sample count ───────────────────────────────────────
tb_in = os.path.join(HLS_DIR, "tb_data", "tb_input_features.dat")
n_rows = 0
if os.path.exists(tb_in):
    with open(tb_in) as fh:
        n_rows = sum(1 for l in fh if l.strip())

print(f"Project    : {PRJ_NAME}")
print(f"Firmware   : {os.path.basename(top_cpp)}  ({n_pragmas} FIFO pragma(s))")
print(f"tb_data    : {n_rows} sample(s)  (each cosim run simulates this many transactions)")
if n_rows > 10:
    print(f"  TIP: Run 'make tbdata TB_SAMPLES=5' first to speed up each cosim pass.")
print()

# ── Helpers ───────────────────────────────────────────────────────────────────
def set_depth(depth: int):
    patched = re.sub(
        r"(#pragma HLS STREAM variable=\w+ depth)=\d+",
        rf"\1={depth}",
        original_cpp
    )
    with open(top_cpp, "w") as fh:
        fh.write(patched)

def restore_cpp():
    with open(top_cpp, "w") as fh:
        fh.write(original_cpp)

VALIDATE_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_cosim.py")


def run_synth_cosim(depth: int) -> bool:
    """Re-synthesise + co-simulate, then validate output against Keras reference."""
    print(f"  [depth={depth}] synth + cosim ...", flush=True)
    subprocess.run(
        [VITIS_HLS, "-f", "build_prj.tcl",
         "-tclargs", "reset=1 csim=0 synth=1 cosim=1 validation=0 fifo_opt=0"],
        cwd=HLS_DIR,
        capture_output=False   # let output stream to terminal so user can see progress
    )
    # Check RTL output is numerically correct — cosim report "Pass" only means
    # main() returned 0, which is meaningless without assertions in the TB.
    rtl_log = os.path.join(HLS_DIR, "tb_data", "rtl_cosim_results.log")
    if not os.path.exists(rtl_log):
        print(f"  [depth={depth}] WARN: rtl_cosim_results.log not found — treating as FAIL")
        return False
    result = subprocess.run(
        [sys.executable, VALIDATE_PY, HLS_DIR, "--quiet"],
        capture_output=False
    )
    return result.returncode == 0

# ── Power-of-2 search ─────────────────────────────────────────────────────────
candidates = []
d = 1
while d <= args.max_depth:
    candidates.append(d)
    d *= 2

print(f"Probing depths: {candidates}")
print("=" * 60)

best = None
try:
    for depth in candidates:
        set_depth(depth)
        passed = run_synth_cosim(depth)
        if passed:
            print(f"  [depth={depth}] PASS")
            best = depth
            break
        else:
            print(f"  [depth={depth}] FAIL")
finally:
    restore_cpp()

print("\n" + "=" * 60)
if best is None:
    print(f"No depth up to {args.max_depth} passed cosim.")
    print("Try --max-depth 512 or check for other issues.")
    sys.exit(1)

print(f"Minimum passing FIFO depth: {best}")
print(f"\nTo make permanent — update firmware/{os.path.basename(top_cpp)}:")
print(f"  Set all '#pragma HLS STREAM variable=... depth=' to {best}")
print(f"Then re-run synthesis:")
print(f"  cd {HLS_DIR} && {VITIS_HLS} -f build_prj.tcl \\")
print(f"      -tclargs 'reset=1 csim=0 synth=1 cosim=0 validation=0'")


