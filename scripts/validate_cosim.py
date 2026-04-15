#!/usr/bin/env python3
"""
validate_cosim.py — Compare RTL co-simulation output against references.

Reads:
  <hls_dir>/tb_data/rtl_cosim_results.log           — C-model output written during cosim setup
                                                        (space-separated floats, used for Keras cmp)
  <hls_dir>/tb_data/tb_output_predictions.dat        — Keras float32 reference
  <hls_dir>/**/sim/tv/cdatafile/c.*.autotvout_*.dat  — C-model transaction vectors (Vitis HLS TV)
  <hls_dir>/**/sim/tv/rtldatafile/rtl.*.autotvout_*.dat — RTL transaction vectors (Vitis HLS TV)

Comparisons performed:
  1. RTL vs Keras  — argmax match + optional tolerance, using the C-model float log as proxy
  2. RTL vs C      — true RTL correctness check via Vitis HLS transaction vectors;
                     each vector packs 5 x 10-bit fields into 16-bit slots;
                     C sign-extends, RTL zero-pads — only the lower 10 bits are compared.

Exit code: 0 = all comparisons PASS, 1 = any FAIL

Usage:
    python3 validate_cosim.py <hls_dir>
    python3 validate_cosim.py <hls_dir> --tol 0.5
    python3 validate_cosim.py <hls_dir> --no-tv     # skip RTL vs C transaction vector check
"""

import argparse
import glob
import os
import re
import sys

parser = argparse.ArgumentParser()
parser.add_argument("hls_dir", help="HLS project directory (contains tb_data/)")
parser.add_argument(
    "--ref",
    default=None,
    help="Alternative Keras reference file (default: tb_data/tb_output_predictions.dat)",
)
parser.add_argument(
    "--tol",
    type=float,
    default=None,
    help="Optional max absolute error tolerance per element (in addition to argmax check)",
)
parser.add_argument(
    "--quiet",
    action="store_true",
    help="Only print summary line, not per-row results",
)
parser.add_argument(
    "--no-tv",
    action="store_true",
    help="Skip the RTL vs C transaction vector comparison",
)
args = parser.parse_args()

hls_dir = os.path.abspath(args.hls_dir)
rtl_log = os.path.join(hls_dir, "tb_data", "rtl_cosim_results.log")
ref_dat = args.ref if args.ref else os.path.join(hls_dir, "tb_data", "tb_output_predictions.dat")

if not os.path.exists(rtl_log):
    sys.exit(f"ERROR: RTL cosim results not found: {rtl_log}")
if not os.path.exists(ref_dat):
    sys.exit(f"ERROR: Keras reference not found: {ref_dat}")


# ── helpers ───────────────────────────────────────────────────

def load_matrix(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append([float(x) for x in line.split()])
    return rows


def compare_floats(a_rows, b_rows, a_label, b_label, tol, quiet):
    """Compare two float matrices row-by-row (argmax + optional tolerance)."""
    if len(a_rows) != len(b_rows):
        print(f"FAIL: row count mismatch — {a_label} has {len(a_rows)} rows, {b_label} has {len(b_rows)} rows")
        return False

    n = len(a_rows)
    argmax_ok = 0
    max_abs_err = 0.0
    mismatch_rows = []

    for i, (a, b) in enumerate(zip(a_rows, b_rows)):
        if len(a) != len(b):
            print(f"FAIL: row {i} width mismatch — {a_label} {len(a)} cols vs {b_label} {len(b)} cols")
            return False

        a_argmax = a.index(max(a))
        b_argmax = b.index(max(b))
        row_max_err = max(abs(x - y) for x, y in zip(a, b))
        max_abs_err = max(max_abs_err, row_max_err)
        match = a_argmax == b_argmax

        if match:
            argmax_ok += 1
        else:
            mismatch_rows.append(i)

        if not quiet:
            status = "OK" if match else "MISMATCH"
            print(f"  [{i:3d}]  argmax {a_label}={a_argmax}  {b_label}={b_argmax}  {status:8s}  max_err={row_max_err:.4f}")

    print()
    print(f"Argmax accuracy : {argmax_ok}/{n} ({100 * argmax_ok / n:.1f}%)")
    print(f"Max abs error   : {max_abs_err:.4f}")

    if mismatch_rows:
        print(f"Mismatch rows   : {mismatch_rows}")

    tol_ok = True
    if tol is not None:
        tol_ok = max_abs_err <= tol
        status = "PASS" if tol_ok else "FAIL"
        print(f"Tolerance check : {max_abs_err:.4f} <= {tol}  →  {status}")

    passed = (argmax_ok == n) and tol_ok
    print()
    print("PASS" if passed else "FAIL")
    return passed


def parse_tv_file(path):
    """Parse a Vitis HLS transaction vector dat file.
    Returns dict: transaction_id (int) -> hex_string (without '0x' prefix).
    """
    transactions = {}
    current_id = None
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            m = re.match(r'\[\[transaction\]\]\s+(\d+)', line)
            if m:
                current_id = int(m.group(1))
            elif line.startswith('0x') and current_id is not None:
                transactions[current_id] = line[2:]
                current_id = None
    return transactions


def compare_tv(c_path, rtl_path, n_fields=5, field_bits=16, data_bits=10, quiet=False):
    """Compare C vs RTL transaction vectors, checking only the lower data_bits per field.

    C sign-extends into the upper bits; RTL zero-pads — masking with (1<<data_bits)-1
    makes both representations directly comparable.
    """
    MASK = (1 << data_bits) - 1
    hex_per_field = field_bits // 4

    c_txns   = parse_tv_file(c_path)
    rtl_txns = parse_tv_file(rtl_path)

    print(f"  C   transactions : {len(c_txns)}")
    print(f"  RTL transactions : {len(rtl_txns)}")

    if not rtl_txns:
        print()
        print("FAIL: RTL transaction file is empty — simulation did not complete.")
        return False

    all_ids = sorted(set(c_txns) | set(rtl_txns))
    field_mismatches = []
    missing_rtl = []
    missing_c   = []

    for txn_id in all_ids:
        if txn_id not in rtl_txns:
            missing_rtl.append(txn_id)
            continue
        if txn_id not in c_txns:
            missing_c.append(txn_id)
            continue

        hex_c   = c_txns[txn_id].zfill(n_fields * hex_per_field)
        hex_rtl = rtl_txns[txn_id].zfill(n_fields * hex_per_field)

        c_fields   = [int(hex_c  [i*hex_per_field:(i+1)*hex_per_field], 16) & MASK for i in range(n_fields)]
        rtl_fields = [int(hex_rtl[i*hex_per_field:(i+1)*hex_per_field], 16) & MASK for i in range(n_fields)]

        if c_fields != rtl_fields:
            diffs = [(i, hex(c_fields[i]), hex(rtl_fields[i]))
                     for i in range(n_fields) if c_fields[i] != rtl_fields[i]]
            field_mismatches.append((txn_id, diffs))
            if not quiet:
                print(f"  MISMATCH txn {txn_id:4d}: {diffs}")

    n_compared = len(all_ids) - len(missing_rtl) - len(missing_c)
    n_fail     = len(field_mismatches)
    n_pass     = n_compared - n_fail

    print()
    print(f"Transactions compared : {n_compared}")
    print(f"Passed                : {n_pass}")
    print(f"Failed                : {n_fail}")
    if missing_rtl:
        print(f"Missing in RTL        : {len(missing_rtl)}  ids={missing_rtl[:10]}{'...' if len(missing_rtl)>10 else ''}")
    if missing_c:
        print(f"Missing in C          : {len(missing_c)}")
    if field_mismatches:
        print(f"Mismatch txn IDs      : {[m[0] for m in field_mismatches]}")

    passed = (n_fail == 0) and (not missing_rtl) and (not missing_c)
    print()
    print("PASS" if passed else "FAIL")
    return passed


def find_tv_pairs(hls_dir):
    """Glob for matching C/RTL transaction vector dat file pairs under hls_dir."""
    c_pat   = os.path.join(hls_dir, "**", "sim", "tv", "cdatafile",   "c.*.autotvout_*.dat")
    rtl_pat = os.path.join(hls_dir, "**", "sim", "tv", "rtldatafile", "rtl.*.autotvout_*.dat")

    def port_key(path):
        return re.search(r'autotvout_(.+)\.dat$', path).group(1)

    c_map   = {port_key(p): p for p in glob.glob(c_pat,   recursive=True)}
    rtl_map = {port_key(p): p for p in glob.glob(rtl_pat, recursive=True)}

    return [(port, c_map[port], rtl_map[port])
            for port in sorted(set(c_map) & set(rtl_map))]


# ── Comparison 1: RTL vs Keras ────────────────────────────────
rtl = load_matrix(rtl_log)
ref = load_matrix(ref_dat)

print("=" * 60)
print("Comparison 1: RTL vs Keras (float32 reference)")
print("=" * 60)
pass1 = compare_floats(rtl, ref, "RTL", "Keras", args.tol, args.quiet)

# ── Comparison 2: RTL vs C (transaction vectors) ─────────────
pass2 = True
if not args.no_tv:
    pairs = find_tv_pairs(hls_dir)
    if not pairs:
        print()
        print("NOTE: No transaction vector dat files found — run cosim_design first.")
        print(f"      Searched under: {hls_dir}/**/sim/tv/")
    else:
        for port, c_path, rtl_path in pairs:
            print()
            print("=" * 60)
            print(f"Comparison 2: RTL vs C — output port '{port}'")
            print(f"  C  : {os.path.relpath(c_path,   hls_dir)}")
            print(f"  RTL: {os.path.relpath(rtl_path, hls_dir)}")
            print("=" * 60)
            pass2 &= compare_tv(c_path, rtl_path, quiet=args.quiet)

overall_pass = pass1 and pass2
sys.exit(0 if overall_pass else 1)
