// Sine-sweep testbench for tt_um_TT06_SAR_wulffern (8-bit SAR ADC)
// Uses spicebind to cosimulate with the transistor-level SPICE netlist
//
// Models single-ended -> differential conversion:
//   ua_1 = Vcm + A_half * sin(2*pi*f*t)
//   ua_0 = Vcm - A_half * sin(2*pi*f*t)
//   Vdiff = ua_1 - ua_0 = 2*A_half * sin(wt)  (Vcm cancels)
//
//   Vcm    = 0.9 V  (VCC/2, cancels in differential)
//   A_half = 0.36 V   -> Vdiff_pk = 0.72 V = ~102 LSB peak
//   Phase  = pi/4     -> first sample at Vdiff = 0.72*sin(pi/4) = 0.51 V (well above RELTOL)
//   AC swing: codes ~-102 to +102 -> raw codes ~26 to 230, center ~128
//   f = 20 kHz, 4 full cycles = 200 us
`timescale 1ns/1ps

module tb_sar_cosim;

    // --- Clock: 4 MHz (250 ns period) ---
    reg clk = 0;
    always #125 clk = ~clk;

    // --- Control signals ---
    reg rst_n   = 0;
    reg ena     = 0;
    reg ui_in_0 = 0;

    // --- Differential analog inputs (initialised to Vcm so SPICE OP is clean) ---
    real ua_1 = 0.9;
    real ua_0 = 0.9;

    // --- Outputs from DUT ---
    wire [7:0] uo_out;
    wire [7:0] uio_out;

    // --- DUT instantiation ---
    tt_um_TT06_SAR_wulffern dut (
        .clk     (clk),
        .rst_n   (rst_n),
        .ena     (ena),
        .ui_in_0 (ui_in_0),
        .uo_out  (uo_out),
        .uio_out (uio_out),
        .ua_1    (ua_1),
        .ua_0    (ua_0)
    );

    // --- Sine wave parameters ---
    real pi     = 3.14159265358979;
    real f_sine = 20000.0;   // 20 kHz
    real Vcm    = 0.9;       // common-mode voltage (cancels differentially)
    real A_half = 0.36;      // half-amplitude -> Vdiff_pk = 0.72V = ~102 LSB
    real phase  = 3.14159265358979 / 4.0; // pi/4 phase offset: first sample at sin(pi/4)=0.71

    // --- Drive sine continuously every 50 ns ---
    // Using always #50 (not @posedge clk) avoids a delta-cycle race in the
    // spicebind VPI: if ua_1/ua_0 are assigned in the same delta cycle as the
    // clock edge, cbAfterDelay=0 may fire before always @(posedge) runs,
    // causing SPICE to receive stale 0.9 V values (≈0 V differential) which
    // triggers metastability and prevents the SAR from completing.
    // The 50 ns update interval introduces negligible input drift at 20 kHz.
    always #50 begin
        if (rst_n) begin
            ua_1 = Vcm + A_half * $sin(2.0 * pi * f_sine * $realtime * 1.0e-9 + phase);
            ua_0 = Vcm - A_half * $sin(2.0 * pi * f_sine * $realtime * 1.0e-9 + phase);
        end else begin
            ua_1 = Vcm;
            ua_0 = Vcm;
        end
    end

    // --- Latch input at falling clock edge (actual ADC sample moment) ---
    real ua_1_sampled = 0.9;
    real ua_0_sampled = 0.9;
    always @(negedge clk) begin
        if (rst_n) begin
            ua_1_sampled = ua_1;
            ua_0_sampled = ua_0;
        end
    end

    // --- Monitor: print on each DONE pulse ---
    // Output is offset binary: subtract 128 to get signed two's complement value.
    integer signed_code;
    always @(posedge uio_out[0]) begin
        signed_code = {1'b0, uo_out} - 9'd128;
        $display("[%0t ns] DONE  raw=%0d  signed=%0d  sampled_diff=%g V",
                 $time, uo_out, signed_code, ua_1_sampled - ua_0_sampled);
    end

    // --- Stimulus ---
    initial begin
        $dumpfile("tb_sar_cosim.vcd");
        $dumpvars(0, tb_sar_cosim);

        rst_n   = 0;
        ena     = 0;
        ui_in_0 = 0;
        ua_1    = 0.9;
        ua_0    = 0.9;
        #500;

        rst_n   = 1;
        ena     = 1;
        ui_in_0 = 1;
        $display("[%0t ns] Sine sweep started: Vcm=%g V  A_half=%g V  Vdiff_pk=%g V  f=%g kHz  phase=pi/4",
                 $time, Vcm, A_half, 2*A_half, f_sine / 1000.0);

        #200000;  // 200 us = 4 full sine cycles

        $display("[%0t ns] Sine sweep complete", $time);
        $finish;
    end

    // --- Safety timeout ---
    initial begin
        #205000;
        $display("TIMEOUT at %0t ns", $time);
        $finish;
    end

endmodule
