`timescale 1ns/1ps
// Reference state is a procedural test oracle, not synthesizable registers.
/* verilator lint_off BLKSEQ */
/* verilator lint_off PROCASSINIT */
module zedboard_hybrid_tb;
    reg clk = 0;
    zedboard_hybrid_top dut(.clk_100mhz(clk));
    integer cycles=0, transactions=0, storage_events=0, candidate_events=0;
    integer checker_events=0, commit_events=0;
    reg [29:0] word_ref=0;
    bit busy_ref=0, req_ref=1;
    integer retry_ref=0;
    integer a_ref=0, b_ref=0;
    reg [7:0] la_ref=0, lb_ref=0;
    reg [2:0] attempts_ref=0, checker_ref=0;
    reg [24:0] candidate_ref=0;
    reg [23:0] commit_ref=0;
    reg [29:0] storage_ref=0;
    reg [1:0] ack_attempt_ref=0;
    integer trace;
    string trace_path;

    function automatic [29:0] encode(input reg [23:0] data);
        reg [29:0] code;
        integer k;
        code=0; k=0;
        for (integer p=1;p<=29;p++) begin
            if ((p & (p-1)) != 0) begin code[p-1]=data[k]; k++; end
        end
        for (integer j=0;j<5;j++) begin
            for (integer p=1;p<=29;p++)
                if ((p & (1<<j)) != 0) code[(1<<j)-1] ^= code[p-1];
        end
        code[29]=^code[28:0];
        return code;
    endfunction

    // Independent integer arithmetic and Hamming-position oracle; no DUT helper.
    task automatic decode(input reg [29:0] raw, output reg [23:0] data,
                          output bit corrected, output bit bad);
        reg [29:0] fixed_word;
        integer syndrome, k;
        syndrome=0; fixed_word=raw; corrected=0; bad=0;
        for(integer p=1;p<=29;p++) if(raw[p-1]) syndrome ^= p;
        if (^raw) begin
            if(syndrome==0) begin fixed_word[29]=!fixed_word[29]; corrected=1; end
            else if(syndrome<=29) begin fixed_word[syndrome-1]=!fixed_word[syndrome-1]; corrected=1; end
            else bad=1;
        end else if(syndrome!=0) bad=1;
        k=0; data=0;
        for(integer p=1;p<=29;p++) if((p & (p-1))!=0) begin
            data[k]=fixed_word[p-1]; k++;
        end
    endtask
    function automatic integer mod7(input integer x);
        return ((x%7)+7)%7;
    endfunction

    always @(posedge clk) begin : oracle
        reg [23:0] data, post_data, commit_wire;
        reg signed [24:0] full_sum, changed;
        reg [24:0] cm;
        reg [2:0] pm, prediction, changed_prediction;
        reg [23:0] km;
        reg [3:0] ack;
        bit cor, bad, unused_post_cor, post_bad, accept, pulse, reset_now;
        bit done_next, valid_next, corrected_next, detected_next, retried_next;
        integer error_next;
        // Check the actual stand-in pins, not only internal wrapper wires.
        if(dut.u_vio.probe_out0!==dut.rst) $fatal(1,"VIO probe_out0 wiring");
        if(dut.u_vio.probe_out1!==dut.clear) $fatal(1,"VIO probe_out1 wiring");
        if(dut.u_vio.probe_out2!==dut.start_request) $fatal(1,"VIO probe_out2 wiring");
        if(dut.u_vio.probe_out3!==dut.operand_a) $fatal(1,"VIO probe_out3 wiring");
        if(dut.u_vio.probe_out4!==dut.operand_b) $fatal(1,"VIO probe_out4 wiring");
        if(dut.u_vio.probe_out5!==dut.attempt_select) $fatal(1,"VIO probe_out5 wiring");
        if(dut.u_vio.probe_out6!==dut.candidate_mask) $fatal(1,"VIO probe_out6 wiring");
        if(dut.u_vio.probe_out7!==dut.checker_mask) $fatal(1,"VIO probe_out7 wiring");
        if(dut.u_vio.probe_out8!==dut.commit_mask) $fatal(1,"VIO probe_out8 wiring");
        if(dut.u_vio.probe_out9!==dut.storage_mask) $fatal(1,"VIO probe_out9 wiring");
        if(dut.u_vio.probe_out10!==dut.abort_request) $fatal(1,"VIO probe_out10 wiring");
        if(dut.u_ila.probe0!==dut.rst) $fatal(1,"ILA probe0 wiring");
        if(dut.u_ila.probe1!==dut.clear) $fatal(1,"ILA probe1 wiring");
        if(dut.u_ila.probe2!==dut.start_request) $fatal(1,"ILA probe2 wiring");
        if(dut.u_ila.probe3!==dut.operand_a) $fatal(1,"ILA probe3 wiring");
        if(dut.u_ila.probe4!==dut.operand_b) $fatal(1,"ILA probe4 wiring");
        if(dut.u_ila.probe5!==dut.attempt_select) $fatal(1,"ILA probe5 wiring");
        if(dut.u_ila.probe6!==dut.candidate_mask) $fatal(1,"ILA probe6 wiring");
        if(dut.u_ila.probe7!==dut.checker_mask) $fatal(1,"ILA probe7 wiring");
        if(dut.u_ila.probe8!==dut.commit_mask) $fatal(1,"ILA probe8 wiring");
        if(dut.u_ila.probe9!==dut.storage_mask) $fatal(1,"ILA probe9 wiring");
        if(dut.u_ila.probe10!==dut.abort_request) $fatal(1,"ILA probe10 wiring");
        if(dut.u_ila.probe11!==dut.start_pulse) $fatal(1,"ILA probe11 wiring");
        if(dut.u_ila.probe12!==dut.launched) $fatal(1,"ILA probe12 wiring");
        if(dut.u_ila.probe13!==dut.ready) $fatal(1,"ILA probe13 wiring");
        if(dut.u_ila.probe14!==dut.busy) $fatal(1,"ILA probe14 wiring");
        if(dut.u_ila.probe15!==dut.done) $fatal(1,"ILA probe15 wiring");
        if(dut.u_ila.probe16!==dut.result_valid) $fatal(1,"ILA probe16 wiring");
        if(dut.u_ila.probe17!==dut.error) $fatal(1,"ILA probe17 wiring");
        if(dut.u_ila.probe18!==dut.accumulator) $fatal(1,"ILA probe18 wiring");
        if(dut.u_ila.probe19!==dut.stored_codeword) $fatal(1,"ILA probe19 wiring");
        if(dut.u_ila.probe20!==dut.corrected) $fatal(1,"ILA probe20 wiring");
        if(dut.u_ila.probe21!==dut.detected) $fatal(1,"ILA probe21 wiring");
        if(dut.u_ila.probe22!==dut.retried) $fatal(1,"ILA probe22 wiring");
        if(dut.u_ila.probe23!==dut.retry_count) $fatal(1,"ILA probe23 wiring");
        if(dut.u_ila.probe24!==dut.inject_fired) $fatal(1,"ILA probe24 wiring");
        if(dut.u_ila.probe25!==dut.fired_attempt) $fatal(1,"ILA probe25 wiring");
        if(dut.u_ila.probe26!==dut.latched_a) $fatal(1,"ILA probe26 wiring");
        if(dut.u_ila.probe27!==dut.latched_b) $fatal(1,"ILA probe27 wiring");
        if(dut.u_ila.probe28!==dut.latched_attempts) $fatal(1,"ILA probe28 wiring");
        if(dut.u_ila.probe29!==dut.latched_candidate) $fatal(1,"ILA probe29 wiring");
        if(dut.u_ila.probe30!==dut.latched_checker) $fatal(1,"ILA probe30 wiring");
        if(dut.u_ila.probe31!==dut.latched_commit) $fatal(1,"ILA probe31 wiring");
        if(dut.u_ila.probe32!==dut.latched_storage) $fatal(1,"ILA probe32 wiring");
        if(dut.u_ila.probe33!==dut.applied_candidate) $fatal(1,"ILA probe33 wiring");
        if(dut.u_ila.probe34!==dut.applied_checker) $fatal(1,"ILA probe34 wiring");
        if(dut.u_ila.probe35!==dut.applied_commit) $fatal(1,"ILA probe35 wiring");
        if(dut.u_ila.probe36!==dut.candidate_before) $fatal(1,"ILA probe36 wiring");
        if(dut.u_ila.probe37!==dut.candidate_after) $fatal(1,"ILA probe37 wiring");
        if(dut.u_ila.probe38!==dut.prediction_before) $fatal(1,"ILA probe38 wiring");
        if(dut.u_ila.probe39!==dut.prediction_after) $fatal(1,"ILA probe39 wiring");
        if(dut.u_ila.probe40!==dut.commit_before) $fatal(1,"ILA probe40 wiring");
        if(dut.u_ila.probe41!==dut.commit_after) $fatal(1,"ILA probe41 wiring");
        if(dut.u_ila.probe42!==dut.source_usable) $fatal(1,"ILA probe42 wiring");
        if(dut.u_ila.probe43!==dut.commit_eligible) $fatal(1,"ILA probe43 wiring");
        if(dut.u_vio.probe_in0!==dut.ready) $fatal(1,"VIO probe_in0 wiring");
        if(dut.u_vio.probe_in1!==dut.busy) $fatal(1,"VIO probe_in1 wiring");
        if(dut.u_vio.probe_in2!==dut.accumulator) $fatal(1,"VIO probe_in2 wiring");
        if(dut.u_vio.probe_in3!==dut.error) $fatal(1,"VIO probe_in3 wiring");
        if(dut.u_vio.probe_in4!==dut.retry_count) $fatal(1,"VIO probe_in4 wiring");
        reset_now=dut.rst || dut.abort_request;
        pulse=!reset_now && dut.start_request && !req_ref;
        accept=pulse && !dut.clear && !busy_ref;
        decode(word_ref,data,cor,bad);
        full_sum=25'(int'($signed(data))+a_ref*b_ref);
        cm=0; pm=0; km=0;
        if(!reset_now && busy_ref && attempts_ref[retry_ref]) begin
            cm=candidate_ref; pm=checker_ref; km=commit_ref;
        end
        changed=full_sum ^ cm;
        prediction=3'(mod7(int'($signed(data))+a_ref*b_ref));
        changed_prediction=prediction^pm;
        commit_wire=changed[23:0] ^ km;
        if(dut.start_pulse!==pulse || dut.ready!==(!reset_now && !dut.clear && !busy_ref))
            $fatal(1,"request/ready edge cycle %0d",cycles);
        if(dut.applied_candidate!==cm || dut.applied_checker!==pm || dut.applied_commit!==km)
            $fatal(1,"selected attempt masks cycle %0d",cycles);
        if(dut.candidate_before!==full_sum || dut.candidate_after!==changed)
            $fatal(1,"candidate actual XOR cycle %0d",cycles);
        if(dut.prediction_before!==prediction || dut.prediction_after!==(prediction^pm))
            $fatal(1,"prediction actual XOR cycle %0d",cycles);
        if(dut.commit_before!==changed[23:0] || dut.commit_after!==commit_wire)
            $fatal(1,"commit actual XOR cycle %0d",cycles);
        if(dut.source_usable!==!bad || dut.commit_eligible!==(!bad && changed_prediction!=3'd7 && int'(changed_prediction)==mod7(int'(changed))))
            $fatal(1,"site eligibility cycle %0d",cycles);
        done_next=0; valid_next=0; corrected_next=0; detected_next=0;
        retried_next=0; error_next=0; ack=0;
        if(reset_now) begin
            la_ref=0; lb_ref=0; word_ref=0; busy_ref=0; retry_ref=0; a_ref=0; b_ref=0;
            attempts_ref=0; candidate_ref=0; checker_ref=0; commit_ref=0; storage_ref=0;
            req_ref=1; ack_attempt_ref=0;
        end else begin
            req_ref=dut.start_request;
            if(busy_ref) begin
                ack_attempt_ref=2'(retry_ref);
                if(!bad) begin
                    ack[1]=|cm; ack[2]=|pm;
                    ack[3]=(|km) && (changed_prediction!=3'd7) && int'(changed_prediction)==mod7(int'(changed));
                end
                if(bad) begin busy_ref=0; done_next=1; error_next=1; end
                else begin
                    if(cor) begin word_ref=encode(data); corrected_next=1; end
                    if(changed_prediction!=3'd7 && int'(changed_prediction)==mod7(int'(changed))) begin
                        word_ref=encode(commit_wire); busy_ref=0; done_next=1; valid_next=1;
                    end else begin
                        detected_next=1;
                        if(retry_ref<2) begin retry_ref++; retried_next=1; end
                        else begin busy_ref=0; done_next=1; error_next=2; end
                    end
                end
            end else if(dut.clear) begin
                la_ref=0; lb_ref=0; word_ref=0; retry_ref=0; ack_attempt_ref=0;
                // Core saved operands persist through idle clear; board latches clear.
                attempts_ref=0; candidate_ref=0; checker_ref=0; commit_ref=0; storage_ref=0;
            end else begin
                if(accept && dut.storage_mask!=0) begin
                    word_ref ^= dut.storage_mask; ack[0]=1;
                end else if(cor) begin word_ref=encode(data); corrected_next=1; end
                if(accept) begin
                    busy_ref=1; retry_ref=0; ack_attempt_ref=0;
                    la_ref=dut.operand_a; lb_ref=dut.operand_b;
                    a_ref=int'($signed(dut.operand_a)); b_ref=int'($signed(dut.operand_b));
                    attempts_ref=dut.attempt_select; candidate_ref=dut.candidate_mask;
                    checker_ref=dut.checker_mask; commit_ref=dut.commit_mask; storage_ref=dut.storage_mask;
                    transactions++;
                end
            end
        end
        $fdisplay(trace,"%0d,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h",cycles+1,dut.rst,dut.clear,dut.start_request,dut.operand_a,dut.operand_b,dut.attempt_select,dut.candidate_mask,dut.checker_mask,dut.commit_mask,dut.storage_mask,dut.abort_request,dut.start_pulse,dut.launched,dut.ready,dut.busy,dut.done,dut.result_valid,dut.error,dut.accumulator,dut.stored_codeword,dut.corrected,dut.detected,dut.retried,dut.retry_count,dut.inject_fired,dut.fired_attempt,dut.latched_a,dut.latched_b,dut.latched_attempts,dut.latched_candidate,dut.latched_checker,dut.latched_commit,dut.latched_storage,dut.applied_candidate,dut.applied_checker,dut.applied_commit,dut.candidate_before,dut.candidate_after,dut.prediction_before,dut.prediction_after,dut.commit_before,dut.commit_after,dut.source_usable,dut.commit_eligible);
        #1;
        cycles++;
        decode(word_ref,post_data,unused_post_cor,post_bad);
        if(reset_now && dut.stored_codeword!==30'b0) $fatal(1,"reset/abort raw storage clear");
        if(dut.stored_codeword!==word_ref) $fatal(1,"raw storage XOR/commit cycle %0d expected %h got %h",cycles,word_ref,dut.stored_codeword);
        if(dut.source_usable!==!post_bad || dut.accumulator!==post_data) $fatal(1,"decoded result cycle %0d",cycles);
        if(dut.busy!==busy_ref || dut.done!==done_next || dut.result_valid!==valid_next || int'(dut.error)!=error_next || int'(dut.retry_count)!=retry_ref)
            $fatal(1,"transaction status cycle %0d",cycles);
        if(dut.corrected!==corrected_next || dut.detected!==detected_next || dut.retried!==retried_next)
            $fatal(1,"protection status cycle %0d",cycles);
        if(dut.inject_fired!==ack || dut.fired_attempt!==ack_attempt_ref)
            $fatal(1,"sampled injection acknowledgement cycle %0d",cycles);
        if(dut.launched!==accept) $fatal(1,"launch acknowledgement cycle %0d",cycles);
        if(dut.latched_attempts!==attempts_ref || dut.latched_candidate!==candidate_ref || dut.latched_checker!==checker_ref || dut.latched_commit!==commit_ref || dut.latched_storage!==storage_ref)
            $fatal(1,"latched settings cycle %0d",cycles);
        if(dut.latched_a!==la_ref || dut.latched_b!==lb_ref) $fatal(1,"latched operands");
        storage_events+=int'(ack[0]); candidate_events+=int'(ack[1]);
        checker_events+=int'(ack[2]); commit_events+=int'(ack[3]);
    end

    task automatic tick;
        #4; clk=1; #2; clk=0; #4;
    endtask

    task automatic config_case(input integer a,b, input reg [2:0] attempts,
                               input reg [24:0] cm, input reg [2:0] pm,
                               input reg [23:0] km, input reg [29:0] sm);
        if(a < -128 || a > 127 || b < -128 || b > 127) $fatal(1,"operand range");
        dut.u_vio.probe_out3=8'(a); dut.u_vio.probe_out4=8'(b);
        dut.u_vio.probe_out5=attempts; dut.u_vio.probe_out6=cm;
        dut.u_vio.probe_out7=pm; dut.u_vio.probe_out8=km; dut.u_vio.probe_out9=sm;
    endtask
    task automatic reset_case;
        dut.u_vio.probe_out0=1; dut.u_vio.probe_out1=0;
        dut.u_vio.probe_out2=0; dut.u_vio.probe_out10=0;
        config_case(0,0,0,0,0,0,0); tick();
        dut.u_vio.probe_out0=0; tick();
    endtask
    task automatic launch;
        dut.u_vio.probe_out2=0; tick();
        dut.u_vio.probe_out2=1; tick();
        if(!dut.busy || !dut.launched) $fatal(1,"expected accepted launch");
    endtask
    task automatic terminal(input integer expected, retries, err);
        integer attempts;
        attempts=0;
        while(dut.busy && attempts<4) begin tick(); attempts++; end
        if(dut.busy || !dut.done || dut.result_valid!==(err==0) || int'(dut.error)!=err || int'(dut.retry_count)!=retries || int'($signed(dut.accumulator))!=expected)
            $fatal(1,"literal terminal expected=%0d retries=%0d error=%0d got=%0d",expected,retries,err,$signed(dut.accumulator));
        tick();
        if(dut.done || dut.busy || dut.inject_fired!=0) $fatal(1,"terminal pulses/held request");
    endtask
    task automatic clean(input integer a,b,expected);
        config_case(a,b,0,0,0,0,0); launch(); terminal(expected,0,0);
    endtask

    initial begin
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"trace path required");
        trace=$fopen(trace_path,"w");
        if(trace==0) $fatal(1,"cannot open trace");
        $fdisplay(trace,"cycle,rst,clear,start_request,operand_a,operand_b,attempt_select,candidate_mask,checker_mask,commit_mask,storage_mask,abort_request,start_pulse,launched,ready,busy,done,result_valid,error,accumulator,stored_codeword,corrected,detected,retried,retry_count,inject_fired,fired_attempt,latched_a,latched_b,latched_attempts,latched_candidate,latched_checker,latched_commit,latched_storage,applied_candidate,applied_checker,applied_commit,candidate_before,candidate_after,prediction_before,prediction_after,commit_before,commit_after,source_usable,commit_eligible");
        reset_case(); clean(34,55,1870); clean(15,10,2020); // H1
        reset_case(); config_case(3,4,1,1,0,0,0); launch(); terminal(12,1,0); // H2
        reset_case(); config_case(3,4,7,1,0,1,0); launch(); terminal(0,2,2); // H3, commit visible but not fired
        reset_case(); config_case(3,4,3,1,0,0,0); launch(); terminal(12,2,0); // H4
        for(integer k=0;k<25;k++) begin // H5, including signed candidate bit
            reset_case(); config_case(3,4,1,25'b1<<k,0,0,0); launch(); terminal(12,1,0);
        end
        reset_case(); config_case(2,3,1,0,1,0,0); launch(); terminal(6,1,0); // H6
        for(integer k=0;k<30;k++) begin // H7 every storage bit, actual launch XOR
            reset_case(); clean(1,1,1);
            config_case(1,-1,1,1,0,0,30'b1<<k); launch(); terminal(0,1,0);
        end
        for(integer i=0;i<30;i++) for(integer j=i+1;j<30;j++) begin // H8 all pairs
            reset_case(); config_case(3,4,7,1,1,1,(30'b1<<i)|(30'b1<<j)); launch();
            tick();
            if(!dut.done || dut.result_valid || dut.error!=1 || dut.retry_count!=0 || dut.inject_fired!=0)
                $fatal(1,"double-error terminal priority");
            tick(); dut.u_vio.probe_out1=1; tick(); dut.u_vio.probe_out1=0; tick();
            clean(2,3,6);
        end
        // H9 reset AND abort at each pending attempt, no stale replay on release.
        for(integer kind=0;kind<2;kind++) for(integer attempt=0;attempt<3;attempt++) begin
            reset_case(); clean(1,1,1);
            config_case(3,4,7,1,0,0,0); launch();
            repeat(attempt) tick();
            if(!dut.busy || int'(dut.retry_count)!=attempt ||
               dut.stored_codeword!==30'h20000007 || dut.accumulator!==24'd1)
                $fatal(1,"H9 nonzero pending setup");
            if(kind==0) dut.u_vio.probe_out0=1; else dut.u_vio.probe_out10=1;
            tick();
            if(dut.stored_codeword!==30'b0 || dut.accumulator!==24'b0)
                $fatal(1,"H9 immediate raw/decoded clear");
            dut.u_vio.probe_out0=0; dut.u_vio.probe_out10=0;
            repeat(4) tick();
            if(dut.busy || dut.done || dut.stored_codeword!=0 || dut.latched_candidate!=0) $fatal(1,"abort late completion");
            clean(2,3,6);
        end
        // H10 nonzero state makes an erroneous busy clear observable.
        // Change every live setting and raise a busy request while clear=1.
        reset_case(); clean(1,1,1); config_case(3,4,3,1,0,0,0); launch();
        dut.u_vio.probe_out2=0; tick(); // first rejection
        config_case(-128,-128,7,25'h1ffffff,7,24'hffffff,30'h3fffffff);
        dut.u_vio.probe_out1=1; dut.u_vio.probe_out2=1; tick(); // second rejection
        dut.u_vio.probe_out1=0; terminal(13,2,0);
        repeat(3) tick(); if(dut.busy || dut.accumulator!=13) $fatal(1,"busy request queued");
        // Independently discard a busy rising request with clear LOW.
        config_case(2,3,3,1,0,0,0); launch();
        dut.u_vio.probe_out2=0; tick();
        config_case(99,99,7,4,4,4,4);
        dut.u_vio.probe_out2=1; tick(); terminal(19,2,0);
        // H11 clear exhausted fault history, then recover.
        reset_case(); config_case(3,4,7,1,0,0,0); launch(); terminal(0,2,2);
        dut.u_vio.probe_out1=1; tick();
        if(dut.retry_count!=0 || dut.latched_attempts!=0 || dut.stored_codeword!=0) $fatal(1,"clear recovery");
        dut.u_vio.probe_out1=0; clean(3,4,12);
        // H12 verified accumulation to both boundaries, no backdoor state seeds.
        reset_case();
        for(integer i=1;i<=512;i++) clean(-128,-128,i==512 ? -8388608 : i*16384);
        clean(-1,1,8388607); clean(1,1,-8388608);
        reset_case(); config_case(0,0,1,7,0,0,0); launch(); terminal(7,0,0); // H13 escape
        reset_case(); config_case(1,1,1,1,1,0,0); launch(); terminal(0,0,0); // H14 escape
        reset_case(); config_case(1,1,1,0,0,1,0); launch(); terminal(0,0,0); // H15 escape
        // Zero mask and unreachable selected attempts: requested is not fired.
        reset_case(); config_case(3,4,7,0,0,0,0); launch(); terminal(12,0,0);
        reset_case(); config_case(3,4,6,1,0,0,0); launch(); terminal(12,0,0);
        // Idle clear beats start; held request cannot launch when clear released.
        reset_case(); config_case(3,4,7,1,1,1,4);
        dut.u_vio.probe_out1=1; dut.u_vio.probe_out2=1; tick();
        dut.u_vio.probe_out1=0; repeat(4) tick();
        if(dut.busy || dut.launched || dut.inject_fired!=0) $fatal(1,"clear discarded request queued");
        // Known nonzero state, reset+clear+start all together.
        clean(3,4,12); dut.u_vio.probe_out0=1; dut.u_vio.probe_out1=1;
        tick(); dut.u_vio.probe_out0=0; dut.u_vio.probe_out1=0; repeat(3) tick();
        clean(3,-4,-12);
        $display("PASS hybrid board H1-H15 cycles=%0d transactions=%0d storage=%0d candidate=%0d checker=%0d commit=%0d",cycles,transactions,storage_events,candidate_events,checker_events,commit_events);
        $fclose(trace); $finish;
    end
endmodule
