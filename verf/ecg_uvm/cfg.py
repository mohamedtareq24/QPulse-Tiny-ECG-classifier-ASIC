import os
from dataclasses import dataclass
from pathlib import Path

# Paths are relative to the directory containing this file (verf/ecg_uvm/).
_HERE = Path(__file__).parent
_TV_C   = _HERE / "tv" / "cdatafile"
_TV_REF = _HERE / "tv"

_DEFAULT_INPUT_PATH      = str(_TV_C   / "c.tiny_ecg_no_activ.autotvin_input_layer_3.dat")
_DEFAULT_HLS_OUTPUT_PATH = str(_TV_C   / "c.tiny_ecg_no_activ.autotvout_layer11_out.dat")
_DEFAULT_REF_ONEHOT_PATH = str(_TV_REF / "ref_onehot.txt")


@dataclass
class ECGEnvConfig:
    frame_len: int = 187
    num_frames: int = 4
    clk_period_ns: int = 10
    uart_bauddiv: int = 16
    rst_cycles: int = 8
    input_path: str = _DEFAULT_INPUT_PATH
    hls_output_path: str = _DEFAULT_HLS_OUTPUT_PATH
    ref_onehot_path: str = _DEFAULT_REF_ONEHOT_PATH
    rx_idle_cycles: int = 1
    tx_timeout_cycles: int = 400000
    end_drain_cycles: int = 200

    @classmethod
    def from_env(cls) -> "ECGEnvConfig":
        return cls(
            frame_len=int(os.getenv("ECG_FRAME_LEN", "187")),
            clk_period_ns=int(os.getenv("CLK_PERIOD_NS", "10")),
            uart_bauddiv=int(os.getenv("UART_BAUDDIV", "16")),
            input_path=os.getenv("TB_INPUT_PATH", _DEFAULT_INPUT_PATH),
            hls_output_path=os.getenv("TB_HLS_OUTPUT_PATH", _DEFAULT_HLS_OUTPUT_PATH),
            ref_onehot_path=os.getenv("TB_REF_ONEHOT_PATH", _DEFAULT_REF_ONEHOT_PATH),
            tx_timeout_cycles=int(os.getenv("TX_TIMEOUT_CYCLES", "400000")),
            end_drain_cycles=int(os.getenv("END_DRAIN_CYCLES", "200")),
        )

    def resolve(self, base_dir: Path) -> "ECGEnvConfig":
        self.input_path = str((base_dir / self.input_path).resolve())
        if self.hls_output_path:
            self.hls_output_path = str((base_dir / self.hls_output_path).resolve())
        if self.ref_onehot_path:
            self.ref_onehot_path = str((base_dir / self.ref_onehot_path).resolve())
        return self
