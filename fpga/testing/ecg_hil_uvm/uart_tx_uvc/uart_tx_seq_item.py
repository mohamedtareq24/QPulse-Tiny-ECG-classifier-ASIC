from pyuvm import uvm_sequence_item

from ecg_hil_uvm.protocol import CSRPacketFields, packet_to_bytes, pack_uart_rx_packet


class UARTTxSeqItem(uvm_sequence_item):
    """Data-driven sequence item with file IO-based samples.
    
    Sends ECG samples as part of UART packets with control signals.
    """

    def __init__(
        self,
        name: str,
        samples_10b: list[int] | None = None,
        idle_cycles: int = 0,
    ):
        super().__init__(name)
        self.samples_10b = [s & 0x3FF for s in (samples_10b or [])]
        self.idle_cycles = max(0, int(idle_cycles))

    @classmethod
    def from_epoch_samples(
        cls,
        name: str,
        samples_10b: list[int],
        idle_cycles: int = 0,
    ) -> "UARTTxSeqItem":
        return cls(name=name, samples_10b=samples_10b, idle_cycles=idle_cycles)

    def _build_packet(self, sample_10b: int) -> tuple[int, int, int]:
        """Build a single data packet (packet_16b, byte0, byte1)."""
        fields = CSRPacketFields(
            soft_rst=0,
            ap_start=0,
            mode=0,
            csr_sel=0,
            ctrl_rsvd_1_0=0,
            sample_10b=sample_10b & 0x3FF,
        )
        packet = pack_uart_rx_packet(fields)
        byte0, byte1 = packet_to_bytes(packet)
        return (packet & 0xFFFF, byte0 & 0xFF, byte1 & 0xFF)

    def iter_packet_bytes(self) -> list[tuple[int, int, int]]:
        """Generate all UART packets for this epoch."""
        packets: list[tuple[int, int, int]] = []
        for sample_10b in self.samples_10b:
            packets.append(self._build_packet(sample_10b))
        return packets

    def clone(self) -> "UARTTxSeqItem":
        return UARTTxSeqItem(
            name=f"{self.get_name()}_clone",
            samples_10b=list(self.samples_10b),
            idle_cycles=self.idle_cycles,
        )

    def __str__(self) -> str:
        return (
            f"UARTTxSeqItem(samples={len(self.samples_10b)}, idle_cycles={self.idle_cycles})"
        )


class UARTCsrSeqItem(uvm_sequence_item):
    """Control-only sequence item for CSR register writes.
    
    Sends a single 2-byte control packet with no sample data.
    Packet format [15:0]:
      [15] = soft_rst
      [14] = ap_start
      [13] = mode
      [12] = csr_sel (always 1 for control packets)
      [9:0] = 0 (no sample data)
    """

    def __init__(
        self,
        name: str,
        soft_rst: int = 0,
        ap_start: int = 0,
        mode: int = 0,
        ctrl_rsvd_1_0: int = 0,
    ):
        super().__init__(name)
        self.soft_rst = soft_rst & 0x1
        self.ap_start = ap_start & 0x1
        self.mode = mode & 0x1
        self.ctrl_rsvd_1_0 = ctrl_rsvd_1_0 & 0x3

    def iter_packet_bytes(self) -> list[tuple[int, int, int]]:
        """Generate the single CSR control packet (csr_sel=1 always asserted)."""
        fields = CSRPacketFields(
            soft_rst=self.soft_rst,
            ap_start=self.ap_start,
            mode=self.mode,
            csr_sel=1,
            ctrl_rsvd_1_0=self.ctrl_rsvd_1_0,
            sample_10b=0,
        )
        packet = pack_uart_rx_packet(fields)
        byte0, byte1 = packet_to_bytes(packet)
        return [(packet & 0xFFFF, byte0 & 0xFF, byte1 & 0xFF)]

    def __str__(self) -> str:
        return (
            f"UARTCsrSeqItem(soft_rst={self.soft_rst}, "
            f"ap_start={self.ap_start}, mode={self.mode}, "
            f"ctrl_rsvd_1_0={self.ctrl_rsvd_1_0})"
        )
