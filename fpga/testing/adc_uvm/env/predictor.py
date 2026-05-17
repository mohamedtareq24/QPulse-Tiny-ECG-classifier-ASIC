"""ECGPredictor — pyUVM predictor component for the 1D-CNN testbench.

Architecture
------------
Data-driven state machine; ZERO internal timers or delays.
Timeouts are handled externally by the Scoreboard.

Ports
-----
seq_metadata_fifo  (uvm_tlm_analysis_fifo) ← ADCMetadataItem from sequencer.metadata_ap
adc_export         (uvm_tlm_analysis_fifo) ← ADCSampleItem from ADCDriver.adc_item_ap
uart_export        (uvm_tlm_analysis_fifo) ← UARTTxSeqItem/UARTCsrSeqItem/UARTRegSeqItem from UARTTxDriver.tx_item_ap
ap                 (uvm_analysis_port)     → ADCMetadataItem to scoreboard.metadata_fifo

State Machine
-------------
IDLE   → wait for Start command (via _start_event; guarded by reset)
ARMED  → accumulate cfg.frame_len ADCSampleItems from adc_export into sample_buf
CHECK  → fetch ADCMetadataItem from seq_metadata_fifo
         → _should_drop(sample_buf)? discard : ap.write(meta_item)
on _ResetException at any stage: flush all FIFOs, clear events, back to IDLE
"""

import asyncio

from pyuvm import ConfigDB, uvm_analysis_port, uvm_component, uvm_tlm_analysis_fifo

from ecg_uvm.adc_uvc.adc_seq_item import ADCMetadataItem, ADCSampleItem
from ecg_uvm.protocol import (
    REG_ADDR_CSR,
    REG_ADDR_FLOOR,
    REG_ADDR_MAX_WIN,
    REG_ADDR_RS_WIN,
    REG_ADDR_SLOPE,
    REG_ADDR_TOLERANCE,
    unpack_rx_packet,
)
from ecg_uvm.uart_tx_uvc.uart_tx_seq_item import UARTCsrSeqItem, UARTRegSeqItem, UARTTxSeqItem


class _ResetException(Exception):
    """Raised by _guarded_get / _guarded_get_event when _reset_event fires."""


class ECGPredictor(uvm_component):
    """Intercepts sequencer→scoreboard metadata, gates on Start/Reset commands
    and an optional drop condition, then forwards clean ADCMetadataItems to
    the scoreboard.
    """

    # ── Build ──────────────────────────────────────────────────────────────────

    def build_phase(self):
        super().build_phase()
        self.cfg = ConfigDB().get(self, "", "cfg")

        # TLM FIFOs — analysis_export connected from env.connect_phase.
        self.seq_metadata_fifo = uvm_tlm_analysis_fifo("seq_metadata_fifo", self)
        self.adc_export        = uvm_tlm_analysis_fifo("adc_export",        self)
        self.uart_export       = uvm_tlm_analysis_fifo("uart_export",       self)

        # Output to scoreboard.
        self.ap = uvm_analysis_port("ap", self)

        # Control events set by _uart_watcher; consumed by _main_loop.
        self._reset_event = asyncio.Event()
        self._start_event = asyncio.Event()

        # Statistics
        self.frames_forwarded = 0
        self.frames_dropped   = 0
        self.resets_handled   = 0
        self._last_violation_type = "none"
        self.violation_counts = {
            "short_frame": 0,
            "rs_window": 0,
            "max_window": 0,
            "tolerance": 0,
            "no_pair": 0,
        }

        # Mirror of wrapper CSR registers (csr_regs[0:5], 12-bit each).
        # Seeded from cfg so _should_drop works correctly before UART CSR writes arrive.
        self._csr_regs: list[int] = [
            0,
            self.cfg.slope_thresh,
            self.cfg.rs_window,
            self.cfg.max_window,
            self.cfg.tolerance,
            self.cfg.floor_offset,
        ]

    def _reset_csr_mirror(self):
        self._csr_regs = [
            0,
            self.cfg.slope_thresh,
            self.cfg.rs_window,
            self.cfg.max_window,
            self.cfg.tolerance,
            self.cfg.floor_offset,
        ]

    def _record_violation(self, kind: str):
        self._last_violation_type = kind
        if kind not in self.violation_counts:
            self.violation_counts[kind] = 0
        self.violation_counts[kind] += 1

    # ── UART watcher ───────────────────────────────────────────────────────────

    async def _uart_watcher(self):
        """Sole consumer of uart_export FIFO.

        Decodes every item and sets _reset_event / _start_event so the main
        state machine can react without consuming the UART stream itself.
        """
        while True:
            item = await self.uart_export.get()
            is_rst, is_start = self._mirror_csr_and_decode_ctrl(item)
            if is_rst:
                self.logger.info("[PREDICTOR] Reset command detected on uart_export")
                self._reset_csr_mirror()
                self._reset_event.set()
            if is_start:
                self.logger.info("[PREDICTOR] Start command detected on uart_export")
                self._start_event.set()

    def _mirror_csr_and_decode_ctrl(self, item) -> tuple[bool, bool]:
        """Mirror all CSR writes exactly like RTL wrapper and return (reset, start)."""
        is_rst = False
        is_start = False

        # Driver stream carries sequence items; all expose iter_packet_bytes().
        if isinstance(item, (UARTCsrSeqItem, UARTRegSeqItem, UARTTxSeqItem)):
            for pkt_16b, _b0, _b1 in item.iter_packet_bytes():
                is_csr, reg_addr, data_12b = unpack_rx_packet(pkt_16b)
                if not is_csr:
                    continue
                if 0 <= reg_addr < len(self._csr_regs):
                    self._csr_regs[reg_addr] = data_12b & 0xFFF
                if reg_addr == REG_ADDR_CSR:
                    is_rst = is_rst or bool((data_12b >> 2) & 0x1)
                    is_start = is_start or bool((data_12b >> 1) & 0x1)

        return is_rst, is_start

    # ── Guarded primitives ────────────────────────────────────────────────────

    async def _guarded_get(self, fifo):
        """Await fifo.get(), but raise _ResetException if _reset_event fires first.

        If both complete simultaneously, reset takes priority.
        """
        get_task   = asyncio.ensure_future(fifo.get())
        reset_task = asyncio.ensure_future(self._reset_event.wait())

        done, pending = await asyncio.wait(
            {get_task, reset_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        if reset_task in done:
            raise _ResetException()
        return get_task.result()

    async def _guarded_wait_event(self, event: asyncio.Event):
        """Await event.wait(), but raise _ResetException if _reset_event fires first."""
        wait_task  = asyncio.ensure_future(event.wait())
        reset_task = asyncio.ensure_future(self._reset_event.wait())

        done, pending = await asyncio.wait(
            {wait_task, reset_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        if reset_task in done:
            raise _ResetException()

    # ── Flush ─────────────────────────────────────────────────────────────────

    async def _flush_all_fifos(self):
        """Drain all three FIFOs non-blockingly, then clear both control events."""
        for fifo in (self.adc_export, self.uart_export, self.seq_metadata_fifo):
            while True:
                try:
                    await asyncio.wait_for(fifo.get(), timeout=0)
                except (asyncio.TimeoutError, Exception):
                    break
        self._reset_event.clear()
        self._start_event.clear()
        self.logger.info("[PREDICTOR] All FIFOs flushed, events cleared")

    # ── Drop condition ────────────────────────────────────────────────────────

    def _should_drop(self, samples: list[int]) -> bool:
        """High-level keep/drop decision over a 187-sample window.

        Flow:
        - take first 187 samples
        - detect slope-qualified peaks
        - use first two peaks
        - evaluate min/max window conditions between them
        - evaluate peak-to-peak tolerance
        """
        self._last_violation_type = "none"

        if len(samples) < 187:
            self._record_violation("short_frame")
            return True

        # Threshold registers mirrored from wrapper CSR map (low 8 bits used).
        slope_thresh = self._csr_regs[REG_ADDR_SLOPE] & 0xFF
        rs_window = self._csr_regs[REG_ADDR_RS_WIN] & 0xFF
        max_window = self._csr_regs[REG_ADDR_MAX_WIN] & 0xFF
        tolerance = self._csr_regs[REG_ADDR_TOLERANCE] & 0xFF
        floor_offset = self._csr_regs[REG_ADDR_FLOOR] & 0xFF

        data = [int(s) & 0xFF for s in samples[:187]]

        # Detect slope-qualified peaks and keep the first two.
        peaks: list[tuple[int, int]] = []
        refractory = 8
        backoff = 0

        for i in range(1, len(data)):
            dy = data[i] - data[i - 1]
            if backoff > 0:
                backoff -= 1
                continue
            if dy > slope_thresh:
                lo = i
                hi = min(len(data) - 1, i + 5)
                pval = max(data[lo : hi + 1])
                pidx = lo + data[lo : hi + 1].index(pval)
                peaks.append((pidx, pval))
                backoff = refractory
                if len(peaks) == 2:
                    break

        if len(peaks) < 2:
            # Only one slope-qualified peak found (typical for a single-beat epoch
            # where the T-wave slope is below slope_thresh).  The DUT still
            # processes and responds to these frames, so forward the metadata.
            return False

        peak1_idx, peak1 = peaks[0]
        peak2_idx, peak2 = peaks[1]

        if peak2_idx <= peak1_idx:
            self._record_violation("no_pair")
            return True

        between = data[peak1_idx:peak2_idx]
        if not between:
            self._record_violation("no_pair")
            return True

        interval_min = min(between)
        interval_max = max(between)

        # RS-window check (drop if fall from peak1 to floor-adjusted minimum is too large).
        floor_min = interval_min - floor_offset if interval_min > floor_offset else 0
        rs_gap = peak1 - floor_min if peak1 > floor_min else 0
        if rs_gap > rs_window:
            self._record_violation("rs_window")
            return True

        # Max-window check (drop if peak1 to interval max gap is too small).
        max_gap = peak1 - interval_max if peak1 > interval_max else 0
        if max_gap < max_window:
            self._record_violation("max_window")
            return True

        # Tolerance check between first and second peaks.
        abs_diff = peak1 - peak2 if peak1 >= peak2 else peak2 - peak1
        if abs_diff > tolerance:
            self._record_violation("tolerance")
            return True

        return False

    # ── Main state machine ────────────────────────────────────────────────────

    async def _main_loop(self):
        frame_len = self.cfg.frame_len

        while True:
            try:
                # ── IDLE: wait for Start ──────────────────────────────────────
                self._start_event.clear()
                self.logger.debug("[PREDICTOR] → IDLE: waiting for Start")
                await self._guarded_wait_event(self._start_event)
                self._start_event.clear()
                self.logger.debug("[PREDICTOR] → ARMED: accumulating frames")

                # ── ARMED: process frames continuously until Reset ────────────
                # One Start event arms the predictor for all subsequent frames;
                # only a Reset sends it back to IDLE.
                while True:
                    slope_thresh = self._csr_regs[REG_ADDR_SLOPE] & 0xFF
                    prev_s: int = 0
                    pre_s: int = 0
                    peak1_found = False

                    while not peak1_found:
                        sample_item: ADCSampleItem = await self._guarded_get(self.adc_export)
                        s = sample_item.sample_value & 0xFF
                        dy = s - prev_s
                        if dy > slope_thresh:
                            peak1_found = True
                            sample_buf: list[int] = [pre_s, s]
                        pre_s = prev_s
                        prev_s = s

                    while len(sample_buf) < frame_len:
                        sample_item = await self._guarded_get(self.adc_export)
                        sample_buf.append(sample_item.sample_value & 0xFF)

                    self.logger.debug(
                        "[PREDICTOR] → CHECK: frame complete (%d samples)", len(sample_buf)
                    )

                    meta_item: ADCMetadataItem = await self._guarded_get(self.seq_metadata_fifo)

                    if self._should_drop(sample_buf):
                        self.frames_dropped += 1
                        self.logger.info(
                            "[PREDICTOR] Frame dropped: epoch=%s reason=%s",
                            meta_item.epoch_index,
                            self._last_violation_type,
                        )
                    else:
                        self.ap.write(meta_item)
                        self.frames_forwarded += 1
                        self.logger.debug(
                            "[PREDICTOR] Metadata forwarded: epoch=%s rows=%s",
                            meta_item.epoch_index,
                            meta_item.row_indices,
                        )

            except _ResetException:
                self.resets_handled += 1
                self.logger.info(
                    "[PREDICTOR] Reset received — flushing buffers "
                    "(resets_handled=%d, frames_forwarded=%d, frames_dropped=%d)",
                    self.resets_handled,
                    self.frames_forwarded,
                    self.frames_dropped,
                )
                await self._flush_all_fifos()
                # loop back to IDLE

    # ── UVM phases ─────────────────────────────────────────────────────────────

    async def run_phase(self):
        asyncio.create_task(self._uart_watcher())
        await self._main_loop()

    def report_phase(self):
        self.logger.info(
            "[PREDICTOR] Summary: forwarded=%d dropped=%d resets=%d "
            "short_frame=%d rs_window=%d max_window=%d tolerance=%d no_pair=%d",
            self.frames_forwarded,
            self.frames_dropped,
            self.resets_handled,
            self.violation_counts.get("short_frame", 0),
            self.violation_counts.get("rs_window", 0),
            self.violation_counts.get("max_window", 0),
            self.violation_counts.get("tolerance", 0),
            self.violation_counts.get("no_pair", 0),
        )
