from pathlib import Path

import asyncio
from pyuvm import ConfigDB, uvm_test

from ecg_uvm.cfg import ECGEnvConfig
from ecg_uvm.env.env import ECGEnv
from ecg_uvm.uart_tx_uvc.uart_tx_seq_lib import (
    ECGAssertStartNEpochsDeassertSequence,
    ECGDatasetSequence,
    ECGDropStartMidEpochSequence,
    ECGEpochCountSequence,
    ECGIdleBetweenEpochsSequence,
    ECGMidEpochResetReplaySequence,
    ECGNormalThenNoStartSequence,
    ECGOneEpochSequence,
    ECGReservedBitsTogglePerEpochSequence,
    ECGReservedBitsWalkingPerEpochSequence,
    ECGSmokeWithThreshSequence,
    ECGSoftResetBetweenEpochsSequence,
    ECGSoftResetMidEpochNoRestartSequence,
    ECGSoftResetMidEpochRetrySequence,
    ECGSoftResetMidMultiEpochSequence,
    ECGTenEpochSequence,
    ECGCsrThresholdSequence,
    ECGCsrModeAdcApStartSequence,
)
from pyuvm import uvm_factory
from ecg_uvm.adc_uvc.adc_seq_lib import (
    ADCNormalSequence,
    ADCSupraventricularSequence,
    ADCVentricularSequence,
    ADCFusionSequence,
    ADCUnknownSequence,
    ADCNineNormalOneBadSequence,
    ADCRepeatEpochSequence,
)
from adc_uvm.adc_uvc.adc_virtual_seq_lib import ECGAdcVirtualSequence

# ---------------------------------------------------------------------------
# UART path tests
# ---------------------------------------------------------------------------
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

        ConfigDB().set(None, "*", "cfg", cfg)

        self.env = ECGEnv.create("env", self)

    async def run_phase(self):
        self.raise_objection()
        cfg = ConfigDB().get(self, "", "cfg")

        serial_transport = ConfigDB().get(self, "", "serial_transport")
        adc_transport = ConfigDB().get(self, "", "adc_transport")

        try:
            await serial_transport.open(cfg.serial_port, cfg.baud_rate)
            await adc_transport.open()
            self.logger.info("HIL transports opened successfully")

            seq = self.SEQ_CLASS.create("seq")
            expected_responses = int(seq.get_num_epochs(cfg))

            # Budget for the sequence to finish driving all items to the HW.
            # Includes: UART TX time per epoch + per-epoch response budget + fixed
            # overhead for CSR setup writes (threshold regs, ap_start CSR) that
            # happen before any epoch data and are not counted in expected_responses.
            tx_time_per_epoch = (cfg.frame_len * 2 * 10) / cfg.baud_rate
            seq_drive_budget = (cfg.response_timeout_s + tx_time_per_epoch) * max(expected_responses, 1) + 5.0

            seq_task = asyncio.create_task(seq.start(self.env.uart_tx_ag.sequencer))
            await asyncio.wait_for(seq_task, timeout=seq_drive_budget)

            wait_s = max(float(cfg.response_timeout_s), float(cfg.response_timeout_s) * expected_responses)
            deadline = asyncio.get_event_loop().time() + wait_s
            while asyncio.get_event_loop().time() < deadline:
                if self.env.scoreboard.total_compares >= expected_responses:
                    break
                await asyncio.sleep(0.01)

            if self.env.scoreboard.total_compares < expected_responses:
                raise RuntimeError(
                    f"Timed out waiting for DUT responses "
                    f"expected={expected_responses} got={self.env.scoreboard.total_compares}"
                )

            if self.env.scoreboard.mismatches != 0:
                raise RuntimeError(
                    f"Scoreboard mismatches detected: {self.env.scoreboard.mismatches}"
                )

            self.logger.info("Test completed successfully")

        finally:
            await serial_transport.close()
            await adc_transport.close()
            self.logger.info("HIL transports closed")
            self.drop_objection()


class ECGSmokeTest(ECGBaseTest):
    """Single-epoch smoke test — writes threshold registers then drives one epoch."""
    SEQ_CLASS = ECGSmokeWithThreshSequence
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


class ECGReservedBitsToggleTest(ECGBaseTest):
    """Alternates reserved control bits between 0b111 and 0b000 across epochs."""
    SEQ_CLASS = ECGReservedBitsTogglePerEpochSequence


class ECGReservedBitsWalkingTest(ECGBaseTest):
    """Walks reserved control bits through 001, 010, 100 per epoch."""
    SEQ_CLASS = ECGReservedBitsWalkingPerEpochSequence


class ECGQualifierToggleTest(ECGReservedBitsToggleTest):
    """Backward-compatible alias for legacy qualifier toggle test name."""


class ECGIdleBetweenEpochsTest(ECGBaseTest):
    """Inserts idle gap between epochs."""
    SEQ_CLASS = ECGIdleBetweenEpochsSequence
    EXPECTED_EPOCHS = 30


class ECGAssertStartNEpochsDeassertTest(ECGBaseTest):
    """Asserts start once, sends N epochs back-to-back, then deasserts start."""
    SEQ_CLASS = ECGAssertStartNEpochsDeassertSequence
    EXPECTED_EPOCHS = 20


# ---------------------------------------------------------------------------
# ADC path tests
# ---------------------------------------------------------------------------

class ECGBaseAdcTest(uvm_test):

    def build_phase(self):
        super().build_phase()
        cfg = ECGEnvConfig.from_env()
        base_dir = Path(__file__).resolve().parents[1] / "tv"
        cfg.input_path = str(base_dir / "cdatafile" / "c.tiny_ecg_no_activ.autotvin_input_layer_3.dat")
        cfg.ref_onehot_path = str(base_dir / "ref_onehot.txt")
        ConfigDB().set(None, "*", "cfg", cfg)
        self.env = ECGEnv.create("env", self)

    def connect_phase(self):
        super().connect_phase()
        self.uart_tx_sequencer = self.env.uart_tx_ag.sequencer
        self.adc_sequencer = self.env.adc_ag.sequencer

    async def run_phase(self):
        self.raise_objection()
        cfg = ConfigDB().get(self, "", "cfg")

        serial_transport = ConfigDB().get(self, "", "serial_transport")
        adc_transport = ConfigDB().get(self, "", "adc_transport")

        try:
            await serial_transport.open(cfg.serial_port, cfg.baud_rate)
            await adc_transport.open()

            vseq = ECGAdcVirtualSequence.create("adc_vseq")
            vseq.uart_tx_sequencer = self.uart_tx_sequencer
            vseq.adc_sequencer = self.adc_sequencer
            vseq.num_epochs = cfg.num_frames
            await vseq.start(None)

            wait_s = float(cfg.response_timeout_s) * cfg.num_frames
            deadline = asyncio.get_event_loop().time() + wait_s
            while asyncio.get_event_loop().time() < deadline:
                if self.env.scoreboard.total_compares >= cfg.num_frames:
                    break
                await asyncio.sleep(0.01)

            if self.env.scoreboard.total_compares < cfg.num_frames:
                raise RuntimeError(
                    f"ADC timed out: expected={cfg.num_frames} "
                    f"got={self.env.scoreboard.total_compares}"
                )
            if self.env.scoreboard.mismatches != 0:
                raise RuntimeError(f"ADC mismatches={self.env.scoreboard.mismatches}")

        finally:
            await serial_transport.close()
            await adc_transport.close()
            self.drop_objection()


class ECGAdcSmokeTest(ECGBaseAdcTest):
    """Single-epoch ADC smoke test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCNormalSequence)


class ECGAdcNormalTenTest(ECGBaseAdcTest):
    """Normal-beat ADC test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCNormalSequence)


class ECGAdcSupraventricularTest(ECGBaseAdcTest):
    """Supraventricular-beat ADC test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCSupraventricularSequence)


class ECGAdcVentricularTest(ECGBaseAdcTest):
    """Ventricular-beat ADC test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCVentricularSequence)


class ECGAdcFusionTest(ECGBaseAdcTest):
    """Fusion-beat ADC test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCFusionSequence)


class ECGAdcUnknownTest(ECGBaseAdcTest):
    """Unknown-beat ADC test."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCUnknownSequence)


class ECGAdcNineNormalOneBadTest(ECGBaseAdcTest):
    """ADC test: 9 normal beats + 1 ventricular outlier per batch."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCNineNormalOneBadSequence)


class ECGAdcRepeatEpochTest(ECGBaseAdcTest):
    """Sends the same epoch (index 0) repeatedly via NUM_FRAMES."""

    def build_phase(self):
        super().build_phase()
        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCRepeatEpochSequence)


# ---------------------------------------------------------------------------
# Control-bit negative / mid-stream tests
# ---------------------------------------------------------------------------

class ECGDropStartNegativeTest(ECGBaseTest):
    """Sends one normal epoch then deasserts ap_start and sends a second epoch."""
    SEQ_CLASS = ECGNormalThenNoStartSequence
    EXPECTED_EPOCHS = 1


class ECGSoftResetMidEpochRetryTest(ECGBaseTest):
    """Asserts soft_rst after sending the first half of an epoch, then retries."""
    SEQ_CLASS = ECGSoftResetMidEpochRetrySequence
    EXPECTED_EPOCHS = 1


class ECGMidEpochResetReplayTest(ECGBaseTest):
    """Injects a mid-epoch reset inside one item, then replays the full epoch."""
    SEQ_CLASS = ECGMidEpochResetReplaySequence
    EXPECTED_EPOCHS = 1


class ECGSoftResetMidMultiEpochTest(ECGBaseTest):
    """Drives 2 complete epochs, resets mid-way through the 3rd, then drives 1 post-reset epoch."""
    SEQ_CLASS = ECGSoftResetMidMultiEpochSequence
    EXPECTED_EPOCHS = 3


class ECGSoftResetMidEpochNoRestartTest(ECGBaseTest):
    """Resets mid-epoch without re-toggling ap_start, then resends the full epoch."""
    SEQ_CLASS = ECGSoftResetMidEpochNoRestartSequence
    EXPECTED_EPOCHS = 1
