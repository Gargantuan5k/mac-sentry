// Tiny Tapeout byte interface to the unchanged production protected hybrid.
`default_nettype none
module tt_um_mac_sentry (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire ena,
    input  wire clk,
    input  wire rst_n
);
    wire reset = !rst_n || !ena;
    reg armed;
    reg signed [7:0] operand_a, operand_b;
    reg loaded_a, loaded_b, pending;
    reg completed, valid;
    reg [1:0] last_error, retries;
    reg saw_corrected, saw_detected, saw_retried, protocol_error;
    reg [23:0] result_snapshot;
    reg [7:0] response;
    wire [3:0] command = uio_in[3:0];
    wire request = !reset && armed && uio_in[4];
    wire legal = uio_in[7:5] == 0 && command <= 8;
    wire launch = request && legal && command == 3 && !pending && loaded_a && loaded_b;
    wire clear = request && legal && command == 4 && !pending;
    wire core_busy, core_done, core_valid, core_corrected, core_detected, core_retried;
    wire [1:0] core_error, core_retries;
    wire signed [23:0] core_accumulator;
    wire unused_ready;

    mac_hybrid #(.OPERAND_WIDTH(8), .ACC_WIDTH(24), .MAX_RETRIES(2)) core (
        .clk(clk), .rst(reset), .clear(clear), .start(launch),
        .operand_a(operand_a), .operand_b(operand_b), .ready(unused_ready),
        .busy(core_busy), .done(core_done), .result_valid(core_valid),
        .error(core_error), .accumulator(core_accumulator),
        .corrected(core_corrected), .detected(core_detected),
        .retried(core_retried), .retry_count(core_retries)
    );
    // No bidirectional pads are driven, including during reset or deselection.
    assign uio_out = 8'b0;
    assign uio_oe = 8'b0;
    assign uo_out = reset ? 8'b0 : response;
    wire _unused = &{1'b0, unused_ready, core_busy};

    always @(posedge clk) begin
        if (reset) begin
            armed <= 0;
            operand_a <= 0;
            operand_b <= 0;
            loaded_a <= 0;
            loaded_b <= 0;
            pending <= 0;
            completed <= 0;
            valid <= 0;
            last_error <= 0;
            retries <= 0;
            saw_corrected <= 0;
            saw_detected <= 0;
            saw_retried <= 0;
            protocol_error <= 0;
            result_snapshot <= 0;
            response <= 0;
        end else begin
            if (!uio_in[4]) armed <= 1;
            else if (request) armed <= 0;

            // Consume core pulses one edge later; pending includes that edge.
            // Idle scrub corrections are diagnostic events until START/CLEAR.
            saw_corrected <= saw_corrected | core_corrected;
            if (pending) begin
                saw_detected <= saw_detected | core_detected;
                saw_retried <= saw_retried | core_retried;
                retries <= core_retries;
                if (core_done) begin
                    pending <= 0;
                    completed <= 1;
                    valid <= core_valid;
                    last_error <= core_error;
                    // Failed results preserve the last successful snapshot.
                    if (core_valid) result_snapshot <= core_accumulator;
                end
            end
            if (request) begin
                if (!legal) begin
                    response <= 8'he1;
                    protocol_error <= 1;
                end else if (command >= 1 && command <= 4 && pending) begin
                    response <= 8'he2;
                    protocol_error <= 1;
                end else begin
                    case (command)
                        0: response <= {protocol_error, saw_detected, saw_corrected,
                                        last_error, valid, completed, pending};
                        1: begin
                            operand_a <= ui_in;
                            loaded_a <= 1;
                            response <= 0;
                        end
                        2: begin
                            operand_b <= ui_in;
                            loaded_b <= 1;
                            response <= 0;
                        end
                        3: begin
                            if (!loaded_a || !loaded_b) begin
                                response <= 8'he3;
                                protocol_error <= 1;
                            end else begin
                                pending <= 1;
                                loaded_a <= 0;
                                loaded_b <= 0;
                                completed <= 0;
                                valid <= 0;
                                last_error <= 0;
                                retries <= 0;
                                saw_corrected <= 0;
                                saw_detected <= 0;
                                saw_retried <= 0;
                                response <= 0;
                            end
                        end
                        4: begin
                            loaded_a <= 0;
                            loaded_b <= 0;
                            completed <= 0;
                            valid <= 0;
                            last_error <= 0;
                            retries <= 0;
                            saw_corrected <= 0;
                            saw_detected <= 0;
                            saw_retried <= 0;
                            protocol_error <= 0;
                            result_snapshot <= 0;
                            response <= 0;
                        end
                        5: response <= result_snapshot[7:0];
                        6: response <= result_snapshot[15:8];
                        7: response <= result_snapshot[23:16];
                        8: response <= {3'b0, loaded_b, loaded_a, saw_retried, retries};
                        default: response <= 8'he1; // unreachable after legal check
                    endcase
                end
            end
        end
    end
endmodule
`default_nettype wire
