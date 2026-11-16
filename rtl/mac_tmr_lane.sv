// One preserved datapath lane. Control and feedback voters live in mac_tmr.
(* keep_hierarchy = "yes" *)
module mac_tmr_lane #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
) (
    input wire clk, rst, clear, busy, start,
    input wire signed [OPERAND_WIDTH-1:0] operand_a, operand_b,
    input wire [ACC_WIDTH-1:0] feedback,
    output wire [ACC_WIDTH-1:0] state_word,
    output wire [ACC_WIDTH-1:0] candidate
);
    localparam integer PRODUCT_WIDTH = 2 * OPERAND_WIDTH;
    reg signed [OPERAND_WIDTH-1:0] saved_a, saved_b;
    reg [ACC_WIDTH-1:0] acc_state;
    wire signed [PRODUCT_WIDTH-1:0] product = saved_a * saved_b;
    wire [ACC_WIDTH-1:0] extended_product =
        {{(ACC_WIDTH-PRODUCT_WIDTH){product[PRODUCT_WIDTH-1]}}, product};
    wire [ACC_WIDTH-1:0] clean_candidate = acc_state + extended_product;
    assign candidate = clean_candidate;
    assign state_word = acc_state;
    always @(posedge clk) begin
        if (rst) begin
            acc_state <= 0;
            saved_a <= 0;
            saved_b <= 0;
        end else begin
            if (!busy && clear) acc_state <= 0;
            else acc_state <= feedback;
            if (!busy && !clear && start) begin
                saved_a <= operand_a;
                saved_b <= operand_b;
            end
        end
    end
endmodule
