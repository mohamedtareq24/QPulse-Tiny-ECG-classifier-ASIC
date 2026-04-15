#!/usr/bin/env python3
"""
parallel_cosim.py — Run csim + cosim across N worker copies of the HLS project in parallel.

Strategy:
  1. Split tb_data into N shards
  2. Copy hls_dir N times (synthesis output reused via reset=0 — no re-synth)
  3. Run csim=1 cosim=1 in each worker simultaneously
  4. Merge results in shard order → hls_dir/tb_data/
  5. Run validate_cosim.py on merged output

Usage:
    python3 parallel_cosim.py <hls_dir> [--workers N]
    make RUN=.. parallel_cosim WORKERS=20
"""

import argparse, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
VALIDATE_PY = os.path.join(SCRIPT_DIR, "validate_cosim.py")

parser = argparse.ArgumentParser()
parser.add_argument("hls_dir")
parser.add_argument("--workers",         type=int, default=20)
parser.add_argument("--vitis-hls",       default=None,
                    help="Path to vitis_hls binary (defaults to VITIS_HLS/XILINX_HLS/PATH)")
parser.add_argument("--vivado-settings", default=None,
                    help="Path to Vivado settings64.sh (optional)")
parser.add_argument("--work-dir",        default=None)
parser.add_argument("--keep-workers",    action="store_true")
args = parser.parse_args()

HLS_DIR         = os.path.abspath(args.hls_dir)


def resolve_vitis_hls(explicit):
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("VITIS_HLS"):
        candidates.append(os.environ["VITIS_HLS"])
    if os.environ.get("XILINX_HLS"):
        candidates.append(os.path.join(os.environ["XILINX_HLS"], "bin", "vitis_hls"))
    candidates.append("vitis_hls")

    for c in candidates:
        if not c:
            continue
        if "/" in c:
            if os.path.isfile(c):
                return c
        else:
            found = shutil.which(c)
            if found:
                return found
    return None


def resolve_vivado_settings(explicit):
    candidates = [explicit, os.environ.get("VIVADO_SETTINGS")]
    if os.environ.get("XILINX_VIVADO"):
        candidates.append(os.path.join(os.environ["XILINX_VIVADO"], "settings64.sh"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


VITIS_HLS = resolve_vitis_hls(args.vitis_hls)
if not VITIS_HLS:
    sys.exit("ERROR: vitis_hls not found. Set --vitis-hls or VITIS_HLS/XILINX_HLS, or add vitis_hls to PATH.")

VIVADO_SETTINGS = resolve_vivado_settings(args.vivado_settings)
if not VIVADO_SETTINGS:
    print("INFO: Vivado settings not provided/found; relying on current shell environment.")

# ── Find project name ─────────────────────────────────────────────────────────
PRJ_NAME = None
for tcl in ("build_prj.tcl", "project.tcl"):
    p = os.path.join(HLS_DIR, tcl)
    if not os.path.exists(p): continue
    for line in open(p):
        m = re.search(r'set project_name\s+"(\S+)"', line)
        if m: PRJ_NAME = m.group(1); break
    if PRJ_NAME: break
if not PRJ_NAME:
    sys.exit("ERROR: could not find set project_name in TCL files")

synth_dir = os.path.join(HLS_DIR, f"{PRJ_NAME}_prj", "solution1", "syn")
if not os.path.isdir(synth_dir):
    sys.exit(f"ERROR: no synthesis output at {synth_dir}\n"
             f"       Run 'make synth' first before parallel_cosim.")

# ── Load tb_data ──────────────────────────────────────────────────────────────
tb_dir = os.path.join(HLS_DIR, "tb_data")

def load_lines(path):
    with open(path) as f: return [l for l in f if l.strip()]

feat_path  = os.path.join(tb_dir, "tb_input_features.dat")
pred_path  = os.path.join(tb_dir, "tb_output_predictions.dat")
label_path = os.path.join(tb_dir, "tb_labels_predictions.dat")

for p in (feat_path, pred_path):
    if not os.path.exists(p):
        sys.exit(f"ERROR: missing tb_data file: {p}\n       Run 'make tbdata' first.")

feat_lines  = load_lines(feat_path)
pred_lines  = load_lines(pred_path)
label_lines = load_lines(label_path) if os.path.exists(label_path) else None

total     = len(feat_lines)
n_workers = min(args.workers, total)
chunk     = (total + n_workers - 1) // n_workers  # ceiling division

print(f"Project       : {PRJ_NAME}")
print(f"Total samples : {total}")
print(f"Workers       : {n_workers}  (~{chunk} samples each)")

# ── Create worker dirs ────────────────────────────────────────────────────────
work_base = os.path.abspath(args.work_dir) if args.work_dir \
    else os.path.join(os.path.dirname(HLS_DIR), "_parallel_cosim_workers")
os.makedirs(work_base, exist_ok=True)
print(f"Worker base   : {work_base}\n")

worker_tasks = []
for i in range(n_workers):
    s = slice(i * chunk, (i + 1) * chunk)
    shard_feat = feat_lines[s]
    if not shard_feat: break

    wdir = os.path.join(work_base, f"worker_{i:02d}")
    if os.path.exists(wdir): shutil.rmtree(wdir)
    print(f"  Copying → worker_{i:02d}/  ({len(shard_feat)} samples) ...", flush=True)
    shutil.copytree(HLS_DIR, wdir)

    wtb = os.path.join(wdir, "tb_data")
    os.makedirs(wtb, exist_ok=True)
    # Remove stale result logs from the copied HLS_DIR so we never merge old data
    for stale in ("csim_results.log", "rtl_cosim_results.log"):
        p = os.path.join(wtb, stale)
        if os.path.exists(p):
            os.remove(p)
    with open(os.path.join(wtb, "tb_input_features.dat"),    "w") as f: f.writelines(shard_feat)
    with open(os.path.join(wtb, "tb_output_predictions.dat"),"w") as f: f.writelines(pred_lines[s])
    if label_lines:
        with open(os.path.join(wtb, "tb_labels_predictions.dat"), "w") as f: f.writelines(label_lines[s])

    worker_tasks.append((i, wdir, len(shard_feat)))

print(f"\nLaunching {len(worker_tasks)} parallel jobs...\n")

# ── Worker function ───────────────────────────────────────────────────────────
def run_worker(i, wdir):
    log_path = os.path.join(wdir, "worker.log")
    # reset=0 reuses existing synthesis output — no re-synthesis
    cmd_parts = []
    if VIVADO_SETTINGS:
        cmd_parts.append(f'. "{VIVADO_SETTINGS}" >/dev/null 2>&1')
    cmd_parts.append(f'cd "{wdir}"')
    cmd_parts.append(
        f'"{VITIS_HLS}" -f build_prj.tcl '
        f'-tclargs reset=0 csim=1 synth=0 cosim=1 validation=0 fifo_opt=0'
    )
    cmd = " && ".join(cmd_parts)
    with open(log_path, "w") as log:
        ret = subprocess.run(["bash", "-c", cmd], stdout=log, stderr=subprocess.STDOUT)
    wtb      = os.path.join(wdir, "tb_data")
    has_rtl  = os.path.exists(os.path.join(wtb, "rtl_cosim_results.log"))
    has_csim = os.path.exists(os.path.join(wtb, "csim_results.log"))
    # File existence is the real success criterion.
    # vitis_hls may return non-zero due to license contention or the built-in
    # C/RTL validation diff — we still collect output if the files are present.
    ok = has_rtl and has_csim
    if ret.returncode != 0 and ok:
        with open(os.path.join(wdir, "worker.log"), "a") as log:
            log.write(f"\nWARN: vitis_hls exit code {ret.returncode} but output files present — treating as OK\n")
    return i, wdir, ok, has_rtl, has_csim

# ── Execute in parallel ───────────────────────────────────────────────────────
results = {}
with ThreadPoolExecutor(max_workers=n_workers) as pool:
    futures = {pool.submit(run_worker, i, wdir): i for i, wdir, _ in worker_tasks}
    for future in as_completed(futures):
        i, wdir, ok, has_rtl, has_csim = future.result()
        rc_warn = f" (rc={results.get(i, (None,))[0]})" if not ok else ""
        print(
            f"  worker_{i:02d}: {'OK  ' if ok else 'FAIL'}  "
            f"{'rtl✓' if has_rtl else 'rtl✗'}  "
            f"{'csim✓' if has_csim else 'csim✗'}",
            flush=True
        )
        results[i] = (wdir, ok, has_rtl, has_csim)

print()

# ── Merge in shard order ──────────────────────────────────────────────────────
merged_rtl, merged_csim, any_missing = [], [], False

for i, wdir, _ in sorted(worker_tasks):
    _, ok, has_rtl, has_csim = results[i]
    wtb = os.path.join(wdir, "tb_data")
    if has_rtl:
        merged_rtl.extend(load_lines(os.path.join(wtb, "rtl_cosim_results.log")))
    else:
        print(f"  WARN: worker_{i:02d} missing rtl log — see {wdir}/worker.log")
        any_missing = True
    if has_csim:
        merged_csim.extend(load_lines(os.path.join(wtb, "csim_results.log")))
    else:
        print(f"  WARN: worker_{i:02d} missing csim log — see {wdir}/worker.log")

def write_lines(path, lines):
    with open(path, "w") as f:
        for l in lines: f.write(l if l.endswith("\n") else l + "\n")

write_lines(os.path.join(tb_dir, "rtl_cosim_results.log"), merged_rtl)
write_lines(os.path.join(tb_dir, "csim_results.log"),      merged_csim)
print(f"Merged RTL cosim : {len(merged_rtl)} rows → {os.path.join(tb_dir, 'rtl_cosim_results.log')}")
print(f"Merged C sim     : {len(merged_csim)} rows → {os.path.join(tb_dir, 'csim_results.log')}")

# ── Cleanup ───────────────────────────────────────────────────────────────────
if not args.keep_workers:
    print(f"\nCleaning up {work_base} ...")
    shutil.rmtree(work_base, ignore_errors=True)
else:
    print(f"\nWorker dirs preserved at: {work_base}")

if any_missing:
    sys.exit("ERROR: some workers failed — check worker.log files")

# ── Validate ──────────────────────────────────────────────────────────────────
# Compare merged RTL against merged csim (both have the same N rows and represent
# the same samples). The original tb_output_predictions.dat has all 10000 rows
# and would cause a row-count mismatch if used directly.
print(f"\nValidating {len(merged_rtl)} samples (RTL cosim vs C sim)...")
ret = subprocess.run(
    [sys.executable, VALIDATE_PY, HLS_DIR,
     "--ref", os.path.join(tb_dir, "csim_results.log")]
)
sys.exit(ret.returncode)
