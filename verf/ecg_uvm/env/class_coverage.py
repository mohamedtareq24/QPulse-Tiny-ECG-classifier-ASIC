import cocotb
from pyuvm import uvm_component, uvm_tlm_analysis_fifo

from ecg_uvm.protocol import class_from_onehot


class ECGClassCoverage(uvm_component):
    """Collects observed-class coverage from DUT UART TX monitor stream."""

    def build_phase(self):
        super().build_phase()
        self.dut_tx_fifo = uvm_tlm_analysis_fifo("dut_tx_fifo", self)
        self.class_hits = [0, 0, 0, 0, 0]
        self.invalid_onehot_hits = 0
        self.total_observed = 0

    async def run_phase(self):
        while True:
            rx_item = await self.dut_tx_fifo.get()
            onehot = rx_item.argmax_onehot & 0x1F
            cls = class_from_onehot(onehot)
            self.total_observed += 1
            if 0 <= cls <= 4:
                self.class_hits[cls] += 1
            else:
                self.invalid_onehot_hits += 1

    def report_phase(self):
        observed_classes = sum(1 for hit in self.class_hits if hit > 0)
        self.logger.info(
            "Class coverage summary: observed_classes=%d/5 hits=%s invalid_onehot=%d total=%d",
            observed_classes,
            self.class_hits,
            self.invalid_onehot_hits,
            self.total_observed,
        )
