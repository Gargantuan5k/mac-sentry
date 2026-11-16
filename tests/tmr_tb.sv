`timescale 1ns/1ps
module tmr_tb;
    parameter integer OPERAND_WIDTH=8, ACC_WIDTH=24;
    localparam integer OW=OPERAND_WIDTH, AW=ACC_WIDTH;
    localparam integer MASK=(1<<AW)-1, OMASK=(1<<OW)-1;
    reg clk=0, rst=0, clear=0, start=0;
    reg signed [OW-1:0] operand_a=0, operand_b=0;
    reg [AW-1:0] cm0=0, cm1=0, cm2=0, sv=0, cv=0;
    wire ready,busy,done,valid,disagreement;
    wire [1:0] error;
    wire signed [AW-1:0] accumulator;
    wire pr,pb,pd,pv,px;
    wire [1:0] pe;
    wire signed [AW-1:0] pa;
    mac_tmr_injectable #(.OPERAND_WIDTH(OW),.ACC_WIDTH(AW)) dut (
        .clk(clk),.rst(rst),.clear(clear),.start(start),.operand_a(operand_a),.operand_b(operand_b),
        .ready(ready),.busy(busy),.done(done),.result_valid(valid),.error(error),
        .accumulator(accumulator),.disagreement(disagreement),
        .candidate_mask0(cm0),.candidate_mask1(cm1),.candidate_mask2(cm2),
        .state_voter_fault_mask(sv),.candidate_voter_fault_mask(cv));
    mac_tmr #(.OPERAND_WIDTH(OW),.ACC_WIDTH(AW)) production (
        .clk(clk),.rst(rst),.clear(clear),.start(start),.operand_a(operand_a),.operand_b(operand_b),
        .ready(pr),.busy(pb),.done(pd),.result_valid(pv),.error(pe),.accumulator(pa),.disagreement(px));
    integer s[3], a[3], b[3], cand[3];
    bit pending=0, compare_clean=1;
    integer cycles=0, injections=0, completions=0, trace;
    integer arithmetic_acks=0, voter_acks=0;
    integer seed=32'h513abc, phase=0;
    string trace_path;
    function automatic integer signop(input integer x);
        return (x & (1<<(OW-1))) != 0 ? (x & OMASK)-(1<<OW) : x & OMASK;
    endfunction
    function automatic integer maj(input integer x,y,z);
        integer result_word;
        result_word=0;
        for (integer k=0;k<AW;k=k+1)
            if (((x>>k)&1)+((y>>k)&1)+((z>>k)&1)>=2) result_word=result_word | (1<<k);
        return result_word;
    endfunction
    task automatic raw_check;
        if (int'(dut.lane0.acc_state)!=s[0] || int'(dut.lane1.acc_state)!=s[1] ||
            int'(dut.lane2.acc_state)!=s[2]) $fatal(1,"TMR_RAW_STATE cycle=%0d",cycles);
        if ((int'(dut.lane0.saved_a)&OMASK)!=a[0] || (int'(dut.lane1.saved_a)&OMASK)!=a[1] ||
            (int'(dut.lane2.saved_a)&OMASK)!=a[2] || (int'(dut.lane0.saved_b)&OMASK)!=b[0] ||
            (int'(dut.lane1.saved_b)&OMASK)!=b[1] || (int'(dut.lane2.saved_b)&OMASK)!=b[2])
            $fatal(1,"TMR_SAVED_OPERANDS cycle=%0d",cycles);
    endtask
    task automatic tick;
        integer voted, expected_done;
        bit mismatch;
        #2;
        raw_check();
        if (ready !== !(rst || clear || pending) || busy !== pending)
            $fatal(1,"TMR_PRE_CONTROL cycle=%0d",cycles);
        for(integer j=0;j<3;j=j+1) cand[j]=(s[j]+signop(a[j])*signop(b[j])) & MASK;
        if (int'(dut.lane0.clean_candidate)!=cand[0] || int'(dut.lane1.clean_candidate)!=cand[1] ||
            int'(dut.lane2.clean_candidate)!=cand[2]) $fatal(1,"TMR_ARITHMETIC cycle=%0d",cycles);
        cand[0]=cand[0]^int'(cm0); cand[1]=cand[1]^int'(cm1); cand[2]=cand[2]^int'(cm2);
        if(int'(dut.candidate0)!=cand[0] || int'(dut.candidate1)!=cand[1] || int'(dut.candidate2)!=cand[2])
            $fatal(1,"TMR_CANDIDATE_XOR cycle=%0d",cycles);
        if(int'(dut.state_vote)!=(maj(s[0],s[1],s[2])^int'(sv)) ||
           int'(dut.candidate_vote)!=(maj(cand[0],cand[1],cand[2])^int'(cv)))
            $fatal(1,"TMR_VOTER cycle=%0d",cycles);
        mismatch=(s[0]!=s[1] || s[0]!=s[2] || (pending && (cand[0]!=cand[1] || cand[0]!=cand[2])));
        if(disagreement!==mismatch) $fatal(1,"TMR_DISAGREEMENT cycle=%0d",cycles);
        if(!rst && pending) arithmetic_acks += int'(cm0!=0)+int'(cm1!=0)+int'(cm2!=0);
        if(!rst && (pending ? cv!=0 : (!clear && sv!=0))) voter_acks++;
        $fwrite(trace,"pre,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0h,%0d\n",
            cycles,rst,clear,start,pending,done,valid,s[0],s[1],s[2],a[0],a[1],a[2],b[0],b[1],b[2],cm0,cm1,cm2,sv,cv,phase);
        expected_done=0;
        if(rst) begin
            pending=0;
            for(integer j=0;j<3;j=j+1) begin s[j]=0; a[j]=0; b[j]=0; end
        end else if(pending) begin
            voted=maj(cand[0],cand[1],cand[2])^int'(cv);
            for(integer j=0;j<3;j=j+1) s[j]=voted;
            pending=0; expected_done=1; completions++;
        end else if(clear) begin
            for(integer j=0;j<3;j=j+1) s[j]=0;
        end else begin
            voted=maj(s[0],s[1],s[2])^int'(sv);
            for(integer j=0;j<3;j=j+1) s[j]=voted;
            if(start) begin
                for(integer j=0;j<3;j=j+1) begin a[j]=int'(operand_a)&OMASK; b[j]=int'(operand_b)&OMASK; end
                pending=1;
            end
        end
        clk=1; #2; cycles++;
        raw_check();
        if (busy !== pending || done !== (expected_done!=0) || valid !== (expected_done!=0) || error!==0 ||
            ready !== !(rst || clear || pending)) $fatal(1,"TMR_POST_CONTROL cycle=%0d",cycles);
        if ((int'(accumulator)&MASK)!=(maj(s[0],s[1],s[2])^int'(sv)))
            $fatal(1,"TMR_READBACK cycle=%0d",cycles);
        if(compare_clean && {pr,pb,pd,pv,pe,pa,px} !== {ready,busy,done,valid,error,accumulator,disagreement})
            $fatal(1,"TMR_PRODUCTION_EQUIVALENCE cycle=%0d",cycles);
        $fwrite(trace,"post,%0d,%0d,%0d,%0d,%0h,%0h,%0h,%0h,%0d\n",cycles,busy,done,valid,
            dut.lane0.acc_state,dut.lane1.acc_state,dut.lane2.acc_state,accumulator,disagreement);
        clk=0; #2;
    endtask
    task automatic reset_all;
        rst=1; clear=0; start=0; cm0=0;cm1=0;cm2=0;sv=0;cv=0;
        tick(); rst=0; compare_clean=1; tick();
    endtask
    // Deliberately truncate task arguments to the selected port widths.
    /* verilator lint_off UNUSEDSIGNAL */
    task automatic launch(input integer x,y);
        start=1; operand_a=OW'(x); operand_b=OW'(y); tick(); start=0;
    endtask
    /* verilator lint_on UNUSEDSIGNAL */
    task automatic expect_acc(input integer value);
        if ((int'(accumulator)&MASK)!=(value&MASK)) $fatal(1,"TMR_LITERAL expected=%0d got=%0d",value,accumulator);
    endtask
    // Between-edge deposits into actual registers, no force held through repair.
    task automatic inject(input integer lane,site,mask);
        integer before_word,after_word;
        compare_clean=0;
        before_word=site==0?s[lane]:(site==1?a[lane]:b[lane]);
        case(lane)
          0: case(site)
            0: dut.lane0.acc_state=dut.lane0.acc_state ^ AW'(mask);
            1: dut.lane0.saved_a=dut.lane0.saved_a ^ OW'(mask);
            2: dut.lane0.saved_b=dut.lane0.saved_b ^ OW'(mask);
          endcase
          1: case(site)
            0: dut.lane1.acc_state=dut.lane1.acc_state ^ AW'(mask);
            1: dut.lane1.saved_a=dut.lane1.saved_a ^ OW'(mask);
            2: dut.lane1.saved_b=dut.lane1.saved_b ^ OW'(mask);
          endcase
          2: case(site)
            0: dut.lane2.acc_state=dut.lane2.acc_state ^ AW'(mask);
            1: dut.lane2.saved_a=dut.lane2.saved_a ^ OW'(mask);
            2: dut.lane2.saved_b=dut.lane2.saved_b ^ OW'(mask);
          endcase
        endcase
        #1;
        case(lane)
          0: after_word=site==0?int'(dut.lane0.acc_state):(site==1?int'(dut.lane0.saved_a)&OMASK:int'(dut.lane0.saved_b)&OMASK);
          1: after_word=site==0?int'(dut.lane1.acc_state):(site==1?int'(dut.lane1.saved_a)&OMASK:int'(dut.lane1.saved_b)&OMASK);
          2: after_word=site==0?int'(dut.lane2.acc_state):(site==1?int'(dut.lane2.saved_a)&OMASK:int'(dut.lane2.saved_b)&OMASK);
          default: after_word=-1;
        endcase
        if ((before_word^after_word)!=mask) $fatal(1,"TMR_STORAGE_ACK");
        if(site==0) s[lane]=s[lane]^mask;
        else if(site==1) a[lane]=a[lane]^mask;
        else b[lane]=b[lane]^mask;
        injections++;
        $fwrite(trace,"inject,%0d,%0d,%0d,%0h,%0h,%0h\n",cycles,lane,site,mask,before_word,after_word);
        raw_check();
    endtask
    /* verilator lint_off UNUSEDSIGNAL */
    task automatic mask_lane(input integer lane,mask);
        compare_clean=0;
        cm0=0;cm1=0;cm2=0;
        case(lane) 0:cm0=AW'(mask); 1:cm1=AW'(mask); 2:cm2=AW'(mask); endcase
    endtask
    /* verilator lint_on UNUSEDSIGNAL */
    initial begin
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"trace path required");
        trace=$fopen(trace_path,"w");
        if(trace==0) $fatal(1,"trace open failed");
        for(integer j=0;j<3;j=j+1) begin s[j]=0;a[j]=0;b[j]=0;end
        reset_all();
        // Directed priorities, signed extremes and wrapping with a clean oracle.
        launch(1,1); clear=1; start=1; operand_a=0; tick(); expect_acc(1);
        tick(); expect_acc(0); clear=0; start=0; tick();
        launch(-1,1); tick(); expect_acc(-1);
        launch(1,1); rst=1; start=1; tick(); expect_acc(0); rst=0; start=0; tick();
        for(integer j=0;j<1100;j=j+1) begin
            launch(1<<(OW-1),1<<(OW-1)); tick();
            if(j==(1<<(AW-2*OW+1))-1) begin
                expect_acc(-(1<<(AW-1)));
                launch(-1,1);tick();expect_acc((1<<(AW-1))-1); // negative wrap
                launch(1,1);tick();expect_acc(-(1<<(AW-1))); // positive wrap
            end
        end
        phase=1;
        for(integer j=0;j<6000;j=j+1) begin
            seed=seed*1664525+1013904223; operand_a=OW'(seed>>8); operand_b=OW'(seed>>16);
            // Separate PRNG advances and high bits avoid low-LCG control locking.
            seed=seed*1664525+1013904223; rst=(seed[31:25]==0);
            seed=seed*1664525+1013904223; clear=(seed[31:28]==0);
            seed=seed*1664525+1013904223; start=seed[31]; tick();
        end
        phase=0;
        // Exhaustive reduced arithmetic starting states, no model-derived vectors.
        if(OW==2) begin
            for(integer st=0;st<16;st++) for(integer x=0;x<4;x++) for(integer y=0;y<4;y++) begin
                reset_all(); launch(1,1); tick();
                for(integer n=1;n<st;n++) begin launch(1,1);tick();end
                if(st==0) begin clear=1;tick();clear=0;end
                launch(x,y);tick();expect_acc(st+signop(x)*signop(y));
            end
        end
        phase=2;
        for(integer lane=0;lane<3;lane++) begin
            for(integer bitno=0;bitno<AW;bitno++) begin
                reset_all(); launch(1,1);tick();
                inject(lane,0,1<<bitno); expect_acc(1); tick();expect_acc(1); // idle repair
                inject(lane,0,1<<bitno); launch(1,1);tick();expect_acc(2); // acceptance repair
                launch(1,1);inject(lane,0,1<<bitno);tick();expect_acc(3); // busy correction
                launch(1,1);mask_lane(lane,1<<bitno);tick();expect_acc(4);
                cm0=0;cm1=0;cm2=0;launch(1,1);tick();expect_acc(5); // no latent corruption
            end
            for(integer site=1;site<=2;site++) for(integer bitno=0;bitno<OW;bitno++) begin
                reset_all();launch(1,1);inject(lane,site,1<<bitno);tick();expect_acc(1);
                tick(); // operand fault persists; raw_check verifies no false repair claim
                launch(1,1);tick();expect_acc(2);
            end
            reset_all();launch(1,1);inject(lane,0,MASK);tick();expect_acc(1); // whole-lane multibit
            // Repeated transient at same candidate site over successive operations.
            for(integer n=0;n<4;n++) begin launch(1,1);mask_lane(lane,MASK);tick();expect_acc(n+2);end
        end
        // Two bad words can be masked if their wrong bits do not overlap.
        reset_all();inject(0,0,1);inject(1,0,2);expect_acc(0);tick();expect_acc(0);
        // No whole-word majority: bitwise result is a fourth word, not a rejection.
        reset_all();inject(0,0,1);inject(1,0,2);inject(2,0,4);expect_acc(0);tick();expect_acc(0);
        // Two overlapping state faults create a wrong majority and poison all lanes.
        reset_all();inject(0,0,1);inject(1,0,1);expect_acc(1);tick();expect_acc(1);
        launch(1,1);tick();expect_acc(2);
        reset_all();launch(1,1);compare_clean=0;cm0=1;cm1=1;tick();expect_acc(0);
        reset_all();launch(1,1);compare_clean=0;cm0=1;cm1=1;cm2=1;tick();expect_acc(0);
        if(disagreement) $fatal(1,"TMR_COMMON_MODE_MUST_BE_UNDETECTED");
        reset_all();launch(1,1);compare_clean=0;cv=1;tick();expect_acc(0);cv=0;tick();expect_acc(0);
        reset_all();compare_clean=0;sv=1;tick();sv=0;#1;expect_acc(1);tick();expect_acc(1);
        // Common saved-input corruption before acceptance: intended 1*1 becomes 0*1.
        reset_all();launch(0,1);tick();expect_acc(0);
        // Common controller upset drops a pending transaction; no completion or error.
        reset_all();launch(1,1);compare_clean=0;
        dut.busy=0; pending=0; #1;
        if(busy!==0) $fatal(1,"TMR_CONTROL_ACK");
        $fwrite(trace,"control_inject,%0d,busy,1,0\n",cycles);
        tick();expect_acc(0);
        if(done || valid || error!=0) $fatal(1,"TMR_CONTROL_LIMIT");
        reset_all();launch(1,1);tick();expect_acc(1);
        // Clean directed idle reset+start and held/back-to-back acceptance.
        phase=0; rst=1; start=1; tick(); expect_acc(0); rst=0; start=0; tick();
        start=1; operand_a=1; operand_b=1;
        tick(); tick(); expect_acc(1); tick(); tick(); expect_acc(2);
        start=0; tick(); expect_acc(2); // ignored busy requests were not queued
        $display("PASS TMR OW=%0d AW=%0d cycles=%0d completions=%0d storage_acks=%0d candidate_acks=%0d voter_acks=%0d control_acks=1",OW,AW,cycles,completions,injections,arithmetic_acks,voter_acks);
        $fclose(trace);$finish;
    end
endmodule
