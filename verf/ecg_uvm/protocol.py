from dataclasses import dataclass


FRAC_BITS = 5
DATA_WIDTH = 10
MAX_RAW = (1 << (DATA_WIDTH - 1)) - 1
MIN_RAW = -(1 << (DATA_WIDTH - 1))


@dataclass(frozen=True)
class CSRPacketFields:
    soft_rst: int
    ap_start: int
    mode: int
    csr_sel: int        # bit [12]: 0 = data packet, 1 = CSR control packet
    ctrl_rsvd_1_0: int  # bits [11:10]: reserved control bits
    sample_10b: int


def float_to_apfixed10_5_bits(value: float) -> int:
    raw = int(round(value * (1 << FRAC_BITS)))
    if raw > MAX_RAW:
        raw = MAX_RAW
    if raw < MIN_RAW:
        raw = MIN_RAW
    return raw & ((1 << DATA_WIDTH) - 1)


def apfixed10_5_bits_to_float(bits: int) -> float:
    bits = bits & ((1 << DATA_WIDTH) - 1)
    if bits & (1 << (DATA_WIDTH - 1)):
        bits -= 1 << DATA_WIDTH
    return float(bits) / float(1 << FRAC_BITS)


def pack_uart_rx_packet(fields: CSRPacketFields) -> int:
    packet = 0
    packet |= (fields.soft_rst & 0x1) << 15
    packet |= (fields.ap_start & 0x1) << 14
    packet |= (fields.mode & 0x1) << 13
    packet |= (fields.csr_sel & 0x1) << 12
    packet |= (fields.ctrl_rsvd_1_0 & 0x3) << 10
    packet |= fields.sample_10b & 0x3FF
    return packet & 0xFFFF


def unpack_uart_rx_packet(packet: int) -> CSRPacketFields:
    packet &= 0xFFFF
    return CSRPacketFields(
        soft_rst=(packet >> 15) & 0x1,
        ap_start=(packet >> 14) & 0x1,
        mode=(packet >> 13) & 0x1,
        csr_sel=(packet >> 12) & 0x1,
        ctrl_rsvd_1_0=(packet >> 10) & 0x3,
        sample_10b=packet & 0x3FF,
    )


def packet_to_bytes(packet: int) -> tuple[int, int]:
    return packet & 0xFF, (packet >> 8) & 0xFF


def decode_uart_tx_byte(value: int) -> tuple[int, int, int, int]:
    value &= 0xFF
    ap_idle = (value >> 7) & 0x1
    ap_ready = (value >> 6) & 0x1
    ap_done = (value >> 5) & 0x1
    argmax_onehot = value & 0x1F
    return ap_idle, ap_ready, ap_done, argmax_onehot


def onehot_from_class(class_idx: int) -> int:
    if class_idx < 0 or class_idx > 4:
        raise ValueError(f"class index out of range: {class_idx}")
    return 1 << class_idx


def class_from_onehot(onehot: int) -> int:
    onehot &= 0x1F
    if onehot == 0 or (onehot & (onehot - 1)) != 0:
        return -1
    return (onehot.bit_length() - 1)
