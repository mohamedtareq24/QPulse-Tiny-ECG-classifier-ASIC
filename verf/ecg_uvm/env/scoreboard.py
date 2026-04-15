from pathlib import Path

import cocotb
from pyuvm import ConfigDB, uvm_component, uvm_tlm_analysis_fifo


class ECGScoreboard(uvm_component):
    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        # dut_rx_fifo: receives TX monitor observed input samples for causality checks.
        self.dut_rx_fifo = uvm_tlm_analysis_fifo("dut_rx_fifo", self)
        # dut_tx_fifo: receives UARTRxSeqItem from RX UVC monitor (bytes captured from DUT tx)
        self.dut_tx_fifo = uvm_tlm_analysis_fifo("dut_tx_fifo", self)

        ref_onehot_path = self.cfg.ref_onehot_path
        if not ref_onehot_path:
            raise RuntimeError("ref_onehot_path must be set in ECGEnvConfig for scoreboard checking")

        with Path(ref_onehot_path).open() as _f:
            self.ref_expected_onehots = [
                int(line.strip(), 16)
                for line in _f
                if line.strip().lower().startswith("0x")
            ]
        self.logger.info(
            "Scoreboard reference loaded from: %s (%d entries)",
            ref_onehot_path,
            len(self.ref_expected_onehots),
        )
        self.ref_cursor = 0
        self.sent_sample_count = 0
        self.causality_violations = 0
        self.ignored_early_outputs = 0
        self.matches = 0
        self.mismatches = 0
        self.total_compares = 0

    async def collect_sent_data(self):
        while True:
            _tx_item = await self.dut_rx_fifo.get()
            self.sent_sample_count += 1

    def _next_expected_onehot(self) -> int:
        if self.ref_cursor >= len(self.ref_expected_onehots):
            self.logger.error(
                "Reference exhausted: cursor=%d available=%d",
                self.ref_cursor,
                len(self.ref_expected_onehots),
            )
            return -1
        expected = self.ref_expected_onehots[self.ref_cursor]
        self.ref_cursor += 1
        return expected

    async def compare_received(self):
        """On each received DUT transaction, compare one-hot byte against reference."""
        while True:
            rx_item = await self.dut_tx_fifo.get()

            required_samples = (self.total_compares + 1) * self.cfg.frame_len
            if self.sent_sample_count < required_samples:
                self.causality_violations += 1
                self.ignored_early_outputs += 1
                self.logger.warning(
                    "Ignoring premature output: arrived before enough input samples sent "
                    "(sent=%d required=%d compare_idx=%d)",
                    self.sent_sample_count,
                    required_samples,
                    self.total_compares + 1,
                )
                continue

            expected_onehot = self._next_expected_onehot()
            self.total_compares += 1

            got_onehot = rx_item.argmax_onehot & 0x1F
            if got_onehot != (expected_onehot & 0x1F):
                self.mismatches += 1
                self.logger.error(
                    "Mismatch[%d]: expected_oh=0b%s (0x%02X) got_oh=0b%s (0x%02X)",
                    self.total_compares,
                    format(expected_onehot & 0x1F, "05b"),
                    expected_onehot,
                    format(got_onehot, "05b"),
                    got_onehot,
                )
            else:
                self.matches += 1

    async def run_phase(self):
        cocotb.start_soon(self.collect_sent_data())
        await self.compare_received()

    def report_phase(self):
        self.logger.info(
            "Scoreboard summary: epochs=%d matches=%d mismatches=%d ignored_early_outputs=%d",
            self.total_compares,
            self.matches,
            self.mismatches,
            self.ignored_early_outputs,
        )
