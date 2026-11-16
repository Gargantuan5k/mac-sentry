// Even-parity shortened extended Hamming encoder. See spec/secded_accumulator.md.
module secded_encoder #(
    parameter integer DATA_WIDTH = 24,
    localparam integer PARITY_WIDTH = secded_parity_width(DATA_WIDTH),
    localparam integer HAMMING_WIDTH = DATA_WIDTH + PARITY_WIDTH,
    localparam integer CODE_WIDTH = HAMMING_WIDTH + 1
) (
    input  wire [DATA_WIDTH-1:0] data,
    output reg  [CODE_WIDTH-1:0] codeword
);
    `include "secded_functions.vh"
    integer data_bit;
    always @* begin
        codeword = 0;
        data_bit = 0;
        for (integer position = 1; position <= HAMMING_WIDTH; position = position + 1) begin
            if ((position & (position - 1)) != 0) begin
                codeword[position-1] = data[data_bit];
                data_bit = data_bit + 1;
            end
        end
        for (integer parity_bit = 0; parity_bit < PARITY_WIDTH; parity_bit = parity_bit + 1) begin
            for (integer position = 1; position <= HAMMING_WIDTH; position = position + 1) begin
                if ((position & (1 << parity_bit)) != 0 && position != (1 << parity_bit))
                    codeword[(1 << parity_bit)-1] = codeword[(1 << parity_bit)-1] ^ codeword[position-1];
            end
        end
        codeword[HAMMING_WIDTH] = ^codeword[HAMMING_WIDTH-1:0];
    end
endmodule
