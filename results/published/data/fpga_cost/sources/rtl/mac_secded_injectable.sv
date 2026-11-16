// Instrumented test variant. Includes injection hardware; exclude from core PPA.
module mac_secded_injectable #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24,
    localparam integer CODE_WIDTH = ACC_WIDTH + secded_parity_width(ACC_WIDTH) + 1
) (
    input wire clk, rst, clear, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    output wire ready,
    output reg busy, done, result_valid,
    output reg [1:0] error,
    output wire signed [ACC_WIDTH-1:0] accumulator,
    output reg corrected,
    input wire inject_pulse,
    input wire [CODE_WIDTH-1:0] inject_mask,
    output reg inject_fired,
    output wire [CODE_WIDTH-1:0] stored_codeword
);
    `include "secded_functions.vh"
    `include "mac_secded_datapath.vh"
    assign stored_codeword = acc_codeword;
    always @(posedge clk) begin
        if (rst)
            inject_fired <= 0;
        else
            inject_fired <= do_inject;
    end
endmodule
