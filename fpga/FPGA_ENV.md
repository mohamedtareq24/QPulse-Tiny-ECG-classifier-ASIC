# FPGA Verification Environment

## Purpose

This Folder combines FPGA build collateral with a Python-based Hardware-In-the-Loop (HIL) verification environment.

The verification flow is centered on:

- Decoupling cocotb runtime/bootstrap from verification behavior.
- Reusing pyUVM sequences and components across tests.
- Running a HIL variant that targets real UART-connected hardware.

## High-Level Architecture

The HIL execution path is:

1. `testing/run_hil.py` parses CLI args and builds environment config.
2. Runtime config is stored through `testing/ecg_uvm/runtime.py`.
3. pyUVM test is launched via `uvm_root().run_test(...)`.
4. `ECGEnv` builds TX/RX UVCs, scoreboard, and coverage.
5. TX sequences generate control/data packets to DUT over UART.
6. RX monitor captures DUT response bytes.
7. Scoreboard compares observed one-hot outputs to reference data.

## Decoupling of cocotb and pyUVM

The environment intentionally keeps cocotb light and puts behavior in pyUVM. This separation makes the verification logic portable — in HIL mode, cocotb is removed entirely and replaced by a pure asyncio runner.

### Simulation mode: cocotb responsibilities

- Process bootstrap and simulator handshake.
- Logging setup and sim-time context.
- Test entry invocation (`uvm_root().run_test`).
- Async runtime hosting via cocotb's event loop.

### HIL mode: asyncio runner responsibilities

- `testing/run_hil.py` replaces cocotb as the entry point.
- Launches `uvm_root().run_test(...)` directly under `asyncio.run()`.
- No simulator backend required; pyuvm internals are patched to use asyncio primitives.

### pyUVM responsibilities

- Verification architecture and test composition (`ECGEnv`, tests, UVCs).
- Stimulus generation (sequence library).
- Protocol item modeling (sequence items for CSR/data packets).
- Checking and reporting (scoreboard, coverage).

This split keeps the verification logic identical across simulation and hardware bring-up.

## pyUVM HIL Variant

The HIL variant replaces simulator interfaces with serial transport while preserving UVM structure.

### HIL configuration

- `testing/ecg_uvm/cfg.py`
  - `ECGEnvConfig.from_env()` reads HIL variables such as:
    - `HIL_SERIAL_PORT`
    - `HIL_BAUD_RATE`
    - `HIL_BYTE_TIMEOUT`
    - `HIL_RESP_TIMEOUT`
    - frame/test data paths

### HIL transport abstraction

- `testing/ecg_uvm/transport.py`
  - `HilSerialTransport` wraps async serial I/O.
  - Explicit flow control disable is used for stable FTDI operation:
    - `rtscts=False`
    - `dsrdtr=False`
    - `xonxoff=False`
  - Handles open/close/read/write and timeout paths used by UVC components.

### Why this variant is useful

- Keeps test intent and sequence reuse identical between simulation and hardware bring-up.
- Isolates hardware communication details in one transport layer.
- Enables controlled debug of UART-level behavior with pyUVM reporting.

### pyuvm asyncio patches

Because pyuvm 4.0.1 is tightly coupled to cocotb, running outside a simulator requires
patching 7 pyuvm source files to replace cocotb primitives with asyncio equivalents.

A pre-patched virtual environment is kept at the project root:

```
/home/zkp_egy2/Desktop/old_desktop/Tarek/ECG/.venv_hil/
```

Files patched in `lib/python3.10/site-packages/pyuvm/`:

| File | Patch summary |
|---|---|
| `_utils.py` | Removed cocotb import; `cocotb_version_info` hardcoded to `(2,0,0)` |
| `s05_base_classes.py` | `get_sim_time` stub that returns `0` |
| `s06_reporting_classes.py` | `FormatterBase = logging.Formatter`; no-op `SimTimeContextFilter` |
| `s09_phasing.py` | `cocotb.start_soon()` → `asyncio.get_event_loop().create_task()` |
| `s13_uvm_component.py` | Same formatter/filter patch as `s06` |
| `s14_15_python_sequences.py` | `from asyncio import Event as CocotbEvent` |
| `utility_classes.py` | `cocotb.queue.Queue` → `asyncio.Queue`; `NullTrigger()` → `asyncio.sleep(0)` |

## How to Run

### Simulation (cocotb/icarus)

From `testing/`:

```bash
pip install -r requirements.txt
make sim TEST=ECGSmokeTest
make sim TEST=ECGMiniRegressionTest UART_BAUDDIV=16 BAUDDIV_SIM=16
```

### HIL (physical FPGA over UART)

Requires `.venv_hil` at project root (see pyuvm asyncio patches above).

Direct invocation:

```bash
VENV=/home/zkp_egy2/Desktop/old_desktop/Tarek/ECG/.venv_hil
VERF=./testing
PYTHONPATH="$VERF:$VERF/pyuvm_ecg" \
  $VENV/bin/python $VERF/run_hil.py \
    --test ECGSmokeTest \
    --port /dev/ttyUSB0 \
    --baud 115200 \
    --timeout 10.0
```

Or via make:

```bash
make hil-test HIL_TEST=ECGNEpochTest HIL_NUM_FRAMES=2000 HIL_BYTE_TIMEOUT=10 HIL_TIMEOUT=120
```
