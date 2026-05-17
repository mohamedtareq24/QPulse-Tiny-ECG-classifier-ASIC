import logging
import random as _random

from pyuvm import ConfigDB, uvm_sequence

from ecg_uvm.adc_uvc.adc_seq_item import ADCMetadataItem, ADCSeqItem

# MIT-BIH one-hot class labels
ONEHOT_N = 0x01  # Normal
ONEHOT_S = 0x02  # Supraventricular ectopic beat
ONEHOT_V = 0x04  # Ventricular ectopic beat
ONEHOT_F = 0x08  # Fusion beat
ONEHOT_Q = 0x10  # Unknown / unclassifiable


class ADCBaseSequence(uvm_sequence):
    """Base class for ADC sequences.

    No file I/O is performed by any sequence.  Stimulus data is retrieved from
    the ``"adc_data_cfg"`` entry in the ConfigDB (an :class:`ADCDataConfig`
    object), which must have been populated during the ``build_phase`` of the
    Test or Environment before the sequence runs.

    Subclasses must implement ``body()`` and ``get_num_epochs()``.

    Metadata flow:
    - After each ``finish_item()``, one ``ADCMetadataItem`` is written to
      ``sequencer.metadata_ap`` so the scoreboard can check incrementally.
    """

    def __init__(self, name: str = "ADCBaseSequence"):
        super().__init__(name)

    def get_num_epochs(self, cfg) -> int:
        raise NotImplementedError(f"{self.__class__.__name__}.get_num_epochs() must be implemented")

    async def pre_body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        msg = (
            f"[ADC SEQ PRE_BODY] name={self.get_name()} type={self.__class__.__name__} "
            f"epochs={self.get_num_epochs(cfg)} frame_len={cfg.frame_len}"
        )
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

    async def body(self):
        raise NotImplementedError(f"{self.__class__.__name__}.body() must be implemented")


class ADCEpochSequence(ADCBaseSequence):
    """Drives a single epoch selected by ``epoch_index`` (default 0).

    One ``ADCMetadataItem`` is written to ``metadata_ap`` immediately after
    ``finish_item()`` so the scoreboard can check as soon as the item is driven.
    """

    def __init__(self, name: str = "ADCEpochSequence"):
        super().__init__(name)
        self.epoch_index: int = 0

    def get_num_epochs(self, cfg) -> int:
        return 1

    async def body(self):
        data_cfg = ConfigDB().get(None, "", "adc_data_cfg")
        if self.epoch_index >= len(data_cfg):
            raise ValueError(
                f"epoch_index={self.epoch_index} out of bounds; "
                f"adc_data_cfg has {len(data_cfg)} epoch(s)"
            )

        epoch = data_cfg[self.epoch_index]
        tr = ADCSeqItem(
            name=f"adc_epoch_{epoch.epoch_index}",
            samples=epoch.samples,
            transaction_id=epoch.epoch_index,
            expected_onehot=epoch.expected_onehot,
        )

        await self.start_item(tr)
        await self.finish_item(tr)
        self.sequencer.metadata_ap.write(
            ADCMetadataItem(
                name=f"meta_epoch_{epoch.epoch_index}",
                row_indices=[epoch.epoch_index],
            )
        )


class ADCRepeatEpochSequence(ADCBaseSequence):
    """Drives the same epoch index ``num_repeats`` times back-to-back.

    Knobs (set before calling start()):
        epoch_index  — which epoch from adc_data_cfg to repeat (default: 0)
        num_repeats  — how many times to send it (default: 1)
    """

    def __init__(self, name: str = "ADCRepeatEpochSequence"):
        super().__init__(name)
        self.epoch_index: int = 17368
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        data_cfg = ConfigDB().get(None, "", "adc_data_cfg")
        if self.epoch_index >= len(data_cfg):
            raise ValueError(
                f"epoch_index={self.epoch_index} out of bounds; "
                f"adc_data_cfg has {len(data_cfg)} epoch(s)"
            )

        epoch = data_cfg[self.epoch_index]

        preamble_tr = ADCSeqItem(
            name=f"preamble_repeat_{epoch.epoch_index}",
            samples=[0] * 125,
            transaction_id=-1,
            expected_onehot=0,
        )
        await self.start_item(preamble_tr)
        await self.finish_item(preamble_tr)

        for repeat_idx in range(self.num_epochs):
            tr = ADCSeqItem(
                name=f"adc_repeat_{epoch.epoch_index}_{repeat_idx}",
                samples=epoch.samples,
                transaction_id=epoch.epoch_index,
                expected_onehot=epoch.expected_onehot,
            )
            await self.start_item(tr)
            await self.finish_item(tr)
            self.sequencer.metadata_ap.write(
                ADCMetadataItem(
                    name=f"meta_repeat_{epoch.epoch_index}_{repeat_idx}",
                    row_indices=[epoch.epoch_index],
                )
            )
            zeros_tr = ADCSeqItem(
                name=f"zeros_after_repeat_{epoch.epoch_index}_{repeat_idx}",
                samples=[0] * 10,
                transaction_id=-1,
                expected_onehot=0,
            )
            await self.start_item(zeros_tr)
            await self.finish_item(zeros_tr)


class ADCNEpochSequence(ADCBaseSequence):
    """Drives ``num_epochs`` consecutive epochs back-to-back.

    ``num_epochs`` defaults to ``cfg.num_frames`` when not set explicitly.
    One ``ADCMetadataItem`` is written to ``metadata_ap`` after each
    ``finish_item()`` for incremental scoreboard checking.
    """

    def __init__(self, name: str = "ADCNEpochSequence"):
        super().__init__(name)
        self.num_epochs: int | None = None

    def get_num_epochs(self, cfg) -> int:
        return cfg.num_frames if self.num_epochs is None else int(self.num_epochs)

    async def body(self):
        cfg = ConfigDB().get(None, "", "cfg")
        n = self.get_num_epochs(cfg)
        if n <= 0:
            return

        data_cfg = ConfigDB().get(None, "", "adc_data_cfg")
        if n > len(data_cfg):
            raise ValueError(
                f"Requested {n} epochs but adc_data_cfg only has {len(data_cfg)} epoch(s)"
            )

        preamble_tr = ADCSeqItem(
            name=f"{self.get_name()}_preamble",
            samples=[0] * 125,
            transaction_id=-1,
            expected_onehot=0,
        )
        await self.start_item(preamble_tr)
        await self.finish_item(preamble_tr)

        for epoch_idx in range(n):
            epoch = data_cfg[epoch_idx]
            tr = ADCSeqItem(
                name=f"adc_epoch_{epoch.epoch_index}",
                samples=epoch.samples,
                transaction_id=epoch.epoch_index,
                expected_onehot=epoch.expected_onehot,
            )

            await self.start_item(tr)
            await self.finish_item(tr)
            self.sequencer.metadata_ap.write(
                ADCMetadataItem(
                    name=f"meta_epoch_{epoch.epoch_index}",
                    row_indices=[epoch.epoch_index],
                )
            )
            zeros_tr = ADCSeqItem(
                name=f"zeros_after_{epoch.epoch_index}",
                samples=[0] * 10,
                transaction_id=-1,
                expected_onehot=0,
            )
            await self.start_item(zeros_tr)
            await self.finish_item(zeros_tr)


class ADCRandomNSequence(ADCBaseSequence):

    def __init__(self, name: str = "ADCRandomNSequence"):
        super().__init__(name)
        
        self.class_ranges: dict[int, tuple[int, int]] = {
            ONEHOT_N: (0, 18117),
            ONEHOT_S: (18118, 18673),
            ONEHOT_V: (18674, 20121),
            ONEHOT_F: (20122, 20283),
            ONEHOT_Q: (20284, 21891),
        }

        self.class_counts: dict[int, int] = {
            ONEHOT_N: 0,
            ONEHOT_S: 0,
            ONEHOT_V: 0,
            ONEHOT_F: 0,
            ONEHOT_Q: 0,
        }
        self.seed: int | None = None
        self._driven: list[tuple[int, int]] = []

    def get_num_epochs(self, cfg) -> int:
        return sum(self.class_counts.values())

    async def body(self):
        active = {label: count for label, count in self.class_counts.items() if count > 0}
        if not active:
            raise ValueError(f"{self.get_name()}: class_counts is empty — nothing to drive")

        for label, count in active.items():
            if label not in self.class_ranges:
                raise ValueError(
                    f"{self.get_name()}: no range defined for class 0x{label:02X}"
                )
            start, end = self.class_ranges[label]
            pool_size = end - start + 1
            if count > pool_size:
                raise ValueError(
                    f"{self.get_name()}: class 0x{label:02X} requests {count} epochs "
                    f"but range [{start}, {end}] only has {pool_size}"
                )

        data_cfg = ConfigDB().get(None, "", "adc_data_cfg")
        total = len(data_cfg)

        rng = _random.Random(self.seed)

        selected_indices: list[int] = []
        for label, count in active.items():
            start, end = self.class_ranges[label]
            if end >= total:
                raise ValueError(
                    f"{self.get_name()}: class 0x{label:02X} range end {end} "
                    f">= adc_data_cfg length {total}"
                )
            selected_indices.extend(rng.sample(range(start, end + 1), count))

        rng.shuffle(selected_indices)
        self._driven = list(enumerate(selected_indices))

        preamble_tr = ADCSeqItem(
            name=f"{self.get_name()}_preamble",
            samples=[0] * 125,
            transaction_id=-1,
            expected_onehot=0,
        )
        await self.start_item(preamble_tr)
        await self.finish_item(preamble_tr)

        msg = (
            f"[ADC RAND-N] name={self.get_name()} total={len(selected_indices)} "
            f"counts={{{', '.join(f'0x{k:02X}:{v}' for k, v in self.class_counts.items())}}} "
            f"seed={self.seed}"
        )
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

        for epoch_idx in selected_indices:
            epoch = data_cfg[epoch_idx]
            tr = ADCSeqItem(
                name=f"adc_epoch_{epoch.epoch_index}",
                samples=epoch.samples,
                transaction_id=epoch.epoch_index,
                expected_onehot=epoch.expected_onehot,
            )
            await self.start_item(tr)
            await self.finish_item(tr)
            self.sequencer.metadata_ap.write(
                ADCMetadataItem(
                    name=f"meta_epoch_{epoch.epoch_index}",
                    row_indices=[epoch.epoch_index],
                )
            )
            # Send 10 zero-valued samples after every epoch (transaction_id=-1 keeps
            # them invisible to adc_item_ap / scoreboard causality counter).  These
            # zeros let the DUT's slope-detector drain back to prev_s=0 before the
            # next epoch arrives, so each epoch's QRS peak produces a clean trigger
            # at position 0 regardless of where the previous window ended.
            zeros_tr = ADCSeqItem(
                name=f"zeros_after_{epoch.epoch_index}",
                samples=[0] * 10,
                transaction_id=-1,
                expected_onehot=0,
            )
            await self.start_item(zeros_tr)
            await self.finish_item(zeros_tr)

    async def post_body(self):
        if not self._driven:
            return
        lines = [
            f"[ADC POST-BODY] {self.get_name()} — {len(self._driven)} epochs driven:"
        ]
        for drive_pos, epoch_idx in self._driven:
            oh = self._driven_onehot(epoch_idx)
            label = {ONEHOT_N: "N", ONEHOT_S: "S", ONEHOT_V: "V",
                     ONEHOT_F: "F", ONEHOT_Q: "Q"}.get(oh, f"0x{oh:02X}")
            lines.append(f"  [{drive_pos:3d}] dataset_idx={epoch_idx:5d}  class={label}")
        msg = "\n".join(lines)
        print(msg)
        logging.getLogger(self.__class__.__name__).info(msg)

    def _driven_onehot(self, epoch_idx: int) -> int:
        data_cfg = ConfigDB().get(None, "", "adc_data_cfg")
        return data_cfg[epoch_idx].expected_onehot


class ADCNineNormalOneBadSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCNineNormalOneBadSequence"):
        super().__init__(name)
        self.bad_class: int = ONEHOT_V

    def get_num_epochs(self, cfg) -> int:
        return 10

    async def body(self):
        self.class_counts = {
            ONEHOT_N: 9,
            ONEHOT_S: 0,
            ONEHOT_V: 0,
            ONEHOT_F: 0,
            ONEHOT_Q: 0,
        }
        self.class_counts[self.bad_class] = 1
        await super().body()


class ADCNormalSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCNormalSequence"):
        super().__init__(name)
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        self.class_counts = {ONEHOT_N: self.num_epochs, ONEHOT_S: 0, ONEHOT_V: 0, ONEHOT_F: 0, ONEHOT_Q: 0}
        await super().body()


class ADCSupraventricularSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCSupraventricularSequence"):
        super().__init__(name)
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        self.class_counts = {ONEHOT_N: 0, ONEHOT_S: self.num_epochs, ONEHOT_V: 0, ONEHOT_F: 0, ONEHOT_Q: 0}
        await super().body()


class ADCVentricularSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCVentricularSequence"):
        super().__init__(name)
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        self.class_counts = {ONEHOT_N: 0, ONEHOT_S: 0, ONEHOT_V: self.num_epochs, ONEHOT_F: 0, ONEHOT_Q: 0}
        await super().body()


class ADCFusionSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCFusionSequence"):
        super().__init__(name)
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        self.class_counts = {ONEHOT_N: 0, ONEHOT_S: 0, ONEHOT_V: 0, ONEHOT_F: self.num_epochs, ONEHOT_Q: 0}
        await super().body()


class ADCUnknownSequence(ADCRandomNSequence):

    def __init__(self, name: str = "ADCUnknownSequence"):
        super().__init__(name)
        self.num_epochs: int = 1

    def get_num_epochs(self, cfg) -> int:
        return self.num_epochs

    async def body(self):
        self.class_counts = {ONEHOT_N: 0, ONEHOT_S: 0, ONEHOT_V: 0, ONEHOT_F: 0, ONEHOT_Q: self.num_epochs}
        await super().body()


class ADCFlatZeroPreambleSequence(ADCBaseSequence):
    """Sends 125 zero samples (~1 s at 125 Hz) before the real epoch."""

    def __init__(self, name: str = "ADCFlatZeroPreambleSequence"):
        super().__init__(name)

    def get_num_epochs(self, cfg) -> int:
        return 0

    async def body(self):
        tr = ADCSeqItem(
            name=f"{self.get_name()}_zeros",
            samples=[0] * 125,
            transaction_id=-1,
            expected_onehot=0,
        )
        await self.start_item(tr)
        await self.finish_item(tr)

