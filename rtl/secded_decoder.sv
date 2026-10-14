// On uncorrectable status, data is diagnostic only and codeword is not repaired.
module secded_decoder #(
    parameter integer DATA_WIDTH = 24,
    localparam integer PARITY_WIDTH = secded_parity_width(DATA_WIDTH),
    localparam integer HAMMING_WIDTH = DATA_WIDTH + PARITY_WIDTH,
    localparam integer CODE_WIDTH = HAMMING_WIDTH + 1
) (
    input  wire [CODE_WIDTH-1:0] codeword,
    output reg  [DATA_WIDTH-1:0] data,
    output reg  [CODE_WIDTH-1:0] repaired_codeword,
    output reg  [PARITY_WIDTH-1:0] syndrome,
    output reg corrected,
    output reg uncorrectable
);
    `include "secded_functions.vh"
    integer data_bit;
    always @* begin
        syndrome = 0;
        for (integer position = 1; position <= HAMMING_WIDTH; position = position + 1) begin
            if (codeword[position-1])
                syndrome = syndrome ^ PARITY_WIDTH'(position);
        end
        repaired_codeword = codeword;
        corrected = 0;
        uncorrectable = 0;
        if (^codeword) begin
            if (syndrome == 0) begin
                repaired_codeword[HAMMING_WIDTH] = ~codeword[HAMMING_WIDTH];
                corrected = 1;
            end else if (int'(syndrome) <= HAMMING_WIDTH) begin
                repaired_codeword[int'(syndrome)-1] = ~codeword[int'(syndrome)-1];
                corrected = 1;
            end else begin
                uncorrectable = 1;
            end
        end else if (syndrome != 0) begin
            uncorrectable = 1;
        end
        data = 0;
        data_bit = 0;
        for (integer position = 1; position <= HAMMING_WIDTH; position = position + 1) begin
            if ((position & (position - 1)) != 0) begin
                data[data_bit] = repaired_codeword[position-1];
                data_bit = data_bit + 1;
            end
        end
    end
endmodule
