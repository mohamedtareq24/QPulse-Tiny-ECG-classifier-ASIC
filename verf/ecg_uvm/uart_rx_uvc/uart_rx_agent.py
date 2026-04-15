from cocotb.triggers import RisingEdge
from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_component

from ecg_uvm.uart_rx_uvc.uart_rx_seq_item import UARTRxSeqItem


class UARTRxMonitor(uvm_component):
    """Captures every UART byte emitted on DUT tx and publishes a UARTRxSeqItem."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.vif = ConfigDB().get(self, "", "vif")
        self.ap = uvm_analysis_port("ap", self)

    async def _wait_cycles(self, cycles: int):
        for _ in range(cycles):
            await RisingEdge(self.vif.clk)

    async def run_phase(self):
        seq_id = 0
        bauddiv = self.cfg.uart_bauddiv

        while True:
            # Wait for start bit (low). 
            while True:
                try:
                    if int(self.vif.tx.value) == 0:
                        break
                except ValueError:
                    pass
                await RisingEdge(self.vif.clk)

            # Validate start bit at center.
            await self._wait_cycles(max(1, bauddiv // 2))  # Instead of # delay #
            try:
                start_bit = int(self.vif.tx.value)
            except ValueError:
                start_bit = 1

            if start_bit != 0:
                await RisingEdge(self.vif.clk)
                continue

            # Sample 8 data bits.
            data = 0
            data_valid = True
            for bit_idx in range(8):
                await self._wait_cycles(bauddiv)
                try:
                    data |= (int(self.vif.tx.value) & 0x1) << bit_idx
                except ValueError:
                    data_valid = False
                    break

            if not data_valid:
                await RisingEdge(self.vif.clk)
                continue

            # Sample stop bit.
            await self._wait_cycles(bauddiv)
            try:
                stop_bit = int(self.vif.tx.value)
            except ValueError:
                stop_bit = 0

            if stop_bit != 1:
                self.logger.warning(
                    "UART RX framing error: expected stop_bit=1 got=%d (partial_data=0x%02X)",
                    stop_bit,
                    data & 0xFF,
                )
                await RisingEdge(self.vif.clk)
                continue

            # Valid frame received.
            item = UARTRxSeqItem(f"rx_item_{seq_id}", rx_byte=data & 0xFF)
            seq_id += 1
            self.ap.write(item)


class UARTRxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.monitor = UARTRxMonitor.create("monitor", self)