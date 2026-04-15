TOPLEVEL_LANG ?= verilog
SIM           ?= icarus
SIM_LOWER     := $(shell echo $(SIM) | tr A-Z a-z)
.DEFAULT_GOAL := sim

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
UVC_DIR := $(abspath $(MAKEFILE_DIR)/..)
VERF_DIR := $(abspath $(MAKEFILE_DIR)/../../..)
ECG_ROOT := $(abspath $(MAKEFILE_DIR)/../../../../..)

TOPLEVEL           := uart_loopback
COCOTB_TEST_MODULES := test_tx_uvc
VERILOG_SOURCES    := uart_loopback.v

# UVC root is in the full pyuvm_ecg tree — point PYTHONPATH there.
PYUVM_ECG_DIR := $(VERF_DIR)/pyuvm_ecg
export PYTHONPATH := $(MAKEFILE_DIR):$(PYUVM_ECG_DIR):$(VERF_DIR):$(PYTHONPATH)
export PYTHON_BIN := $(ECG_ROOT)/.venv/bin/python
export PYTHON     := $(PYTHON_BIN)
export PATH       := $(ECG_ROOT)/.venv/bin:$(PATH)

# Simulation speed
BAUDDIV_SIM ?= 16

ifeq ($(SIM_LOWER),verilator)
EXTRA_ARGS += --timing
else
# No parameter override needed — loopback DUT has no generics.
endif

# Waveforms
WAVES    ?= 0
VCD      ?= 0
VCD_FILE ?= sim.vcd

ifeq ($(VCD),1)
ifeq ($(SIM_LOWER),verilator)
$(error VCD=1 is not supported with Verilator. Use WAVES=1 instead.)
endif
VERILOG_SOURCES += $(VERF_DIR)/pyuvm_ecg/wave_gen.v
COMPILE_ARGS    += '-DVCD_FILE="$(VCD_FILE)"'
endif

# Data sources — same defaults as the full env.
export TB_INPUT_PATH  ?= $(ECG_ROOT)/Newstart/hls4ml_tinyecg_8bit/tb_data/tb_input_features.dat
export TB_HLS_OUTPUT_PATH ?= $(dir $(TB_INPUT_PATH))csim_results.log
export ECG_FRAME_LEN  ?= 187
export CLK_PERIOD_NS  ?= 10
export UART_BAUDDIV   ?= $(BAUDDIV_SIM)

# Test selection
TEST ?= TxUvcOneEpochTest
export UVM_TESTNAME := $(TEST)

COCOTB_CONFIG       ?= $(or $(shell command -v cocotb-config 2>/dev/null),$(ECG_ROOT)/.venv/bin/cocotb-config)
COCOTB_MAKEFILES_DIR := $(shell $(COCOTB_CONFIG) --makefiles)

include $(COCOTB_MAKEFILES_DIR)/Makefile.inc
include $(COCOTB_MAKEFILES_DIR)/simulators/Makefile.$(SIM_LOWER)

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Usage: make sim [OPTION=value ...]"
	@echo ""
	@echo "Simulator:"
	@echo "  SIM=icarus      Use Icarus Verilog (default)"
	@echo "  SIM=verilator   Use Verilator"
	@echo ""
	@echo "Test selection:"
	@echo "  TEST=TxUvcOneEpochTest    Drive 1 epoch (default)"
	@echo "  TEST=TxUvcTenEpochTest    Drive 10 epochs"
	@echo "  TEST=TxUvcCsrSoftResetTest"
	@echo "  TEST=TxUvcCsrApStartPulseTest"
	@echo "  TEST=TxUvcCsrQualifierEnableTest"
	@echo "  TEST=TxUvcCsrQualifierDisableTest"
	@echo "  TEST=TxUvcCsrQualifierToggleTest"
	@echo "  TEST=TxUvcCsrSanityTest"
	@echo ""
	@echo "Waveforms:"
	@echo "  WAVES=1             FST via cocotb (Icarus + Verilator)"
	@echo "  VCD=1               VCD via wave_gen.v (Icarus only)"
	@echo ""
	@echo "Simulation parameters:"
	@echo "  BAUDDIV_SIM=N     UART clock divider (default: 16)"
	@echo "  ECG_FRAME_LEN=N   Samples per epoch  (default: 187)"
	@echo ""

clean::
	rm -rf sim_build
	rm -f results.xml
	rm -f sim.vcd
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
