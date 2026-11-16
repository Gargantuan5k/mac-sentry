// Portable, fault-free comparison baseline. See spec/mac_interface_and_fault_model.md.
module mac_unprotected #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
) (
    input  wire                          clk,
    input  wire                          rst,
    input  wire                          clear,
    input  wire                          start,
    input  wire signed [OPERAND_WIDTH-1:0] operand_a,
    input  wire signed [OPERAND_WIDTH-1:0] operand_b,
    output wire                          ready,
    output reg                           busy,
    output reg                           done,
    output reg                           result_valid,
    output wire [1:0]                     error,
    output reg signed [ACC_WIDTH-1:0]     accumulator
);
    localparam integer PRODUCT_WIDTH = 2 * OPERAND_WIDTH;
    reg signed [OPERAND_WIDTH-1:0] saved_a, saved_b;
    wire signed [PRODUCT_WIDTH-1:0] product;
    wire signed [ACC_WIDTH:0] extended_product;
    // The top bit is deliberately discarded by the specified wrapping commit.
    /* verilator lint_off UNUSEDSIGNAL */
    wire signed [ACC_WIDTH:0] exact_sum;
    /* verilator lint_on UNUSEDSIGNAL */

    // Supported configurations require OPERAND_WIDTH >= 2 and ACC_WIDTH >= PRODUCT_WIDTH.
    assign product = saved_a * saved_b;
    assign extended_product = {{(ACC_WIDTH+1-PRODUCT_WIDTH){product[PRODUCT_WIDTH-1]}}, product};
    assign exact_sum = {accumulator[ACC_WIDTH-1], accumulator} + extended_product;
    assign ready = !rst && !clear && !busy;
    assign error = 2'b00; // No fault detection in this baseline.

    always @(posedge clk) begin
        if (rst) begin
            saved_a <= 0;
            saved_b <= 0;
            accumulator <= 0;
            busy <= 0;
            done <= 0;
            result_valid <= 0;
        end else begin
            done <= 0;
            result_valid <= 0;
            if (busy) begin
                accumulator <= exact_sum[ACC_WIDTH-1:0];
                busy <= 0;
                done <= 1;
                result_valid <= 1;
            end else if (clear) begin
                accumulator <= 0;
            end else if (start) begin
                saved_a <= operand_a;
                saved_b <= operand_b;
                busy <= 1;
            end
        end
    end
endmodule
