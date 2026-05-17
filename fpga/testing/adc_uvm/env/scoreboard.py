import asyncio
from collections import deque
from pathlib import Path

from pyuvm import ConfigDB, uvm_component, uvm_tlm_analysis_fifo


class ECGScoreboard(uvm_component):
    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        # dut_rx_fifo: receives TX monitor observed input samples for causality checks.
        self.dut_rx_fifo = uvm_tlm_analysis_fifo("dut_rx_fifo", self)
        # dut_tx_fifo: receives UARTRxSeqItem from RX UVC monitor (bytes captured from DUT tx)
        self.dut_tx_fifo = uvm_tlm_analysis_fifo("dut_tx_fifo", self)
        # metadata_fifo: receives ADCMetadataItem from sequencer with row indices.
        self.metadata_fifo = uvm_tlm_analysis_fifo("metadata_fifo", self)

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
        self.pending_row_indices = deque()
        self.metadata_batches_received = 0
        self.metadata_rows_received = 0
        self.sent_sample_count = 0
        self.causality_violations = 0
        self.ignored_early_outputs = 0
        self.matches = 0
        self.mismatches = 0
        self.total_compares = 0
        self.metadata_underflows = 0

    async def collect_sent_data(self):
        while True:
            item = await self.dut_rx_fifo.get()
            # ADCTransactionDoneItem carries sample_count (number of ADC samples driven).
            # All other items (e.g. UARTTxSeqItem from the TX monitor) count as 1 sample.
            self.sent_sample_count += getattr(item, "sample_count", 1)

    async def collect_metadata(self):
        while True:
            meta_item = await self.metadata_fifo.get()
            # Preferred payload is a queue in meta_item.row_indices.
            # Fallback to epoch_index for backward compatibility.
            row_indices = getattr(meta_item, "row_indices", None)
            if row_indices is None:
                row_indices = [int(getattr(meta_item, "epoch_index"))]
            normalized = [int(idx) for idx in row_indices]
            self.pending_row_indices.extend(normalized)
            self.metadata_batches_received += 1
            self.metadata_rows_received += len(normalized)

    def _expected_onehot_for_row(self, row_idx: int) -> int:
        if row_idx < 0 or row_idx >= len(self.ref_expected_onehots):
            self.logger.error(
                "Row index out of bounds: row=%d available=%d",
                row_idx,
                len(self.ref_expected_onehots),
            )
            return -1
        return self.ref_expected_onehots[row_idx]

    async def compare_received(self):
        """Compare each DUT output against reference indexed by queued metadata row."""
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

            while not self.pending_row_indices:
                self.metadata_underflows += 1
                await asyncio.sleep(0.001)

            row_idx = self.pending_row_indices.popleft()
            expected_onehot = self._expected_onehot_for_row(row_idx)
            self.total_compares += 1

            got_onehot = rx_item.argmax_onehot & 0x1F
            if got_onehot != (expected_onehot & 0x1F):
                self.mismatches += 1
                self.logger.error(
                    "Mismatch[%d]: row=%d expected_oh=0b%s (0x%02X) got_oh=0b%s (0x%02X)",
                    self.total_compares,
                    row_idx,
                    format(expected_onehot & 0x1F, "05b"),
                    expected_onehot,
                    format(got_onehot, "05b"),
                    got_onehot,
                )
            else:
                self.matches += 1

    async def run_phase(self):
        asyncio.create_task(self.collect_sent_data())
        asyncio.create_task(self.collect_metadata())
        await self.compare_received()

    def report_phase(self):
        self.logger.info(
            "Scoreboard summary: epochs=%d metadata_batches=%d metadata_rows=%d pending_metadata=%d "
            "matches=%d mismatches=%d ignored_early_outputs=%d metadata_underflows=%d",
            self.total_compares,
            self.metadata_batches_received,
            self.metadata_rows_received,
            len(self.pending_row_indices),
            self.matches,
            self.mismatches,
            self.ignored_early_outputs,
            self.metadata_underflows,
        )
