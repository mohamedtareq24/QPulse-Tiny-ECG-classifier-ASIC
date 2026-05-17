from pyuvm import uvm_sequence


class UARTRxBaseSeq(uvm_sequence):
    """Base sequence for the UART RX UVC. Subclass to define expected result patterns."""

    async def body(self):
        pass
