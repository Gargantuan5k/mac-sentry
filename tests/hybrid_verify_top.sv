module hybrid_verify_top #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24,
    parameter integer MAX_RETRIES = 2,
    localparam integer CODE_WIDTH = ACC_WIDTH + secded_parity_width(ACC_WIDTH) + 1,
    localparam integer RETRY_WIDTH = MAX_RETRIES < 1 ? 1 : $clog2(MAX_RETRIES+1)
) (
    input wire clk, rst, clear, start,
    input wire [OPERAND_WIDTH-1:0] operand_a, operand_b,
    input wire [ACC_WIDTH:0] candidate_fault_mask,
    input wire [2:0] checker_fault_mask,
    input wire [ACC_WIDTH-1:0] commit_fault_mask,
    output wire ready, busy, done, result_valid, corrected, detected, retried,
    output wire [1:0] error,
    output wire [RETRY_WIDTH-1:0] retry_count,
    output wire [ACC_WIDTH-1:0] accumulator,
    output wire [CODE_WIDTH-1:0] stored_codeword,
    output wire source_uncorrectable,
    output wire [ACC_WIDTH:0] candidate_before_fault, candidate_after_fault,
    output wire [2:0] prediction_before_fault, prediction_after_fault,
    output wire [ACC_WIDTH-1:0] commit_before_fault, commit_after_fault,
    output wire clean_ready, clean_busy, clean_done, clean_valid,
    output wire clean_corrected, clean_detected, clean_retried,
    output wire [1:0] clean_error,
    output wire [RETRY_WIDTH-1:0] clean_retry_count,
    output wire [ACC_WIDTH-1:0] clean_accumulator,
    input wire [ACC_WIDTH-1:0] check_acc,
    input wire [OPERAND_WIDTH-1:0] check_a, check_b,
    input wire [ACC_WIDTH:0] check_candidate,
    output wire [2:0] prediction, observation
);
    `include "secded_functions.vh"
    // Verification-only observation: a visible XOR is not necessarily sampled.
    assign source_uncorrectable = dut.decode_uncorrectable;
    mac_hybrid_injectable #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH),
                           .MAX_RETRIES(MAX_RETRIES)) dut (
        .clk(clk), .rst(rst), .clear(clear), .start(start),
        .operand_a(operand_a), .operand_b(operand_b), .ready(ready), .busy(busy),
        .done(done), .result_valid(result_valid), .error(error), .accumulator(accumulator),
        .corrected(corrected), .detected(detected), .retried(retried), .retry_count(retry_count),
        .candidate_fault_mask(candidate_fault_mask), .checker_fault_mask(checker_fault_mask),
        .commit_fault_mask(commit_fault_mask), .stored_codeword(stored_codeword),
        .candidate_before_fault(candidate_before_fault), .candidate_after_fault(candidate_after_fault),
        .prediction_before_fault(prediction_before_fault), .prediction_after_fault(prediction_after_fault),
        .commit_before_fault(commit_before_fault), .commit_after_fault(commit_after_fault)
    );
    mac_hybrid #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH),
                 .MAX_RETRIES(MAX_RETRIES)) clean (
        .clk(clk), .rst(rst), .clear(clear), .start(start),
        .operand_a(operand_a), .operand_b(operand_b), .ready(clean_ready), .busy(clean_busy),
        .done(clean_done), .result_valid(clean_valid), .error(clean_error), .accumulator(clean_accumulator),
        .corrected(clean_corrected), .detected(clean_detected), .retried(clean_retried),
        .retry_count(clean_retry_count)
    );
    mac_residue7_check #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) standalone (
        .accumulator(check_acc), .operand_a(check_a), .operand_b(check_b), .candidate(check_candidate),
        .predicted_residue(prediction), .observed_residue(observation)
    );
endmodule
