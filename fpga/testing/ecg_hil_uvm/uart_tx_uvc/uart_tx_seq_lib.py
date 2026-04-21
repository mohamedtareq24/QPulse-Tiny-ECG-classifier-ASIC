import logging
import random

from pyuvm import uvm_sequence

from ecg_hil_uvm.data_loader import load_input_frames
from ecg_hil_uvm.runtime import get_cfg
from ecg_hil_uvm.uart_tx_uvc.uart_tx_seq_item import UARTCsrSeqItem, UARTTxSeqItem


class ECGBaseSequence(uvm_sequence):
    """Base TX sequence style: prints metadata in pre_body and leaves body unimplemented."""

    def __init__(self, name="ECGBaseSequence"):
        super().__init__(name)
        self.num_epochs = None

    def get_num_epochs(self, cfg) -> int:
        return cfg.num_frames if self.num_epochs is None else int(self.num_epochs)

    async def pre_body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        msg = (
            f"[SEQ PRE_BODY] name={self.get_name()} type={self.__class__.__name__} "
            f"epochs={epochs_to_drive} frame_len={cfg.frame_len} "
            f"num_frames_cfg={cfg.num_frames} bauddiv={cfg.uart_bauddiv}"
        )
        # Keep a plain terminal print in addition to UVM logging for quick visibility.
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

    async def body(self):
        raise NotImplementedError(f"{self.__class__.__name__}.body() must be implemented")


class ECGEpochCountSequence(ECGBaseSequence):
    """Drives a requested number of epochs; one sequence item per epoch."""

    def __init__(self, name="ECGEpochCountSequence"):
        super().__init__(name)

    async def body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)

        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

        for item_id, samples in enumerate(frames):
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=samples,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGOneEpochSequence(ECGEpochCountSequence):
    """Convenience sequence for driving exactly one epoch."""

    def __init__(self, name="ECGOneEpochSequence"):
        super().__init__(name)
        self.num_epochs = 1


class ECGTenEpochSequence(ECGEpochCountSequence):
    """Convenience sequence for driving exactly ten epochs."""

    def __init__(self, name="ECGTenEpochSequence"):
        super().__init__(name)
        self.num_epochs = 10


class ECGNEpochSequence(ECGEpochCountSequence):
    """Convenience sequence for driving a configurable number of N epochs.
    
    Reads num_epochs from cfg.num_frames if not explicitly set.
    """

    def __init__(self, name="ECGNEpochSequence"):
        super().__init__(name)
        # Leave num_epochs as None to pick up cfg.num_frames in get_num_epochs()



class ECGSoftResetBetweenEpochsSequence(ECGEpochCountSequence):
    """Between each epoch, sends a soft reset pulse then an ap_start pulse via nested CSR sequences.

    A post-epoch drain (default: bauddiv * 64 cycles) is inserted after each epoch
    that is followed by a reset.  This ensures the engine has asserted ap_done and
    the RX output byte has been transmitted before the reset fires.
    """

    def __init__(self, name="ECGSoftResetBetweenEpochsSequence"):
        super().__init__(name)
        self.post_epoch_drain_cycles: int | None = None  # None → auto from cfg

    def _resolve_drain(self, cfg) -> int:
        if self.post_epoch_drain_cycles is not None:
            return max(0, int(self.post_epoch_drain_cycles))
        # Pipeline drain (~336 cycles) + UART TX byte (bauddiv*10) + margin → bauddiv*64
        return cfg.uart_bauddiv * 64

    async def body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)
        drain = self._resolve_drain(cfg)

        for frame_id, samples in enumerate(frames):
            if frame_id > 0:
                await ECGCsrSoftResetAndRestartSequence(f"between_ep{frame_id}_reset_restart").start(self.sequencer)
            else:
                await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

            # Drain only before epochs followed by a reset; no drain after the last epoch.
            epoch_drain = drain if frame_id < epochs_to_drive - 1 else 0
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{frame_id}",
                samples_10b=samples,
                idle_cycles=epoch_drain,
            )
            await self.start_item(tr)
            await self.finish_item(tr)
            # finish_item() returns only after the driver completes idle_cycles,
            # guaranteeing the engine has produced its output before reset fires.


class ECGReservedBitsTogglePerEpochSequence(ECGEpochCountSequence):
    """Toggles reserved control bits between 0b000 and 0b111 per epoch."""

    def __init__(self, name="ECGReservedBitsTogglePerEpochSequence"):
        super().__init__(name)


class ECGReservedBitsWalkingPerEpochSequence(ECGEpochCountSequence):
    """Walks one-hot reserved control bits across epochs: 001, 010, 100."""

    def __init__(self, name="ECGReservedBitsWalkingPerEpochSequence"):
        super().__init__(name)


class ECGCsrSequenceBase(ECGBaseSequence):
    """Base class for CSR-only sequences built from UARTCsrSeqItem transactions."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        """Return list of (soft_rst, ap_start, mode, ctrl_rsvd_1_0, name_suffix)."""
        raise NotImplementedError(f"{self.__class__.__name__}.get_csr_steps() must be implemented")

    async def pre_body(self):
        if getattr(self, "suppress_pre_body_log", False):
            return
        steps = self.get_csr_steps()
        msg = (
            f"[SEQ PRE_BODY] name={self.get_name()} type={self.__class__.__name__} "
            f"kind=csr-only packets={len(steps)}"
        )
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

    async def body(self):
        for idx, (soft_rst, ap_start, mode, ctrl_rsvd_1_0, suffix) in enumerate(self.get_csr_steps()):
            tr = UARTCsrSeqItem(
                name=f"csr_{idx}_{suffix}",
                soft_rst=soft_rst,
                ap_start=ap_start,
                mode=mode,
                ctrl_rsvd_1_0=ctrl_rsvd_1_0,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGCsrSoftResetPulseSequence(ECGCsrSequenceBase):
    """Asserts then deasserts soft_rst."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (1, 0, 0, 0, "soft_rst_assert"),
            (0, 0, 0, 0, "soft_rst_deassert"),
        ]


class ECGCsrApStartPulseSequence(ECGCsrSequenceBase):
    """Asserts ap_start via ctrl_reg (latched — stays high until next CSR write)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (0, 1, 0, 0, "ap_start_assert"),
        ]


class ECGCsrSoftResetAndRestartSequence(uvm_sequence):
    """Nested composite: soft reset pulse followed by an ap_start assert.

    Use this anywhere a reset must be immediately followed by re-arming the DUT.
    Nests ECGCsrSoftResetPulseSequence then ECGCsrApStartPulseSequence on the
    same sequencer so callers only need one await.
    """

    def __init__(self, name="ECGCsrSoftResetAndRestartSequence"):
        super().__init__(name)

    async def body(self):
        await ECGCsrSoftResetPulseSequence(f"{self.get_name()}_rst").start(self.sequencer)
        await ECGCsrApStartPulseSequence(f"{self.get_name()}_start").start(self.sequencer)


class ECGCsrModeUartSequence(ECGCsrSequenceBase):
    """Set DUT to UART input mode (mode=0)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [(0, 0, 0, 0, "mode_uart")]


class ECGCsrModeAdcSequence(ECGCsrSequenceBase):
    """Set DUT to ADC input mode (mode=1)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [(0, 0, 1, 0, "mode_adc")]


class ECGCsrReservedBitsSweepSequence(ECGCsrSequenceBase):
    """Sweeps reserved control bits through all 2-bit values with mode kept at UART."""

    def __init__(self, name="ECGCsrReservedBitsSweepSequence"):
        super().__init__(name)
        self.start_value = 0
        self.count = 4

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        steps: list[tuple[int, int, int, int, str]] = []
        for idx in range(int(self.count)):
            val = (self.start_value + idx) & 0x3
            steps.append((0, 0, 0, val, f"ctrl_rsvd_{val:02b}"))
        return steps


class ECGCsrControlSanitySequence(ECGCsrSequenceBase):
    """Mixed CSR sequence: soft reset pulse, reserved-bit update, ap_start pulse."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (1, 0, 0, 0, "soft_rst_assert"),
            (0, 0, 0, 0x1, "soft_rst_deassert_ctrl_01"),
            (0, 1, 0, 0x1, "ap_start_assert"),
            (0, 0, 0, 0x1, "ap_start_deassert"),
        ]


class ECGIdleBetweenEpochsSequence(ECGEpochCountSequence):
    """Inserts a configurable number of idle clock cycles between epochs.

    ``inter_epoch_idle_cycles`` controls the gap length (default: 10 baud
    periods expressed in clock cycles, i.e. ``10 * uart_bauddiv``).  Set it
    to any non-negative integer before starting the sequence.
    """

    def __init__(self, name="ECGIdleBetweenEpochsSequence"):
        super().__init__(name)
        self.inter_epoch_idle_cycles: int | None = None  # None → use default

    def _resolve_idle_cycles(self, cfg) -> int:
        if self.inter_epoch_idle_cycles is not None:
            return max(0, int(self.inter_epoch_idle_cycles))
        return 10 * cfg.uart_bauddiv

    async def body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        idle = self._resolve_idle_cycles(cfg)
        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)

        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

        for item_id, samples in enumerate(frames):
            # Apply idle gap after every epoch except the last.
            epoch_idle = idle if item_id < epochs_to_drive - 1 else 0
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=samples,
                idle_cycles=epoch_idle,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGDatasetSequence(ECGEpochCountSequence):

    def __init__(self, name="ECGDatasetSequence"):
        super().__init__(name)
        self.num_epochs = 50


class ECGCsrQualifierToggleSequence(ECGCsrReservedBitsSweepSequence):
    """Backward-compatible alias to reserved-bit sweep sequence."""


class ECGCsrSanitySequence(ECGCsrControlSanitySequence):
    """Backward-compatible alias to control sanity sequence."""


class ECGCsrQualifierEnableSequence(ECGCsrSequenceBase):
    """Backward-compatible legacy name mapped to reserved bits set to 0b111."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (0, 0, 0, 0x3, "ctrl_rsvd_enable"),
            (0, 0, 0, 0x3, "ctrl_rsvd_hold"),
        ]


class ECGCsrQualifierDisableSequence(ECGCsrSequenceBase):
    """Backward-compatible legacy name mapped to reserved bits set to 0b000."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (0, 0, 0, 0x0, "ctrl_rsvd_disable"),
            (0, 0, 0, 0x0, "ctrl_rsvd_hold"),
        ]


class ECGNormalThenNoStartSequence(ECGBaseSequence):
    """Sends one normal epoch (ap_start asserted), then deasserts ap_start and
    sends a second full epoch which the DUT should ignore.

    The deassert CSR packet is issued immediately after epoch 0's last sample,
    arriving ~300 cycles before the pipeline asserts ap_done.  The engine sees
    ap_start=0 when it checks after completing epoch 0 and stays idle, so epoch 1
    data accumulates in the FIFO but is never processed.

    Expected responses: 1 (epoch 0 only).
    """

    def __init__(self, name="ECGNormalThenNoStartSequence"):
        super().__init__(name)

    def get_num_epochs(self, cfg) -> int:
        return 1  # only epoch 0 produces a valid response

    async def body(self):
        cfg = get_cfg()
        frames = load_input_frames(cfg.input_path, cfg.frame_len, 2)

        # Arm engine and send epoch 0
        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)
        tr0 = UARTTxSeqItem.from_epoch_samples(
            name="tx_epoch_0_valid",
            samples_10b=frames[0],
        )
        await self.start_item(tr0)
        await self.finish_item(tr0)

        # Deassert ap_start immediately — arrives while epoch 0 is still in pipeline,
        # before ap_done fires, so engine stays idle after completion.
        await ECGCsrModeUartSequence("deassert_ap_start").start(self.sequencer)

        # Send epoch 1 without ap_start — DUT should ignore it, no response expected.
        tr1 = UARTTxSeqItem.from_epoch_samples(
            name="tx_epoch_1_no_start",
            samples_10b=frames[1],
        )
        await self.start_item(tr1)
        await self.finish_item(tr1)


class ECGDropStartMidEpochSequence(ECGBaseSequence):
    """Negative test: sends half an epoch with ap_start=0, then a full valid epoch.

    The DUT should ignore the partial no-start burst and produce exactly one response
    from the subsequent valid full epoch.
    """

    def __init__(self, name="ECGDropStartMidEpochSequence"):
        super().__init__(name)
        self.num_epochs = 1
        self.cutoff_fraction: float = 0.5

    def get_num_epochs(self, cfg) -> int:
        # Negative scenario: start is dropped, so no valid epoch response is expected.
        return 0

    async def body(self):
        cfg = get_cfg()
        frames = load_input_frames(cfg.input_path, cfg.frame_len, 1)
        samples = frames[0]
        cutoff = max(1, int(len(samples) * self.cutoff_fraction))

        partial = UARTTxSeqItem.from_epoch_samples(
            name="partial_no_start",
            samples_10b=samples[:cutoff],
        )
        await self.start_item(partial)
        await self.finish_item(partial)

        await ECGCsrApStartPulseSequence("ap_start_before_full").start(self.sequencer)
        full = UARTTxSeqItem.from_epoch_samples(
            name="full_epoch_with_start",
            samples_10b=samples,
        )
        await self.start_item(full)
        await self.finish_item(full)


class ECGSoftResetMidEpochRetrySequence(ECGBaseSequence):
    """Aborts mid-epoch via injected reset pulse, then retries the full epoch."""

    def __init__(self, name="ECGSoftResetMidEpochRetrySequence"):
        super().__init__(name)
        self.num_epochs = 1
        self.cutoff_fraction: float = 0.5
        self.randomize_abort_point: bool = False
        self.abort_sample_idx: int = 93
        self.frame_offset: int = 0

    def _pick_abort_idx(self, samples: list[int]) -> int:
        n = len(samples)
        if n <= 1:
            return 1

        if self.randomize_abort_point:
            # Deterministic randomization per sequence run for reproducibility.
            rng = random.Random(f"{self.get_name()}:{n}")
            return rng.randint(1, n - 1)

        return max(1, min(int(self.abort_sample_idx), n - 1))

    async def body(self):
        cfg = get_cfg()
        frames = load_input_frames(cfg.input_path, cfg.frame_len, self.frame_offset + 1)
        samples = frames[self.frame_offset]
        abort_idx = self._pick_abort_idx(samples)

        # Arm the DUT before sending the (doomed) partial epoch
        await ECGCsrApStartPulseSequence("pre_partial_ap_start").start(self.sequencer)

        # Partial epoch up to abort point
        partial = UARTTxSeqItem.from_epoch_samples(
            name="partial_epoch_abort",
            samples_10b=samples[:abort_idx],
        )
        await self.start_item(partial)
        await self.finish_item(partial)

        # Reset + re-arm: abort partial epoch, then re-assert ap_start
        await ECGCsrSoftResetAndRestartSequence("mid_epoch_reset_restart").start(self.sequencer)

        # Full epoch replay from sample 0
        full = UARTTxSeqItem.from_epoch_samples(
            name="retry_full_epoch",
            samples_10b=samples,
        )
        await self.start_item(full)
        await self.finish_item(full)


class ECGMidEpochResetReplaySequence(ECGSoftResetMidEpochRetrySequence):
    """Alias: abort an epoch with mid-epoch reset, then replay it from sample 0."""


class ECGSoftResetMidEpochNoRestartSequence(ECGBaseSequence):
    """Aborts mid-epoch via reset pulse only — no ap_start re-toggle — then resends the full epoch.

    Use this to verify the DUT still processes the epoch when ap_start was
    already asserted before the partial burst and is not re-toggled after reset.
    """

    def __init__(self, name="ECGSoftResetMidEpochNoRestartSequence"):
        super().__init__(name)
        self.num_epochs = 1
        self.cutoff_fraction: float = 0.5
        self.randomize_abort_point: bool = False
        self.abort_sample_idx: int = 93
        self.frame_offset: int = 0

    def _pick_abort_idx(self, samples: list[int]) -> int:
        n = len(samples)
        if n <= 1:
            return 1
        if self.randomize_abort_point:
            rng = random.Random(f"{self.get_name()}:{n}")
            return rng.randint(1, n - 1)
        return max(1, min(int(self.abort_sample_idx), n - 1))

    async def body(self):
        cfg = get_cfg()
        frames = load_input_frames(cfg.input_path, cfg.frame_len, self.frame_offset + 1)
        samples = frames[self.frame_offset]
        abort_idx = self._pick_abort_idx(samples)

        # Arm the DUT before the partial — verifying the DUT uses the latched ap_start after reset
        await ECGCsrApStartPulseSequence("pre_partial_ap_start").start(self.sequencer)

        # Partial epoch up to abort point
        partial = UARTTxSeqItem.from_epoch_samples(
            name="partial_epoch_abort",
            samples_10b=samples[:abort_idx],
        )
        await self.start_item(partial)
        await self.finish_item(partial)

        # Reset only — no ap_start re-toggle
        await ECGCsrSoftResetPulseSequence("mid_epoch_rst_no_restart").start(self.sequencer)

        # Resend full epoch without re-arming ap_start
        full = UARTTxSeqItem.from_epoch_samples(
            name="resend_full_epoch",
            samples_10b=samples,
        )
        await self.start_item(full)
        await self.finish_item(full)


class ECGSoftResetMidMultiEpochSequence(ECGBaseSequence):
    """Drive epochs, reset mid-stream, then continue and verify response count."""

    def __init__(self, name="ECGSoftResetMidMultiEpochSequence"):
        super().__init__(name)
        self.epochs_before_reset: int = 2
        self.epochs_after_reset: int = 1
        self.cutoff_fraction: float = 0.5

    def get_num_epochs(self, cfg) -> int:
        return self.epochs_before_reset + self.epochs_after_reset

    async def body(self):
        cfg = get_cfg()
        total = self.epochs_before_reset + self.epochs_after_reset
        frames = load_input_frames(cfg.input_path, cfg.frame_len, total)

        item_id = 0

        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

        for frame_id in range(self.epochs_before_reset):
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=frames[frame_id],
            )
            item_id += 1
            await self.start_item(tr)
            await self.finish_item(tr)

        nested = ECGSoftResetMidEpochRetrySequence(f"nested_retry_{item_id}")
        nested.cutoff_fraction = self.cutoff_fraction
        nested.frame_offset = self.epochs_before_reset
        await nested.start(self.sequencer)


class ECGCsrApStartDesassertSequence(ECGCsrSequenceBase):
    """Deasserts ap_start (clears the latched control bit)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, int, str]]:
        return [
            (0, 0, 0, 0, "ap_start_deassert"),
        ]


class ECGEpochCountAssertedStartSequence(ECGBaseSequence):
    """Asserts ap_start once, drives a configurable number of epochs without
    pulsing start again, then deasserts ap_start.

    Unlike ECGEpochCountSequence which pulses ap_start before driving epochs,
    this sequence:
    1. Optionally wiggles reset via nested CSR sequence (reset + restart)
    2. Asserts ap_start via CSR (latched high) if reset wiggle is disabled
    3. Drives all epochs while ap_start remains asserted
    4. Deasserts ap_start via CSR (clears the bit)

    This pattern tests the engine's behavior when start is held high across
    multiple epochs. Set ``num_epochs`` or use the default from cfg.num_frames.
    """

    def __init__(self, name="ECGEpochCountAssertedStartSequence"):
        super().__init__(name)
        # Default behavior: use a nested reset wiggle sequence before traffic.
        self.wiggle_reset_before_start: bool = False

    async def body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)

        # Either nest reset+restart, or only assert start once.
        if self.wiggle_reset_before_start:
            await ECGCsrSoftResetAndRestartSequence("pre_epoch_reset_restart").start(self.sequencer)
        else:
            await ECGCsrApStartPulseSequence("assert_ap_start").start(self.sequencer)

        # Drive all epochs without pulsing/reasserting start
        for item_id, samples in enumerate(frames):
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=samples,
            )
            await self.start_item(tr)
            await self.finish_item(tr)

        # Deassert ap_start at the end
        await ECGCsrApStartDesassertSequence("deassert_ap_start").start(self.sequencer)


class ECGSoftResetEveryFiveEpochsSequence(ECGBaseSequence):
    """Drive full traffic with boundary control every 5 epochs.

    Pattern:
    start assertion -> 5 epochs -> start deassertion -> reset pulse -> start assertion
    """

    def __init__(self, name="ECGSoftResetEveryFiveEpochsSequence"):
        super().__init__(name)
        self.chunk_size: int = 5
        self.boundary_drain_cycles: int | None = None

    def _resolve_boundary_drain(self, cfg) -> int:
        if self.boundary_drain_cycles is not None:
            return max(0, int(self.boundary_drain_cycles))
        # Allow pipeline/UART to drain before boundary control writes.
        return cfg.uart_bauddiv * 64

    async def _start_quiet(self, seq: uvm_sequence) -> None:
        # Keep top-level sequence banner visible, silence nested control banners.
        setattr(seq, "suppress_pre_body_log", True)
        await seq.start(self.sequencer)

    async def body(self):
        cfg = get_cfg()
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)
        chunk = max(1, int(self.chunk_size))
        drain = self._resolve_boundary_drain(cfg)

        await self._start_quiet(ECGCsrApStartPulseSequence("initial_ap_start"))

        for item_id, samples in enumerate(frames):
            end_of_chunk = ((item_id + 1) % chunk) == 0
            has_more = item_id < (epochs_to_drive - 1)
            epoch_drain = drain if (end_of_chunk and has_more) else 0

            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=samples,
                idle_cycles=epoch_drain,
            )
            await self.start_item(tr)
            await self.finish_item(tr)

            if end_of_chunk and has_more:
                await self._start_quiet(ECGCsrApStartDesassertSequence(f"chunk_{item_id}_deassert_ap_start"))
                await self._start_quiet(ECGCsrSoftResetPulseSequence(f"chunk_{item_id}_soft_reset_pulse"))
                await self._start_quiet(ECGCsrApStartPulseSequence(f"chunk_{item_id}_assert_ap_start"))

        await self._start_quiet(ECGCsrApStartDesassertSequence("final_deassert_ap_start"))
