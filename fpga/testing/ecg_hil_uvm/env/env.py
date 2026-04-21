from pyuvm import uvm_env

from ecg_hil_uvm.env.class_coverage import ECGClassCoverage
from ecg_hil_uvm.uart_rx_uvc.uart_rx_agent import UARTRxAgent
from ecg_hil_uvm.uart_tx_uvc.uart_tx_agent import UARTTxAgent
from ecg_hil_uvm.env.scoreboard import ECGScoreboard


class ECGEnv(uvm_env):
    def build_phase(self):
        super().build_phase()
        self.uart_tx_ag = UARTTxAgent.create("uart_tx_ag", self)
        self.uart_rx_ag = UARTRxAgent.create("uart_rx_ag", self)
        self.scoreboard = ECGScoreboard.create("scoreboard", self)
        self.class_coverage = ECGClassCoverage.create("class_coverage", self)

    def connect_phase(self):
        super().connect_phase()
        # TX driver stream is used for causality sanity: input must precede output.
        self.uart_tx_ag.driver.ap.connect(self.scoreboard.dut_rx_fifo.analysis_export)
        # RX UVC monitor publishes DUT result bytes consumed by scoreboard reference model.
        self.uart_rx_ag.monitor.ap.connect(self.scoreboard.dut_tx_fifo.analysis_export)
        # RX stream also feeds observed-class functional coverage collection.
        self.uart_rx_ag.monitor.ap.connect(self.class_coverage.dut_tx_fifo.analysis_export)
                            