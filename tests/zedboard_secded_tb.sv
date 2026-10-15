`timescale 1ns/1ps
module zedboard_secded_tb;
    reg clk = 0;
    zedboard_secded_top dut(.clk_100mhz(clk));
    reg [29:0] original_word, damaged_word, mask;
    integer injections = 0;

    task automatic tick;
        #4; clk = 1; #1; clk = 0; #5;
    endtask
    task automatic reset_core;
        dut.u_vio.probe_out0 = 1;
        dut.u_vio.probe_out1 = 0;
        dut.u_vio.probe_out2 = 0;
        dut.u_vio.probe_out3 = 0;
        dut.u_vio.probe_out4 = 0;
        dut.u_vio.probe_out5 = 0;
        dut.u_vio.probe_out6 = 0;
        tick();
        dut.u_vio.probe_out0 = 0;
        tick();
        if (dut.accumulator !== 0 || dut.inject_fired || dut.corrected || !dut.ready)
            $fatal(1, "reset failed");
    endtask
    task automatic seed_acc;
        reset_core();
        dut.u_vio.probe_out3 = 34;
        dut.u_vio.probe_out4 = 55;
        dut.u_vio.probe_out2 = 1;
        tick();
        if (!dut.busy) $fatal(1, "start not accepted");
        tick();
        if (!dut.done || !dut.result_valid || dut.error != 0 || dut.accumulator != 1870)
            $fatal(1, "seed MAC failed");
        tick();
        if (dut.done || dut.busy || dut.accumulator != 1870)
            $fatal(1, "held start repeated transaction");
        dut.u_vio.probe_out2 = 0;
        tick();
    endtask
    task automatic inject(input reg [29:0] fault_mask);
        original_word = dut.stored_codeword;
        dut.u_vio.probe_out6 = fault_mask;
        dut.u_vio.probe_out5 = 1;
        tick();
        damaged_word = original_word ^ fault_mask;
        if (!dut.inject_fired || dut.stored_codeword !== damaged_word || dut.corrected)
            $fatal(1, "injection did not change exactly the requested bits");
        injections = injections + 1;
    endtask
    initial begin
        for (integer bit_index = 0; bit_index < 30; bit_index = bit_index + 1) begin
            seed_acc();
            inject(30'b1 << bit_index);
            tick();
            if (!dut.corrected || dut.inject_fired || dut.stored_codeword !== original_word
                || dut.accumulator != 1870)
                $fatal(1, "single-bit repair failed at bit %0d", bit_index);
            tick();
            if (dut.corrected || dut.inject_fired || dut.stored_codeword !== original_word)
                $fatal(1, "held injection request retriggered");
        end
        for (integer first = 0; first < 30; first = first + 1) begin
            for (integer second = first + 1; second < 30; second = second + 1) begin
                seed_acc();
                mask = (30'b1 << first) | (30'b1 << second);
                inject(mask);
                tick();
                if (dut.corrected || dut.inject_fired || dut.stored_codeword !== damaged_word)
                    $fatal(1, "double fault incorrectly scrubbed");
                dut.u_vio.probe_out2 = 1;
                tick(); tick();
                if (!dut.done || dut.result_valid || dut.error != 1
                    || dut.stored_codeword !== damaged_word)
                    $fatal(1, "double fault not rejected");
                tick();
                if (dut.done || dut.error != 0) $fatal(1, "status not pulsed");
                dut.u_vio.probe_out1 = 1;
                tick();
                if (dut.stored_codeword !== 0 || dut.accumulator !== 0)
                    $fatal(1, "clear recovery failed");
            end
        end
        // Zero mask does not block a simultaneous ordinary start.
        reset_core();
        dut.u_vio.probe_out2 = 1;
        dut.u_vio.probe_out5 = 1;
        tick();
        if (dut.inject_fired || !dut.busy) $fatal(1, "zero mask semantics failed");
        // A nonzero idle injection takes priority over simultaneous start.
        reset_core();
        dut.u_vio.probe_out2 = 1;
        dut.u_vio.probe_out6 = 4;
        dut.u_vio.probe_out5 = 1;
        tick();
        if (!dut.inject_fired || dut.busy) $fatal(1, "injection priority failed");
        tick();
        if (!dut.corrected || dut.busy) $fatal(1, "discarded start was queued");
        // A request while busy is ignored; completion keeps its normal timing.
        seed_acc();
        dut.u_vio.probe_out2 = 1;
        tick();
        dut.u_vio.probe_out6 = 4;
        dut.u_vio.probe_out5 = 1;
        tick();
        if (dut.inject_fired || !dut.result_valid || dut.accumulator != 3740)
            $fatal(1, "busy injection was not ignored");
        tick();
        if (dut.inject_fired || dut.corrected) $fatal(1, "busy injection was queued");
        // Reset and clear suppress injection.
        reset_core();
        dut.u_vio.probe_out1 = 1;
        dut.u_vio.probe_out5 = 1;
        dut.u_vio.probe_out6 = 4;
        tick();
        if (dut.inject_fired || dut.stored_codeword !== 0) $fatal(1, "clear priority failed");
        dut.u_vio.probe_out5 = 0; tick();
        dut.u_vio.probe_out0 = 1;
        dut.u_vio.probe_out5 = 1;
        tick();
        if (dut.inject_fired || dut.stored_codeword !== 0) $fatal(1, "reset priority failed");
        $display("PASS: board wrapper, %0d enumerated injections, repair/rejection and request priorities", injections);
        $finish;
    end
endmodule
