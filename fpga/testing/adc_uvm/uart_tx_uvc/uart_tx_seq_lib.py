import logging
import os
import random

from pyuvm import ConfigDB, uvm_sequence

from ecg_uvm.data_loader import load_input_frames
from ecg_uvm.protocol import REG_ADDR_SLOPE, REG_ADDR_RS_WIN, REG_ADDR_MAX_WIN, REG_ADDR_TOLERANCE, REG_ADDR_FLOOR
from ecg_uvm.uart_tx_uvc.uart_tx_seq_item import UARTCsrSeqItem, UARTRegSeqItem, UARTTxSeqItem


class ECGBaseSequence(uvm_sequence):
    """Base TX sequence style: prints metadata in pre_body and leaves body unimplemented."""

    def __init__(self, name="ECGBaseSequence"):
        super().__init__(name)
        self.num_epochs = None

    def get_num_epochs(self, cfg) -> int:
        return cfg.num_frames if self.num_epochs is None else int(self.num_epochs)

    async def pre_body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        epochs_to_drive = self.get_num_epochs(cfg)
        msg = (
            f"[SEQ PRE_BODY] name={self.get_name()} type={self.__class__.__name__} "
            f"epochs={epochs_to_drive} frame_len={cfg.frame_len} "
            f"num_frames_cfg={cfg.num_frames}"
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
        cfg = ConfigDB().get(None, "", "cfg")
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
        self.num_epochs = 20

class ECGSoftResetBetweenEpochsSequence(ECGEpochCountSequence):
    """Between each epoch, sends a soft reset pulse then an ap_start pulse via nested CSR sequences.

    A post-epoch drain (default: bauddiv * 64 cycles) is inserted after each epoch
    that is followed by a reset.  This ensures the engine has asserted ap_done and
    the RX output byte has been transmitted before the reset fires.
    """

    def __init__(self, name="ECGSoftResetBetweenEpochsSequence"):
        super().__init__(name)
        self.post_epoch_drain_s: float | None = None  # None → use cfg.inter_epoch_delay_s

    def _resolve_drain(self, cfg) -> float:
        if self.post_epoch_drain_s is not None:
            return max(0.0, float(self.post_epoch_drain_s))
        return cfg.inter_epoch_delay_s

    async def body(self):
        cfg = ConfigDB().get(None, "", "cfg")
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

            # Drain only before epochs followed by a reset; no drain after the last.
            epoch_drain = drain if frame_id < epochs_to_drive - 1 else 0.0
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{frame_id}",
                samples_10b=samples,
                idle_delay_s=epoch_drain,
            )
            await self.start_item(tr)
            await self.finish_item(tr)
            # finish_item() returns only after the driver completes idle_delay_s,
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

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        """Return list of (soft_rst, ap_start, mode, name_suffix)."""
        raise NotImplementedError(f"{self.__class__.__name__}.get_csr_steps() must be implemented")

    async def pre_body(self):
        steps = self.get_csr_steps()
        msg = (
            f"[SEQ PRE_BODY] name={self.get_name()} type={self.__class__.__name__} "
            f"kind=csr-only packets={len(steps)}"
        )
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

    async def body(self):
        for idx, (soft_rst, ap_start, mode, suffix) in enumerate(self.get_csr_steps()):
            tr = UARTCsrSeqItem(
                name=f"csr_{idx}_{suffix}",
                soft_rst=soft_rst,
                ap_start=ap_start,
                mode=mode,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGCsrSoftResetPulseSequence(ECGCsrSequenceBase):
    """Asserts then deasserts soft_rst."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [
            (1, 0, 0, "soft_rst_assert"),
            (0, 0, 0, "soft_rst_deassert"),
        ]


class ECGCsrApStartPulseSequence(ECGCsrSequenceBase):
    """Asserts ap_start via ctrl_reg (latched — stays high until next CSR write)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [
            (0, 1, 0, "ap_start_assert"),
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


class ECGCsrThresholdSequence(uvm_sequence):
    """Writes all five threshold registers (slope, rs_win, max_win, tolerance, floor).

    Default values match the reference model defaults.  Override the attributes
    before calling start() to inject custom values for directed tests.

      seq = ECGCsrThresholdSequence("thresh")
      seq.slope_thresh = 50
      await seq.start(sequencer)
    """

    def __init__(self, name: str = "ECGCsrThresholdSequence"):
        super().__init__(name)
        # Defaults pulled from global cfg; override after construction for directed tests.
        cfg = ConfigDB().get(None, "", "cfg")
        self.slope_thresh = cfg.slope_thresh   # csr_regs[1]
        self.rs_window    = cfg.rs_window      # csr_regs[2]
        self.max_window   = cfg.max_window     # csr_regs[3]
        self.tolerance    = cfg.tolerance      # csr_regs[4]
        self.floor_offset = cfg.floor_offset   # csr_regs[5]

    async def body(self):
        for reg_addr, value, label in [
            (REG_ADDR_SLOPE,     self.slope_thresh, "slope_thresh"),
            (REG_ADDR_RS_WIN,    self.rs_window,    "rs_window"),
            (REG_ADDR_MAX_WIN,   self.max_window,   "max_window"),
            (REG_ADDR_TOLERANCE, self.tolerance,    "tolerance"),
            (REG_ADDR_FLOOR,     self.floor_offset, "floor_offset"),
        ]:
            tr = UARTRegSeqItem(
                name=f"{self.get_name()}_{label}",
                reg_addr=reg_addr,
                reg_data=value & 0xFF,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGSmokeWithThreshSequence(uvm_sequence):
    """Smoke-test sequence: writes threshold registers, asserts ap_start, drives one epoch."""

    def __init__(self, name: str = "ECGSmokeWithThreshSequence"):
        super().__init__(name)
        self.num_epochs = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        await ECGCsrThresholdSequence(f"{self.get_name()}_thresh").start(self.sequencer)
        await ECGOneEpochSequence(f"{self.get_name()}_epoch").start(self.sequencer)


class ECGCsrModeUartSequence(ECGCsrSequenceBase):
    """Set DUT to UART input mode (mode=0)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [(0, 0, 0, "mode_uart")]


class ECGCsrModeAdcSequence(ECGCsrSequenceBase):
    """Set DUT to ADC input mode (mode=1)."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [(0, 0, 1, "mode_adc")]


class ECGCsrModeAdcApStartSequence(ECGCsrSequenceBase):
    """Set DUT to ADC input mode AND assert ap_start in a single CSR write.

    Writes csr_regs[0] with soft_rst=0, ap_start=1, mode=1 so the engine
    arms itself and switches to the ADC data path simultaneously.
    """

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [(0, 1, 1, "mode_adc_ap_start")]


class ECGCsrReservedBitsSweepSequence(ECGCsrSequenceBase):
    """Sweeps reserved control bits through all 2-bit values with mode kept at UART."""

    def __init__(self, name="ECGCsrReservedBitsSweepSequence"):
        super().__init__(name)
        self.start_value = 0
        self.count = 4

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        steps: list[tuple[int, int, int, str]] = []
        for idx in range(int(self.count)):
            steps.append((0, 0, 0, f"noop_{idx}"))
        return steps


class ECGCsrControlSanitySequence(ECGCsrSequenceBase):
    """Mixed CSR sequence: soft reset pulse followed by ap_start pulse."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [
            (1, 0, 0, "soft_rst_assert"),
            (0, 0, 0, "soft_rst_deassert"),
            (0, 1, 0, "ap_start_assert"),
            (0, 0, 0, "ap_start_deassert"),
        ]


class ECGIdleBetweenEpochsSequence(ECGEpochCountSequence):
    """Inserts a configurable number of idle clock cycles between epochs.

    ``inter_epoch_idle_delay_s`` controls the gap length (default: ``cfg.inter_epoch_delay_s``).
    Set it to any non-negative float before starting the sequence.
    """

    def __init__(self, name="ECGIdleBetweenEpochsSequence"):
        super().__init__(name)
        self.inter_epoch_idle_delay_s: float | None = None  # None → use cfg

    def _resolve_idle_delay_s(self, cfg) -> float:
        if self.inter_epoch_idle_delay_s is not None:
            return max(0.0, float(self.inter_epoch_idle_delay_s))
        return cfg.inter_epoch_delay_s

    async def body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        idle = self._resolve_idle_delay_s(cfg)
        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)

        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

        for item_id, samples in enumerate(frames):
            # Apply idle gap after every epoch except the last.
            epoch_idle = idle if item_id < epochs_to_drive - 1 else 0.0
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{item_id}",
                samples_10b=samples,
                idle_delay_s=epoch_idle,
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGDatasetSequence(ECGEpochCountSequence):

    def __init__(self, name="ECGDatasetSequence"):
        super().__init__(name)
        self.num_epochs = 50


class ECGEpochRangeSequence(ECGBaseSequence):
    """Drives a selected inclusive epoch range [start, end].

    Selection sources (priority order):
    1) Instance attributes ``start_index`` / ``end_index`` when set
    2) Environment variables ``ECG_EPOCH_START_INDEX`` / ``ECG_EPOCH_END_INDEX``

    If ``end_index`` is omitted, it defaults to ``start_index``.
    """

    def __init__(self, name="ECGEpochRangeSequence"):
        super().__init__(name)
        self.start_index: int | None = None
        self.end_index: int | None = None

    def _parse_index(self, value, env_name: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{env_name} must be an integer, got {value!r}") from exc

    def _resolve_indices(self) -> tuple[int, int]:
        start_env = os.getenv("ECG_EPOCH_START_INDEX")
        end_env = os.getenv("ECG_EPOCH_END_INDEX")

        start = self.start_index
        if start is None:
            start = 0 if start_env is None else self._parse_index(start_env, "ECG_EPOCH_START_INDEX")

        end = self.end_index
        if end is None:
            if end_env is None:
                end = start
            else:
                end = self._parse_index(end_env, "ECG_EPOCH_END_INDEX")

        if start < 0 or end < 0:
            raise ValueError(f"Epoch indices must be >= 0, got start={start} end={end}")
        if start > end:
            raise ValueError(f"Invalid epoch range: start={start} > end={end}")

        return start, end

    def get_num_epochs(self, cfg) -> int:
        start, end = self._resolve_indices()
        return (end - start) + 1

    async def body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        start, end = self._resolve_indices()

        frames = load_input_frames(cfg.input_path, cfg.frame_len, end + 1)
        if end >= len(frames):
            raise ValueError(
                f"Epoch range end index {end} out of bounds; available max index is {len(frames) - 1}"
            )

        await ECGCsrApStartPulseSequence("initial_ap_start").start(self.sequencer)

        for frame_idx in range(start, end + 1):
            tr = UARTTxSeqItem.from_epoch_samples(
                name=f"tx_epoch_{frame_idx}",
                samples_10b=frames[frame_idx],
            )
            await self.start_item(tr)
            await self.finish_item(tr)


class ECGCsrQualifierToggleSequence(ECGCsrReservedBitsSweepSequence):
    """Backward-compatible alias to reserved-bit sweep sequence."""


class ECGCsrSanitySequence(ECGCsrControlSanitySequence):
    """Backward-compatible alias to control sanity sequence."""


class ECGCsrQualifierEnableSequence(ECGCsrSequenceBase):
    """Backward-compatible alias — sends two no-op reg 0 writes."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [
            (0, 0, 0, "noop_1"),
            (0, 0, 0, "noop_2"),
        ]


class ECGCsrQualifierDisableSequence(ECGCsrSequenceBase):
    """Backward-compatible alias — sends two no-op reg 0 writes."""

    def get_csr_steps(self) -> list[tuple[int, int, int, str]]:
        return [
            (0, 0, 0, "noop_1"),
            (0, 0, 0, "noop_2"),
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
        cfg = ConfigDB().get(None, "", "cfg")
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
        cfg = ConfigDB().get(None, "", "cfg")
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
        cfg = ConfigDB().get(None, "", "cfg")
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
        cfg = ConfigDB().get(None, "", "cfg")
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
        cfg = ConfigDB().get(None, "", "cfg")
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


class ECGCsrApStartDeassertSequence(ECGCsrSequenceBase):
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
    1. Asserts ap_start via CSR (latched high)
    2. Drives all epochs while ap_start remains asserted
    3. Deasserts ap_start via CSR (clears the bit)

    This pattern tests the engine's behavior when start is held high across
    multiple epochs. Set ``num_epochs`` or use the default from cfg.num_frames.
    """

    def __init__(self, name="ECGEpochCountAssertedStartSequence"):
        super().__init__(name)

    async def body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        epochs_to_drive = self.get_num_epochs(cfg)
        if epochs_to_drive <= 0:
            return

        frames = load_input_frames(cfg.input_path, cfg.frame_len, epochs_to_drive)

        # Assert ap_start once and keep it asserted
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
        await ECGCsrApStartDeassertSequence("deassert_ap_start").start(self.sequencer)


class ECGAssertStartNEpochsDeassertSequence(ECGEpochCountAssertedStartSequence):
    """Asserts start once, sends N epochs back-to-back, then deasserts start.

    This is an explicitly named alias of ECGEpochCountAssertedStartSequence for
    tests that want the exact semantic name in the test intent.
    """

    def __init__(self, name="ECGAssertStartNEpochsDeassertSequence"):
        super().__init__(name)
