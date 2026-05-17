from pyuvm import ConfigDB, uvm_sequence

from ecg_uvm.uart_tx_uvc.uart_tx_seq_lib import (
    ECGCsrModeAdcApStartSequence,
    ECGCsrSoftResetPulseSequence,
    ECGCsrThresholdSequence,
)
from ecg_uvm.adc_uvc.adc_seq_lib import ADCNormalSequence


class ECGAdcVirtualSequence(uvm_sequence):
    """Full ADC test virtual sequence: CSR setup followed by N ADC epochs.

    Knobs (set before calling start()):
        uart_tx_sequencer : UART TX agent sequencer handle
        adc_sequencer     : ADC agent sequencer handle
        num_epochs        : number of epochs to drive (default: 1)

    Default per-epoch sequence is ADCNormalSequence.  To change the stimulus,
    register a factory override in the test's build_phase() after calling
    super().build_phase():

        uvm_factory().set_type_override_by_type(ADCNormalSequence, ADCVentricularSequence)
    """

    def __init__(self, name: str = "ECGAdcVirtualSequence"):
        super().__init__(name)
        self.uart_tx_sequencer = None
        self.adc_sequencer = None
        self.num_epochs: int = 1

    async def body(self):
        # 0. Soft reset: clears any in-flight HLS engine state from a previous
        #    run.  Without this, a half-processed inference left over from the
        #    last test can produce a spurious UART output byte at the start of
        #    this run, shifting the output→epoch alignment.
        soft_rst = ECGCsrSoftResetPulseSequence("pre_run_soft_rst")
        await soft_rst.start(self.uart_tx_sequencer)

        # 0b. Flush the serial RX buffer AFTER soft reset.
        #     The HLS engine is now halted, so no new output bytes will be
        #     generated.  Any byte that the previous run's inference had queued
        #     in the FPGA UART serializer (takes ≤87 µs/byte at 115200 baud)
        #     will have arrived in the OS buffer within the 200 ms drain window
        #     and is then atomically discarded.  Without this, a stale byte
        #     enters scoreboard.dut_tx_fifo before any metadata is queued,
        #     causing the scoreboard to spin on metadata_underflows and then
        #     match the stale byte against the wrong epoch — shifting all
        #     subsequent comparisons.
        serial_transport = ConfigDB().get(None, "", "serial_transport")
        await serial_transport.flush_rx(drain_s=0.3)

        # 1. CSR: threshold registers
        thresh = ECGCsrThresholdSequence("thresh")
        await thresh.start(self.uart_tx_sequencer)

        # 2. CSR: ADC mode + ap_start
        mode = ECGCsrModeAdcApStartSequence("mode_start")
        await mode.start(self.uart_tx_sequencer)

        # 3. Drive all N epochs in a single sequence so that:
        #    - the DUT window counter stays aligned (num_epochs * frame_len samples exactly)
        #    - post_body is called once for the full batch
        epoch_seq = ADCNormalSequence.create("epochs")
        epoch_seq.num_epochs = self.num_epochs
        epoch_seq.seed = 5
        await epoch_seq.start(self.adc_sequencer)
