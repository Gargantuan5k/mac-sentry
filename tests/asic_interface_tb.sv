`timescale 1ns/1ps
module asic_interface_tb;
    reg clk = 0;
    reg rst_n = 0, ena = 1;
    reg [7:0] ui_in = 0, uio_in = 0;
    wire [7:0] uo_out, uio_out, uio_oe;
    tt_um_mac_sentry dut (.*);
    integer cycles = 0, transactions = 0, injections = 0;
    integer expected_acc = 0;
    reg [29:0] raw_before;
    reg [7:0] s, d, lo, mid, hi;
    reg skip_fault, bad_expected;

    task automatic check(input bit ok, input string reason);
        if (!ok) $fatal(1, "FAIL cycle %0d: %s", cycles, reason);
    endtask
    task automatic tick;
        #5; clk = 1; #5; cycles++;
        check(uio_oe == 0 && uio_out == 0, "pads must remain inputs");
        clk = 0; #1;
    endtask
    task automatic command(input reg [7:0] op, input reg [7:0] data,
                           output reg [7:0] answer);
        uio_in = 0; tick();
        ui_in = data; uio_in = op | 8'h10; tick();
        answer = uo_out;
    endtask
    task automatic cmd_ok(input reg [7:0] op, input reg [7:0] data);
        reg [7:0] answer;
        command(op, data, answer);
        check(answer == 0, $sformatf("command %0d ACK got %02x", op, answer));
    endtask
    task automatic reset_host;
        rst_n = 0; tick();
        check(uo_out == 0 && dut.core.acc_codeword == 0, "reset clears outputs/storage");
        rst_n = 1; uio_in = 0; tick();
        expected_acc = 0;
    endtask
    task automatic result_check(input integer expected_value);
        integer actual;
        command(5, 0, lo); command(6, 0, mid); command(7, 0, hi);
        actual = (int'(hi) << 16) | (int'(mid) << 8) | int'(lo);
        check(actual == (expected_value & 'hffffff),
              $sformatf("result bytes expected %06x got %06x", expected_value & 'hffffff, actual));
    endtask
    task automatic load(input integer a, b);
        check(a >= -128 && a <= 127 && b >= -128 && b <= 127, "host operands in signed byte range");
        cmd_ok(1, 8'(a)); cmd_ok(2, 8'(b));
    endtask
    task automatic launch;
        cmd_ok(3, 0);
        check(dut.core.busy && dut.pending, "launch reaches production core");
        check(!dut.completed && !dut.valid, "launch invalidates terminal status");
    endtask
    task automatic mac(input integer a, b);
        load(a,b); launch();
        // Independent mathematical integer oracle, only pins transfer operands/results.
        expected_acc = (expected_acc + a*b) & 'hffffff;
        command(0, 0, s); // capture edge N+2 still samples pending=1
        check(s == 1, "status on completion-capture edge uses pre-edge state");
        command(0, 0, s);
        check(s == 6, "clean sticky done/valid status");
        command(8, 0, d); check(d == 0, "clean retry count and consumed operands");
        result_check(expected_acc);
        transactions++;
    endtask
    task automatic fail_status(input reg [7:0] status, detail);
        command(0, 0, s); check(s == status, $sformatf("fault status expected %02x got %02x",status,s));
        command(8, 0, d); check(d == detail, "fault retry detail");
    endtask
    task automatic inject_candidate_zero;
        check(dut.core.busy && !dut.core.decode_uncorrectable && dut.core.exact_sum == 1,
              "candidate injection eligible on actual attempt");
        if (!skip_fault) force dut.core.checked_candidate = 25'd0;
        #1;
        check((dut.core.checked_candidate ^ dut.core.exact_sum) == 1,
              "candidate XOR acknowledgement");
        injections++;
        $display("INJECT candidate XOR1 cycle=%0d raw=%08x", cycles, dut.core.acc_codeword);
    endtask

    // Replay separately: the two-edge host strobe cannot read every register
    // on every retry edge in one transaction. N+2 is the earliest legal read.
    task automatic retry_read(input integer op, edge_number);
        reg [7:0] expected_byte;
        cmd_ok(4,0); expected_acc = 0; mac(3,-4);
        load(1,1); launch(); raw_before = dut.core.acc_codeword;
        check(dut.core.exact_sum == -25'sd11 && !dut.core.decode_uncorrectable,
              "nonzero retry source eligibility");
        force dut.core.checked_candidate = 25'h1fffff4; // -11 XOR1 -> -12
        #1;
        check((dut.core.checked_candidate ^ dut.core.exact_sum) == 1,
              "nonzero candidate XOR acknowledgement");
        injections++;
        for (integer edge_offset = 1; edge_offset <= 5; edge_offset++) begin
            uio_in = edge_offset == edge_number ? (8'(op) | 8'h10) : 0;
            if (edge_offset <= 3) begin
                check(dut.core.busy && !dut.core.decode_uncorrectable &&
                      (dut.core.checked_candidate ^ dut.core.exact_sum) == 1,
                      "nonzero persistent XOR sampled at eligible attempt");
            end
            tick();
            check(dut.core.acc_codeword == raw_before,
                  "nonzero exhausted transaction preserves raw storage");
            if (edge_offset == edge_number) begin
                case (op)
                    0: expected_byte = edge_number < 3 ? 8'h01 :
                                       edge_number < 5 ? 8'h41 : 8'h52;
                    5: expected_byte = 8'hf4;
                    6,7: expected_byte = 8'hff;
                    8: expected_byte = edge_number == 2 ? 0 :
                                       edge_number == 3 ? 5 : 6;
                    default: expected_byte = 8'he1;
                endcase
                check(uo_out == expected_byte,
                      $sformatf("retry pin read op=%0d N+%0d expected=%02x got=%02x",
                                op, edge_number, expected_byte, uo_out));
                $display("RETRY_READ op=%0d N+%0d response=%02x raw=%08x",
                         op, edge_number, uo_out, dut.core.acc_codeword);
            end
            check(dut.pending == (edge_offset < 4), "retry wrapper capture at N+4");
            check(dut.core.busy == (edge_offset < 3), "retry core terminal at N+3");
        end
        release dut.core.checked_candidate;
        fail_status(8'h52,6); result_check(-12);
        // No clear: a clean successor proves the retained logical source.
        mac(2,5); check(expected_acc == 'hfffffe, "exhaustion retained logical source");
    endtask

    // Start every recovery case from a real, nonzero host result. kind:
    // 0 = exhausted arithmetic, 1 = uncorrectable storage, 2 = repaired storage.
    task automatic terminal_fault(input integer kind);
        cmd_ok(4,0); expected_acc = 0; mac(1,1);
        load(0,0); launch(); raw_before = dut.core.acc_codeword;
        if (kind == 0) begin
            inject_candidate_zero();
            for (integer attempt = 0; attempt < 3; attempt++) begin
                check(dut.core.busy && !dut.core.decode_uncorrectable &&
                      (dut.core.checked_candidate ^ dut.core.exact_sum) == 1,
                      "recovery setup persistent XOR eligible at each attempt");
                tick();
                check(dut.core.acc_codeword == raw_before,
                      "recovery exhaustion preserves nonzero raw word");
            end
            release dut.core.checked_candidate;
            tick(); fail_status(8'h52,6);
        end else begin
            dut.core.acc_codeword = raw_before ^ (kind == 1 ? 30'h3 : 30'h4);
            #1;
            check((dut.core.acc_codeword ^ raw_before) == (kind == 1 ? 3 : 4) &&
                  (kind == 1 ? dut.core.decode_uncorrectable : dut.core.decode_corrected),
                  "recovery setup storage XOR acknowledgement");
            injections++;
            $display("INJECT recovery kind=%0d before=%08x after=%08x",
                     kind,raw_before,dut.core.acc_codeword);
            tick();
            check(dut.core.acc_codeword == (kind == 1 ? raw_before ^ 3 : raw_before),
                  "recovery setup raw retention or repair");
            tick(); fail_status(kind == 1 ? 8'h0a : 8'h26,0);
        end
        result_check(1);
        check(!dut.pending && !dut.core.busy, "recovery begins from terminal fault status");
    endtask

    task automatic recovery_check(input integer kind, recovery);
        string action_name;
        terminal_fault(kind);
        case (recovery)
            0: begin action_name = "CLEAR"; cmd_ok(4,0); end
            1: begin
                action_name = "RESET"; rst_n = 0; tick();
                check(uo_out == 0, "fault reset masks response");
                rst_n = 1; uio_in = 0; tick();
            end
            2: begin
                action_name = "DISABLE"; ena = 0; tick();
                check(uo_out == 0, "fault disable masks response");
                ena = 1; uio_in = 0; tick();
            end
            default: $fatal(1,"invalid recovery test selection");
        endcase
        // No START may hide a failure to erase terminal fault history here.
        command(0,0,s);
        check(s == 0, $sformatf("fault recovery %s STATUS kind=%0d expected=00 got=%02x",
                               action_name,kind,s));
        command(8,0,d);
        check(d == 0, $sformatf("fault recovery %s DETAIL kind=%0d expected=00 got=%02x",
                               action_name,kind,d));
        result_check(0);
        check(dut.core.acc_codeword == 0 && !dut.pending && !dut.core.busy,
              "fault recovery clears raw storage without late completion");
        $display("RECOVERY kind=%0d action=%s STATUS=%02x DETAIL=%02x result=%02x%02x%02x",
                 kind,action_name,s,d,hi,mid,lo);
        expected_acc = 0; mac(2,3);
    endtask

    // mode 0/1: history already observed, then START/CLEAR;
    // mode 2/3: correction pulse arrives on START/CLEAR;
    // mode 4/5: raw repair is scheduled on START/CLEAR itself.
    task automatic idle_scrub_check(input integer mode);
        cmd_ok(4,0); expected_acc = 0; mac(1,1);
        load(2,3); uio_in = 0; tick(); // arm before the injected idle edge
        check(!dut.pending && !dut.core.busy && !dut.core.corrected,
              "idle scrub has no pending transaction or old correction pulse");
        raw_before = dut.core.acc_codeword;
        dut.core.acc_codeword = raw_before ^ 30'h4; #1;
        check((dut.core.acc_codeword ^ raw_before) == 4 && dut.core.decode_corrected,
              "idle scrub raw XOR acknowledgement");
        injections++;
        $display("INJECT idle mode=%0d before=%08x after=%08x",mode,raw_before,dut.core.acc_codeword);
        if (mode < 4) begin
            tick(); // idle repair, registered correction pulse is now high
            check(dut.core.acc_codeword == raw_before && dut.core.corrected && !dut.pending,
                  "idle scrub repairs actual raw word and emits correction pulse");
            if (mode < 2) begin
                tick(); // wrapper observes pulse without a pending transaction
                command(0,0,s);
                check(s == 8'h26, "idle scrub STATUS expected=26");
                command(8,0,d); check(d == 8'h18, "idle scrub preserves DETAIL loaded flags");
                result_check(1);
                repeat (3) tick();
                command(0,0,s); check(s == 8'h26, "idle scrub correction history is sticky");
                uio_in = 0; tick(); // rearm for following START/CLEAR
            end
        end
        // Direct high edge preserves the pulse alignment; command() would add
        // an extra low edge and miss the simultaneous-priority cases.
        uio_in = (mode % 2 == 0) ? 8'h13 : 8'h14; tick();
        check(uo_out == 0 && !dut.saw_corrected,
              "START or CLEAR overrides old correction history on its edge");
        if (mode % 2 == 0) begin
            check(dut.pending && dut.core.busy && dut.core.acc_codeword == raw_before,
                  "idle scrub START accepts once and retains repaired source");
            if (mode == 4)
                check(dut.core.corrected, "START repair edge emits new correction pulse");
            tick(); tick();
            command(0,0,s);
            check(s == (mode == 4 ? 8'h26 : 8'h06),
                  "idle scrub START terminal correction timing");
            command(8,0,d); check(d == 0, "idle scrub START consumes loads without retries");
            result_check(7); expected_acc = 7;
        end else begin
            command(0,0,s); check(s == 0, "idle scrub CLEAR erases correction history");
            command(8,0,d); check(d == 0, "idle scrub CLEAR erases load flags");
            result_check(0); expected_acc = 0;
            check(dut.core.acc_codeword == 0 && !dut.core.corrected,
                  "idle scrub CLEAR leaves raw zero and no late correction pulse");
        end
        $display("IDLE_SCRUB mode=%0d STATUS=%02x DETAIL=%02x result=%02x%02x%02x",
                 mode,s,d,hi,mid,lo);
    endtask

    initial begin
        skip_fault = $test$plusargs("skip_fault");
        bad_expected = $test$plusargs("bad_expected");
        reset_host();
        command(0, 0, s); check(s == 0, "initial status");
        command(3, 0, s); check(s == 8'he3, "missing both operands rejected");
        cmd_ok(1, 3);
        command(3, 0, s); check(s == 8'he3, "missing B rejected");
        command(8, 0, d); check(d == 8, "partial operand validity retained");
        for (integer op = 9; op < 16; op++) begin
            command(8'(op), 0, s); check(s == 8'he1, "invalid opcode rejected");
        end
        for (integer bitno = 5; bitno < 8; bitno++) begin
            command(8'(1 << bitno), 0, s); check(s == 8'he1, "reserved control bit rejected");
        end
        command(0, 0, s); check(s == 8'h80, "protocol error sticky");
        cmd_ok(4, 0); expected_acc = 0;
        command(8, 0, d); check(d == 0, "clear invalidates operand loads");
        mac(3,-4);
        if (bad_expected) result_check(13);
        // Nonzero output, no clock edge: masking must not reset the response.
        command(5,0,s); check(s == 8'hf4, "mask test nonzero response precondition");
        ena = 0; #1; check(uo_out == 0, "nonzero response masked by ena between edges");
        ena = 1; #1; check(uo_out == 8'hf4, "ena glitch restores original response");
        rst_n = 0; #1; check(uo_out == 0, "nonzero response masked by reset between edges");
        rst_n = 1; #1; check(uo_out == 8'hf4, "reset glitch restores original response");
        fail_status(6,0); result_check(-12);
        mac(-128,-128); mac(-128,127); mac(127,127); mac(0,-128); mac(-1,1);
        $display("PASS signed boundaries and invalid commands");

        // Seed actual 24-bit wrap by legal host transactions, never preload storage.
        cmd_ok(4, 0); expected_acc = 0;
        for (integer i = 0; i < 512; i++) mac(-128,-128);
        check(expected_acc == 'h800000, "positive signed wrap reached");
        mac(-1,1); check(expected_acc == 'h7fffff, "negative signed wrap reached");
        $display("PASS positive and negative accumulator wrap via 513 transactions");

        // A held high strobe executes once, even if opcode/data change while high.
        cmd_ok(4,0); expected_acc = 0; load(2,3); launch();
        for (integer i = 0; i < 8; i++) begin ui_in = 99; uio_in = 8'h14; tick(); end
        result_check(6); fail_status(6,0);
        command(3,0,s); check(s == 8'he3, "operands consumed; no implicit replay");
        cmd_ok(4,0);

        // On N+2 core is done but wrapper is still pending before edge: reject write.
        for (integer op = 1; op <= 4; op++) begin
            cmd_ok(4,0); load(2,3); launch();
            command(8'(op), 99, s); check(s == 8'he2, "busy write rejected on terminal capture edge");
            fail_status(8'h86,0); result_check(6);
            for (integer i = 0; i < 5; i++) tick();
            result_check(6); // rejected commands cannot queue or alter operands/state
        end
        $display("PASS held strobe and all busy write rejections");

        // Reset while core busy, while idle, and held request across reset/enable.
        reset_host(); load(1,1); launch(); rst_n = 0; tick();
        check(!dut.core.busy && !dut.pending, "busy reset aborts");
        rst_n = 1; uio_in = 8'h13; repeat (5) tick();
        check(!dut.pending && !dut.completed && !dut.protocol_error, "high request after reset not armed");
        command(0,0,s); check(s == 0, "reset has no late completion");
        load(1,1); launch(); ena = 0; #1; check(uo_out == 0, "disable masks response immediately");
        tick(); check(dut.core.acc_codeword == 0 && !dut.pending, "disable synchronously aborts");
        ena = 1; uio_in = 8'h13; repeat (4) tick();
        check(!dut.completed && !dut.protocol_error, "held request after enable not armed");
        command(0,0,s); check(s == 0, "disable clears status");
        expected_acc = 0; mac(1,1);
        ena = 0; uio_in = 8'h11; ui_in = 99; repeat (3) tick();
        ena = 1; repeat (3) tick(); command(8,0,d); check(d == 0, "disabled writes discarded");
        fail_status(0,0); result_check(0);
        check(dut.core.acc_codeword == 0, "idle disable clears nonzero accumulator");
        reset_host();
        $display("PASS synchronous reset/ena abort and rearming");

        // Real production candidate path forced only by simulation; no debug RTL build.
        load(1,1); launch(); raw_before = dut.core.acc_codeword;
        inject_candidate_zero(); uio_in = 0; tick();
        check(dut.core.busy && dut.core.retry_count == 1 && dut.core.detected && dut.core.retried,
              "first mismatch retries");
        check(dut.core.acc_codeword == raw_before, "rejected attempt preserves raw storage");
        release dut.core.checked_candidate;
        uio_in = 8'h10; tick(); // STATUS while retry result not yet captured
        check(uo_out == 1, "busy read accepted");
        tick(); fail_status(8'h46, 5); result_check(1);
        repeat (8) tick(); fail_status(8'h46,5); // sticky after all core pulses are gone
        $display("PASS transient fault recovery and persistent readback");

        cmd_ok(4,0); load(1,1); launch(); raw_before = dut.core.acc_codeword;
        inject_candidate_zero();
        for (integer attempt = 0; attempt < 3; attempt++) begin
            check(dut.core.busy && dut.core.checked_candidate == 0, "persistent fault sampled while busy");
            tick();
            check(dut.core.acc_codeword == raw_before, "persistent mismatch cannot commit");
            check(int'(dut.core.retry_count) == (attempt < 2 ? attempt+1 : 2), "bounded retry count");
        end
        check(dut.core.done && !dut.core.result_valid && dut.core.error == 2, "third attempt exhausts");
        release dut.core.checked_candidate; tick(); fail_status(8'h52,6); result_check(0);
        cmd_ok(4,0); expected_acc = 0; mac(1,1);

        // Actual registered storage XOR between launch and completion; masks acknowledged.
        load(0,0); launch(); raw_before = dut.core.acc_codeword;
        dut.core.acc_codeword = raw_before ^ 30'h4; #1;
        check((dut.core.acc_codeword ^ raw_before) == 4 && dut.core.decode_corrected,
              "single storage XOR acknowledgement"); injections++;
        $display("INJECT storage mask4 before=%08x after=%08x",raw_before,dut.core.acc_codeword);
        tick(); check(dut.core.acc_codeword == raw_before && dut.core.corrected, "single repair raw writeback");
        tick(); fail_status(8'h26,0); result_check(1);
        load(1,1); launch(); raw_before = dut.core.acc_codeword;
        dut.core.acc_codeword = raw_before ^ 30'h3; #1;
        check((dut.core.acc_codeword ^ raw_before) == 3 && dut.core.decode_uncorrectable,
              "double storage XOR acknowledgement"); injections++;
        $display("INJECT storage mask3 before=%08x after=%08x",raw_before,dut.core.acc_codeword);
        tick(); check(dut.core.acc_codeword == (raw_before ^ 3), "double failure retains raw storage");
        tick(); fail_status(8'h0a,0); result_check(1); // snapshot retained but invalid
        // Two DATA flips make the live diagnostic decode differ from the last
        // success, proving the interface does not leak that invalid decode.
        cmd_ok(4,0); expected_acc = 0; mac(1,1);
        load(1,1); launch(); raw_before = dut.core.acc_codeword;
        dut.core.acc_codeword = raw_before ^ 30'h14; #1;
        check((dut.core.acc_codeword ^ raw_before) == 30'h14 &&
              dut.core.decode_uncorrectable && dut.core_accumulator == 24'd2,
              "double data XOR acknowledgement and changed diagnostic decode"); injections++;
        $display("INJECT storage mask14 before=%08x after=%08x diagnostic=%06x",
                 raw_before,dut.core.acc_codeword,dut.core_accumulator);
        tick(); check(dut.core.acc_codeword == (raw_before ^ 30'h14),
                      "double data failure retains raw storage");
        tick(); fail_status(8'h0a,0); result_check(1);
        cmd_ok(4,0); expected_acc = 0; mac(3,4);
        $display("PASS error1/error2 distinction, correction, clear recovery");

        // Reject each write while the core itself is still retrying, not only
        // during the wrapper capture cycle. After rejection it must never queue.
        for (integer op = 1; op <= 4; op++) begin
            cmd_ok(4,0); load(1,1); launch(); inject_candidate_zero();
            command(8'(op),99,s);
            check(s == 8'he2 && dut.core.busy && dut.core.retry_count == 2,
                  "write rejected during active core retry");
            check(dut.core.acc_codeword == 0, "busy write cannot change source");
            release dut.core.checked_candidate; tick(); tick();
            fail_status(8'hc6,6); result_check(1);
            command(3,0,s); check(s == 8'he3, "busy writes never preload or queue");
        end
        // B-first and overwrite of an operand are legal; invalid reserved bits
        // must not accidentally CLEAR the prior accumulator or accept a load.
        cmd_ok(4,0); cmd_ok(2,4); cmd_ok(1,2); cmd_ok(1,3); launch();
        tick(); tick(); result_check(12);
        command(8'h24,0,s); check(s == 8'he1, "reserved CLEAR rejected");
        result_check(12);
        command(8'h21,99,s); check(s == 8'he1, "reserved LOAD rejected");
        command(8,0,d); check(d == 0, "invalid LOAD cannot set flag");
        $display("PASS active-retry busy rejections, B-first loads and overwrite");

        // A malformed START must not take the independently decoded launch path.
        for (integer which = 0; which < 4; which++) begin
            cmd_ok(4,0); expected_acc = 0; mac(3,-4); load(2,5);
            raw_before = dut.core.acc_codeword;
            case (which)
                0: command(8'h23,0,s);
                1: command(8'h43,0,s);
                2: command(8'h83,0,s);
                3: command(8'h0b,0,s);
            endcase
            check(s == 8'he1, "malformed loaded START response E1");
            check(!dut.core.busy && !dut.pending,
                  "malformed loaded START must not launch core");
            check(dut.core.acc_codeword == raw_before, "malformed START preserves raw storage");
            result_check(-12); command(8,0,d);
            check(d == 8'h18, "malformed START retains both loaded flags");
            check(dut.core.acc_codeword == raw_before && !dut.core.busy,
                  "malformed START has no deferred mutation");
            launch(); tick(); tick();
            fail_status(8'h86,0); result_check(-2);
            repeat (4) tick(); result_check(-2);
            command(3,0,s); check(s == 8'he3, "legal successor executed exactly once");
            cmd_ok(4,0); fail_status(0,0);
        end
        $display("PASS malformed loaded START and protocol error surviving legal START");
        // Successful commit changes all three bytes (FFFFF4 -> 000002).
        // A read on N+2 must still see the prior snapshot, not live core data.
        for (integer op = 5; op <= 7; op++) begin
            cmd_ok(4,0); expected_acc = 0; mac(3,-4); load(2,7); launch();
            command(8'(op),0,s);
            check(s == (op == 5 ? 8'hf4 : 8'hff), "clean capture-edge read retains prior snapshot");
            fail_status(6,0); result_check(2);
        end
        for (integer op = 0; op <= 8; op++) begin
            if (op == 0 || op >= 5)
                for (integer edge_number = 2; edge_number <= 5; edge_number++)
                    retry_read(op, edge_number);
        end
        $display("PASS twenty intermediate/terminal pin reads with nonzero retained snapshot");

        for (integer recovery = 0; recovery < 3; recovery++)
            for (integer kind = 0; kind < 3; kind++)
                recovery_check(kind,recovery);
        $display("PASS nine terminal-fault CLEAR/reset/disable recovery cases before new START");
        for (integer mode = 0; mode < 6; mode++) idle_scrub_check(mode);
        $display("PASS idle scrub observation and START/CLEAR correction-edge priorities");

        // Reset during an actual retry, with the fault still visible.
        cmd_ok(4,0); load(1,1); launch(); inject_candidate_zero(); tick();
        check(dut.core.retry_count == 1 && dut.core.busy, "retry reset precondition");
        rst_n = 0; tick(); release dut.core.checked_candidate;
        rst_n = 1; uio_in = 0; tick(); fail_status(0,0); result_check(0);
        $display("PASS interface transactions=%0d acknowledged_injection_setups=%0d cycles=%0d", transactions,injections,cycles);
        $finish;
    end
    initial begin
        #1000000; $fatal(1,"FAIL watchdog timeout");
    end
endmodule
