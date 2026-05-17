# =============================================================================
# build_bitstream.tcl
# Batch build/program helper for fpga/vivado_project/ecg_zybo.xpr
#
# Usage:
#   vivado -mode batch -source build_bitstream.tcl -tclargs bitstream
#   vivado -mode batch -source build_bitstream.tcl -tclargs program
# =============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set PROJ_XPR   [file normalize "$SCRIPT_DIR/vivado_project/ecg_zybo.xpr"]
set ACTION     [expr {[llength $argv] > 0 ? [lindex $argv 0] : "bitstream"}]
set STAGE_ROM_TCL [file normalize "$SCRIPT_DIR/stage_rom_dat_files.tcl"]

if {![file exists $PROJ_XPR]} {
    puts "ERROR: Project not found: $PROJ_XPR"
    puts "Run: vivado -source project_gen.tcl"
    exit 1
}

open_project $PROJ_XPR

proc configure_rom_dat_staging {stage_tcl} {
    if {![file exists $stage_tcl]} {
        puts "ERROR: Missing ROM staging helper: $stage_tcl"
        exit 1
    }

    foreach run_name {synth_1 block_design_ecg_wrapper_0_0_synth_1} {
        set run_obj [get_runs -quiet $run_name]
        if {[llength $run_obj] == 0} {
            puts "WARNING: Run $run_name not found; skipping ROM staging hook"
            continue
        }

        set_property STEPS.SYNTH_DESIGN.TCL.PRE $stage_tcl $run_obj
    }

    save_project
}

proc stage_rom_dat_files_now {} {
    set proj_dir [file dirname [file normalize [get_property DIRECTORY [current_project]]]]
    set dat_dir [file normalize "$proj_dir/q_pulse_debug.srcs/sources_1/imports/.marwan"]
    set dat_files [lsort [glob -nocomplain -directory $dat_dir *.dat]]

    if {[llength $dat_files] == 0} {
        puts "ERROR: No ROM .dat files found in $dat_dir"
        exit 1
    }

    foreach run_name {synth_1 block_design_ecg_wrapper_0_0_synth_1} {
        set run_dir [file normalize "$proj_dir/q_pulse_debug.runs/$run_name"]
        file mkdir $run_dir

        foreach dat_file $dat_files {
            if {![file readable $dat_file]} {
                puts "ERROR: ROM data file is not readable: $dat_file"
                exit 1
            }

            file copy -force $dat_file $run_dir
        }

        puts "INFO: Staged [llength $dat_files] ROM .dat files into $run_dir"
    }
}

configure_rom_dat_staging $STAGE_ROM_TCL

proc ensure_bitstream {} {
    stage_rom_dat_files_now

    launch_runs synth_1 -jobs 8
    wait_on_run synth_1

    launch_runs impl_1 -to_step write_bitstream -jobs 8
    wait_on_run impl_1

    set run_obj [get_runs impl_1]
    set bitfile [get_property BITSTREAM.FILE $run_obj]
    if {$bitfile eq "" || ![file exists $bitfile]} {
        puts "ERROR: Bitstream was not generated"
        exit 1
    }

    puts "INFO: Bitstream generated: $bitfile"
    return $bitfile
}

set bitfile [ensure_bitstream]

if {$ACTION eq "program"} {
    open_hw_manager
    connect_hw_server
    open_hw_target

    set devs [get_hw_devices]
    if {[llength $devs] == 0} {
        puts "ERROR: No hardware targets found"
        close_project
        exit 1
    }

    set dev [lindex $devs 0]
    current_hw_device $dev
    refresh_hw_device $dev

    set_property PROGRAM.FILE $bitfile $dev
    program_hw_devices $dev

    puts "INFO: Programmed [get_property NAME $dev] with $bitfile"
}

close_project
exit 0
