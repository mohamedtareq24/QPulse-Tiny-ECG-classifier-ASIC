"""TX-only environment: just the TX UVC agent — no DUT, no RX agent."""
from pyuvm import uvm_env

from ecg_uvm.uart_tx_uvc.uart_tx_agent import UARTTxAgent
from tape_out.verf.ecg_uvm.uart_tx_uvc.test.tb_uvm.tx_scoreboard import TxUvcScoreboard


class TxUvcEnv(uvm_env):
    def build_phase(self):
        super().build_phase()
        self.uart_tx_ag = UARTTxAgent.create("uart_tx_ag", self)
        self.scoreboard = TxUvcScoreboard.create("scoreboard", self)

    def connect_phase(self):
        super().connect_phase()
        self.uart_tx_ag.monitor.ap.connect(self.scoreboard.mon_fifo.analysis_export)
