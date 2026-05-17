from pyuvm import ConfigDB, uvm_env

from ecg_uvm.adc_uvc.adc_agent import ADCAgent
from ecg_uvm.adc_uvc.adc_data_config import ADCDataConfig
from ecg_uvm.env.class_coverage import ECGClassCoverage
from ecg_uvm.env.predictor import ECGPredictor
from ecg_uvm.uart_rx_uvc.uart_rx_agent import UARTRxAgent
from ecg_uvm.uart_tx_uvc.uart_tx_agent import UARTTxAgent
from ecg_uvm.env.scoreboard import ECGScoreboard


class ECGEnv(uvm_env):
    def build_phase(self):
        super().build_phase()

        cfg = ConfigDB().get(self, "", "cfg")

        # ── Initialize HIL transports ─────────────────────────────────────────
        from ecg_uvm.transport import SerialTransport
        from ecg_uvm.adc_uvc.adc_jtag_transport import AdcJiagTransport

        serial_transport = SerialTransport()
        ConfigDB().set(None, "*", "serial_transport", serial_transport)
        ConfigDB().set(None, "*", "serial_vif", serial_transport)

        adc_transport = AdcJiagTransport(
            xsdb_path=cfg.xsdb_path,
            jtag_target_idx=cfg.jtag_target_idx,
            sample_addr=cfg.adc_sample_addr,
            valid_addr=cfg.adc_valid_addr,
        )
        ConfigDB().set(None, "*", "adc_transport", adc_transport)
        ConfigDB().set(None, "*", "adc_vif", adc_transport)
        self.logger.info("HIL transports initialized")

        # ── ADC data config: file I/O occurs exactly once here. ───────────────
        # Load the FULL dataset so random-sampling sequences (e.g. ADCNormalSequence)
        # can draw from the entire pool. cfg.num_frames controls how many epochs
        # the test runs, not how many rows exist in the data file.
        num_total = sum(
            1 for line in open(cfg.ref_onehot_path, encoding="utf-8")
            if line.strip().lower().startswith("0x")
        )
        adc_data_cfg = ADCDataConfig.from_files(
            input_path=cfg.input_path,
            ref_onehot_path=cfg.ref_onehot_path,
            frame_len=cfg.frame_len,
            num_epochs=num_total,
        )
        ConfigDB().set(None, "*", "adc_data_cfg", adc_data_cfg)
        self.logger.info(
            "ADCDataConfig loaded: %d epochs from %s",
            len(adc_data_cfg),
            cfg.input_path,
        )

        self.uart_tx_ag = UARTTxAgent.create("uart_tx_ag", self)
        self.uart_rx_ag = UARTRxAgent.create("uart_rx_ag", self)
        self.adc_ag     = ADCAgent.create("adc_ag", self)
        self.scoreboard = ECGScoreboard.create("scoreboard", self)
        self.predictor  = ECGPredictor.create("predictor", self)
        self.class_coverage = ECGClassCoverage.create("class_coverage", self)

    def connect_phase(self):
        super().connect_phase()
        # ── Predictor intercepts sequencer → scoreboard metadata wire ─────────
        # Sequencer metadata goes into the predictor, not directly to scoreboard.
        self.adc_ag.sequencer.metadata_ap.connect(self.predictor.seq_metadata_fifo.analysis_export)
        # ADC driver publishes one ADCSampleItem per driven sample (post-send).
        self.adc_ag.driver.adc_item_ap.connect(self.predictor.adc_export.analysis_export)
        # Also feed the scoreboard's causality counter so sent_sample_count increments.
        self.adc_ag.driver.adc_item_ap.connect(self.scoreboard.dut_rx_fifo.analysis_export)
        # TX driver publishes sent commands post-send; predictor detects Start/Reset.
        self.uart_tx_ag.driver.tx_item_ap.connect(self.predictor.uart_export.analysis_export)
        # Predictor outputs filtered ADCMetadataItems to scoreboard.
        self.predictor.ap.connect(self.scoreboard.metadata_fifo.analysis_export)
        # RX UVC monitor publishes DUT result bytes consumed by scoreboard reference model.
        self.uart_rx_ag.monitor.ap.connect(self.scoreboard.dut_tx_fifo.analysis_export)
        # RX stream also feeds observed-class functional coverage collection.
        self.uart_rx_ag.monitor.ap.connect(self.class_coverage.dut_tx_fifo.analysis_export)
