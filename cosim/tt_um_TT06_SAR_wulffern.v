// spicebind VPI shell module for tt_um_TT06_SAR_wulffern (8-bit SAR ADC)
// Maps Verilog ports to top-level SPICE nodes in tt06_sar_cosim.cir
//
// Analog inputs (real type → drive SPICE external sources):
//   ua_1   -> Vua_1   (node ua_1 → DUT ua[1] = SAR_IP positive input)
//   ua_0   -> Vua_0   (node ua_0 → DUT ua[0] = SAR_IN negative input)
//
// Digital inputs (wire type → drive SPICE external sources):
//   clk    -> Vclk    (node clk)
//   rst_n  -> Vrst_n  (node rst_n)
//   ena    -> Vena    (node ena)
//   ui_in_0 -> Vui_in_0 (node ui_in_0 → DUT ui_in[0] = EN/start)
//
// Digital outputs (wire type → read from SPICE node voltages):
//   uo_out[7:0]  <- v(uo_out[7]) .. v(uo_out[0])   (8-bit ADC result)
//   uio_out[7:0] <- v(uio_out[7]) .. v(uio_out[0]) (uio_out[0] = DONE)
`timescale 1ns/1ps
module tt_um_TT06_SAR_wulffern (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        ena,
    input  wire        ui_in_0,    // SAR enable/start (DUT ui_in[0])
    output reg  [7:0]  uo_out,     // 8-bit ADC conversion result
    output reg  [7:0]  uio_out,    // uio_out[0] = DONE (conversion complete)
    input  real        ua_1,       // SAR_IP: positive differential input
    input  real        ua_0        // SAR_IN: negative differential input
);
endmodule
