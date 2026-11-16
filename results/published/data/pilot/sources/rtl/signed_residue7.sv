// Signed two's-complement reduction to a canonical residue in [0,6].
// Since 2^3 == 1 mod 7, sum 3-bit chunks, then subtract the sign weight.
module signed_residue7 #(
    parameter integer WIDTH = 24
) (
    input wire [WIDTH-1:0] value,
    output reg [2:0] residue
);
    localparam [3:0] SIGN_WEIGHT = 4'(1 << (WIDTH % 3)); // 2^WIDTH mod 7
    localparam integer CHUNKS = (WIDTH+2)/3;
    localparam integer SUM_WIDTH = $clog2(CHUNKS*7+1);
    wire [CHUNKS*3-1:0] padded = {{(CHUNKS*3-WIDTH){1'b0}}, value};
    reg [SUM_WIDTH-1:0] folded;
    reg [3:0] remainder;
    always @* begin
        folded = 0;
        for (integer chunk = 0; chunk < CHUNKS; chunk = chunk+1)
            folded = folded + SUM_WIDTH'(padded[chunk*3 +: 3]);
        remainder = 4'(folded % SUM_WIDTH'(7));
        if (value[WIDTH-1]) begin
            if (remainder >= SIGN_WEIGHT)
                remainder = remainder - SIGN_WEIGHT;
            else
                remainder = remainder + 7 - SIGN_WEIGHT;
        end
        residue = remainder[2:0];
    end
endmodule
