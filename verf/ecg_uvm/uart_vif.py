"""Virtual interface for ECG UART wrapper."""


class ECGUartVif:
    """Wraps the DUT pins for the ECG UART interface.
    
    Pins:
      clk     - clock (input to DUT)
      arst_n  - async reset, active low (input to DUT)
      rx      - UART receive from host (input to DUT)
      tx      - UART transmit to host (output from DUT)
    """

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk
        self.arst_n = dut.arst_n
        self.rx = dut.rx
        self.tx = dut.tx
