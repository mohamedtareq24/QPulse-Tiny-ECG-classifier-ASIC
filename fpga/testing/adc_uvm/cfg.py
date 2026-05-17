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


def _parse_int_env(name: str, default: int) -> int:
    val = os.getenv(name, "")
    if not val:
        return default
    return int(val, 16) if val.lower().startswith("0x") else int(val)


@dataclass
class ECGEnvConfig:
    frame_len: int = 187
    num_frames: int = 5
    input_path: str = _DEFAULT_INPUT_PATH
    hls_output_path: str = _DEFAULT_HLS_OUTPUT_PATH
    ref_onehot_path: str = _DEFAULT_REF_ONEHOT_PATH

    # HIL UART configuration
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    byte_timeout_s: float = 2.0
    response_timeout_s: float = 10.0

    # HIL ADC JTAG configuration
    xsdb_path: str = "xsdb"
    jtag_target_idx: int = 6
    adc_sample_addr: int = 0x40000000
    adc_valid_addr: int = 0x40010000
    adc_sample_period_s: float = 1.0 / 125.0  # 8 ms per sample

    # Delay inserted between epochs (e.g. to let the DUT output a result byte before next reset)
    inter_epoch_delay_s: float = 0.001

    # ECG predictor / DUT threshold registers (written via ECGCsrThresholdSequence)
    slope_thresh: int = 15   # csr_regs[1]
    rs_window:    int = 255   # csr_regs[2]
    max_window:   int = 0     # csr_regs[3]
    tolerance:    int = 255   # csr_regs[4]
    floor_offset: int = 10   # csr_regs[5]

    # ADC sample scaling applied by the driver before injection
    dc_offset: int   = 70   # integer added to every scaled sample
    ac_gain:   float = 2  # multiplicative gain on every raw sample

    @classmethod
    def from_env(cls) -> "ECGEnvConfig":
        d = cls()  # dataclass field defaults are the single source of truth
        return cls(
            frame_len=int(os.getenv("ECG_FRAME_LEN", str(d.frame_len))),
            num_frames=int(os.getenv("NUM_FRAMES", str(d.num_frames))),
            input_path=os.getenv("TB_INPUT_PATH", _DEFAULT_INPUT_PATH),
            hls_output_path=os.getenv("TB_HLS_OUTPUT_PATH", _DEFAULT_HLS_OUTPUT_PATH),
            ref_onehot_path=os.getenv("TB_REF_ONEHOT_PATH", _DEFAULT_REF_ONEHOT_PATH),
            serial_port=os.getenv("SERIAL_PORT", d.serial_port),
            baud_rate=int(os.getenv("BAUD_RATE", str(d.baud_rate))),
            byte_timeout_s=float(os.getenv("BYTE_TIMEOUT_S", str(d.byte_timeout_s))),
            response_timeout_s=float(os.getenv("RESPONSE_TIMEOUT_S", str(d.response_timeout_s))),
            xsdb_path=os.getenv("XSDB_PATH", d.xsdb_path),
            jtag_target_idx=int(os.getenv("JTAG_TARGET_IDX", str(d.jtag_target_idx))),
            adc_sample_addr=_parse_int_env("ADC_SAMPLE_ADDR", d.adc_sample_addr),
            adc_valid_addr=_parse_int_env("ADC_VALID_ADDR", d.adc_valid_addr),
            adc_sample_period_s=float(os.getenv("ADC_SAMPLE_PERIOD_S", str(d.adc_sample_period_s))),
            inter_epoch_delay_s=float(os.getenv("INTER_EPOCH_DELAY_S", str(d.inter_epoch_delay_s))),
            slope_thresh=int(os.getenv("ECG_SLOPE_THRESH", str(d.slope_thresh))),
            rs_window=int(os.getenv("ECG_RS_WINDOW", str(d.rs_window))),
            max_window=int(os.getenv("ECG_MAX_WINDOW", str(d.max_window))),
            tolerance=int(os.getenv("ECG_TOLERANCE", str(d.tolerance))),
            floor_offset=int(os.getenv("ECG_FLOOR_OFFSET", str(d.floor_offset))),
            dc_offset=int(os.getenv("ADC_DC_OFFSET", str(d.dc_offset))),
            ac_gain=float(os.getenv("ADC_AC_GAIN", str(d.ac_gain))),
        )

    def resolve(self, base_dir: Path) -> "ECGEnvConfig":
        self.input_path = str((base_dir / self.input_path).resolve())
        if self.hls_output_path:
            self.hls_output_path = str((base_dir / self.hls_output_path).resolve())
        if self.ref_onehot_path:
            self.ref_onehot_path = str((base_dir / self.ref_onehot_path).resolve())
        return self
