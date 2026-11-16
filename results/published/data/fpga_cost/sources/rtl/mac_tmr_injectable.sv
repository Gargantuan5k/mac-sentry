// Conventional datapath TMR; see spec/tmr_mac.md.
module mac_tmr_injectable #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
) (
    input wire clk, rst, clear, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    output wire ready,
    output reg busy, done, result_valid,
    output wire [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output wire disagreement,
    input wire [ACC_WIDTH-1:0] candidate_mask0, candidate_mask1, candidate_mask2, state_voter_fault_mask, candidate_voter_fault_mask
);
    `include "mac_tmr_datapath.vh"
endmodule
