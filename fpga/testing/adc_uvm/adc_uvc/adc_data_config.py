from dataclasses import dataclass
from pathlib import Path

from pyuvm import uvm_object

from ecg_uvm.data_loader import load_input_frames


@dataclass
class ADCEpochData:
    """Physical payload and logical metadata for one ADC epoch.

    Attributes
    ----------
    epoch_index     : 0-based position in the TV dataset.
    samples         : raw 10-bit ECG samples — physical payload for the driver.
    expected_onehot : 5-bit one-hot class label from the reference file — metadata
                      for the scoreboard.
    """

    epoch_index: int
    samples: list[int]
    expected_onehot: int


class ADCDataConfig(uvm_object):
    """Pre-parsed ADC stimulus and reference data.

    Must be instantiated exactly once via :meth:`from_files` during the
    ``build_phase`` or ``start_of_simulation_phase`` of the UVM Test or
    Environment.  The resulting object is placed into the ConfigDB under
    key ``"adc_data_cfg"`` so sequences can retrieve it without performing
    any file I/O themselves.

    Physical payloads (raw 10-bit ECG samples) and logical metadata
    (expected one-hot class labels) are stored together as a list of
    :class:`ADCEpochData` entries indexed by epoch number.
    """

    def __init__(self, name: str = "ADCDataConfig"):
        super().__init__(name)
        self.epochs: list[ADCEpochData] = []

    @classmethod
    def from_files(
        cls,
        input_path: str,
        ref_onehot_path: str,
        frame_len: int,
        num_epochs: int,
    ) -> "ADCDataConfig":
        """Parse input dat and reference one-hot files and return a populated object.

        Parameters
        ----------
        input_path      : path to the TV input dat file (hex, one sample per line).
        ref_onehot_path : path to the reference one-hot txt file.
        frame_len       : number of samples per epoch (e.g. 187).
        num_epochs      : number of epochs to parse.
        """
        obj = cls("ADCDataConfig")

        # ── Physical payloads ──────────────────────────────────────────────────
        frames = load_input_frames(input_path, frame_len, num_epochs)

        # ── Logical metadata: expected one-hot class labels ────────────────────
        ref_onehots: list[int] = []
        with Path(ref_onehot_path).open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.lower().startswith("0x"):
                    ref_onehots.append(int(stripped, 16) & 0x1F)

        for epoch_idx, samples in enumerate(frames):
            expected = ref_onehots[epoch_idx] if epoch_idx < len(ref_onehots) else 0
            obj.epochs.append(
                ADCEpochData(
                    epoch_index=epoch_idx,
                    samples=samples,
                    expected_onehot=expected,
                )
            )

        return obj

    def __len__(self) -> int:
        return len(self.epochs)

    def __getitem__(self, idx: int) -> ADCEpochData:
        return self.epochs[idx]
