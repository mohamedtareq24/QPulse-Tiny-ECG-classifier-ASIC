# ECG pyUVM Integration Environment

This environment verifies integration of UART packet control + ECG core in ecg_wrapper using cocotb + pyuvm.

Architecture:
- 2 UART agents:
  - uart_rx_agent: active, drives DUT rx with CSR packetized transactions.
  - uart_tx_agent: passive, monitors DUT tx response bytes.
- Scoreboard with 2 TLM FIFOs:
  - rx_fifo captures expected sequence items from RX-side monitor stream.
  - tx_fifo captures observed TX sequence items from TX-side monitor stream.
- Comparison target: final argmax class result (one-hot bits [4:0] in TX byte).

Hard constraint:
- No memory-mapped CSR path is modeled.
- UART packet bits are the only CSR mechanism:
  - bit[12]: soft_rst
  - bit[11]: ap_start
  - bit[10]: qualifier
  - bit[9:0]: sample payload

Default stimulus and reference files are reused from cosim artifacts:
- ../../../Newstart/hls4ml_tinyecg_8bit/tb_data/tb_input_features.dat
- ../../../Newstart/hls4ml_tinyecg_8bit/tb_data/csim_results.log

## Setup

pip install -r requirements.txt

## Run Smoke

make sim TEST=ECGSmokeTest

## Run Regression Slice

make sim TEST=ECGMiniRegressionTest UART_BAUDDIV=16 BAUDDIV_SIM=16

## Useful overrides

- TB_INPUT_PATH=/custom/path/tb_input_features.dat
- TB_HLS_OUTPUT_PATH=/custom/path/csim_results.log
- ECG_FRAME_LEN=187
- UART_BAUDDIV=16
- CLK_PERIOD_NS=10
