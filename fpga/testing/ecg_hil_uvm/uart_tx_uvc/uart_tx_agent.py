import asyncio

from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_driver, uvm_sequencer


class UARTTxSequencer(uvm_sequencer):
    pass


class UARTTxDriver(uvm_driver):
    """Drives physical UART with raw bytes for each sequence item."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.transport = ConfigDB().get(self, "", "transport")
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        while True:
            tr = await self.seq_item_port.get_next_item()
            for packet, _byte0, _byte1 in tr.iter_packet_bytes():
                await asyncio.wait_for(
                    self.transport.write_packet(packet),
                    timeout=self.cfg.byte_timeout_s,
                )
            if getattr(tr, "idle_cycles", 0) > 0:
                await asyncio.sleep((tr.idle_cycles * self.cfg.clk_period_ns) / 1_000_000_000.0)
            self.seq_item_port.item_done()
            self.ap.write(tr)

class UARTTxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.sequencer = UARTTxSequencer.create("sequencer", self)
        self.driver = UARTTxDriver.create("driver", self)

    def connect_phase(self):
        super().connect_phase()
        self.driver.seq_item_port.connect(self.sequencer.seq_item_export)
