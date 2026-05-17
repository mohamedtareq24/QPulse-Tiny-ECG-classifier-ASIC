// uart_loopback.v — minimal DUT for TX UVC standalone testing.
// Wires rx directly to tx so the TX monitor can observe every byte the driver sends.
`timescale 1ns / 1ps

module uart_loopback (
    input  wire clk,
    input  wire arst_n,
    input  wire rx,
    output wire tx
);
    assign tx = rx;
endmodule
