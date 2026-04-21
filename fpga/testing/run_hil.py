#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# cocotb is co-installed with pyuvm in this venv; its sim-time log filter
# crashes when no simulator backend is present.  Patch it before any other
# import so the pure-Python asyncio HIL path runs cleanly.
# ---------------------------------------------------------------------------
try:
    import cocotb.logging as _cocotb_logging
    _cocotb_logging.get_sim_time = lambda: (0, 0)
except Exception:
    pass

import argparse
import asyncio
import os

from pyuvm import uvm_root

# Import tests so pyuvm factory registers all classes.
from ecg_hil_uvm.tests.test_lib import (  # noqa: F401
    ECGDropStartNegativeTest,
    ECGFullDatasetTest,
    ECGFullDatasetResetEveryFiveEpochsTest,
    ECGIdleBetweenEpochsTest,
    ECGMidEpochResetReplayTest,
    ECGMiniRegressionTest,
    ECGQualifierToggleTest,
    ECGReservedBitsToggleTest,
    ECGReservedBitsWalkingTest,
    ECGSmokeTest,
    ECGSoftResetMidEpochNoRestartTest,
    ECGSoftResetMidEpochRetryTest,
    ECGSoftResetMidMultiEpochTest,
    ECGSoftResetTest,
    ECGTenEpochTest,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ECG pyuvm tests over physical UART HIL")
    parser.add_argument("--test", default="ECGSmokeTest", help="pyuvm test class name")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate")
    parser.add_argument("--num-frames", type=int, default=None, help="Override ECG_NUM_FRAMES for epoch-count tests")
    parser.add_argument("--timeout", type=float, default=10.0, help="Response timeout in seconds")
    parser.add_argument("--byte-timeout", type=float, default=2.0, help="Per-byte timeout in seconds")
    return parser.parse_args()


def _configure_env(args: argparse.Namespace) -> None:
    os.environ["UVM_TESTNAME"] = args.test
    os.environ["HIL_SERIAL_PORT"] = args.port
    os.environ["HIL_BAUD_RATE"] = str(args.baud)
    if args.num_frames is not None:
        os.environ["ECG_NUM_FRAMES"] = str(args.num_frames)
    os.environ["HIL_RESP_TIMEOUT"] = str(args.timeout)
    os.environ["HIL_BYTE_TIMEOUT"] = str(args.byte_timeout)


async def _main() -> None:
    args = _parse_args()
    _configure_env(args)
    await uvm_root().run_test(args.test)


if __name__ == "__main__":
    asyncio.run(_main())
