`timescale 1ns/1ps
// Pin-only test: usable with the actual flattened routed standard-cell netlist.
// Functional zero-delay simulation; independent integer/command expectations,
// plus cycle-by-cycle RTL comparison. No hierarchical force or debug ports.
module asic_gl_tb;
    reg clk = 0, ena = 1, rst_n = 0;
    reg [7:0] ui_in = 0, uio_in = 0;
    wire [7:0] uo_out, uio_out, uio_oe;
    wire [7:0] ref_uo, ref_out, ref_oe;
    integer samples = 0, transactions = 0, aborts = 0, oracle = 0;
    integer i, a, b;
    reg [31:0] seed = 32'h5a17c9e3;
    reg [7:0] observed;
    string trace_path;
    tt_um_mac_sentry dut (.clk(clk), .ena(ena), .rst_n(rst_n),
        .ui_in(ui_in), .uio_in(uio_in), .uo_out(uo_out), .uio_out(uio_out), .uio_oe(uio_oe));
    tt_um_mac_sentry_reference reference_dut (.clk(clk), .ena(ena), .rst_n(rst_n),
        .ui_in(ui_in), .uio_in(uio_in), .uo_out(ref_uo), .uio_out(ref_out), .uio_oe(ref_oe));

    task sample;
        begin
            samples = samples + 1;
            observed = uo_out;
            if ($test$plusargs("NEGATIVE_OBSERVATION") && samples == 100)
                observed = observed ^ 8'h01;
            if ({observed, uio_out, uio_oe} !== {ref_uo, ref_out, ref_oe})
                $fatal(1, "M2_GLS_COMPARE sample=%0d got=%h ref=%h", samples, observed, ref_uo);
            if ((^uo_out === 1'bx) || uio_out !== 0 || uio_oe !== 0)
                $fatal(1, "M2_GLS_UNKNOWN_OR_PAD sample=%0d", samples);
        end
    endtask
    task tick;
        begin
            // Inputs driven while clock low. 50 ns clock, sample after edge.
            #24; clk = 1; #1; sample(); #25; clk = 0;
        end
    endtask
    task expect_byte(input [7:0] value, input [255:0] context_name);
        begin
            if (uo_out !== value)
                $fatal(1, "M2_GLS_ORACLE %0s expected=%02h got=%02h sample=%0d",
                       context_name, value, uo_out, samples);
        end
    endtask
    task cmd(input [7:0] op, input [7:0] data, input [7:0] response);
        begin
            uio_in = 0; ui_in = data; tick();
            uio_in = op | 8'h10; tick(); expect_byte(response, "command");
        end
    endtask
    task reset_all;
        begin
            rst_n = 0; uio_in = 0; tick(); expect_byte(0, "reset");
            rst_n = 1; tick(); oracle = 0;
        end
    endtask
    task check_result;
        reg [23:0] expected_result;
        begin
            expected_result = oracle[23:0];
            if ($test$plusargs("NEGATIVE_ARITHMETIC") && transactions == 1)
                expected_result = expected_result ^ 24'h1;
            cmd(5, 0, expected_result[7:0]);
            cmd(6, 0, expected_result[15:8]);
            cmd(7, 0, expected_result[23:16]);
        end
    endtask
    task mac(input integer signed av, input integer signed bv);
        begin
            cmd(1, av[7:0], 0); cmd(2, bv[7:0], 0); cmd(8, 0, 8'h18);
            cmd(3, 0, 0);
            // N+1 complete in core, N+2 wrapper capture. Read N+2 sees busy.
            cmd(0, 0, 1); cmd(0, 0, 6); cmd(8, 0, 0);
            oracle = (oracle + av * bv) & 32'h00ffffff;
            transactions = transactions + 1;
            check_result();
        end
    endtask
    initial begin
        if ($value$plusargs("TRACE=%s", trace_path)) begin
            $dumpfile(trace_path);
            $dumpvars(0, clk, ena, rst_n, ui_in, uio_in, uo_out, uio_out,
                      uio_oe, ref_uo, ref_out, ref_oe);
        end
        reset_all(); cmd(0, 0, 0); cmd(8, 0, 0); check_result();
        mac(3, -4); mac(2, 5); mac(-128, 127); mac(127, -128);
        cmd(4, 0, 0); oracle = 0;
        // Both signed wrap directions through real MAC commands, no preload.
        for (i = 0; i < 512; i = i + 1) mac(-128, -128);
        if (oracle != 32'h00800000) $fatal(1, "bad positive wrap stimulus");
        mac(-1, 1);
        if (oracle != 32'h007fffff) $fatal(1, "bad negative wrap stimulus");
        for (i = 0; i < 256; i = i + 1) begin
            seed = (seed * 32'd1664525) + 32'd1013904223;
            a = $signed(seed[7:0]); b = $signed(seed[23:16]); mac(a, b);
        end
        // Invalid/missing/held requests and sticky status.
        cmd(4, 0, 0); oracle = 0;
        cmd(3, 0, 8'he3); cmd(0, 0, 8'h80);
        cmd(9, 0, 8'he1); cmd(8'h20, 0, 8'he1);
        cmd(8'h40, 0, 8'he1); cmd(8'h80, 0, 8'he1);
        cmd(4, 0, 0); cmd(1, 3, 0); cmd(2, 8'hfc, 0);
        cmd(8'h23, 0, 8'he1); cmd(8, 0, 8'h18); check_result();
        cmd(3, 0, 0);
        // Change opcode to CLEAR under held strobe: no repeated operation.
        uio_in = 8'h14; repeat (8) tick();
        oracle = 24'hfffff4;
        transactions = transactions + 1;
        cmd(0, 0, 8'h86); check_result(); cmd(3, 0, 8'he3);
        // Busy write on N+2 rejects, capture still finishes.
        cmd(4, 0, 0); cmd(1, 2, 0); cmd(2, 3, 0); cmd(3, 0, 0);
        cmd(4, 0, 8'he2); cmd(0, 0, 8'h86); oracle = 6;
        transactions = transactions + 1; check_result();
        // Pending reset and deselection abort, high strobe cannot replay.
        for (i = 0; i < 2; i = i + 1) begin
            cmd(4, 0, 0); cmd(1, 1, 0); cmd(2, 1, 0); cmd(3, 0, 0);
            if (i == 0) rst_n = 0; else ena = 0;
            tick(); expect_byte(0, "abort");
            aborts = aborts + 1;
            ena = 1; rst_n = 1; repeat (4) tick(); expect_byte(0, "no replay");
            oracle = 0; cmd(0, 0, 0); cmd(8, 0, 0); check_result(); mac(2, 3);
        end
        // Masking between edges does not reset stored response/state.
        cmd(5, 0, 6); ena = 0; #1; sample(); expect_byte(0, "ena mask");
        ena = 1; #1; sample(); expect_byte(6, "ena restore");
        rst_n = 0; #1; sample(); expect_byte(0, "reset mask");
        rst_n = 1; #1; sample(); expect_byte(6, "reset restore");
        cmd(0, 0, 6); check_result();
        $display("M2_GLS_PASS transactions=%0d aborts=%0d samples=%0d", transactions, aborts, samples);
        $finish;
    end
    initial begin
        #1000000; $fatal(1, "M2_GLS_TIMEOUT");
    end
endmodule
