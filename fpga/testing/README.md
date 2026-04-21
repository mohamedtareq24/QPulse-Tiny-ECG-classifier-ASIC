# pyuvm Asyncio Patches — HIL Backend

## Background

pyuvm 4.0.1 is tightly coupled to cocotb. Every internal module imports cocotb
primitives for scheduling, synchronisation, and time reporting. This causes
immediate import failures when no simulator backend is present.

To enable HIL testing against real hardware without a simulator, 7 pyuvm source
files were patched to replace all cocotb primitives with standard `asyncio`
equivalents. The patched library is published at:

```
https://github.com/mohamedtareq24/pyuvm-asyncio-HIL  (branch: asyncio-hil)
```

Install with:

```bash
pip install "git+https://github.com/mohamedtareq24/pyuvm-asyncio-HIL@asyncio-hil"
```

---

## Patched Files

### `pyuvm/_utils.py`

**Problem:** Imported cocotb to read its version tuple, crashing without a simulator.

**Fix:** Removed the cocotb import. Hardcoded the version tuple that the rest of
pyuvm expects:

```python
# Before
import cocotb
cocotb_version_info = cocotb.__version_info__

# After
cocotb_version_info = (2, 0, 0)
```

---

### `pyuvm/s05_base_classes.py`

**Problem:** `get_sim_time()` was imported from `cocotb.utils` and called during
object construction.

**Fix:** Replaced with a stub that returns `0`:

```python
# Before
from cocotb.utils import get_sim_time

# After
def get_sim_time(units=None):
    return 0
```

---

### `pyuvm/s06_reporting_classes.py`

**Problem:** `FormatterBase` was set to cocotb's custom log formatter, and
`SimTimeContextFilter` used cocotb's sim-time API.

**Fix:** `FormatterBase` falls back to `logging.Formatter`. `SimTimeContextFilter`
becomes a no-op filter:

```python
# Before
from cocotb.logging import SimTimeContextFilter, SimFormatter as FormatterBase

# After
import logging
FormatterBase = logging.Formatter

class SimTimeContextFilter(logging.Filter):
    def filter(self, record):
        return True
```

---

### `pyuvm/s09_phasing.py`

**Problem:** `cocotb.start_soon()` was used to launch phase coroutines in the
background. Without cocotb there is no scheduler to call it on.

**Fix:** Replaced with `asyncio.get_event_loop().create_task()`:

```python
# Before
import cocotb
cocotb.start_soon(method())

# After
import asyncio
asyncio.get_event_loop().create_task(method())
```

This is the most critical patch — it enables `run_phase()` coroutines in
`UARTTxDriver`, `UARTRxMonitor`, and `ECGScoreboard` to be scheduled and run
concurrently under the asyncio event loop.

---

### `pyuvm/s13_uvm_component.py`

**Problem:** Same formatter/filter imports as `s06_reporting_classes.py` were
duplicated here.

**Fix:** Same patch applied — `FormatterBase = logging.Formatter`, no-op
`SimTimeContextFilter`.

---

### `pyuvm/s14_15_python_sequences.py`

**Problem:** `cocotb.triggers.Event` was imported for sequence handshaking. The
`cocotb.triggers` module itself requires the cocotb C extension and cannot be
imported without a simulator.

**Fix:** Replaced directly with `asyncio.Event`:

```python
# Before
from cocotb.triggers import Event as CocotbEvent

# After
from asyncio import Event as CocotbEvent
```

This enables `start_item()` / `finish_item()` handshaking between sequences and
the driver to work under asyncio.

---

### `pyuvm/utility_classes.py`

**Problem:** `UVMQueue` was built on `cocotb.queue.Queue` and `cocotb.triggers.Event`.
`NullTrigger` used a cocotb trigger to yield one scheduler tick.

**Fix:** Full rewrite on asyncio primitives:

```python
# Before
import cocotb.queue
import cocotb.triggers
queue = cocotb.queue.Queue()
event = cocotb.triggers.Event()
await NullTrigger()

# After
import asyncio
queue = asyncio.Queue()
event = asyncio.Event()
await asyncio.sleep(0)
```

`UVMQueue.get()` and `UVMQueue.put()` now delegate to `asyncio.Queue`.
`UVMQueue.get_nowait()` raises `asyncio.QueueEmpty` on empty, which pyuvm's
TLM FIFOs already handle correctly.

---

## How the Driver Works After Patches

`UARTTxDriver.run_phase()` is an `async def` coroutine that loops forever,
pulling sequence items and writing them to the UART transport:

```python
async def run_phase(self):
    while True:
        tr = await self.seq_item_port.get_next_item()
        for packet, _, _ in tr.iter_packet_bytes():
            await asyncio.wait_for(
                self.transport.write_packet(packet),
                timeout=self.cfg.byte_timeout_s,
            )
        self.seq_item_port.item_done()
        self.ap.write(tr)
```

The patch to `s09_phasing.py` (`create_task` instead of `start_soon`) is what
causes this coroutine to be scheduled and run concurrently with the scoreboard
and monitor under the asyncio event loop.

---

## How the Monitor Works After Patches

`UARTRxMonitor.run_phase()` loops forever reading bytes from the physical UART:

```python
async def run_phase(self):
    while True:
        data = await asyncio.wait_for(
            self.transport.read_rx_byte(),
            timeout=self.cfg.byte_timeout_s,
        )
        item = UARTRxSeqItem(f"rx_item_{seq_id}", rx_byte=data & 0xFF)
        self.ap.write(item)
```

The monitor publishes each received byte as a `UARTRxSeqItem` to its analysis
port, which feeds the scoreboard's `dut_tx_fifo`. This works without any cocotb
change because `uvm_analysis_port.write()` is synchronous, and the asyncio
event loop drives the `await` calls.

---

## How Tests Work After Patches

Tests extend `uvm_test` and define `SEQ_CLASS` and `EXPECTED_EPOCHS`:

```python
class ECGSmokeTest(ECGBaseTest):
    SEQ_CLASS = ECGOneEpochSequence
    EXPECTED_EPOCHS = 1
```

The entry point in `run_hil.py` launches the test with:

```python
async def _main():
    args = _parse_args()
    _configure_env(args)
    await uvm_root().run_test(args.test)

asyncio.run(_main())
```

`uvm_root().run_test()` drives the UVM phase machine, which calls
`build_phase → connect_phase → run_phase` on all components. The `run_phase`
coroutines (driver, monitor, scoreboard tasks) are all scheduled via
`asyncio.get_event_loop().create_task()` (the patched `start_soon`), and run
concurrently under the single `asyncio.run()` event loop. No cocotb, no
simulator.

---

## Scoreboard Checking

The scoreboard runs two concurrent tasks under `run_phase`:

- `collect_sent_data()` — drains `dut_rx_fifo` (TX monitor observations),
  increments `sent_sample_count` per sample to track causality.
- `compare_received()` — drains `dut_tx_fifo` (RX monitor observations), checks
  causality guard, fetches next expected one-hot from the reference file, compares
  `rx_item.argmax_onehot & 0x1F` against the expected value, increments
  `matches` or `mismatches`.

At the end of the test, results are logged:

```
epochs=N matches=N mismatches=0
```

---

## Other Edits

### `testing/run_hil.py`

- Replaces cocotb as the process entry point entirely.
- Applies a defensive patch at the top to silence any residual cocotb log
  filter crash if cocotb happens to be co-installed:
  ```python
  try:
      import cocotb.logging as _cocotb_logging
      _cocotb_logging.get_sim_time = lambda: (0, 0)
  except Exception:
      pass
  ```
- Sets all config through environment variables (`HIL_SERIAL_PORT`,
  `HIL_BAUD_RATE`, `HIL_RESP_TIMEOUT`, `HIL_BYTE_TIMEOUT`, `ECG_NUM_FRAMES`).
- Launches `uvm_root().run_test(args.test)` directly under `asyncio.run()`.

### `testing/Makefile`

- Added `hil-test` target pointing to `.venv_hil` and `run_hil.py`.
- Cocotb Makefile includes are guarded with `ifneq ($(MAKECMDGOALS),hil-test)`
  to prevent `cocotb-config` from being called when running HIL.

### `testing/setup_hil_venv.sh`

- Creates `.venv_hil` from scratch.
- Installs the asyncio-patched pyuvm fork from GitHub and `pyserial-asyncio`.
- Prints the exact run command after setup.
