import asyncio
import time

from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_driver, uvm_sequencer

from ecg_uvm.adc_uvc.adc_seq_item import ADCSeqItem, ADCSampleItem


class ADCSequencer(uvm_sequencer):
    def build_phase(self):
        super().build_phase()
        self.metadata_ap = uvm_analysis_port("metadata_ap", self)


class ADCDriver(uvm_driver):
    """Streams ADC samples to the FPGA via the XSDB JTAG transport.

    Instance attributes (configure before calling ``start()``):

      sample_rate_hz — ignored in HIL (timing is driven by adc_transport)
      dc_offset      — integer offset added to every sample after scaling (default: 0)
      ac_gain        — multiplicative gain applied to each raw sample      (default: 1.0)

    Driven value per sample: ``int(raw_sample * ac_gain + dc_offset) & 0xFF``
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")
        self.dc_offset: int   = self.cfg.dc_offset
        self.ac_gain:   float = self.cfg.ac_gain
        self.adc_vif = ConfigDB().get(self, "", "adc_vif")
        self.adc_item_ap = uvm_analysis_port("adc_item_ap", self)

    async def run_phase(self):
        sample_period_s = self.cfg.adc_sample_period_s

        # Assert valid permanently.  With valid=1, the FPGA outer FSM
        # (WAIT_COUNT → SEND_CMD → WAIT_ADC) captures whatever is in the data
        # register on every WAIT_ADC entry — once every 8 ms, at a fixed phase
        # set by its own 8 MHz clock.
        await self.adc_vif.write_valid(1)

        # Monotonic-clock write grid.
        # Instead of sleep(period) relative to the previous write (which
        # accumulates asyncio jitter over a 187-sample epoch), we target an
        # absolute wall-clock grid: grid_t, grid_t+T, grid_t+2T, …
        # Each write fires AT the grid point (maximum setup time before the next
        # FPGA capture), and the grid advances by exactly one sample period
        # regardless of how long the XSDB write actually took.
        # This eliminates within-run drift and keeps the phase relationship
        # between Python's writes and the FPGA's captures constant throughout
        # the entire test.
        grid_t = time.monotonic()

        while True:
            tr: ADCSeqItem = await self.seq_item_port.get_next_item()

            for sample_idx, sample in enumerate(tr.samples):
                # Sleep until the next grid point.
                delay = grid_t - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)

                driven = int(sample * self.ac_gain + self.dc_offset) & 0xFF
                await self.adc_vif.write_sample(driven)

                if tr.transaction_id != -1:
                    self.adc_item_ap.write(ADCSampleItem(
                        name=f"adc_sample_{tr.transaction_id}_{sample_idx}",
                        sample_value=driven,
                        epoch_index=tr.transaction_id,
                        sample_index=sample_idx,
                    ))

                # Advance the grid by one sample period (absolute, not relative).
                grid_t += sample_period_s

            self.seq_item_port.item_done()


class ADCAgent(uvm_agent):
    def build_phase(self):
        super().build_phase()
        self.sequencer = ADCSequencer.create("sequencer", self)
        self.driver    = ADCDriver.create("driver",    self)

    def connect_phase(self):
        super().connect_phase()
        self.driver.seq_item_port.connect(self.sequencer.seq_item_export)
