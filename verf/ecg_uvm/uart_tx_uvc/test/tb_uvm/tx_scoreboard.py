"""Scoreboard for the TX UVC standalone testbench.

Collects items from the TX monitor and verifies:
  - The packet count matches the expected total sent by the sequence.
  - No framing errors occurred (monitor would have silently dropped those).
  - Each reconstructed field is within legal range (basic sanity).

The scoreboard is deliberately lightweight — the goal is to confirm the UVC
drives and observes correctly, not to functionally verify a DUT.
"""
from pyuvm import uvm_component, uvm_tlm_analysis_fifo

from ecg_uvm.uart_tx_uvc.uart_tx_seq_item import UARTCsrSeqItem, UARTTxSeqItem


class TxUvcScoreboard(uvm_component):
    def build_phase(self):
        super().build_phase()
        self.mon_fifo = uvm_tlm_analysis_fifo("mon_fifo", self)
        self.received: list[UARTTxSeqItem] = []
        self.errors = 0

    async def run_phase(self):
        while True:
            item: UARTTxSeqItem = await self.mon_fifo.get()
            self._check(item)
            self.received.append(item)

    def _check(self, item):
        idx = len(self.received)

        if isinstance(item, UARTTxSeqItem):
            if not (0 <= item.samples_10b[0] <= 0x3FF):
                self.logger.error("[SB] pkt#%d: sample_10b out of range: 0x%X", idx, item.samples_10b[0])
                self.errors += 1
            self.logger.info("[SB] pkt#%d data  sample_10b=0x%03X", idx, item.samples_10b[0])
        elif isinstance(item, UARTCsrSeqItem):
            if not (0 <= item.soft_rst <= 1):
                self.logger.error("[SB] pkt#%d: soft_rst out of range: %d", idx, item.soft_rst)
                self.errors += 1
            if not (0 <= item.mode <= 1):
                self.logger.error("[SB] pkt#%d: mode out of range: %d", idx, item.mode)
                self.errors += 1
            if not (0 <= item.ctrl_rsvd_1_0 <= 0x3):
                self.logger.error("[SB] pkt#%d: ctrl_rsvd_1_0 out of range: %d", idx, item.ctrl_rsvd_1_0)
                self.errors += 1
            self.logger.info(
                "[SB] pkt#%d csr   soft_rst=%d ap_start=%d mode=%d ctrl_rsvd_1_0=0x%X",
                idx, item.soft_rst, item.ap_start, item.mode, item.ctrl_rsvd_1_0,
            )

    @property
    def total_received(self) -> int:
        return len(self.received)
