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
    localparam integer PRODUCT_WIDTH = 2 * OPERAND_WIDTH;
    // Simulator visibility permits testbench-only register upsets between edges.
    // This comment creates no hardware injection port or mux.
    reg [CODE_WIDTH-1:0] acc_codeword /* verilator public_flat_rw */;
    reg signed [OPERAND_WIDTH-1:0] saved_a, saved_b;
    wire [CODE_WIDTH-1:0] repaired_codeword, next_codeword;
    wire decode_corrected, decode_uncorrectable;
    wire [secded_parity_width(ACC_WIDTH)-1:0] unused_syndrome;
    wire signed [PRODUCT_WIDTH-1:0] product;
    wire signed [ACC_WIDTH:0] extended_product;
    /* verilator lint_off UNUSEDSIGNAL */
    wire signed [ACC_WIDTH:0] exact_sum;
    /* verilator lint_on UNUSEDSIGNAL */

    secded_decoder #(.DATA_WIDTH(ACC_WIDTH)) decode_acc (
        .codeword(acc_codeword), .data(accumulator),
        .repaired_codeword(repaired_codeword), .syndrome(unused_syndrome),
        .corrected(decode_corrected), .uncorrectable(decode_uncorrectable)
    );
    secded_encoder #(.DATA_WIDTH(ACC_WIDTH)) encode_next (
        .data(exact_sum[ACC_WIDTH-1:0]), .codeword(next_codeword)
    );
    assign product = saved_a * saved_b;
    assign extended_product = {{(ACC_WIDTH+1-PRODUCT_WIDTH){product[PRODUCT_WIDTH-1]}}, product};
    assign exact_sum = {accumulator[ACC_WIDTH-1], accumulator} + extended_product;
    assign ready = !rst && !clear && !busy;

    // Same supported width relationship as mac_unprotected.
    always @(posedge clk) begin
        if (rst) begin
            acc_codeword <= 0; // The all-zero data word has all-zero check bits.
            saved_a <= 0;
            saved_b <= 0;
            busy <= 0;
            done <= 0;
            result_valid <= 0;
            error <= 0;
            corrected <= 0;
        end else begin
            done <= 0;
            result_valid <= 0;
            error <= 0;
            corrected <= 0;
            if (busy) begin
                busy <= 0;
                done <= 1;
                if (decode_uncorrectable) begin
                    error <= 2'b01;
                end else begin
                    acc_codeword <= next_codeword;
                    result_valid <= 1;
                    corrected <= decode_corrected;
                end
            end else if (clear) begin
                acc_codeword <= 0;
            end else begin
                if (decode_corrected) begin
                    acc_codeword <= repaired_codeword;
                    corrected <= 1;
                end
                if (start) begin
                    saved_a <= operand_a;
                    saved_b <= operand_b;
                    busy <= 1;
                end
            end
        end
    end
endmodule
