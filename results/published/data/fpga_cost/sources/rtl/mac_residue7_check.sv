// Independent narrow residue prediction; no datapath product/carry/overflow input.
module mac_residue7_check #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
) (
    input wire [ACC_WIDTH-1:0] accumulator,
    input wire [OPERAND_WIDTH-1:0] operand_a, operand_b,
    input wire [ACC_WIDTH:0] candidate,
    output wire [2:0] predicted_residue,
    output wire [2:0] observed_residue
);
    wire [2:0] acc_r, a_r, b_r;
    wire [5:0] residue_sum;
    signed_residue7 #(.WIDTH(ACC_WIDTH)) r_acc (.value(accumulator), .residue(acc_r));
    signed_residue7 #(.WIDTH(OPERAND_WIDTH)) r_a (.value(operand_a), .residue(a_r));
    signed_residue7 #(.WIDTH(OPERAND_WIDTH)) r_b (.value(operand_b), .residue(b_r));
    signed_residue7 #(.WIDTH(ACC_WIDTH+1)) r_candidate (.value(candidate), .residue(observed_residue));
    assign residue_sum = {3'b0, acc_r} + {3'b0, a_r} * {3'b0, b_r};
    assign predicted_residue = 3'(residue_sum % 6'd7);
endmodule
