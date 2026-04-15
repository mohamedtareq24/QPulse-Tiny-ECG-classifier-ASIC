from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from pyuvm import ConfigDB, uvm_test

from ecg_uvm.cfg import ECGEnvConfig
from ecg_uvm.env.env import ECGEnv
from ecg_uvm.runtime import get_dut, set_cfg
from ecg_uvm.uart_vif import ECGUartVif
from ecg_uvm.uart_tx_uvc.uart_tx_seq_lib import (
    ECGDatasetSequence,
    ECGDropStartMidEpochSequence,
    ECGEpochCountSequence,
    ECGIdleBetweenEpochsSequence,
    ECGMidEpochResetReplaySequence,
    ECGNormalThenNoStartSequence,
    ECGOneEpochSequence,
    ECGReservedBitsTogglePerEpochSequence,
    ECGReservedBitsWalkingPerEpochSequence,
    ECGSoftResetBetweenEpochsSequence,
    ECGSoftResetMidEpochNoRestartSequence,
    ECGSoftResetMidEpochRetrySequence,
    ECGSoftResetMidMultiEpochSequence,
    ECGTenEpochSequence,
)


class ECGBaseTest(uvm_test):
    SEQ_CLASS = ECGEpochCountSequence
    EXPECTED_EPOCHS = 4

    def build_phase(self):
        super().build_phase()

        cfg = ECGEnvConfig.from_env()
        cfg.num_frames = int(self.EXPECTED_EPOCHS)
        # Keep dataset path resolution anchored to the pyuvm_ecg project root.
        base_dir = Path(__file__).resolve().parents[2] / "pyuvm_ecg"
        cfg.resolve(base_dir)
        vif = ECGUartVif(get_dut())
        set_cfg(cfg)

        ConfigDB().set(None, "*", "cfg", cfg)
        ConfigDB().set(None, "*", "vif", vif)

        self.env = ECGEnv.create("env", self)

    async def reset_dut(self):
        vif = ConfigDB().get(self, "", "vif")
        cfg = ConfigDB().get(self, "", "cfg")

        vif.arst_n.value = 0
        vif.rx.value = 1
        for _ in range(cfg.rst_cycles):
            await RisingEdge(vif.clk)
        vif.arst_n.value = 1
        for _ in range(cfg.rst_cycles):
            await RisingEdge(vif.clk)

    async def run_phase(self):
        self.raise_objection()

        vif = ConfigDB().get(self, "", "vif")
        cfg = ConfigDB().get(self, "", "cfg")

        clock = Clock(vif.clk, cfg.clk_period_ns, unit="ns")
        cocotb.start_soon(clock.start())

        await self.reset_dut()

        seq = self.SEQ_CLASS.create("seq")
        expected_responses = int(seq.get_num_epochs(cfg))
        await seq.start(self.env.uart_tx_ag.sequencer)

        # Drain for responses after all input samples are sent.
        for _ in range(cfg.tx_timeout_cycles):
            await RisingEdge(vif.clk)
            if self.env.scoreboard.total_compares >= expected_responses:
                break

        if self.env.scoreboard.total_compares < expected_responses:
            raise RuntimeError(
                f"Timed out waiting for responses expected={expected_responses} got={self.env.scoreboard.total_compares}"
            )

        if self.env.scoreboard.mismatches != 0:
            raise RuntimeError(
                f"Scoreboard mismatches detected: {self.env.scoreboard.mismatches}"
            )

        # Allow any in-flight transactions to settle before ending the test.
        for _ in range(cfg.end_drain_cycles):
            await RisingEdge(vif.clk)

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
    EXPECTED_EPOCHS = 10


class ECGFullDatasetTest(ECGBaseTest):
    """Runs all 50 epochs in the TV dataset — full regression."""
    SEQ_CLASS = ECGDatasetSequence
    EXPECTED_EPOCHS = 50


class ECGSoftResetTest(ECGBaseTest):
    """Asserts soft_rst at the start of every epoch after the first, then re-arms ap_start."""
    SEQ_CLASS = ECGSoftResetBetweenEpochsSequence

    async def run_phase(self):
        cfg = ConfigDB().get(self, "", "cfg")
        cfg.tx_timeout_cycles *= 3
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
        cfg.tx_timeout_cycles *= 3
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
        cfg.tx_timeout_cycles *= 3
        await super().run_phase()
