import asyncio

from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_component

from ecg_hil_uvm.uart_rx_uvc.uart_rx_seq_item import UARTRxSeqItem


class UARTRxMonitor(uvm_component):
    """Captures UART bytes from physical transport and publishes UARTRxSeqItem."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.transport = ConfigDB().get(self, "", "transport")
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        seq_id = 0
        timeout_count = 0
        max_consecutive_timeouts = 5
        
        while True:
            try:
                data = await asyncio.wait_for(
                    self.transport.read_rx_byte(),
                    timeout=self.cfg.byte_timeout_s,
                )
                timeout_count = 0  # Reset on successful read
            except asyncio.TimeoutError:
                timeout_count += 1
                self.logger.warning(
                    "RX timeout waiting for DUT response byte (timeout=%.3fs, count=%d). "
                    "DUT may be stalled or UART may not be properly connected.",
                    self.cfg.byte_timeout_s,
                    timeout_count,
                )
                if timeout_count >= max_consecutive_timeouts:
                    self.logger.error(
                        "RX: %d consecutive timeouts. DUT communication has likely failed.",
                        timeout_count
                    )
                continue
            except RuntimeError as exc:
                self.logger.warning("RX read retry: %s", exc)
                await asyncio.sleep(0.01)
                continue

            item = UARTRxSeqItem(f"rx_item_{seq_id}", rx_byte=data & 0xFF)
            seq_id += 1
            self.ap.write(item)


class UARTRxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.monitor = UARTRxMonitor.create("monitor", self)