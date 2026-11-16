// Shared by the production and experimental fault-input wrappers.
    localparam integer PRODUCT_WIDTH = 2 * OPERAND_WIDTH;
    reg [CODE_WIDTH-1:0] acc_codeword /* verilator public_flat_rw */;
    reg signed [OPERAND_WIDTH-1:0] saved_a, saved_b;
    wire [CODE_WIDTH-1:0] repaired_codeword, next_codeword;
    wire decode_corrected, decode_uncorrectable;
    wire [secded_parity_width(ACC_WIDTH)-1:0] unused_syndrome;
    wire signed [PRODUCT_WIDTH-1:0] product = saved_a * saved_b;
    wire signed [ACC_WIDTH:0] extended_product =
        {{(ACC_WIDTH+1-PRODUCT_WIDTH){product[PRODUCT_WIDTH-1]}}, product};
    wire [ACC_WIDTH:0] exact_sum = {accumulator[ACC_WIDTH-1], accumulator} + extended_product;
    wire [ACC_WIDTH:0] checked_candidate = exact_sum ^ candidate_fault_mask;
    wire [2:0] predicted_residue, observed_residue;
    wire [2:0] checked_prediction = predicted_residue ^ checker_fault_mask;
    wire arithmetic_ok = (checked_prediction != 3'd7) && (observed_residue != 3'd7)
                         && (checked_prediction == observed_residue);
    wire [ACC_WIDTH-1:0] commit_data = checked_candidate[ACC_WIDTH-1:0] ^ commit_fault_mask;

    secded_decoder #(.DATA_WIDTH(ACC_WIDTH)) decode_acc (
        .codeword(acc_codeword), .data(accumulator), .repaired_codeword(repaired_codeword),
        .syndrome(unused_syndrome), .corrected(decode_corrected), .uncorrectable(decode_uncorrectable)
    );
    secded_encoder #(.DATA_WIDTH(ACC_WIDTH)) encode_next (.data(commit_data), .codeword(next_codeword));
    mac_residue7_check #(.OPERAND_WIDTH(OPERAND_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_checker (
        .accumulator(accumulator), .operand_a(saved_a), .operand_b(saved_b),
        .candidate(checked_candidate), .predicted_residue(predicted_residue),
        .observed_residue(observed_residue)
    );
    assign ready = !rst && !clear && !busy;
    always @(posedge clk) begin
        if (rst) begin
            acc_codeword <= 0;
            saved_a <= 0;
            saved_b <= 0;
            busy <= 0;
            done <= 0;
            result_valid <= 0;
            error <= 0;
            corrected <= 0;
            detected <= 0;
            retried <= 0;
            retry_count <= 0;
        end else begin
            done <= 0;
            result_valid <= 0;
            error <= 0;
            corrected <= 0;
            detected <= 0;
            retried <= 0;
            if (busy) begin
                if (decode_uncorrectable) begin
                    busy <= 0;
                    done <= 1;
                    error <= 1;
                end else begin
                    if (decode_corrected) begin
                        acc_codeword <= repaired_codeword;
                        corrected <= 1;
                    end
                    if (arithmetic_ok) begin
                        acc_codeword <= next_codeword;
                        busy <= 0;
                        done <= 1;
                        result_valid <= 1;
                    end else begin
                        detected <= 1;
                        if (int'(retry_count) < MAX_RETRIES) begin
                            retry_count <= retry_count + 1'b1;
                            retried <= 1;
                        end else begin
                            busy <= 0;
                            done <= 1;
                            error <= 2;
                        end
                    end
                end
            end else if (clear) begin
                acc_codeword <= 0;
                retry_count <= 0;
            end else begin
                // Board-only launch-edge upset. Real storage changes while the
                // operands are captured; decoding/repair occurs next edge.
                // Existing production/experimental wrappers tie this hook off.
                if (storage_inject && (|storage_mask)) begin
                    acc_codeword <= acc_codeword ^ storage_mask;
                end else if (decode_corrected) begin
                    acc_codeword <= repaired_codeword;
                    corrected <= 1;
                end
                if (start) begin
                    saved_a <= operand_a;
                    saved_b <= operand_b;
                    busy <= 1;
                    retry_count <= 0;
                end
            end
        end
    end
