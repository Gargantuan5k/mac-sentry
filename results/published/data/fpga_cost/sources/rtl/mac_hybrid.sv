// Conventional SECDED + residue + bounded retry baseline; not protected commit.
module mac_hybrid #(
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
    output reg [RETRY_WIDTH-1:0] retry_count
);
    `include "secded_functions.vh"
    wire [ACC_WIDTH:0] candidate_fault_mask = 0;
    wire [2:0] checker_fault_mask = 0;
    wire [ACC_WIDTH-1:0] commit_fault_mask = 0;
    wire storage_inject = 1'b0;
    wire [CODE_WIDTH-1:0] storage_mask = 0;
    `include "mac_hybrid_datapath.vh"
endmodule
