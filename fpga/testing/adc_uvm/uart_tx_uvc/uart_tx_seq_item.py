from pyuvm import uvm_sequence_item

from ecg_uvm.protocol import pack_ctrl_csr, pack_csr_packet, pack_data_packet, packet_to_bytes, REG_ADDR_CSR


class UARTTxSeqItem(uvm_sequence_item):
    """Data-driven sequence item with file IO-based samples.
    
    Sends ECG samples as part of UART packets with control signals.
    """

    def __init__(
        self,
        name: str,
        samples_10b: list[int] | None = None,
        idle_delay_s: float = 0.0,
    ):
        super().__init__(name)
        self.samples_10b = [s & 0x3FF for s in (samples_10b or [])]
        self.idle_delay_s = max(0.0, float(idle_delay_s))

    @classmethod
    def from_epoch_samples(
        cls,
        name: str,
        samples_10b: list[int],
        idle_delay_s: float = 0.0,
    ) -> "UARTTxSeqItem":
        return cls(name=name, samples_10b=samples_10b, idle_delay_s=idle_delay_s)

    def _build_packet(self, sample_10b: int) -> tuple[int, int, int]:
        """Build a single data packet (packet_16b, byte0, byte1)."""
        packet = pack_data_packet(sample_10b & 0x3FF)
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
            idle_delay_s=self.idle_delay_s,
        )

    def __str__(self) -> str:
        return (
            f"UARTTxSeqItem(samples={len(self.samples_10b)}, idle_delay_s={self.idle_delay_s})"
        )


class UARTCsrSeqItem(uvm_sequence_item):
    """Control-only sequence item for CSR reg 0 (control register) writes.

    Sends a single 2-byte CSR write packet:
      bit[15]=1 (CSR-space), bits[14:12]=0 (reg addr 0),
      bits[11:0]={9'b0, soft_rst, ap_start, mode}
    """

    def __init__(
        self,
        name: str,
        soft_rst: int = 0,
        ap_start: int = 0,
        mode: int = 0,
    ):
        super().__init__(name)
        self.soft_rst = soft_rst & 0x1
        self.ap_start = ap_start & 0x1
        self.mode     = mode & 0x1

    def iter_packet_bytes(self) -> list[tuple[int, int, int]]:
        """Generate the single CSR reg 0 write packet."""
        csr_data = pack_ctrl_csr(self.soft_rst, self.ap_start, self.mode)
        packet   = pack_csr_packet(REG_ADDR_CSR, csr_data)
        byte0, byte1 = packet_to_bytes(packet)
        return [(packet & 0xFFFF, byte0 & 0xFF, byte1 & 0xFF)]

    def __str__(self) -> str:
        return (
            f"UARTCsrSeqItem(soft_rst={self.soft_rst}, "
            f"ap_start={self.ap_start}, mode={self.mode})"
        )


class UARTRegSeqItem(uvm_sequence_item):
    """Generic CSR register write — writes any reg_addr with a 12-bit value."""

    def __init__(self, name: str, reg_addr: int, reg_data: int):
        super().__init__(name)
        self.reg_addr = reg_addr & 0x7
        self.reg_data = reg_data & 0xFFF

    def iter_packet_bytes(self) -> list[tuple[int, int, int]]:
        packet = pack_csr_packet(self.reg_addr, self.reg_data)
        byte0, byte1 = packet_to_bytes(packet)
        return [(packet & 0xFFFF, byte0 & 0xFF, byte1 & 0xFF)]

    def __str__(self) -> str:
        return f"UARTRegSeqItem(reg_addr={self.reg_addr}, reg_data=0x{self.reg_data:03X})"
