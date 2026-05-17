import asyncio

from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_component

from ecg_uvm.uart_rx_uvc.uart_rx_seq_item import UARTRxSeqItem


class UARTRxMonitor(uvm_component):
    """Captures every UART byte emitted by the DUT over the physical serial port."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.serial_vif = ConfigDB().get(self, "", "serial_vif")
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        seq_id = 0
        byte_timeout_s = max(0.01, float(self.cfg.byte_timeout_s))
        self.logger.debug("RX monitor started (byte_timeout=%.2fs)", byte_timeout_s)

        while True:
            try:
                rx_b = await asyncio.wait_for(
                    self.serial_vif.read_rx_byte(), timeout=byte_timeout_s
                )
            except asyncio.TimeoutError:
                self.logger.debug("RX monitor: timeout waiting for byte (seq_id=%d, still listening)", seq_id)
                continue
            except RuntimeError as exc:
                if "EOF" in str(exc):
                    self.logger.debug("RX monitor: EOF on serial stream, retrying")
                    await asyncio.sleep(0.01)
                    continue
                raise

            self.logger.debug("RX[%d] received 0x%02X", seq_id, rx_b & 0xFF)
            item = UARTRxSeqItem(f"rx_item_{seq_id}", rx_byte=rx_b & 0xFF)
            seq_id += 1
            self.ap.write(item)
            self.logger.debug("RX[%d] published to analysis port (total=%d)", seq_id - 1, seq_id)


class UARTRxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.monitor = UARTRxMonitor.create("monitor", self)
