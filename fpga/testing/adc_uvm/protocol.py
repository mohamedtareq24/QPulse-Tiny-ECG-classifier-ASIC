FRAC_BITS = 5
DATA_WIDTH = 10
MAX_RAW = (1 << (DATA_WIDTH - 1)) - 1
MIN_RAW = -(1 << (DATA_WIDTH - 1))

# CSR register address map (bits[14:12] of the RX packet)
REG_ADDR_CSR       = 0  # Control: bits [2]=soft_rst [1]=ap_start [0]=mode
REG_ADDR_SLOPE     = 1  # Slope Threshold
REG_ADDR_RS_WIN    = 2  # RS Window
REG_ADDR_MAX_WIN   = 3  # Max Window
REG_ADDR_TOLERANCE = 4  # Tolerance
REG_ADDR_FLOOR     = 5  # Floor Offset


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


# ── RX Packet helpers ───────────────────────────────────────────────────────
#
#  RX Packet (16-bit, 2 UART bytes — byte-0 first / LSB):
#    [15]    : CSR-space select  (0 = data packet, 1 = CSR write)
#    [14:12] : Register address  (for CSR writes; ignored for data packets)
#    [11:0]  : CSR data (12-bit) OR input sample (10-bit in [9:0])

def pack_data_packet(sample_10b: int) -> int:
    """Pack a 10-bit sample into a 16-bit data packet (bit[15]=0)."""
    return sample_10b & 0x3FF


def pack_csr_packet(reg_addr: int, csr_data: int) -> int:
    """Pack a CSR write packet: bit[15]=1, bits[14:12]=reg_addr, bits[11:0]=csr_data."""
    return (0x1 << 15) | ((reg_addr & 0x7) << 12) | (csr_data & 0xFFF)


def pack_ctrl_csr(soft_rst: int, ap_start: int, mode: int) -> int:
    """Build the 12-bit CSR data for reg 0 (control register).

    RTL mapping: csr_regs[0][2]=soft_rst, [1]=ap_start, [0]=mode
    """
    return ((soft_rst & 0x1) << 2) | ((ap_start & 0x1) << 1) | (mode & 0x1)


def unpack_rx_packet(packet: int) -> tuple[bool, int, int]:
    """Decode a 16-bit RX packet.

    Returns (is_csr, reg_addr, data_12b).
    For data packets is_csr=False and bits[9:0] of data_12b carry the sample.
    """
    packet &= 0xFFFF
    is_csr   = bool((packet >> 15) & 0x1)
    reg_addr = (packet >> 12) & 0x7
    data_12b = packet & 0xFFF
    return is_csr, reg_addr, data_12b


def packet_to_bytes(packet: int) -> tuple[int, int]:
    """Split a 16-bit packet into (byte0_LSB, byte1_MSB) for UART transmission."""
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
