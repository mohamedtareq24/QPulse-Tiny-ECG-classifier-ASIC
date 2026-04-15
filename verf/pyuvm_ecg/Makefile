TOPLEVEL_LANG ?= verilog
SIM           ?= icarus
SIM_LOWER     := $(shell echo $(SIM) | tr A-Z a-z)
.DEFAULT_GOAL := sim

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VERF_DIR := $(abspath $(MAKEFILE_DIR)/..)
ECG_ROOT := $(abspath $(MAKEFILE_DIR)/../../..)
TAPE_OUT_ROOT := $(abspath $(MAKEFILE_DIR)/../..)

TOPLEVEL := ecg_wrapper
COCOTB_TEST_MODULES := pyuvm_ecg.test_ecg_uart

RTL_DIR := $(TAPE_OUT_ROOT)/src/verilog
VERILOG_SOURCES := $(filter-out $(RTL_DIR)/FixedCompare.v,$(wildcard $(RTL_DIR)/*.v))
ROM_DATA_FILES := $(wildcard $(RTL_DIR)/*.dat)
ROM_STAGE_STAMP := sim_build/.rom_data_staged

# Speed up UART simulation while keeping protocol behavior identical.
BAUDDIV_SIM ?= 16

# Parameter override syntax differs per simulator:
#   Icarus:    -P<top>.<param>=<val>
#   Verilator: -G<param>=<val>  (no module prefix)
ifeq ($(SIM_LOWER),verilator)
COMPILE_ARGS += -GBAUDIV=$(BAUDDIV_SIM)
# --timing is required for cocotb coroutines under Verilator 5+
EXTRA_ARGS   += --timing
# Verilator timing runtime uses C++20 coroutines. GCC on this host expects -std=c++2a.
export CXXFLAGS += -std=c++2a
COROUTINE_CHECK := $(shell echo '' | $(CXX) -std=c++2a -x c++ - -include coroutine -c -o /tmp/.coro_check.o >/dev/null 2>&1 && echo ok || echo fail)
ifeq ($(COROUTINE_CHECK),fail)
$(error Verilator build needs a C++ compiler with <coroutine> support. Current CXX='$(CXX)' cannot compile it. Install a newer toolchain, for example g++-10 or newer, then rerun with CXX=/path/to/newer/g++)
endif
else
COMPILE_ARGS += -Pecg_wrapper.BAUDIV=$(BAUDDIV_SIM)
endif

# Waveform dumping.
# WAVES=1  -> FST via cocotb built-in (works for both Icarus and Verilator)
# VCD=1    -> VCD via wave_gen.v      (Icarus only — not supported under Verilator)
WAVES    ?= 0
VCD      ?= 0
VCD_FILE ?= sim.vcd

ifeq ($(VCD),1)
ifeq ($(SIM_LOWER),verilator)
$(error VCD=1 is not supported with Verilator. Use WAVES=1 instead.)
endif
VERILOG_SOURCES += wave_gen.v
COMPILE_ARGS    += '-DVCD_FILE="$(VCD_FILE)"'
endif

export PYTHONPATH := $(VERF_DIR):$(MAKEFILE_DIR):$(PYTHONPATH)
export PYTHON_BIN := $(ECG_ROOT)/.venv/bin/python
export PYTHON := $(PYTHON_BIN)
export PATH := $(ECG_ROOT)/.venv/bin:$(PATH)

# Data sources (can be overridden from CLI)
export TB_INPUT_PATH ?= $(ECG_ROOT)/Newstart/hls4ml_tinyecg_8bit/tb_data/tb_input_features.dat
export TB_HLS_OUTPUT_PATH ?= $(dir $(TB_INPUT_PATH))csim_results.log
export ECG_FRAME_LEN ?= 187
export CLK_PERIOD_NS ?= 10
export UART_BAUDDIV ?= $(BAUDDIV_SIM)

# Test selection: make sim TEST=ECGSmokeTest  (default: ECGSmokeTest)
TEST ?= ECGSmokeTest
export UVM_TESTNAME := $(TEST)


.PHONY: rom_stage
rom_stage: $(ROM_DATA_FILES)
	@mkdir -p sim_build
	@cp -f $(ROM_DATA_FILES) .
	@touch $(ROM_STAGE_STAMP)

CUSTOM_SIM_DEPS += rom_stage

COCOTB_CONFIG ?= $(or $(shell command -v cocotb-config 2>/dev/null),$(ECG_ROOT)/.venv/bin/cocotb-config)
COCOTB_MAKEFILES_DIR := $(shell $(COCOTB_CONFIG) --makefiles)

include $(COCOTB_MAKEFILES_DIR)/Makefile.inc
include $(COCOTB_MAKEFILES_DIR)/simulators/Makefile.$(SIM_LOWER)

.PHONY: wave
wave:
	@if ! command -v gtkwave >/dev/null 2>&1; then \
		echo "gtkwave not found in PATH"; \
		exit 1; \
	fi
	@if [ -f sim_build/ecg_wrapper.fst ]; then \
		gtkwave sim_build/ecg_wrapper.fst; \
	elif [ -f "$(VCD_FILE)" ]; then \
		gtkwave "$(VCD_FILE)"; \
	elif [ -f sim.vcd ]; then \
		gtkwave sim.vcd; \
	else \
		echo "No waveform found. Run 'make sim WAVES=1' or 'make sim VCD=1' first."; \
		exit 1; \
	fi

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Usage: make sim [OPTION=value ...]"
	@echo ""
	@echo "Simulator:"
	@echo "  SIM=icarus          Use Icarus Verilog (default)"
	@echo "  SIM=verilator       Use Verilator"
	@echo ""
	@echo "Test selection:"
	@echo "  TEST=ECGSmokeTest               1 epoch smoke test (default)"
	@echo "  TEST=ECGMiniRegressionTest      8 epochs"
	@echo "  TEST=ECGTenEpochTest            10 epochs"
	@echo "  TEST=ECGSoftResetTest           soft_rst between epochs"
	@echo "  TEST=ECGQualifierToggleTest     qualifier alternates per epoch"
	@echo ""
	@echo "Waveforms (pick one):"
	@echo "  WAVES=1             FST dump — sim_build/ecg_wrapper.fst (Icarus + Verilator)"
	@echo "  VCD=1               VCD dump — sim.vcd                   (Icarus only)"
	@echo "  VCD=1 VCD_FILE=f    VCD dump to custom file f            (Icarus only)"
	@echo "  make wave           Open sim_build/ecg_wrapper.fst or sim.vcd in GTKWave"
	@echo ""
	@echo "Simulation parameters:"
	@echo "  BAUDDIV_SIM=N       UART clock divider (default: 16)"
	@echo "  ECG_FRAME_LEN=N     Samples per epoch (default: 187)"
	@echo "  CLK_PERIOD_NS=N     Clock period in ns (default: 10)"
	@echo ""
	@echo "Data paths:"
	@echo "  TB_INPUT_PATH=path  Input features .dat file"
	@echo "  TB_HLS_OUTPUT_PATH=path  HLS cosim logits file (csim_results.log)"
	@echo ""
	@echo "Examples:"
	@echo "  make sim"
	@echo "  make sim TEST=ECGMiniRegressionTest SIM=verilator"
	@echo "  make sim WAVES=1"
	@echo "  make wave"
	@echo "  make sim VCD=1 VCD_FILE=debug.vcd TEST=ECGSmokeTest"
	@echo ""

clean::
	rm -rf sim_build
	rm -f results.xml
	rm -f tiny_ecg_no_activ_*.dat
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
