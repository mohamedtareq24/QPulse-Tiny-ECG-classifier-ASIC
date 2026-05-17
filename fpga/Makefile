# =============================================================================
# fpga/Makefile — Vivado project flow for Zybo Z7-10 ECG design
# =============================================================================
VIVADO     ?= vivado
PROJ_TCL   := project_gen.tcl
PROJ_XPR   := vivado_project/ecg_zybo.xpr
BUILD_TCL  := build_bitstream.tcl

# HIL defaults (override on command line)
HIL_TEST    ?= ECGSmokeTest
HIL_PORT    ?= /dev/ttyUSB0
HIL_BAUD    ?= 115200
HIL_TIMEOUT ?= 10.0
HIL_NUM_FRAMES ?=
HIL_BYTE_TIMEOUT ?= 2.0

.PHONY: project open bitstream program hil-test clean help

## Create the Vivado project and open the GUI  (run once)
project:
	$(VIVADO) -source $(PROJ_TCL)

## Re-open an already generated project in the Vivado GUI
open:
	$(VIVADO) $(PROJ_XPR)

## Build bitstream in batch mode from an existing project
bitstream:
	$(VIVADO) -mode batch -source $(BUILD_TCL) -tclargs bitstream

## Program connected Zybo Z7-10 with generated bitstream
program:
	$(VIVADO) -mode batch -source $(BUILD_TCL) -tclargs program

## Run HIL test from fpga root (proxies into testing/Makefile)
hil-test:
	$(MAKE) -C testing hil TEST=$(HIL_TEST) PORT=$(HIL_PORT) BAUD=$(HIL_BAUD) TIMEOUT=$(HIL_TIMEOUT) HIL_NUM_FRAMES=$(HIL_NUM_FRAMES) BYTE_TIMEOUT=$(HIL_BYTE_TIMEOUT)

## Delete the generated project directory
clean:
	rm -rf vivado_project

help:
	@echo ""
	@echo "Usage: make <target> [VIVADO=/path/to/vivado]"
	@echo ""
	@echo "  project   Create project + open Vivado GUI (references src/, no copy)"
	@echo "  open      Re-open existing project in Vivado GUI"
	@echo "  bitstream Build implementation + bitstream in batch mode"
	@echo "  program   Program connected board with latest bitstream"
	@echo "  hil-test  Run HIL test from fpga root"
	@echo "  clean     Delete vivado_project/"
	@echo ""
	@echo "HIL variables (override inline):"
	@echo "  HIL_TEST=$(HIL_TEST)"
	@echo "  HIL_PORT=$(HIL_PORT)"
	@echo "  HIL_BAUD=$(HIL_BAUD)"
	@echo "  HIL_TIMEOUT=$(HIL_TIMEOUT)"
	@echo "  HIL_NUM_FRAMES=$(HIL_NUM_FRAMES)"
	@echo "  HIL_BYTE_TIMEOUT=$(HIL_BYTE_TIMEOUT)"
	@echo ""
	@echo "Example:"
	@echo "  make hil-test HIL_TEST=ECGTenEpochTest"
	@echo "  make hil-test HIL_TEST=ECGNEpochTest HIL_NUM_FRAMES=50"
	@echo "  make hil-test HIL_TEST=ECGNEpochTest HIL_NUM_FRAMES=50 HIL_BYTE_TIMEOUT=10 HIL_TIMEOUT=120"
	@echo ""
