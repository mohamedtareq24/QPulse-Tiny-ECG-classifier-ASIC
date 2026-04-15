"""Tests for the TX UVC standalone testbench."""
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from pyuvm import ConfigDB, uvm_test

from ecg_uvm.cfg import ECGEnvConfig
from ecg_uvm.runtime import get_dut, set_cfg
from ecg_uvm.uart_vif import ECGUartVif
from ecg_uvm.uart_tx_uvc.uart_tx_seq_lib import (
    ECGCsrApStartPulseSequence,
    ECGCsrQualifierDisableSequence,
    ECGCsrQualifierEnableSequence,
    ECGCsrQualifierToggleSequence,
    ECGCsrSanitySequence,
    ECGCsrSoftResetAndRestartSequence,
    ECGCsrSoftResetPulseSequence,
    ECGOneEpochSequence,
    ECGTenEpochSequence,
)
from .tx_uvc_env import TxUvcEnv


class TxUvcBaseTest(uvm_test):
    """Base test: creates env, drives N epochs, checks scoreboard packet count."""

    #: override in subclasses to change the sequence type
    SEQ_CLASS = ECGOneEpochSequence
    EXPECTED_PACKETS = None

    def build_phase(self):
        super().build_phase()

        cfg = ECGEnvConfig.from_env()
        # Resolve relative TB paths against the verf/pyuvm_ecg project root.
        probe = Path(__file__).resolve().parent
        while probe != probe.parent and not (probe / "pyuvm_ecg").exists():
            probe = probe.parent
        cfg.resolve(probe / "pyuvm_ecg")
        set_cfg(cfg)

        vif = ECGUartVif(get_dut())
        ConfigDB().set(None, "*", "cfg", cfg)
        ConfigDB().set(None, "*", "vif", vif)

        self.env = TxUvcEnv.create("env", self)

    async def run_phase(self):
        self.raise_objection()

        cfg = ConfigDB().get(self, "", "cfg")
        vif = ConfigDB().get(self, "", "vif")

        clock = Clock(vif.clk, cfg.clk_period_ns, unit="ns")
        cocotb.start_soon(clock.start())

        # Reset
        vif.arst_n.value = 0
        vif.rx.value = 1
        for _ in range(cfg.rst_cycles):
            await RisingEdge(vif.clk)
        vif.arst_n.value = 1
        for _ in range(cfg.rst_cycles):
            await RisingEdge(vif.clk)

        seq = self.SEQ_CLASS.create("seq")
        await seq.start(self.env.uart_tx_ag.sequencer)

        # Give the monitor time to observe the last byte's stop bit.
        await self._drain(cfg)

        self._check_results(cfg)
        self.drop_objection()

    async def _drain(self, cfg):
        """Wait one full UART frame time after the last byte so the monitor catches it."""
        frame_bits = 10  # start + 8 data + stop
        drain_cycles = frame_bits * cfg.uart_bauddiv * 2
        vif = ConfigDB().get(self, "", "vif")
        for _ in range(drain_cycles):
            await RisingEdge(vif.clk)

    def _check_results(self, cfg):
        sb = self.env.scoreboard
        epochs = self.SEQ_CLASS.__name__  # for logging
        self.logger.info(
            "[TEST] %s done: received=%d scoreboard_errors=%d",
            epochs, sb.total_received, sb.errors,
        )
        if sb.errors:
            raise RuntimeError(f"Scoreboard field errors: {sb.errors}")
        if self.EXPECTED_PACKETS is not None:
            if sb.total_received != int(self.EXPECTED_PACKETS):
                raise RuntimeError(
                    "Unexpected packet count: "
                    f"expected={self.EXPECTED_PACKETS} got={sb.total_received}"
                )
        elif sb.total_received == 0:
            raise RuntimeError("Scoreboard received 0 packets — monitor may not be observing correctly")


class TxUvcOneEpochTest(TxUvcBaseTest):
    """Drive one epoch (cfg.frame_len samples) through the TX UVC."""
    SEQ_CLASS = ECGOneEpochSequence

    def build_phase(self):
        super().build_phase()
        cfg = ConfigDB().get(self, "", "cfg")
        self.EXPECTED_PACKETS = cfg.frame_len


class TxUvcTenEpochTest(TxUvcBaseTest):
    """Drive ten epochs through the TX UVC."""
    SEQ_CLASS = ECGTenEpochSequence

    def build_phase(self):
        super().build_phase()
        cfg = ConfigDB().get(self, "", "cfg")
        self.EXPECTED_PACKETS = 10 * cfg.frame_len


class TxUvcCsrSoftResetTest(TxUvcBaseTest):
    """Run CSR soft-reset pulse sequence."""

    SEQ_CLASS = ECGCsrSoftResetPulseSequence
    EXPECTED_PACKETS = 2


class TxUvcCsrApStartPulseTest(TxUvcBaseTest):
    """Run CSR ap_start assert sequence (1 CSR packet — latched in ctrl_reg)."""

    SEQ_CLASS = ECGCsrApStartPulseSequence
    EXPECTED_PACKETS = 1


class TxUvcCsrQualifierEnableTest(TxUvcBaseTest):
    """Run CSR qualifier enable sequence."""

    SEQ_CLASS = ECGCsrQualifierEnableSequence
    EXPECTED_PACKETS = 2


class TxUvcCsrQualifierDisableTest(TxUvcBaseTest):
    """Run CSR qualifier disable sequence."""

    SEQ_CLASS = ECGCsrQualifierDisableSequence
    EXPECTED_PACKETS = 2


class TxUvcCsrQualifierToggleTest(TxUvcBaseTest):
    """Run CSR qualifier toggle sequence."""

    SEQ_CLASS = ECGCsrQualifierToggleSequence
    EXPECTED_PACKETS = 6


class TxUvcCsrSanityTest(TxUvcBaseTest):
    """Run mixed CSR sanity sequence."""

    SEQ_CLASS = ECGCsrSanitySequence
    EXPECTED_PACKETS = 4


class TxUvcCsrSoftResetAndRestartTest(TxUvcBaseTest):
    """Run combined soft-reset + ap_start restart sequence (3 CSR packets total)."""

    SEQ_CLASS = ECGCsrSoftResetAndRestartSequence
    EXPECTED_PACKETS = 3
