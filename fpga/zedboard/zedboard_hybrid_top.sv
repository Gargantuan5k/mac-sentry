// Separate instrumented hybrid project; see spec/hybrid_fpga_setup.md.
module zedboard_hybrid_top(input wire clk_100mhz);
    wire rst;
    wire clear;
    wire start_request;
    wire [7:0] operand_a;
    wire [7:0] operand_b;
    wire [2:0] attempt_select;
    wire [24:0] candidate_mask;
    wire [2:0] checker_mask;
    wire [23:0] commit_mask;
    wire [29:0] storage_mask;
    wire abort_request;
    wire start_pulse;
    wire launched;
    wire ready;
    wire busy;
    wire done;
    wire result_valid;
    wire [1:0] error;
    wire [23:0] accumulator;
    wire [29:0] stored_codeword;
    wire corrected;
    wire detected;
    wire retried;
    wire [1:0] retry_count;
    wire [3:0] inject_fired;
    wire [1:0] fired_attempt;
    wire [7:0] latched_a;
    wire [7:0] latched_b;
    wire [2:0] latched_attempts;
    wire [24:0] latched_candidate;
    wire [2:0] latched_checker;
    wire [23:0] latched_commit;
    wire [29:0] latched_storage;
    wire [24:0] applied_candidate;
    wire [2:0] applied_checker;
    wire [23:0] applied_commit;
    wire [24:0] candidate_before;
    wire [24:0] candidate_after;
    wire [2:0] prediction_before;
    wire [2:0] prediction_after;
    wire [23:0] commit_before;
    wire [23:0] commit_after;
    wire source_usable;
    wire commit_eligible;
    vio_hybrid u_vio (
        .clk(clk_100mhz),
        .probe_in0(ready),
        .probe_in1(busy),
        .probe_in2(accumulator),
        .probe_in3(error),
        .probe_in4(retry_count),
        .probe_out0(rst),
        .probe_out1(clear),
        .probe_out2(start_request),
        .probe_out3(operand_a),
        .probe_out4(operand_b),
        .probe_out5(attempt_select),
        .probe_out6(candidate_mask),
        .probe_out7(checker_mask),
        .probe_out8(commit_mask),
        .probe_out9(storage_mask),
        .probe_out10(abort_request)
    );
    hybrid_fault_sequencer u_seq (
        .clk(clk_100mhz),
        .rst(rst),
        .clear(clear),
        .start_request(start_request),
        .operand_a(operand_a),
        .operand_b(operand_b),
        .attempt_select(attempt_select),
        .candidate_mask(candidate_mask),
        .checker_mask(checker_mask),
        .commit_mask(commit_mask),
        .storage_mask(storage_mask),
        .abort_request(abort_request),
        .start_pulse(start_pulse),
        .launched(launched),
        .ready(ready),
        .busy(busy),
        .done(done),
        .result_valid(result_valid),
        .error(error),
        .accumulator(accumulator),
        .stored_codeword(stored_codeword),
        .corrected(corrected),
        .detected(detected),
        .retried(retried),
        .retry_count(retry_count),
        .inject_fired(inject_fired),
        .fired_attempt(fired_attempt),
        .latched_a(latched_a),
        .latched_b(latched_b),
        .latched_attempts(latched_attempts),
        .latched_candidate(latched_candidate),
        .latched_checker(latched_checker),
        .latched_commit(latched_commit),
        .latched_storage(latched_storage),
        .applied_candidate(applied_candidate),
        .applied_checker(applied_checker),
        .applied_commit(applied_commit),
        .candidate_before(candidate_before),
        .candidate_after(candidate_after),
        .prediction_before(prediction_before),
        .prediction_after(prediction_after),
        .commit_before(commit_before),
        .commit_after(commit_after),
        .source_usable(source_usable),
        .commit_eligible(commit_eligible)
    );
    ila_hybrid u_ila (
        .clk(clk_100mhz),
        .probe0(rst),
        .probe1(clear),
        .probe2(start_request),
        .probe3(operand_a),
        .probe4(operand_b),
        .probe5(attempt_select),
        .probe6(candidate_mask),
        .probe7(checker_mask),
        .probe8(commit_mask),
        .probe9(storage_mask),
        .probe10(abort_request),
        .probe11(start_pulse),
        .probe12(launched),
        .probe13(ready),
        .probe14(busy),
        .probe15(done),
        .probe16(result_valid),
        .probe17(error),
        .probe18(accumulator),
        .probe19(stored_codeword),
        .probe20(corrected),
        .probe21(detected),
        .probe22(retried),
        .probe23(retry_count),
        .probe24(inject_fired),
        .probe25(fired_attempt),
        .probe26(latched_a),
        .probe27(latched_b),
        .probe28(latched_attempts),
        .probe29(latched_candidate),
        .probe30(latched_checker),
        .probe31(latched_commit),
        .probe32(latched_storage),
        .probe33(applied_candidate),
        .probe34(applied_checker),
        .probe35(applied_commit),
        .probe36(candidate_before),
        .probe37(candidate_after),
        .probe38(prediction_before),
        .probe39(prediction_after),
        .probe40(commit_before),
        .probe41(commit_after),
        .probe42(source_usable),
        .probe43(commit_eligible)
    );
endmodule
