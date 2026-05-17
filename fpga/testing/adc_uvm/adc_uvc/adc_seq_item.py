from pyuvm import uvm_sequence_item


class ADCSeqItem(uvm_sequence_item):
    """One ADC transaction: a full epoch of ``frame_len`` raw 10-bit samples.

    Fields
    ------
    Physical payload (consumed by driver only):
      samples         — list of raw 10-bit values; driver applies ac_gain /
                        dc_offset and masks to 8 bits before driving adc_data.

    Logical metadata (consumed by scoreboard):
      transaction_id  — 0-based epoch index within the TV dataset.
      expected_onehot — 5-bit one-hot class label from the reference file.
    """

    def __init__(
        self,
        name: str,
        samples: list[int] | None = None,
        transaction_id: int = 0,
        expected_onehot: int = 0,
    ):
        super().__init__(name)
        self.samples: list[int]   = [s & 0x3FF for s in (samples or [])]
        self.transaction_id: int  = int(transaction_id)
        self.expected_onehot: int = int(expected_onehot) & 0x1F

    def __str__(self) -> str:
        first = f"0x{self.samples[0]:03X}" if self.samples else "N/A"
        return (
            f"ADCSeqItem(id={self.transaction_id}, "
            f"samples={len(self.samples)}, "
            f"first={first}, "
            f"expected_oh=0b{self.expected_onehot:05b})"
        )


class ADCTransactionDoneItem(uvm_sequence_item):
    """Published by ADCMonitor on the analysis port when a full transaction completes.

    Carries ``transaction_index`` (count of completed transactions since reset)
    and ``sample_count`` (number of valid-high sample periods observed).
    """

    def __init__(self, name: str, transaction_index: int = 0, sample_count: int = 0):
        super().__init__(name)
        self.transaction_index: int = int(transaction_index)
        self.sample_count: int      = int(sample_count)

    def __str__(self) -> str:
        return (
            f"ADCTransactionDoneItem(tx_idx={self.transaction_index}, "
            f"samples={self.sample_count})"
        )


class ADCMetadataItem(uvm_sequence_item):
    """Metadata batch written by a sequence onto the sequencer ``metadata_ap``.

    ``row_indices`` carries an ordered queue of reference row numbers to be
    consumed by the scoreboard for output comparison.
    """

    def __init__(
        self,
        name: str,
        epoch_index: int = 0,
        row_indices: list[int] | None = None,
        expected_onehot: int = 0,
    ):
        super().__init__(name)
        self.epoch_index: int     = int(epoch_index)
        if row_indices is None:
            self.row_indices: list[int] = [self.epoch_index]
        else:
            self.row_indices = [int(idx) for idx in row_indices]
        self.expected_onehot: int = int(expected_onehot) & 0x1F

    def __str__(self) -> str:
        return (
            f"ADCMetadataItem(rows={self.row_indices}, "
            f"expected_oh=0b{self.expected_onehot:05b})"
        )


class ADCSampleItem(uvm_sequence_item):
    """Published by ADCDriver after each individual sample is sent to the DUT.

    Consumed by ECGPredictor to accumulate a full frame before checking.
    """

    def __init__(
        self,
        name: str,
        sample_value: int = 0,
        epoch_index: int = 0,
        sample_index: int = 0,
    ):
        super().__init__(name)
        self.sample_value: int = int(sample_value) & 0xFF
        self.epoch_index: int  = int(epoch_index)
        self.sample_index: int = int(sample_index)

    def __str__(self) -> str:
        return (
            f"ADCSampleItem(epoch={self.epoch_index}, "
            f"sample_idx={self.sample_index}, "
            f"value=0x{self.sample_value:02X})"
        )
