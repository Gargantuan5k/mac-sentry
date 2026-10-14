`timescale 1ns / 1ps

// Behavioral simulation only. Replay vectors from scripts/generate_vectors.py.
// In Vivado, add this file as a Simulation Source and use mac_tb as sim top.
module mac_tb #(
    parameter integer OPERAND_WIDTH = 8,
    parameter integer ACC_WIDTH = 24
);
    reg clk = 0;
    reg rst = 0;
    reg clear = 0;
    reg start = 0;
    reg signed [OPERAND_WIDTH-1:0] operand_a = 0, operand_b = 0;
    wire ready, busy, done, result_valid;
    wire [1:0] error;
    wire signed [ACC_WIDTH-1:0] accumulator;

    mac_unprotected #(
        .OPERAND_WIDTH(OPERAND_WIDTH),
        .ACC_WIDTH(ACC_WIDTH)
    ) dut (
        .clk(clk), .rst(rst), .clear(clear), .start(start),
        .operand_a(operand_a), .operand_b(operand_b),
        .ready(ready), .busy(busy), .done(done),
        .result_valid(result_valid), .error(error), .accumulator(accumulator)
    );

    // 100 MHz simulation clock; this is not a board timing constraint.
    always #5 clk = ~clk;

    string vector_file, line;
    integer fd, fields, columns, cycle = 0;
    bit in_column;
    integer expected_cycles = 0;
    integer in_rst, in_clear, in_start, in_a, in_b;
    integer exp_pre_ready, exp_busy, exp_done, exp_valid;
    integer exp_error, exp_acc, exp_ready;

    // Case inequality also rejects X/Z outputs in a four-state simulator.
    task automatic check_value(
        input string signal_name,
        input integer actual,
        input integer expected_value
    );
        if (actual !== expected_value)
            $fatal(1, "FAIL cycle %0d, %s: expected %0d, got %0d (%h). Vector: %s",
                   cycle, signal_name, expected_value, actual, actual, line);
    endtask

    initial begin
        if (OPERAND_WIDTH < 2 || OPERAND_WIDTH > 8 ||
            ACC_WIDTH < 2 * OPERAND_WIDTH || ACC_WIDTH > 30)
            $fatal(1, "Unsupported vector-runner widths: %0d/%0d", OPERAND_WIDTH, ACC_WIDTH);

        if (!$value$plusargs("VECTORS=%s", vector_file))
            vector_file = "vectors.txt";
        if ($value$plusargs("EXPECTED_CYCLES=%d", expected_cycles)) begin
            if (expected_cycles < 1)
                $fatal(1, "EXPECTED_CYCLES must be positive");
        end
        fd = $fopen(vector_file, "r");
        if (fd == 0)
            $fatal(1, "Cannot open %s. Run make vectors and scripts/setup_vivado_sim.tcl.", vector_file);
        $display("Replaying %s at widths %0d/%0d", vector_file, OPERAND_WIDTH, ACC_WIDTH);

        while ($fgets(line, fd) != 0) begin
            cycle = cycle + 1;
            // Count whitespace-separated columns separately: requesting a
            // thirteenth conversion at EOF is not portable across simulators.
            columns = 0;
            in_column = 0;
            for (integer i = 0; i < line.len(); i = i + 1) begin
                if (line[i] == 8'd32 || line[i] == 8'd9 ||
                    line[i] == 8'd10 || line[i] == 8'd13)
                    in_column = 0;
                else if (!in_column) begin
                    columns = columns + 1;
                    in_column = 1;
                end
            end
            fields = $sscanf(line, "%d %d %d %d %d %d %d %d %d %d %d %d",
                             in_rst, in_clear, in_start, in_a, in_b,
                             exp_pre_ready, exp_busy, exp_done, exp_valid,
                             exp_error, exp_acc, exp_ready);
            if (fields != 12 || columns != 12)
                $fatal(1, "Malformed vector at cycle %0d: expected 12 integer columns. Vector: %s", cycle, line);
            if (cycle == 1 && in_rst != 1)
                $fatal(1, "The first vector must reset the DUT");

            // Drive while clock is low, away from the sampling edge.
            rst = in_rst[0];
            clear = in_clear[0];
            start = in_start[0];
            operand_a = in_a[OPERAND_WIDTH-1:0];
            operand_b = in_b[OPERAND_WIDTH-1:0];
            #1;
            check_value("ready before edge", int'(ready), exp_pre_ready);

            @(posedge clk);
            #1; // Wait for the DUT's nonblocking assignments to settle.
            check_value("busy", int'(busy), exp_busy);
            check_value("done", int'(done), exp_done);
            check_value("result_valid", int'(result_valid), exp_valid);
            check_value("error", int'(error), exp_error);
            check_value("accumulator", int'(accumulator), exp_acc);
            check_value("ready after edge", int'(ready), exp_ready);

            @(negedge clk);
            #1;
            check_value("accumulator stable off edge", int'(accumulator), exp_acc);
        end
        $fclose(fd);
        if (cycle == 0)
            $fatal(1, "Empty vector file: %s", vector_file);
        if (expected_cycles != 0 && cycle != expected_cycles)
            $fatal(1, "Vector count mismatch: expected %0d, read %0d", expected_cycles, cycle);
        $display("PASS: %0d cycles matched the Python reference (SystemVerilog testbench)", cycle);
        $finish;
    end
endmodule
