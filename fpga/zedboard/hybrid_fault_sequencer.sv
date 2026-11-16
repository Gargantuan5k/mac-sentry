// Fixed 8/24, three-attempt board experiment controller. No CDC: VIO shares clk.
module hybrid_fault_sequencer (
    input wire clk, rst, abort_request, clear, start_request,
    input wire signed [7:0] operand_a, operand_b,
    input wire [2:0] attempt_select,
    input wire [24:0] candidate_mask,
    input wire [2:0] checker_mask,
    input wire [23:0] commit_mask,
    input wire [29:0] storage_mask,
    output wire ready, busy, done, result_valid, corrected, detected, retried,
    output wire [1:0] error, retry_count,
    output wire signed [23:0] accumulator,
    output wire [29:0] stored_codeword,
    output wire start_pulse,
    output reg launched,
    output reg [3:0] inject_fired,
    output reg [1:0] fired_attempt,
    output reg signed [7:0] latched_a, latched_b,
    output reg [2:0] latched_attempts,
    output reg [24:0] latched_candidate,
    output reg [2:0] latched_checker,
    output reg [23:0] latched_commit,
    output reg [29:0] latched_storage,
    output wire [24:0] applied_candidate,
    output wire [2:0] applied_checker,
    output wire [23:0] applied_commit,
    output wire [24:0] candidate_before, candidate_after,
    output wire [2:0] prediction_before, prediction_after,
    output wire [23:0] commit_before, commit_after,
    output wire source_usable, commit_eligible
);
    wire reset_core = rst || abort_request;
    reg request_d;
    wire accept = start_pulse && ready;
    wire selected = !reset_core && busy && latched_attempts[retry_count];
    assign start_pulse = !reset_core && start_request && !request_d;
    assign applied_candidate = selected ? latched_candidate : 25'b0;
    assign applied_checker = selected ? latched_checker : 3'b0;
    assign applied_commit = selected ? latched_commit : 24'b0;

    always @(posedge clk) begin
        if (reset_core) begin
            // Require a sampled low after reset/abort, even if request was held.
            request_d <= 1;
            launched <= 0;
            inject_fired <= 0;
            fired_attempt <= 0;
            latched_a <= 0;
            latched_b <= 0;
            latched_attempts <= 0;
            latched_candidate <= 0;
            latched_checker <= 0;
            latched_commit <= 0;
            latched_storage <= 0;
        end else begin
            request_d <= start_request;
            launched <= accept;
            inject_fired <= 0;
            if (busy) begin
                fired_attempt <= retry_count;
                // A changed combinational wire alone is not a sampled fault.
                inject_fired[1] <= source_usable && (|applied_candidate);
                inject_fired[2] <= source_usable && (|applied_checker);
                inject_fired[3] <= commit_eligible && (|applied_commit);
            end else if (clear) begin
                fired_attempt <= 0;
                latched_a <= 0;
                latched_b <= 0;
                latched_attempts <= 0;
                latched_candidate <= 0;
                latched_checker <= 0;
                latched_commit <= 0;
                latched_storage <= 0;
            end else if (accept) begin
                latched_a <= operand_a;
                latched_b <= operand_b;
                latched_attempts <= attempt_select;
                latched_candidate <= candidate_mask;
                latched_checker <= checker_mask;
                latched_commit <= commit_mask;
                latched_storage <= storage_mask;
                fired_attempt <= 0;
                inject_fired[0] <= |storage_mask;
            end
        end
    end

    mac_hybrid_board_core u_mac (
        .clk(clk), .rst(reset_core), .clear(clear), .start(accept),
        .operand_a(operand_a), .operand_b(operand_b),
        .storage_inject(accept), .storage_mask(storage_mask),
        .ready(ready), .busy(busy), .done(done), .result_valid(result_valid),
        .error(error), .accumulator(accumulator), .corrected(corrected),
        .detected(detected), .retried(retried), .retry_count(retry_count),
        .candidate_fault_mask(applied_candidate), .checker_fault_mask(applied_checker),
        .commit_fault_mask(applied_commit), .stored_codeword(stored_codeword),
        .candidate_before_fault(candidate_before), .candidate_after_fault(candidate_after),
        .prediction_before_fault(prediction_before), .prediction_after_fault(prediction_after),
        .commit_before_fault(commit_before), .commit_after_fault(commit_after),
        .source_usable(source_usable), .commit_eligible(commit_eligible)
    );
endmodule
