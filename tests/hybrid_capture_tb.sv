`timescale 1ns/1ps
// R4 directed real-RTL capture. Literal checks deliberately do not use the
// Python capture replay or a decoded diagnostic word as a clean-result oracle.
/* verilator lint_off BLKSEQ */
module hybrid_capture_tb;
    reg clk=0;
    zedboard_hybrid_top dut(.clk_100mhz(clk));
    integer cycles=0, trace;
    string trace_path;
    task automatic tick;
        #4;
        $fdisplay(trace,"%0d,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h",cycles,dut.rst,dut.clear,dut.start_request,dut.operand_a,dut.operand_b,dut.attempt_select,dut.candidate_mask,dut.checker_mask,dut.commit_mask,dut.storage_mask,dut.abort_request,dut.start_pulse,dut.launched,dut.ready,dut.busy,dut.done,dut.result_valid,dut.error,dut.accumulator,dut.stored_codeword,dut.corrected,dut.detected,dut.retried,dut.retry_count,dut.inject_fired,dut.fired_attempt,dut.latched_a,dut.latched_b,dut.latched_attempts,dut.latched_candidate,dut.latched_checker,dut.latched_commit,dut.latched_storage,dut.applied_candidate,dut.applied_checker,dut.applied_commit,dut.candidate_before,dut.candidate_after,dut.prediction_before,dut.prediction_after,dut.commit_before,dut.commit_after,dut.source_usable,dut.commit_eligible);
        clk=1; #2; clk=0; #4; cycles++;
    endtask
    task automatic reset_case;
        dut.u_vio.probe_out0=1; dut.u_vio.probe_out1=0;
        dut.u_vio.probe_out2=0; dut.u_vio.probe_out10=0;
        dut.u_vio.probe_out3=3; dut.u_vio.probe_out4=4;
        dut.u_vio.probe_out5=0; dut.u_vio.probe_out6=0;
        dut.u_vio.probe_out7=0; dut.u_vio.probe_out8=0;
        dut.u_vio.probe_out9=0;
        tick(); dut.u_vio.probe_out0=0; tick();
        if(dut.stored_codeword!==0) $fatal(1,"reset source must be zero");
    endtask
    task automatic launch(input reg [29:0] mask);
        dut.u_vio.probe_out2=0; dut.u_vio.probe_out9=mask; tick();
        dut.u_vio.probe_out2=1; tick();
        if(!dut.busy || !dut.launched || dut.inject_fired!==(mask==0 ? 4'b0000 : 4'b0001))
            $fatal(1,"actual launch/storage acknowledgement required");
    endtask
    task automatic exhaust_case(input integer value, input bit busy_clear);
        // Observe every actual candidate XOR/ack, scrub and retry; clear while
        // busy is ignored and must not recover the analyzer's state trust.
        dut.u_vio.probe_out1=busy_clear;
        for(integer attempt=0;attempt<3;attempt++) begin
            if(dut.applied_candidate!==25'd1 ||
               (dut.candidate_before ^ dut.candidate_after)!==25'd1)
                $fatal(1,"candidate XOR required on attempt %0d",attempt);
            tick();
            if(dut.inject_fired!==4'b0010 || int'(dut.fired_attempt)!=attempt ||
               !dut.detected || dut.result_valid || int'($signed(dut.accumulator))!=value)
                $fatal(1,"rejected attempt/ack/state %0d",attempt);
            if(attempt<2 && (!dut.busy || !dut.retried || dut.done || dut.error!=0))
                $fatal(1,"retry must remain pending");
        end
        dut.u_vio.probe_out1=0;
        if(!dut.done || dut.busy || dut.error!=2 || dut.retry_count!=2 || dut.retried)
            $fatal(1,"literal exhaustion error2/count2");
        tick(); tick();
        dut.u_vio.probe_out5=0; dut.u_vio.probe_out6=0;
    endtask
    task automatic finish_case(input integer value, err);
        tick();
        if(!dut.done || dut.busy || dut.result_valid!==(err==0) ||
           int'(dut.error)!=err || int'($signed(dut.accumulator))!=value || dut.retry_count!=0)
            $fatal(1,"literal terminal expected %0d/error%0d",value,err);
        tick(); tick(); // terminal AND successor are in the pre-edge trace
    endtask
    initial begin
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"trace required");
        trace=$fopen(trace_path,"w");
        if(trace==0) $fatal(1,"trace open failed");
        $fdisplay(trace,"cycle,rst,clear,start_request,operand_a,operand_b,attempt_select,candidate_mask,checker_mask,commit_mask,storage_mask,abort_request,start_pulse,launched,ready,busy,done,result_valid,error,accumulator,stored_codeword,corrected,detected,retried,retry_count,inject_fired,fired_attempt,latched_a,latched_b,latched_attempts,latched_candidate,latched_checker,latched_commit,latched_storage,applied_candidate,applied_checker,applied_commit,candidate_before,candidate_after,prediction_before,prediction_after,commit_before,commit_after,source_usable,commit_eligible");
        reset_case();
        launch(3);
        if(dut.stored_codeword!==30'd3 || dut.source_usable) $fatal(1,"raw3 must be unusable");
        finish_case(0,1);
        // NO clear/reset between these two launches. Physical storage retains 3.
        launch(4);
        if(dut.stored_codeword!==30'd7 || !dut.source_usable || dut.accumulator!==24'd1)
            $fatal(1,"raw7 miscorrects to data1");
        finish_case(13,0); // Intended pre-fault total0 + 3*4 is 12, not 13.
        // Sibling: same second launch/mask, but usable raw zero at launch.
        reset_case(); launch(4);
        if(dut.stored_codeword!==30'd4 || !dut.source_usable || dut.accumulator!==0)
            $fatal(1,"single-bit usable-source control");
        finish_case(12,0);
        // Even a coincidentally correct diagnostic total cannot certify a source
        // that was unusable at launch: raw3 XOR3 repairs to zero, returns12.
        reset_case(); launch(3); finish_case(0,1); launch(3); finish_case(12,0);
        // Usable launch source with a new three-bit injection is a known escape.
        reset_case(); launch(7); finish_case(13,0);
        // A forgotten attempt bitmap is visible as a configuration warning,
        // not invented evidence of arithmetic injection or recovery.
        reset_case(); dut.u_vio.probe_out6=1; launch(4); finish_case(12,0);
        // Review scenario A: usable zero -> triple upset -> scrubbed one on
        // rejection. All injections fire; error2 does NOT preserve logical zero.
        reset_case(); dut.u_vio.probe_out5=7; dut.u_vio.probe_out6=1;
        launch(7);
        if(dut.stored_codeword!==30'd7) $fatal(1,"scenario A raw7");
        exhaust_case(1,1);
        if(dut.stored_codeword!==30'h20000007) $fatal(1,"rejection scrubbed data1");
        launch(0); finish_case(13,0); // Busy clear above must not restore trust.
        reset_case(); launch(0); finish_case(12,0); // Reset recovery sibling.
        // Review scenario B: unusable raw3 -> raw7 -> rejected scrub -> valid13.
        reset_case(); launch(3); finish_case(0,1);
        dut.u_vio.probe_out5=7; dut.u_vio.probe_out6=1; launch(4);
        if(dut.stored_codeword!==30'd7) $fatal(1,"scenario B raw7");
        exhaust_case(1,0);
        launch(0); finish_case(13,0);
        // Even a later state-preserving rejection cannot certify tainted data.
        dut.u_vio.probe_out5=7; dut.u_vio.probe_out6=1; launch(0);
        exhaust_case(13,0);
        dut.u_vio.probe_out2=0; dut.u_vio.probe_out1=1; tick();
        dut.u_vio.probe_out1=0; tick();
        launch(0); finish_case(12,0); // Idle clear recovery sibling.
        $display("PASS R4 raw3/raw7 result13 versus clean12; usable control12; unusable coincident12; direct triple13");
        $display("PASS R4 rejected scrub acc1/error2; tainted continuation13; reset/clear recovery12");
        $fclose(trace); $finish;
    end
endmodule
