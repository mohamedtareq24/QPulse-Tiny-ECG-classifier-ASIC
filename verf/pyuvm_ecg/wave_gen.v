// wave_gen.v — standalone VCD dump module for Icarus Verilog.
// Included in the build only when WAVES=1.  The VCD_FILE macro is injected
// by the Makefile via -DVCD_FILE=\"sim.vcd\" (or a custom VCD_FILE= path).
//
// Usage:
//   make WAVES=1                     → writes sim.vcd
//   make WAVES=1 VCD_FILE=foo.vcd   → writes foo.vcd
`timescale 1ns / 1ps

`ifndef VCD_FILE
  `define VCD_FILE "sim.vcd"
`endif

module wave_gen;
  initial begin
    $dumpfile(`VCD_FILE);
    $dumpvars(0);   // dump every signal in every module
  end
endmodule
