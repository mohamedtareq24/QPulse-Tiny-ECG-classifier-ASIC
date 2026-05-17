import asyncio

from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_driver, uvm_sequencer


class UARTTxSequencer(uvm_sequencer):
    pass


class UARTTxDriver(uvm_driver):
    """Drives DUT rx pin with the 2-byte CSR control packet for each sequence item."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.serial_vif = ConfigDB().get(self, "", "serial_vif")
        self.tx_item_ap = uvm_analysis_port("tx_item_ap", self)

    async def run_phase(self):
        self.logger.debug("TX driver started (port=%s baud=%d timeout=%.2fs)",
                          self.cfg.serial_port, self.cfg.baud_rate, self.cfg.byte_timeout_s)
        tr_count = 0
        while True:
            tr = await self.seq_item_port.get_next_item()
            tr_count += 1
            packets = list(tr.iter_packet_bytes())
            self.logger.debug("TX[%d] sending item=%s packets=%d",
                              tr_count, tr.get_name(), len(packets))
            try:
                for pkt_idx, (_packet, byte0, byte1) in enumerate(packets):
                    self.logger.debug("TX[%d] pkt[%d] 0x%04X -> [0x%02X, 0x%02X]",
                                      tr_count, pkt_idx, _packet, byte0, byte1)
                    await asyncio.wait_for(
                        self.serial_vif.write_bytes(bytes((byte0 & 0xFF, byte1 & 0xFF))),
                        timeout=self.cfg.byte_timeout_s,
                    )
            except asyncio.TimeoutError as exc:
                self.logger.error(
                    "TX[%d] byte write timed out after %.2fs (item=%s pkt=%d) — aborting",
                    tr_count, self.cfg.byte_timeout_s, tr.get_name(), pkt_idx,
                )
                self.seq_item_port.item_done()
                raise RuntimeError(
                    f"TX driver: serial write timed out on item {tr.get_name()} "
                    f"packet {pkt_idx}"
                ) from exc
            self.logger.debug("TX[%d] item done, publishing to ap", tr_count)
            self.tx_item_ap.write(tr)
            if getattr(tr, "idle_delay_s", 0.0) > 0.0:
                self.logger.debug("TX[%d] idle delay %.4fs", tr_count, tr.idle_delay_s)
                await asyncio.sleep(tr.idle_delay_s)
            self.seq_item_port.item_done()


class UARTTxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.sequencer = UARTTxSequencer.create("sequencer", self)
        self.driver = UARTTxDriver.create("driver", self)

    def connect_phase(self):
        super().connect_phase()
        self.driver.seq_item_port.connect(self.sequencer.seq_item_export)
