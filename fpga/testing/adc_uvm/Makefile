# =============================================================================
# adc_uvm/Makefile — HIL test runner for adc_uvm package
# =============================================================================
# Run from fpga/adc_uvm/:   make test TEST=ECGAdcSmokeTest
# Run from fpga/:           make -C adc_uvm test TEST=ECGAdcSmokeTest
# =============================================================================

FPGA_ROOT    := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
VENV_PYTHON  := $(FPGA_ROOT)/.venv/bin/python
RUNNER       := $(FPGA_ROOT)/run_adc.py

# Defaults (override on command line)
TEST         ?= ECGAdcSmokeTest
PORT         ?= /dev/ttyUSB2
BAUD         ?= 115200
TIMEOUT      ?= 2.0
BYTE_TIMEOUT ?= 2.0
VERBOSITY    ?= MEDIUM
NUM_FRAMES   ?=

.PHONY: test adc-smoke smoke ten regression full soft-reset help

## Run any test by name
test:
	$(VENV_PYTHON) $(RUNNER) \
		--test $(TEST) \
		--port $(PORT) \
		--baud $(BAUD) \
		--timeout $(TIMEOUT) \
		--byte-timeout $(BYTE_TIMEOUT) \
		--verbosity $(VERBOSITY) \
		$(if $(NUM_FRAMES),--num-frames $(NUM_FRAMES),)

## ADC smoke test — 1 epoch via JTAG ADC path
adc-smoke:
	$(MAKE) test TEST=ECGAdcSmokeTest

## UART smoke test — 1 epoch via UART data path
smoke:
	$(MAKE) test TEST=ECGSmokeTest

## 10-epoch test
ten:
	$(MAKE) test TEST=ECGTenEpochTest

## Mini regression — 8 epochs
regression:
	$(MAKE) test TEST=ECGMiniRegressionTest

## Full dataset — 50 epochs
full:
	$(MAKE) test TEST=ECGFullDatasetTest TIMEOUT=60

## Soft-reset between epochs
soft-reset:
	$(MAKE) test TEST=ECGSoftResetTest

help:
	@echo ""
	@echo "Usage: make [target] [VAR=value ...]"
	@echo ""
	@echo "Shortcut targets:"
	@echo "  adc-smoke    ECGAdcSmokeTest       - 1 epoch via JTAG ADC path (default)"
	@echo "  smoke        ECGSmokeTest           - 1 epoch via UART data path"
	@echo "  ten          ECGTenEpochTest        - 10 epochs"
	@echo "  regression   ECGMiniRegressionTest  - 8 epochs"
	@echo "  full         ECGFullDatasetTest     - 50 epochs"
	@echo "  soft-reset   ECGSoftResetTest"
	@echo ""
	@echo "Generic target:"
	@echo "  make test TEST=<ClassName>"
	@echo ""
	@echo "All test classes:"
	@echo "  ECGAdcSmokeTest               ECGSmokeTest"
	@echo "  ECGMiniRegressionTest         ECGTenEpochTest"
	@echo "  ECGFullDatasetTest            ECGSoftResetTest"
	@echo "  ECGReservedBitsToggleTest     ECGReservedBitsWalkingTest"
	@echo "  ECGIdleBetweenEpochsTest      ECGAssertStartNEpochsDeassertTest"
	@echo "  ECGDropStartNegativeTest      ECGSoftResetMidEpochRetryTest"
	@echo "  ECGMidEpochResetReplayTest    ECGSoftResetMidMultiEpochTest"
	@echo "  ECGSoftResetMidEpochNoRestartTest"
	@echo ""
	@echo "Variables (current values):"
	@echo "  TEST=$(TEST)"
	@echo "  PORT=$(PORT)"
	@echo "  BAUD=$(BAUD)"
	@echo "  TIMEOUT=$(TIMEOUT)"
	@echo "  BYTE_TIMEOUT=$(BYTE_TIMEOUT)"
	@echo "  VERBOSITY=$(VERBOSITY)"
	@echo "  NUM_FRAMES=$(NUM_FRAMES)"
	@echo ""
	@echo "Examples:"
	@echo "  make adc-smoke"
	@echo "  make adc-smoke VERBOSITY=DEBUG"
	@echo "  make test TEST=ECGTenEpochTest"
	@echo "  make test TEST=ECGFullDatasetTest TIMEOUT=60"
	@echo ""
