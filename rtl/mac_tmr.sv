// Conventional datapath TMR; see spec/tmr_mac.md.
module mac_tmr #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
) (
    input wire clk, rst, clear, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    output wire ready,
    output reg busy, done, result_valid,
    output wire [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output wire disagreement
);
    wire [ACC_WIDTH-1:0] candidate_mask0 = {ACC_WIDTH{1'b0}};
    wire [ACC_WIDTH-1:0] candidate_mask1 = {ACC_WIDTH{1'b0}};
    wire [ACC_WIDTH-1:0] candidate_mask2 = {ACC_WIDTH{1'b0}};
    wire [ACC_WIDTH-1:0] state_voter_fault_mask = {ACC_WIDTH{1'b0}};
    wire [ACC_WIDTH-1:0] candidate_voter_fault_mask = {ACC_WIDTH{1'b0}};
    `include "mac_tmr_datapath.vh"
endmodule
