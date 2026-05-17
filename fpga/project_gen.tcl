# =============================================================================
# project_gen.tcl
# Vivado GUI project creation — ECG accelerator on Zybo Z7-10
#
# Part    : xc7z010clg400-1  (Zybo Z7-10)
# Top     : ecg_wrapper  (explicit — no alias mapping)
# Clock   : 25 MHz via PS FCLK_CLK0  (BAUDIV = 217 for 115200 baud)
# UART TX : PS UART0  <-> MIO 14/15  (host virtual COM port)
# UART RX : PS UART1  <-> EMIO       (drives ecg_wrapper rx/tx in PL)
#
# Usage:
#   vivado -source project_gen.tcl          # batch — creates & opens GUI
#   make project                            # via fpga/Makefile
# =============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set RTL_DIR    [file normalize "$SCRIPT_DIR/../src/verilog"]
set PROJ_NAME  ecg_zybo
set PROJ_DIR   "$SCRIPT_DIR/vivado_project"
set PART       xc7z010clg400-1

# ---------------------------------------------------------------------------
# Create project  (force overwrites an existing one)
# ---------------------------------------------------------------------------
create_project $PROJ_NAME $PROJ_DIR -part $PART -force
set_property target_language  Verilog [current_project]
set_property default_lib      work    [current_project]
set_property source_mgmt_mode DisplayOnly [current_project]
puts "INFO: source_mgmt_mode=DisplayOnly (RTL is referenced in-place, not copied)"

# ---------------------------------------------------------------------------
# RTL sources
# Exclude FixedCompare.v  — simulation-only utility, not instantiated by DUT
# ---------------------------------------------------------------------------
set all_v    [glob -nocomplain "$RTL_DIR/*.v"]
set rtl_srcs [lsearch -all -inline -not $all_v "*FixedCompare.v"]

add_files -norecurse $rtl_srcs
puts "INFO: Added [llength $rtl_srcs] RTL source files"

# ---------------------------------------------------------------------------
# ROM initialisation .dat files
# The HLS-generated ROMs use $readmemh with relative paths; adding them to
# the fileset keeps them visible to synthesis/simulation while still
# referenced in place (source_mgmt_mode=DisplayOnly).
# ---------------------------------------------------------------------------
set dat_srcs [glob -nocomplain "$RTL_DIR/*.dat"]
if {[llength $dat_srcs] > 0} {
    add_files -norecurse $dat_srcs
    puts "INFO: Added [llength $dat_srcs] ROM .dat initialisation files"
} else {
    puts "WARNING: No .dat ROM files found in $RTL_DIR"
}

# ---------------------------------------------------------------------------
# Explicit top module — user preference: no alias / no auto-detect
# ---------------------------------------------------------------------------
set_property top ecg_wrapper [current_fileset]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------------------
# Synthesis strategy — keep defaults, set top explicitly in synth run too
# ---------------------------------------------------------------------------
set_property top ecg_wrapper [get_filesets sources_1]

# ---------------------------------------------------------------------------
# XDC constraint stub — Zybo Z7-10 PL clock
# The PS generates FCLK_CLK0 internally; the only PL clock pin needed is
# the Zybo 125 MHz oscillator if you choose to use it directly, or no
# external clock pin at all when using PS FCLK only.
# This stub creates the constraint file so it appears in the GUI.
# Populate the EMIO UART and any other PL I/O pinouts after BD creation.
# ---------------------------------------------------------------------------
set xdc_path "$PROJ_DIR/${PROJ_NAME}.srcs/constrs_1"
file mkdir $xdc_path
set xdc_file "$xdc_path/zybo_z710.xdc"
set fh [open $xdc_file w]
puts $fh "# ==================================================================="
puts $fh "# zybo_z710.xdc  — Zybo Z7-10 constraints"
puts $fh "# Populate after the Zynq PS7 block design is created in the GUI."
puts $fh "# ==================================================================="
puts $fh ""
puts $fh "# ---- PL system clock (125 MHz onboard oscillator) ----------------"
puts $fh "# Uncomment if driving ecg_wrapper directly from PL clock instead of"
puts $fh "# PS FCLK_CLK0.  With the PS EMIO UART approach this is not required."
puts $fh "# set_property PACKAGE_PIN K17 \[get_ports clk\]"
puts $fh "# set_property IOSTANDARD LVCMOS33 \[get_ports clk\]"
puts $fh "# create_clock -period 8.000 -name sys_clk_pin -waveform {0.000 4.000} \\"
puts $fh "#              -add \[get_ports clk\]"
puts $fh ""
puts $fh "# ---- PMOD UART (optional — not used in default PS EMIO flow) ------"
puts $fh "# set_property PACKAGE_PIN P14 \[get_ports rx\]"
puts $fh "# set_property PACKAGE_PIN P15 \[get_ports tx\]"
puts $fh "# set_property IOSTANDARD LVCMOS33 \[get_ports {rx tx}\]"
puts $fh ""
puts $fh "# ---- Active-low reset (BTN0 on Zybo) ------------------------------"
puts $fh "# Uncomment if exposing arst_n as a PL port instead of using"
puts $fh "# PS FCLK_RESET0_N through the block design."
puts $fh "# set_property PACKAGE_PIN K18 \[get_ports arst_n\]"
puts $fh "# set_property IOSTANDARD LVCMOS33 \[get_ports arst_n\]"
close $fh

add_files -fileset constrs_1 -norecurse $xdc_file
puts "INFO: Created constraint stub at $xdc_file"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
puts ""
puts "================================================================"
puts " Project   : $PROJ_NAME"
puts " Location  : $PROJ_DIR"
puts " Part      : $PART"
puts " Top       : ecg_wrapper  (explicitly set, no alias)"
puts " RTL files : [llength $rtl_srcs]"
puts " DAT files : [llength $dat_srcs]"
puts "================================================================"
puts " Next steps in the Vivado GUI:"
puts "  1. IP Integrator -> Create Block Design"
puts "     - Add Zynq PS7"
puts "     - Enable UART0 on MIO 14/15 (host VCP)"
puts "     - Enable UART1 on EMIO"
puts "     - Set FCLK_CLK0 = 25 MHz"
puts "     - Expose FCLK_RESET0_N"
puts "  2. Wrap block design -> add to sources"
puts "  3. In ecg_zybo_wrapper (or top RTL):"
puts "     - ecg_wrapper.clk    <- FCLK_CLK0"
puts "     - ecg_wrapper.arst_n <- FCLK_RESET0_N"
puts "     - ecg_wrapper.rx     <- emio_uart1_txd"
puts "     - ecg_wrapper.tx     -> emio_uart1_rxd"
puts "     - BAUDIV parameter   = 217"
puts "  4. Add ILA on rx/tx serial lines and internal handshakes"
puts "  5. Run Synthesis -> Implementation -> Generate Bitstream"
puts "================================================================"
