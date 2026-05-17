# Makefile for tt06-sar spicebind cosimulation
#
# Prerequisites:
#   - spicebind installed (pip install -e /path/to/cosim/spicebind)
#   - ngspice 43 at ~/.local/lib/libngspice.so
#   - iverilog (system package)
#   - VCC=1.8 sets 1.8V logic thresholds in spicebind

# Locate the spicebind VPI module directory
SPICEBIND_DIR := $(shell python3 -c "import spicebind, os; print(os.path.dirname(spicebind.__file__))" 2>/dev/null)

HDL_MODULE  := tt_um_TT06_SAR_wulffern
TB          := tb_sar_cosim
OUT         := $(TB).vvp
SPICE       := tt06_sar_cosim.cir
HDL_INSTANCE := $(TB).dut

.PHONY: all run run_debug clean

all: $(OUT)

$(OUT): $(TB).v $(HDL_MODULE).v
	iverilog -g2005-sv -o $@ $(TB).v $(HDL_MODULE).v

run: $(OUT)
	SPICE_NETLIST=$(SPICE) \
	HDL_INSTANCE=$(HDL_INSTANCE) \
	VCC=1.8 \
	LD_LIBRARY_PATH=$(HOME)/.local/lib:$$LD_LIBRARY_PATH \
	vvp -M $(SPICEBIND_DIR) -m spicebind_vpi $(OUT)

run_debug: $(OUT)
	SPICE_NETLIST=$(SPICE) \
	HDL_INSTANCE=$(HDL_INSTANCE) \
	VCC=1.8 \
	LD_LIBRARY_PATH=$(HOME)/.local/lib:$$LD_LIBRARY_PATH \
	vvp -M $(SPICEBIND_DIR) -m spicebind_vpi_debug $(OUT)

clean:
	rm -f $(OUT) tb_sar_cosim.vcd
