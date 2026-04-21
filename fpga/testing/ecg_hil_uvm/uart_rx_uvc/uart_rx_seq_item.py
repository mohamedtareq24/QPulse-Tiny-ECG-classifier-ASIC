from pyuvm import uvm_sequence_item

from ecg_hil_uvm.protocol import decode_uart_tx_byte


# ──────────────────────────────────────────────────────────────────────────────
# UARTRxSeqItem
#   What the HOST RECEIVES from the DUT (captures DUT tx pin).
#   Carries the one-byte inference result:
#     [7] ap_idle  [6] ap_ready  [5] ap_done  [4:0] argmax one-hot
# ──────────────────────────────────────────────────────────────────────────────
class UARTRxSeqItem(uvm_sequence_item):
    def __init__(self, name: str, rx_byte: int = 0):
        super().__init__(name)
        self.rx_byte = rx_byte & 0xFF
        self.ap_idle, self.ap_ready, self.ap_done, self.argmax_onehot = decode_uart_tx_byte(self.rx_byte)

    def __str__(self) -> str:
        return (
            f"UARTRxSeqItem(byte=0x{self.rx_byte:02X}, idle={self.ap_idle}, ready={self.ap_ready}, "
            f"done={self.ap_done}, onehot=0b{self.argmax_onehot:05b})"
        )
