import os
from dataclasses import dataclass
from pathlib import Path

# Paths are relative to the directory containing this file (verf/ecg_hil_uvm/).
_HERE = Path(__file__).parent
_TV_C   = _HERE / "tv" / "cdatafile"
_TV_REF = _HERE / "tv"

_DEFAULT_INPUT_PATH      = str(_TV_C   / "c.tiny_ecg_no_activ.autotvin_input_layer_3.dat")
_DEFAULT_HLS_OUTPUT_PATH = str(_TV_C   / "c.tiny_ecg_no_activ.autotvout_layer11_out.dat")
_DEFAULT_REF_ONEHOT_PATH = str(_TV_REF / "ref_onehot.txt")


@dataclass
class ECGEnvConfig:
    frame_len: int = 187
    num_frames: int = 50
    clk_period_ns: int = 33
    uart_bauddiv: int = 260
    input_path: str = _DEFAULT_INPUT_PATH
    hls_output_path: str = _DEFAULT_HLS_OUTPUT_PATH
    ref_onehot_path: str = _DEFAULT_REF_ONEHOT_PATH
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    byte_timeout_s: float = 2.0
    response_timeout_s: float = 10.0

    @classmethod
    def from_env(cls) -> "ECGEnvConfig":
        return cls(
            frame_len=int(os.getenv("ECG_FRAME_LEN", "187")),
            num_frames=int(os.getenv("ECG_NUM_FRAMES", "50")),
            clk_period_ns=int(os.getenv("CLK_PERIOD_NS", "10")),
            uart_bauddiv=int(os.getenv("UART_BAUDDIV", "260")),
            input_path=os.getenv("TB_INPUT_PATH", _DEFAULT_INPUT_PATH),
            hls_output_path=os.getenv("TB_HLS_OUTPUT_PATH", _DEFAULT_HLS_OUTPUT_PATH),
            ref_onehot_path=os.getenv("TB_REF_ONEHOT_PATH", _DEFAULT_REF_ONEHOT_PATH),
            serial_port=os.getenv("HIL_SERIAL_PORT", "/dev/ttyUSB0"),
            baud_rate=int(os.getenv("HIL_BAUD_RATE", "115200")),
            byte_timeout_s=float(os.getenv("HIL_BYTE_TIMEOUT", "2.0")),
            response_timeout_s=float(os.getenv("HIL_RESP_TIMEOUT", "10.0")),
        )

    def resolve(self, base_dir: Path) -> "ECGEnvConfig":
        self.input_path = str((base_dir / self.input_path).resolve())
        if self.hls_output_path:
            self.hls_output_path = str((base_dir / self.hls_output_path).resolve())
        if self.ref_onehot_path:
            self.ref_onehot_path = str((base_dir / self.ref_onehot_path).resolve())
        return self
