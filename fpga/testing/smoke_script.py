#!/usr/bin/env python3
"""Minimal UART smoke test for ecg_wrapper on FPGA.

Sequence:
1) send_reset
2) send_start
3) send first test vector (epoch 0)
4) wait for one output byte
5) compare output one-hot vs first reference
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial


DEFAULT_VECTOR_FILE = Path(__file__).parent / "ecg_hil_uvm" / "tv" / "cdatafile" / "c.tiny_ecg_no_activ.autotvin_input_layer_3.dat"
DEFAULT_REF_FILE = Path(__file__).parent / "ecg_hil_uvm" / "tv" / "ref_onehot.txt"


def _parse_transaction_samples(path: Path, txn_index: int) -> list[int]:
    if txn_index < 0:
        raise ValueError("txn_index must be >= 0")

    samples: list[int] = []
    in_txn = False
    current_idx = -1

    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("[[transaction]]"):
                current_idx += 1
                in_txn = current_idx == txn_index
                continue

            if line.startswith("[[/transaction]]"):
                if in_txn:
                    break
                continue

            if not in_txn:
                continue

            if line.startswith("0x"):
                samples.append(int(line, 16) & 0x03FF)

    if not samples:
        raise RuntimeError(f"No samples found for transaction index {txn_index}: {path}")

    return samples


def _parse_ref_onehot(path: Path, ref_index: int) -> int:
    if ref_index < 0:
        raise ValueError("ref_index must be >= 0")

    current_idx = -1
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("0x"):
                current_idx += 1
                if current_idx == ref_index:
                    return int(line, 16) & 0x1F

    raise RuntimeError(f"No reference one-hot value found for index {ref_index}: {path}")


def _pack_control_word(soft_reset: int, start: int, mode: int = 0) -> int:
    # [15]=soft_reset, [14]=start, [13]=mode, [12]=csr_sel=1
    return ((soft_reset & 1) << 15) | ((start & 1) << 14) | ((mode & 1) << 13) | (1 << 12)


def _pack_data_word(sample_10b: int) -> int:
    # Data packet: [12]=0, payload in [9:0]
    return sample_10b & 0x03FF


def _send_word_lsb_first(ser: serial.Serial, word: int) -> None:
    b0 = word & 0xFF
    b1 = (word >> 8) & 0xFF
    ser.write(bytes((b0, b1)))


def _format_word(label: str, word: int) -> str:
    b0 = word & 0xFF
    b1 = (word >> 8) & 0xFF
    return f"{label:<18} word=0x{word:04X} bytes=[0x{b0:02X}, 0x{b1:02X}]"


def run_smoke(
    port: str,
    baud: int,
    timeout_s: float,
    vector_file: Path,
    ref_file: Path,
    vector_index: int,
    print_first_n: int = 0,
) -> int:
    if vector_index < 1:
        raise ValueError("vector_index must be >= 1 (scoreboard-style indexing)")

    # Scoreboard prints compare indices starting at 1 (Mismatch[1], Match[1], ...).
    data_index = vector_index - 1

    samples = _parse_transaction_samples(vector_file, data_index)
    expected_onehot = _parse_ref_onehot(ref_file, data_index)

    print(f"Using port={port} baud={baud}")
    print(f"Vector index (scoreboard): {vector_index}")
    print(f"Vector samples: {len(samples)}")
    print(f"Expected one-hot: 0x{expected_onehot:02X}")

    if print_first_n > 0:
        print("\nFirst transmitted words:")
        csr_reset_assert = _pack_control_word(1, 0)
        csr_reset_deassert = _pack_control_word(0, 0)
        csr_start_assert = _pack_control_word(0, 1)
        words = [
            ("csr_reset_assert", csr_reset_assert),
            ("csr_reset_deassert", csr_reset_deassert),
            ("csr_start_assert", csr_start_assert),
        ]
        for i, sample in enumerate(samples):
            words.append((f"data_{i+1:03d}", _pack_data_word(sample)))
        for i, (label, word) in enumerate(words[:print_first_n], start=1):
            print(f"  {i:02d}: {_format_word(label, word)}")
        print()

    with serial.Serial(port=port, baudrate=baud, timeout=timeout_s) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 1) send_reset pulse (assert then deassert)
        _send_word_lsb_first(ser, _pack_control_word(soft_reset=1, start=0, mode=0))
        _send_word_lsb_first(ser, _pack_control_word(soft_reset=0, start=0, mode=0))

        # 2) send_start
        _send_word_lsb_first(ser, _pack_control_word(soft_reset=0, start=1, mode=0))

        # 3) send first test vector (epoch 0)
        for sample in samples:
            _send_word_lsb_first(ser, _pack_data_word(sample))

        ser.flush()

        # 4) wait_for_the_output
        rx = ser.read(1)

    if len(rx) != 1:
        print("FAIL: no output byte received before timeout")
        return 2

    observed = rx[0]
    observed_onehot = observed & 0x1F

    print(f"Observed raw byte: 0x{observed:02X}")
    print(f"Observed one-hot: 0x{observed_onehot:02X}")

    # 5) compare output vs reference
    if observed_onehot != expected_onehot:
        print(
            "FAIL: mismatch "
            f"expected=0x{expected_onehot:02X} observed=0x{observed_onehot:02X}"
        )
        return 1

    print("PASS: smoke test matched reference")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Simple FPGA UART smoke test")
    p.add_argument("--port", required=True, help="UART device, e.g. /dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200, help="UART baud rate")
    p.add_argument("--timeout", type=float, default=2.0, help="Read timeout in seconds")
    p.add_argument(
        "--vector-index",
        type=int,
        default=1,
        help="Scoreboard-style epoch index (1-based)",
    )
    p.add_argument("--print-first-n", type=int, default=0,
                   help="Print first N UART words transmitted (0=none)")
    p.add_argument("--vector-file", type=Path, default=DEFAULT_VECTOR_FILE)
    p.add_argument("--ref-file", type=Path, default=DEFAULT_REF_FILE)
    return p


def main() -> int:
    args = _build_argparser().parse_args()
    try:
        return run_smoke(
            port=args.port,
            baud=args.baud,
            timeout_s=args.timeout,
            vector_file=args.vector_file,
            ref_file=args.ref_file,
            vector_index=args.vector_index,
            print_first_n=args.print_first_n,
        )
    except Exception as exc:  # Keep failure output simple and explicit.
        print(f"FAIL: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
