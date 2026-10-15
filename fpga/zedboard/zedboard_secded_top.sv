// Instrumented ZedBoard design. IP configurations are in spec/secded_fpga_setup.md.
module zedboard_secded_top(input wire clk_100mhz);
    wire rst, clear, start_request, inject_request;
    wire signed [7:0] operand_a, operand_b;
    wire [29:0] inject_mask;
    wire ready, busy, done, result_valid, corrected, inject_fired;
    wire [1:0] error;
    wire signed [23:0] accumulator;
    wire [29:0] stored_codeword;
    reg start_request_d, inject_request_d;
    wire start_pulse = !rst && start_request && !start_request_d;
    wire inject_pulse = !rst && inject_request && !inject_request_d;

    always @(posedge clk_100mhz) begin
        if (rst) begin
            start_request_d <= 0;
            inject_request_d <= 0;
        end else begin
            start_request_d <= start_request;
            inject_request_d <= inject_request;
        end
    end

    vio_secded u_vio (
        .clk(clk_100mhz),
        .probe_in0(ready), .probe_in1(busy),
        .probe_in2(accumulator), .probe_in3(error),
        .probe_out0(rst), .probe_out1(clear), .probe_out2(start_request),
        .probe_out3(operand_a), .probe_out4(operand_b),
        .probe_out5(inject_request), .probe_out6(inject_mask)
    );
    mac_secded_injectable #(.OPERAND_WIDTH(8), .ACC_WIDTH(24)) u_mac (
        .clk(clk_100mhz), .rst(rst), .clear(clear), .start(start_pulse),
        .operand_a(operand_a), .operand_b(operand_b),
        .ready(ready), .busy(busy), .done(done), .result_valid(result_valid),
        .error(error), .accumulator(accumulator), .corrected(corrected),
        .inject_pulse(inject_pulse), .inject_mask(inject_mask),
        .inject_fired(inject_fired), .stored_codeword(stored_codeword)
    );
    ila_secded u_ila (
        .clk(clk_100mhz), .probe0(rst), .probe1(clear), .probe2(start_pulse),
        .probe3(operand_a), .probe4(operand_b), .probe5(ready), .probe6(busy),
        .probe7(done), .probe8(result_valid), .probe9(error),
        .probe10(accumulator), .probe11(corrected), .probe12(inject_pulse),
        .probe13(inject_mask), .probe14(inject_fired), .probe15(stored_codeword)
    );
endmodule
