// Accumulator-only SECDED baseline: decode, MAC, encode; idle correction writeback.
module mac_secded #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24,
    localparam integer CODE_WIDTH = ACC_WIDTH + secded_parity_width(ACC_WIDTH) + 1
) (
    input wire clk,
    input wire rst,
    input wire clear,
    input wire start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a,
    input wire signed [OPERAND_WIDTH-1:0] operand_b,
    output wire ready,
    output reg busy,
    output reg done,
    output reg result_valid,
    output reg [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output reg corrected
);
    `include "secded_functions.vh"
    wire inject_pulse = 1'b0;
    wire [CODE_WIDTH-1:0] inject_mask = {CODE_WIDTH{1'b0}};
    `include "mac_secded_datapath.vh"
endmodule
