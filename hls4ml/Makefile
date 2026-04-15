# =============================================================
# TinyECG HLS4ML Flow Makefile
#
# Directory layout:
# Usage:
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 convert
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 tbdata
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 csim
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 synth
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 cosim
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 all
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 compare
#   make MODEL=../models/tiny_ecg_softmax_1 RUN=../run_1 clean
#   make summary                              -- all runs
# =============================================================

VITIS_HLS       ?= $(or $(shell command -v vitis_hls 2>/dev/null),vitis_hls)
VIVADO_SETTINGS ?= $(if $(XILINX_VIVADO),$(XILINX_VIVADO)/settings64.sh,)
PYTHON          := python3
SCRIPT_DIR      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TOOLS_SCRIPT_DIR ?= $(abspath $(SCRIPT_DIR)/../scripts)
TB_SAMPLES      := 500
TEST_CSV        := $(SCRIPT_DIR)/mitbih_test.csv

# ── Model directory (contains the .h5 file) ───────────────────
MODEL     ?= ../model/tiny_ecg_clip_relu_f3s
MODEL_DIR := $(abspath $(MODEL))
# Auto-detect the .h5 file inside MODEL_DIR (first match wins)
KERAS_MODEL := $(firstword $(wildcard $(MODEL_DIR)/*.h5))

# ── Run directory (contains hls4ml_config.yml) ────────────────
RUN     ?= ./tiny_ecg_clip_reluf3s_run1
RUN_DIR := $(abspath $(RUN))
CONFIG  := $(RUN_DIR)/hls4ml_config.yml

# Extract OutputDir and ProjectName from the run's YAML config
HLS_DIR  = $(RUN_DIR)/$(shell grep '^OutputDir:' $(CONFIG) | awk '{print $$2}')
PRJ_NAME = $(shell grep '^ProjectName:' $(CONFIG) | awk '{print $$2}')
LOG_DIR  := $(RUN_DIR)/logs

.PHONY: all convert tbdata csim synth cosim fifo_search change_depth validate parallel_cosim clean summary compare vivado_prj help

# ── Extract part from the HLS project.tcl ─────────────────────
PART := $(shell grep '^set part' $(HLS_DIR)/project.tcl 2>/dev/null | awk '{print $$3}' | tr -d '"')

# ── Default target ─────────────────────────────────────────────
all: convert tbdata csim synth

help:
	@echo ""
	@echo "TinyECG HLS4ML Flow"
	@echo "-------------------"
	@echo "  Specify MODEL=<keras model dir>  RUN=<run dir>"
	@echo ""
	@echo "  make MODEL=.. RUN=.. convert   — convert Keras → HLS project"
	@echo "  make MODEL=.. RUN=.. tbdata    — generate tb_data test vectors"
	@echo "  make MODEL=.. RUN=.. csim      — run C simulation"
	@echo "  make MODEL=.. RUN=.. synth     — run C/RTL synthesis"
	@echo "  make MODEL=.. RUN=.. cosim     — run RTL co-simulation (slow)"
	@echo "  make MODEL=.. RUN=.. all       — convert + tbdata + csim + synth"
	@echo "  make MODEL=.. RUN=.. clean     — remove generated files"
	@echo "  make MODEL=.. RUN=.. compare   — Keras vs HLS prediction comparison"
	@echo "  make RUN=.. vivado_prj           — create Vivado project from HLS RTL"
	@echo "  make RUN=.. vivado_prj CLOCK_NS=10.0 — override clock period (ns)"
	@echo "  make RUN=.. change_depth DEPTH=N          — set all FIFOs to depth N"
	@echo "  make RUN=.. change_depth DEPTH=N FIFO=... — set specific FIFOs only"
	@echo "  make RUN=.. change_depth DRY_RUN=1 DEPTH=N — preview changes only"
	@echo "  make RUN=.. change_depth RESTORE=1         — restore .bak backup"
	@echo "  make summary                   — print resource summary for all runs"
	@echo ""
	@echo "  Default MODEL : $(MODEL_DIR)"
	@echo "  Default RUN   : $(RUN_DIR)"
	@echo "  Models found  : $(wildcard ../model/*/*.h5)"
	@echo "  Runs found    : $(wildcard ./tiny_*/hls4ml_config.yml)"
	@echo ""

# ── Compare: Keras float32 vs HLS fixed-point ─────────────────
compare:
	@echo ">>> [$(RUN)] Comparing Keras vs HLS predictions..."
	@echo "    Keras model  : $(KERAS_MODEL)"
	@echo "    HLS project  : $(HLS_DIR)"
	@echo "    Test CSV     : $(TEST_CSV)"
	@mkdir -p $(LOG_DIR)
	KERAS_MODEL="$(KERAS_MODEL)" HLS_MODEL_DIR="$(HLS_DIR)" TEST_CSV="$(TEST_CSV)" \
	    $(PYTHON) $(TOOLS_SCRIPT_DIR)/compare_sim.py 2>&1 | tee $(LOG_DIR)/compare.log

# ── Convert: run hls4ml conversion ────────────────────────────
convert: $(CONFIG)
	@echo ">>> [$(RUN)] Converting model to HLS..."
	@mkdir -p $(LOG_DIR)
	cd $(TOOLS_SCRIPT_DIR) && KERAS_MODEL="$(KERAS_MODEL)" $(PYTHON) run_hls_conversion.py $(CONFIG) 2>&1 | tee $(LOG_DIR)/convert.log
	@echo ">>> [$(RUN)] HLS project written to $(HLS_DIR)"

# ── Generate testbench data ────────────────────────────────────
tbdata: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Generating tb_data ($(TB_SAMPLES) samples)..."
	@mkdir -p $(LOG_DIR)
	KERAS_MODEL="$(KERAS_MODEL)" TEST_CSV="$(TEST_CSV)" \
	    $(PYTHON) $(TOOLS_SCRIPT_DIR)/generate_tb_data.py $(HLS_DIR) $(TB_SAMPLES) 2>&1 | tee $(LOG_DIR)/tbdata.log

# ── C Simulation ───────────────────────────────────────────────
csim: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Running C simulation..."
	@mkdir -p $(LOG_DIR)
	cd $(HLS_DIR) && $(VITIS_HLS) -f build_prj.tcl \
	    -tclargs reset csim=1 synth=0 cosim=0 validation=0 \
	    2>&1 | tee $(abspath $(LOG_DIR))/csim.log
	@echo ">>> [$(RUN)] Csim done. Results: $(HLS_DIR)/tb_data/csim_results.log"

# ── C/RTL Synthesis ────────────────────────────────────────────
synth: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Running synthesis..."
	@mkdir -p $(LOG_DIR)
	cd $(HLS_DIR) && $(VITIS_HLS) -f build_prj.tcl \
	    -tclargs csim=0 synth=1 cosim=0 validation=0 \
	    2>&1 | tee $(abspath $(LOG_DIR))/synth.log
	@echo ">>> [$(RUN)] Synthesis done."
	@$(MAKE) --no-print-directory _print_synth_summary RUN=$(RUN)

# ── RTL Co-simulation ──────────────────────────────────────────
cosim: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Running RTL co-simulation (this takes a while)..."
	@mkdir -p $(LOG_DIR)
	@if [ -n "$(VIVADO_SETTINGS)" ] && [ -f "$(VIVADO_SETTINGS)" ]; then . "$(VIVADO_SETTINGS)"; fi; \
	cd $(HLS_DIR) && $(VITIS_HLS) -f build_prj.tcl \
	    -tclargs csim=0 synth=0 cosim=1 validation=1 \
	    2>&1 | tee $(abspath $(LOG_DIR))/cosim.log

# ── FIFO depth binary search ───────────────────────────────────
fifo_search: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Searching for minimum passing FIFO depth..."
	@mkdir -p $(LOG_DIR)
	$(PYTHON) $(TOOLS_SCRIPT_DIR)/fifo_depth_search.py $(HLS_DIR) 2>&1 | tee $(LOG_DIR)/fifo_search.log

# ── Validate RTL cosim output vs Keras reference and HLS (csim) ────────────
# Comparison 1: tb_data/rtl_cosim_results.log vs tb_data/tb_output_predictions.dat (Keras)
# Comparison 2: tb_data/rtl_cosim_results.log vs tb_data/csim_results.log (HLS csim, auto-detected)
# Checks argmax match per row (classification decision) for both comparisons.
# Usage:
#   make RUN=.. validate
#   make RUN=.. validate TOL=0.5    # also enforce max abs error <= 0.5
TOL ?=
validate:
	@echo ">>> [$(RUN)] Validating RTL cosim output..."
	$(PYTHON) $(TOOLS_SCRIPT_DIR)/validate_cosim.py $(HLS_DIR) \
	    $(if $(TOL),--tol $(TOL),)

# ── Parallel csim + cosim across N workers ────────────────────
# Splits tb_data across WORKERS copies of the HLS project and runs them in
# parallel. Synthesis is done once beforehand (reset=0 reuses it).
# Usage:
#   make RUN=.. parallel_cosim              # 20 workers, current tb_data
#   make RUN=.. parallel_cosim WORKERS=8
#   make RUN=.. parallel_cosim WORKERS=20 KEEP_WORKERS=1   # preserve worker dirs
WORKERS      ?= 20
KEEP_WORKERS ?=
parallel_cosim: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Parallel cosim: $(WORKERS) workers ..."
	@mkdir -p $(LOG_DIR)
	$(PYTHON) $(TOOLS_SCRIPT_DIR)/parallel_cosim.py $(HLS_DIR) \
	    --workers $(WORKERS) \
	    --vitis-hls $(VITIS_HLS) \
	    --vivado-settings $(VIVADO_SETTINGS) \
	    $(if $(KEEP_WORKERS),--keep-workers,) \
	    2>&1 | tee $(LOG_DIR)/parallel_cosim.log

# ── Change FIFO depth ──────────────────────────────────────────
# Usage:
#   make RUN=.. change_depth DEPTH=1
#   make RUN=.. change_depth DEPTH=8 FIFO="layer2_out layer4_out"
#   make RUN=.. change_depth DEPTH=4 DRY_RUN=1
#   make RUN=.. change_depth RESTORE=1
DEPTH   ?=
FIFO    ?=
DRY_RUN ?=
RESTORE ?=

change_depth: $(HLS_DIR)/build_prj.tcl
	@echo ">>> [$(RUN)] Changing FIFO depth..."
	$(PYTHON) $(TOOLS_SCRIPT_DIR)/change_fifo_depth.py $(HLS_DIR) \
	    $(if $(DEPTH),--depth $(DEPTH),) \
	    $(if $(FIFO),--fifo $(FIFO),) \
	    $(if $(DRY_RUN),--dry-run,) \
	    $(if $(RESTORE),--restore,)

# ── Clean ──────────────────────────────────────────────────────
clean:
	@echo ">>> [$(RUN)] Cleaning..."
	rm -rf $(HLS_DIR)/$(PRJ_NAME)_prj $(LOG_DIR) $(HLS_DIR)/vitis_hls*.log

# ── Create Vivado project from HLS RTL (syn/verilog) ──────────
# Reads the post-HLS RTL and creates a Vivado project (.xpr) that
# you can open in the Vivado GUI or run through implementation.
# Requires synthesis to have been run first (synth target).
# Usage:
#   make RUN=.. vivado_prj
#   make RUN=.. vivado_prj CLOCK_NS=10.0   # override clock period
CLOCK_NS  ?= 50.0
VIVADO_PRJ_DIR := $(RUN_DIR)/vivado_prj
RTL_DIR   := $(HLS_DIR)/$(PRJ_NAME)_prj/solution1/syn/verilog

vivado_prj:
	@echo ">>> [$(RUN)] Creating Vivado project from HLS RTL..."
	@if [ ! -d "$(RTL_DIR)" ]; then \
	    echo "ERROR: RTL directory not found: $(RTL_DIR)"; \
	    echo "       Run 'make RUN=$(RUN) synth' first."; \
	    exit 1; \
	fi
	@mkdir -p $(LOG_DIR)
	@if [ -n "$(VIVADO_SETTINGS)" ] && [ -f "$(VIVADO_SETTINGS)" ]; then . "$(VIVADO_SETTINGS)"; fi; \
	vivado -mode batch -nolog -nojournal \
	    -source $(TOOLS_SCRIPT_DIR)/create_vivado_project.tcl \
	    -tclargs "$(RTL_DIR)" "$(PART)" "$(PRJ_NAME)" "$(CLOCK_NS)" "$(VIVADO_PRJ_DIR)" \
	    2>&1 | tee $(LOG_DIR)/vivado_prj.log
	@echo ">>> [$(RUN)] Vivado project ready: $(VIVADO_PRJ_DIR)/$(PRJ_NAME)_vivado.xpr"


# ── Internal: print synthesis resource summary ─────────────────
_print_synth_summary:
	@RPT=$(HLS_DIR)/$(PRJ_NAME)_prj/solution1/syn/report/$(PRJ_NAME)_csynth.rpt; \
	if [ -f "$$RPT" ]; then \
	    echo ""; \
	    echo "=== Synthesis Summary: $(RUN) ==="; \
	    grep -A 8 "^\+-----" $$RPT | grep "^|Total\|^|Available \|^|Utilization" | head -6; \
	    grep "Estimated Fmax" $$RPT; \
	    echo ""; \
	fi

# ── Summary across all runs ────────────────────────────────────
summary:
	@echo ""
	@echo "============================================================"
	@echo " Synthesis Summary — All Runs"
	@echo "============================================================"
	@for cfg in $(wildcard ../run_*/hls4ml_config.yml); do \
	    run=$$(dirname $$cfg); \
	    $(MAKE) --no-print-directory _print_synth_summary RUN=$$run 2>/dev/null; \
	done
