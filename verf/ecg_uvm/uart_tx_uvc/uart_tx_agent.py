from cocotb.triggers import RisingEdge
from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_component, uvm_driver, uvm_sequencer

from ecg_uvm.protocol import unpack_uart_rx_packet
from ecg_uvm.uart_tx_uvc.uart_tx_seq_item import UARTCsrSeqItem, UARTTxSeqItem


class UARTTxSequencer(uvm_sequencer):
    pass


class UARTTxDriver(uvm_driver):
    """Drives DUT rx pin with the 2-byte CSR control packet for each sequence item."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.vif = ConfigDB().get(self, "", "vif")

    async def _wait_cycles(self, cycles: int):
        for _ in range(cycles):
            await RisingEdge(self.vif.clk)

    async def _send_byte(self, byte_val: int) -> None:
        self.vif.rx.value = 0
        await self._wait_cycles(self.cfg.uart_bauddiv)

        for bit_idx in range(8):
            self.vif.rx.value = (byte_val >> bit_idx) & 0x1
            await self._wait_cycles(self.cfg.uart_bauddiv)

        self.vif.rx.value = 1
        await self._wait_cycles(self.cfg.uart_bauddiv)

    async def run_phase(self):
        # Hold rx high (idle) during and after reset.
        self.vif.rx.value = 1
        await self._wait_cycles(self.cfg.rx_idle_cycles)

        while True:
            tr = await self.seq_item_port.get_next_item()
            for _packet, byte0, byte1 in tr.iter_packet_bytes():
                await self._send_byte(byte0)
                await self._send_byte(byte1)
            if getattr(tr, "idle_cycles", 0) > 0:
                await self._wait_cycles(tr.idle_cycles)
            self.seq_item_port.item_done()


class UARTTxMonitor(uvm_component):
    """Passively observes vif.rx and reconstructs UARTTxSeqItem transactions."""

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.vif = ConfigDB().get(self, "", "vif")
        self.ap = uvm_analysis_port("ap", self)

    async def _wait_cycles(self, cycles: int):
        for _ in range(cycles):
            await RisingEdge(self.vif.clk)

    async def _recv_byte(self) -> int:
        bauddiv = self.cfg.uart_bauddiv

        while True:
            while True:
                try:
                    if int(self.vif.rx.value) == 0:
                        break
                except ValueError:
                    pass
                await RisingEdge(self.vif.clk)

            await self._wait_cycles(max(1, bauddiv // 2))
            try:
                start_bit = int(self.vif.rx.value)
            except ValueError:
                start_bit = 1

            if start_bit != 0:
                await RisingEdge(self.vif.clk)
                continue

            data = 0
            data_valid = True
            for bit_idx in range(8):
                await self._wait_cycles(bauddiv)
                try:
                    data |= (int(self.vif.rx.value) & 0x1) << bit_idx
                except ValueError:
                    data_valid = False
                    break

            if not data_valid:
                await RisingEdge(self.vif.clk)
                continue

            await self._wait_cycles(bauddiv)
            try:
                stop_bit = int(self.vif.rx.value)
            except ValueError:
                stop_bit = 0

            if stop_bit != 1:
                self.logger.warning(
                    "UART TX monitor framing error: expected stop_bit=1 got=%d (partial_data=0x%02X)",
                    stop_bit,
                    data & 0xFF,
                )
                await RisingEdge(self.vif.clk)
                continue

            return data & 0xFF

    async def run_phase(self):
        tr_id = 0

        while True:
            byte0 = await self._recv_byte()
            byte1 = await self._recv_byte()

            packet = ((byte1 & 0xFF) << 8) | (byte0 & 0xFF)
            fields = unpack_uart_rx_packet(packet)

            if fields.csr_sel == 0:
                tr = UARTTxSeqItem(
                    name=f"tx_mon_item_{tr_id}",
                    samples_10b=[fields.sample_10b],
                )
            else:
                tr = UARTCsrSeqItem(
                    name=f"tx_mon_item_{tr_id}",
                    soft_rst=fields.soft_rst,
                    ap_start=fields.ap_start,
                    mode=fields.mode,
                    ctrl_rsvd_1_0=fields.ctrl_rsvd_1_0,
                )
            self.ap.write(tr)

            tr_id += 1

class UARTTxAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.sequencer = UARTTxSequencer.create("sequencer", self)
        self.driver = UARTTxDriver.create("driver", self)
        self.monitor = UARTTxMonitor.create("monitor", self)

    def connect_phase(self):
        super().connect_phase()
        self.driver.seq_item_port.connect(self.sequencer.seq_item_export)
