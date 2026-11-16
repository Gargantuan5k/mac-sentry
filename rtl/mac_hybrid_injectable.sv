// Experimental fault sites. Keep its hardware cost separate from mac_hybrid.
module mac_hybrid_injectable #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24,
    parameter integer MAX_RETRIES = 2,
    localparam integer CODE_WIDTH = ACC_WIDTH + secded_parity_width(ACC_WIDTH) + 1,
    localparam integer RETRY_WIDTH = MAX_RETRIES < 1 ? 1 : $clog2(MAX_RETRIES+1)
) (
    input wire clk, rst, clear, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    output wire ready,
    output reg busy, done, result_valid,
    output reg [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output reg corrected, detected, retried,
    output reg [RETRY_WIDTH-1:0] retry_count,
    input wire [ACC_WIDTH:0] candidate_fault_mask,
    input wire [2:0] checker_fault_mask,
    input wire [ACC_WIDTH-1:0] commit_fault_mask,
    output wire [CODE_WIDTH-1:0] stored_codeword,
    output wire [ACC_WIDTH:0] candidate_before_fault, candidate_after_fault,
    output wire [2:0] prediction_before_fault, prediction_after_fault,
    output wire [ACC_WIDTH-1:0] commit_before_fault, commit_after_fault
);
    `include "secded_functions.vh"
    wire storage_inject = 1'b0;
    wire [CODE_WIDTH-1:0] storage_mask = 0;
    `include "mac_hybrid_datapath.vh"
    assign stored_codeword = acc_codeword;
    assign candidate_before_fault = exact_sum;
    assign candidate_after_fault = checked_candidate;
    assign prediction_before_fault = predicted_residue;
    assign prediction_after_fault = checked_prediction;
    assign commit_before_fault = checked_candidate[ACC_WIDTH-1:0];
    assign commit_after_fault = commit_data;
endmodule
