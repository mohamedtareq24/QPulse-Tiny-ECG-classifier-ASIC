import asyncio
from pathlib import Path

from pyuvm import ConfigDB, uvm_test

from ecg_hil_uvm.cfg import ECGEnvConfig
from ecg_hil_uvm.env.env import ECGEnv
from ecg_hil_uvm.runtime import set_cfg
from ecg_hil_uvm.transport import HilSerialTransport
from ecg_hil_uvm.uart_tx_uvc.uart_tx_seq_lib import (
    ECGDatasetSequence,
    ECGDropStartMidEpochSequence,
    ECGEpochCountAssertedStartSequence,
    ECGEpochCountSequence,
    ECGIdleBetweenEpochsSequence,
    ECGMidEpochResetReplaySequence,
    ECGNEpochSequence,
    ECGNormalThenNoStartSequence,
    ECGOneEpochSequence,
    ECGReservedBitsTogglePerEpochSequence,
    ECGReservedBitsWalkingPerEpochSequence,
    ECGSoftResetBetweenEpochsSequence,
    ECGSoftResetEveryFiveEpochsSequence,
    ECGSoftResetMidEpochNoRestartSequence,
    ECGSoftResetMidEpochRetrySequence,
    ECGSoftResetMidMultiEpochSequence,
    ECGTenEpochSequence,
)


def _count_hex_lines(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip().lower().startswith("0x"):
                count += 1
    return count


def _full_epochs_from_input(input_path: str, frame_len: int) -> int:
    samples = _count_hex_lines(Path(input_path))
    epochs = samples // int(frame_len)
    if epochs <= 0:
        raise RuntimeError(
            f"Input TV has insufficient samples for one frame: samples={samples} frame_len={frame_len}"
        )
    return epochs


class ECGBaseTest(uvm_test):
    SEQ_CLASS = ECGEpochCountSequence
    EXPECTED_EPOCHS = 4
    USE_CFG_NUM_FRAMES = False

    def build_phase(self):
        super().build_phase()

        cfg = ECGEnvConfig.from_env()
        if not self.USE_CFG_NUM_FRAMES:
            cfg.num_frames = int(self.EXPECTED_EPOCHS)
        # Keep dataset path resolution anchored to the pyuvm_ecg project root.
        base_dir = Path(__file__).resolve().parents[2] / "pyuvm_ecg"
        cfg.resolve(base_dir)
        set_cfg(cfg)
        transport = HilSerialTransport()

        ConfigDB().set(None, "*", "cfg", cfg)
        ConfigDB().set(None, "*", "transport", transport)

        self.env = ECGEnv.create("env", self)

    async def run_phase(self):
        self.raise_objection()
        cfg = ConfigDB().get(self, "", "cfg")
        transport = ConfigDB().get(self, "", "transport")
        
        # Print config values at the beginning of test
        print("\n" + "="*80)
        print(f"[TEST CONFIG] {self.__class__.__name__}")
        print("="*80)
        print(f"  frame_len:            {cfg.frame_len}")
        print(f"  num_frames:           {cfg.num_frames}")
        print(f"  clk_period_ns:        {cfg.clk_period_ns}")
        print(f"  uart_bauddiv:         {cfg.uart_bauddiv}")
        print(f"  serial_port:          {cfg.serial_port}")
        print(f"  baud_rate:            {cfg.baud_rate}")
        print(f"  byte_timeout_s:       {cfg.byte_timeout_s}")
        print(f"  response_timeout_s:   {cfg.response_timeout_s}")
        print(f"  input_path:           {cfg.input_path}")
        print(f"  hls_output_path:      {cfg.hls_output_path}")
        print(f"  ref_onehot_path:      {cfg.ref_onehot_path}")
        print("="*80 + "\n")
        
        try:
            await transport.open(cfg.serial_port, cfg.baud_rate)

            seq = self.SEQ_CLASS.create("seq")
            expected_responses = int(seq.get_num_epochs(cfg))
            await seq.start(self.env.uart_tx_ag.sequencer)

            deadline = asyncio.get_running_loop().time() + cfg.response_timeout_s
            while self.env.scoreboard.total_compares < expected_responses:
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(0.05)

            if self.env.scoreboard.total_compares < expected_responses:
                raise RuntimeError(
                    f"Timed out waiting for responses expected={expected_responses} got={self.env.scoreboard.total_compares}"
                )

            if self.env.scoreboard.mismatches != 0:
                raise RuntimeError(
                    f"Scoreboard mismatches detected: {self.env.scoreboard.mismatches}"
                )
        finally:
            await transport.close()
            self.drop_objection()


class ECGSmokeTest(ECGBaseTest):
    """Single-epoch smoke test — fast pass/fail check."""
    SEQ_CLASS = ECGOneEpochSequence
    EXPECTED_EPOCHS = 1


class ECGMiniRegressionTest(ECGBaseTest):
    """Runs 8 epochs (mini regression; no sequence override)."""
    EXPECTED_EPOCHS = 8


class ECGTenEpochTest(ECGBaseTest):
    """Drives exactly ten epochs."""
    SEQ_CLASS = ECGTenEpochSequence
    EXPECTED_EPOCHS = 20


class ECGFullDatasetTest(ECGBaseTest):
    """Runs all epochs in the current TV dataset with idle delay between epochs."""
    SEQ_CLASS = ECGIdleBetweenEpochsSequence

    def build_phase(self):
        super().build_phase()
        cfg = ConfigDB().get(self, "", "cfg")
        full_epochs = _full_epochs_from_input(cfg.input_path, cfg.frame_len)
        cfg.num_frames = int(full_epochs)
        self.EXPECTED_EPOCHS = int(full_epochs)


class ECGSoftResetTest(ECGBaseTest):
    """Asserts soft_rst at the start of every epoch after the first, then re-arms ap_start."""
    SEQ_CLASS = ECGSoftResetBetweenEpochsSequence

    async def run_phase(self):
        cfg = ConfigDB().get(self, "", "cfg")
        cfg.response_timeout_s *= 3.0
        await super().run_phase()


class ECGReservedBitsToggleTest(ECGBaseTest):
    """Alternates reserved control bits between 0b111 and 0b000 across epochs."""
    SEQ_CLASS = ECGReservedBitsTogglePerEpochSequence


class ECGReservedBitsWalkingTest(ECGBaseTest):
    """Walks reserved control bits through 001, 010, 100 per epoch."""
    SEQ_CLASS = ECGReservedBitsWalkingPerEpochSequence


class ECGQualifierToggleTest(ECGReservedBitsToggleTest):
    """Backward-compatible alias for legacy qualifier toggle test name."""


class ECGIdleBetweenEpochsTest(ECGBaseTest):
    """Inserts idle gap (10 × bauddiv cycles by default) between epochs."""
    SEQ_CLASS = ECGIdleBetweenEpochsSequence
    EXPECTED_EPOCHS = 30


# ---------------------------------------------------------------------------
# Control-bit negative / mid-stream tests
# ---------------------------------------------------------------------------

class ECGDropStartNegativeTest(ECGBaseTest):
    """Sends one normal epoch then deasserts ap_start and sends a second epoch.

    The DUT should process epoch 0 and ignore epoch 1 (ap_start=0).
    Expected responses: 1.
    """
    SEQ_CLASS = ECGNormalThenNoStartSequence
    EXPECTED_EPOCHS = 1


class ECGSoftResetMidEpochRetryTest(ECGBaseTest):
    """Asserts soft_rst after sending the first half of an epoch, then retries
    the same epoch in full.

    The aborted partial epoch must not produce a DUT response.  The retried
    epoch should yield exactly 1 valid response.
    """
    SEQ_CLASS = ECGSoftResetMidEpochRetrySequence
    EXPECTED_EPOCHS = 1


class ECGMidEpochResetReplayTest(ECGBaseTest):
    """Injects a mid-epoch reset inside one item, then replays the full epoch."""
    SEQ_CLASS = ECGMidEpochResetReplaySequence
    EXPECTED_EPOCHS = 1

    async def run_phase(self):
        cfg = ConfigDB().get(self, "", "cfg")
        cfg.response_timeout_s *= 3.0
        await super().run_phase()


class ECGSoftResetMidMultiEpochTest(ECGBaseTest):
    """Drives 2 complete epochs, resets mid-way through the 3rd, then drives
    1 post-reset full epoch.

    Expected DUT responses: 3 (2 pre-reset + 1 post-reset).
    The aborted mid-stream epoch must not produce any response.
    """
    SEQ_CLASS = ECGSoftResetMidMultiEpochSequence
    EXPECTED_EPOCHS = 3


class ECGSoftResetMidEpochNoRestartTest(ECGBaseTest):
    """Resets mid-epoch without re-toggling ap_start, then resends the full epoch.

    Verifies the DUT processes the epoch when ap_start was already latched
    before the partial burst started and is not re-asserted after reset.
    Expected DUT responses: 1.
    """
    SEQ_CLASS = ECGSoftResetMidEpochNoRestartSequence
    EXPECTED_EPOCHS = 1

    async def run_phase(self):
        cfg = ConfigDB().get(self, "", "cfg")
        cfg.response_timeout_s *= 3.0
        await super().run_phase()

class TxUvcEpochCountAssertedStartTest(ECGBaseTest):
    """Drive full dataset epochs with ap_start asserted (not pulsed).

    Assert ap_start once, drive all epochs while it remains high, then deassert.
    Verifies the engine processes epochs correctly when start is held across them.
    """

    SEQ_CLASS = ECGEpochCountAssertedStartSequence

    def build_phase(self):
        super().build_phase()
        cfg = ConfigDB().get(self, "", "cfg")
        full_epochs = _full_epochs_from_input(cfg.input_path, cfg.frame_len)
        cfg.num_frames = int(full_epochs)
        self.EXPECTED_EPOCHS = int(full_epochs)


class ECGFullDatasetResetEveryFiveEpochsTest(ECGBaseTest):
    """Run full dataset with reset/start boundary control every 5 epochs."""

    SEQ_CLASS = ECGSoftResetEveryFiveEpochsSequence

    def build_phase(self):
        super().build_phase()
        cfg = ConfigDB().get(self, "", "cfg")
        full_epochs = _full_epochs_from_input(cfg.input_path, cfg.frame_len)
        cfg.num_frames = int(full_epochs)
        self.EXPECTED_EPOCHS = int(full_epochs)


class ECGNEpochTest(ECGBaseTest):
    """Generic N-epoch test — reads epoch count from cfg.num_frames.

    Set ``ECG_NUM_FRAMES`` in the environment to choose N.
    Example: ``ECG_NUM_FRAMES=50 make hil-test HIL_TEST=ECGNEpochTest``
    """

    SEQ_CLASS = ECGNEpochSequence
    USE_CFG_NUM_FRAMES = True
