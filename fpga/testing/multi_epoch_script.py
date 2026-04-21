#!/usr/bin/env python3
"""Multi-epoch UART test for ecg_wrapper on FPGA.

Protocol sequence
-----------------
1. send_reset  — pulse soft_rst CSR (assert then deassert)
2. assert start — CSR with start=1 (latched by ctrl_reg)
3. send N epochs of samples back-to-back, each as 187 data packets
4. deassert start — CSR with start=0

Checking
--------
The DUT emits exactly one TX byte per completed inference (one per epoch).
Bits [4:0] of that byte carry the argmax one-hot; bits [7:5] are ap status
(ignored here — cap_status is always 0 in current RTL).

We collect exactly N bytes, one at a time, each with its own --byte-timeout.
Byte i is compared against ref_onehot[start_index + i - 1] (scoreboard-style
1-based start index, matching Mismatch[N] / Match[N] log lines).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import serial

FRAME_LEN = 187

DEFAULT_VECTOR_FILE = (
    Path(__file__).parent
    / "ecg_hil_uvm" / "tv" / "cdatafile"
    / "c.tiny_ecg_no_activ.autotvin_input_layer_3.dat"
)
DEFAULT_REF_FILE = Path(__file__).parent / "ecg_hil_uvm" / "tv" / "ref_onehot.txt"


# ---------------------------------------------------------------------------
# Data loading — mirrors data_loader.py: read every 0x... line flat,
# slice into FRAME_LEN-sample frames.  This matches the scoreboard exactly.
# ---------------------------------------------------------------------------

def _hex_lines(path: Path) -> list[int]:
    values = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.lower().startswith("0x"):
                values.append(int(line, 16))
    return values


def _load_frames(vector_file: Path, start_idx_0: int, num_epochs: int) -> list[list[int]]:
    """Return num_epochs frames starting at start_idx_0 (0-based).
    Slices flat hex values by FRAME_LEN — identical to data_loader.load_input_frames."""
    all_samples = [v & 0x3FF for v in _hex_lines(vector_file)]
    frames = []
    for i in range(num_epochs):
        epoch = start_idx_0 + i
        lo = epoch * FRAME_LEN
        hi = lo + FRAME_LEN
        if hi > len(all_samples):
            raise RuntimeError(
                f"vector file too short for epoch {epoch + 1}: "
                f"need sample [{lo}:{hi}], have {len(all_samples)}"
            )
        frames.append(all_samples[lo:hi])
    return frames


def _load_refs(ref_file: Path, start_idx_0: int, num_epochs: int) -> list[int]:
    """Return num_epochs one-hot bytes starting at start_idx_0 (0-based)."""
    all_refs = [v & 0x1F for v in _hex_lines(ref_file)]
    end = start_idx_0 + num_epochs
    if end > len(all_refs):
        raise RuntimeError(
            f"ref file has {len(all_refs)} entries, need up to index {end}"
        )
    return all_refs[start_idx_0:end]


# ---------------------------------------------------------------------------
# UART helpers — same pack / send conventions as smoke_script.py
# ---------------------------------------------------------------------------

def _pack_csr(soft_reset: int, start: int, mode: int = 0) -> int:
    return (
        ((soft_reset & 1) << 15)
        | ((start & 1) << 14)
        | ((mode & 1) << 13)
        | (1 << 12)          # bit[12]=1 → CSR packet
    )


def _pack_data(sample_10b: int) -> int:
    return sample_10b & 0x03FF   # bit[12]=0 → data packet


def _send_word(ser: serial.Serial, word: int) -> None:
    ser.write(bytes((word & 0xFF, (word >> 8) & 0xFF)))


def _format_word(label: str, word: int) -> str:
    b0 = word & 0xFF
    b1 = (word >> 8) & 0xFF
    return f"{label:<18} word=0x{word:04X} bytes=[0x{b0:02X}, 0x{b1:02X}]"


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def run_multi_epoch(
    port: str,
    baud: int,
    byte_timeout_s: float,
    vector_file: Path,
    ref_file: Path,
    start_index: int,   # scoreboard-style: 1-based
    num_epochs: int,
    print_first_n: int = 0,
) -> int:
    if start_index < 1:
        raise ValueError("start-index must be >= 1 (scoreboard-style 1-based)")
    if num_epochs < 1:
        raise ValueError("num-epochs must be >= 1")

    start_idx_0 = start_index - 1   # internal 0-based

    frames = _load_frames(vector_file, start_idx_0, num_epochs)
    refs   = _load_refs(ref_file, start_idx_0, num_epochs)

    total_samples = sum(len(f) for f in frames)
    print(f"port={port}  baud={baud}  byte-timeout={byte_timeout_s}s")
    print(f"epochs {start_index}..{start_index + num_epochs - 1}  "
          f"({num_epochs} epochs × {FRAME_LEN} samples = {total_samples} samples)")

    if print_first_n > 0:
        print("\nFirst transmitted words:")
        csr_reset_assert = _pack_csr(soft_reset=1, start=0)
        csr_reset_deassert = _pack_csr(soft_reset=0, start=0)
        csr_start_assert = _pack_csr(soft_reset=0, start=1)
        words = [
            ("csr_reset_assert", csr_reset_assert),
            ("csr_reset_deassert", csr_reset_deassert),
            ("csr_start_assert", csr_start_assert),
        ]
        for frame in frames:
            for i, sample in enumerate(frame):
                words.append((f"data_{i+1:03d}", _pack_data(sample)))
        for i, (label, word) in enumerate(words[:print_first_n], start=1):
            print(f"  {i:02d}: {_format_word(label, word)}")
        print()

    with serial.Serial(port=port, baudrate=baud, timeout=byte_timeout_s) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 1) send_reset pulse
        _send_word(ser, _pack_csr(soft_reset=1, start=0))
        _send_word(ser, _pack_csr(soft_reset=0, start=0))

        # 2) assert start
        _send_word(ser, _pack_csr(soft_reset=0, start=1))

        # 3) send all N epochs back-to-back
        for frame in frames:
            for sample in frame:
                _send_word(ser, _pack_data(sample))

        ser.flush()

        # 4) deassert start
        _send_word(ser, _pack_csr(soft_reset=0, start=0))

        # 5) collect N output bytes, one per epoch
        # Each DUT inference emits exactly one TX byte when done.
        # Bits [4:0] = argmax one-hot.  We wait up to byte_timeout_s per byte.
        results: list[int | None] = []
        for i in range(num_epochs):
            chunk = ser.read(1)
            results.append(chunk[0] if len(chunk) == 1 else None)

    # 6) compare
    passed = 0
    failed = 0
    timed_out = 0
    mismatch_rows: list[tuple[int, int, int, int]] = []
    timeout_indices: list[int] = []

    for i, (got_raw, expected_onehot) in enumerate(zip(results, refs)):
        scoreboard_idx = start_index + i
        if got_raw is None:
            timed_out += 1
            failed += 1
            timeout_indices.append(scoreboard_idx)
            print(f"  [{scoreboard_idx:3d}] TIMEOUT  expected=0x{expected_onehot:02X}")
            continue

        got_onehot = got_raw & 0x1F
        if got_onehot == expected_onehot:
            passed += 1
            print(f"  [{scoreboard_idx:3d}] PASS     got=0x{got_onehot:02X}  expected=0x{expected_onehot:02X}  raw=0x{got_raw:02X}")
        else:
            failed += 1
            mismatch_rows.append((scoreboard_idx, got_onehot, expected_onehot, got_raw))
            print(f"  [{scoreboard_idx:3d}] FAIL     got=0x{got_onehot:02X}  expected=0x{expected_onehot:02X}  raw=0x{got_raw:02X}")

    total = num_epochs
    mismatch_count = len(mismatch_rows)
    timeout_count = len(timeout_indices)
    error_count = mismatch_count + timeout_count

    mismatch_pct = (100.0 * mismatch_count / total) if total else 0.0
    timeout_pct = (100.0 * timeout_count / total) if total else 0.0
    error_pct = (100.0 * error_count / total) if total else 0.0
    pass_pct = (100.0 * passed / total) if total else 0.0

    print()
    print(f"Summary: {passed} passed / {failed} failed")
    print(f"Pass percentage      : {pass_pct:.2f}%")
    print(f"Mismatch percentage  : {mismatch_pct:.2f}% ({mismatch_count}/{total})")
    print(f"Timeout percentage   : {timeout_pct:.2f}% ({timeout_count}/{total})")
    print(f"Total error percent  : {error_pct:.2f}% ({error_count}/{total})")

    if mismatch_rows:
        print("Mismatch details:")
        for idx, got_oh, exp_oh, raw in mismatch_rows:
            print(
                f"  idx={idx:3d} got=0x{got_oh:02X} expected=0x{exp_oh:02X} raw=0x{raw:02X}"
            )

    if timeout_indices:
        print("Timeout indices:", " ".join(str(i) for i in timeout_indices))

    return 0 if failed == 0 else 1


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-epoch FPGA UART test")
    p.add_argument("--port",         required=True,    help="Serial device, e.g. /dev/ttyUSB0")
    p.add_argument("--baud",         type=int,   default=115200, help="UART baud rate")
    p.add_argument("--byte-timeout", type=float, default=5.0,
                   help="Per-byte read timeout in seconds (default 5.0)")
    p.add_argument("--start-index",  type=int,   default=1,
                   help="First epoch to run, scoreboard-style 1-based (default 1)")
    p.add_argument("--num-epochs",   type=int,   default=10,
                   help="Number of epochs to send (default 10)")
    p.add_argument("--print-first-n", type=int, default=0,
                   help="Print first N UART words transmitted (0=none)")
    p.add_argument("--vector-file",  type=Path,  default=DEFAULT_VECTOR_FILE)
    p.add_argument("--ref-file",     type=Path,  default=DEFAULT_REF_FILE)
    return p


def main() -> int:
    args = _build_argparser().parse_args()
    try:
        return run_multi_epoch(
            port=args.port,
            baud=args.baud,
            byte_timeout_s=args.byte_timeout,
            vector_file=args.vector_file,
            ref_file=args.ref_file,
            start_index=args.start_index,
            num_epochs=args.num_epochs,
            print_first_n=args.print_first_n,
        )
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
