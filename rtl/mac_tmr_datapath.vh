// Shared by production (all fault masks zero) and simulation instrumentation.
    wire [ACC_WIDTH-1:0] state0, state1, state2;
    wire [ACC_WIDTH-1:0] lane_candidate0, lane_candidate1, lane_candidate2;
    // Injection belongs outside kept lane hierarchy, so production zero masks
    // eliminate the XORs without compromising lane/state preservation.
    wire [ACC_WIDTH-1:0] candidate0 = lane_candidate0 ^ candidate_mask0;
    wire [ACC_WIDTH-1:0] candidate1 = lane_candidate1 ^ candidate_mask1;
    wire [ACC_WIDTH-1:0] candidate2 = lane_candidate2 ^ candidate_mask2;
    wire [ACC_WIDTH-1:0] state_vote_clean =
        (state0 & state1) | (state0 & state2) | (state1 & state2);
    wire [ACC_WIDTH-1:0] candidate_vote_clean =
        (candidate0 & candidate1) | (candidate0 & candidate2) | (candidate1 & candidate2);
    wire [ACC_WIDTH-1:0] state_vote = state_vote_clean ^ state_voter_fault_mask;
    wire [ACC_WIDTH-1:0] candidate_vote = candidate_vote_clean ^ candidate_voter_fault_mask;
    wire [ACC_WIDTH-1:0] feedback = busy ? candidate_vote : state_vote;
    assign accumulator = state_vote;
    assign ready = !rst && !clear && !busy;
    assign error = 2'b00;
    // Disagreement is evidence of unequal lanes, not proof that the vote is right.
    assign disagreement = (state0 != state1) || (state0 != state2) ||
        (busy && ((candidate0 != candidate1) || (candidate0 != candidate2)));
    (* keep_hierarchy = "yes" *) mac_tmr_lane #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) lane0 (
        .clk(clk), .rst(rst), .clear(clear), .busy(busy), .start(start),
        .operand_a(operand_a), .operand_b(operand_b), .feedback(feedback),
        .state_word(state0), .candidate(lane_candidate0));
    (* keep_hierarchy = "yes" *) mac_tmr_lane #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) lane1 (
        .clk(clk), .rst(rst), .clear(clear), .busy(busy), .start(start),
        .operand_a(operand_a), .operand_b(operand_b), .feedback(feedback),
        .state_word(state1), .candidate(lane_candidate1));
    (* keep_hierarchy = "yes" *) mac_tmr_lane #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) lane2 (
        .clk(clk), .rst(rst), .clear(clear), .busy(busy), .start(start),
        .operand_a(operand_a), .operand_b(operand_b), .feedback(feedback),
        .state_word(state2), .candidate(lane_candidate2));
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0;
            done <= 0;
            result_valid <= 0;
        end else begin
            done <= 0;
            result_valid <= 0;
            if (busy) begin
                busy <= 0;
                done <= 1;
                result_valid <= 1;
            end else if (!clear && start) busy <= 1;
        end
    end
