// Simulation harness only. Standalone codec and MAC share a configurable width.
module secded_verify_top #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24,
    localparam integer PARITY_WIDTH = secded_parity_width(ACC_WIDTH),
    localparam integer CODE_WIDTH = ACC_WIDTH + PARITY_WIDTH + 1
) (
    input wire clk, rst, clear, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    output wire ready, busy, done, result_valid, corrected,
    output wire [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output wire [CODE_WIDTH-1:0] stored_codeword,
    input wire [ACC_WIDTH-1:0] codec_data,
    input wire [CODE_WIDTH-1:0] codec_word,
    output wire [CODE_WIDTH-1:0] encoded_word, repaired_word,
    output wire [ACC_WIDTH-1:0] decoded_data,
    output wire [PARITY_WIDTH-1:0] syndrome,
    output wire codec_corrected, codec_uncorrectable
);
    `include "secded_functions.vh"
    mac_secded #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) dut (
        .clk(clk), .rst(rst), .clear(clear), .start(start),
        .operand_a(operand_a), .operand_b(operand_b),
        .ready(ready), .busy(busy), .done(done), .result_valid(result_valid),
        .error(error), .accumulator(accumulator), .corrected(corrected)
    );
    assign stored_codeword = dut.acc_codeword;
    secded_encoder #(.DATA_WIDTH(ACC_WIDTH)) encoder (
        .data(codec_data), .codeword(encoded_word)
    );
    secded_decoder #(.DATA_WIDTH(ACC_WIDTH)) decoder (
        .codeword(codec_word), .data(decoded_data), .repaired_codeword(repaired_word),
        .syndrome(syndrome), .corrected(codec_corrected), .uncorrectable(codec_uncorrectable)
    );
endmodule
