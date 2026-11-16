`timescale 1ns/1ps
// M6 observation harness: expectations and classification live outside the RTL.
module pilot_tb;
    reg clk=0, rst=0, clear=0, start=0;
    reg signed [7:0] operand_a=0, operand_b=0;
    wire [3:0] ready,busy,done,valid;
    wire [1:0] error[4];
    wire signed [23:0] acc[4];
    wire sc,hc,hd,hr,td;
    wire [1:0] retry;
    reg [24:0] cm=0;
    reg [2:0] hm=0;
    reg [23:0] commit_mask=0,tm0=0,tm1=0,tm2=0,sv=0,cv=0;
    reg [24:0] forced_sum=0;
    mac_unprotected u(.clk(clk),.rst(rst),.clear(clear),.start(start),
        .operand_a(operand_a),.operand_b(operand_b),.ready(ready[0]),.busy(busy[0]),
        .done(done[0]),.result_valid(valid[0]),.error(error[0]),.accumulator(acc[0]));
    mac_secded s(.clk(clk),.rst(rst),.clear(clear),.start(start),
        .operand_a(operand_a),.operand_b(operand_b),.ready(ready[1]),.busy(busy[1]),
        .done(done[1]),.result_valid(valid[1]),.error(error[1]),.accumulator(acc[1]),.corrected(sc));
    mac_hybrid_injectable h(.clk(clk),.rst(rst),.clear(clear),.start(start),
        .operand_a(operand_a),.operand_b(operand_b),.ready(ready[2]),.busy(busy[2]),
        .done(done[2]),.result_valid(valid[2]),.error(error[2]),.accumulator(acc[2]),
        .corrected(hc),.detected(hd),.retried(hr),.retry_count(retry),
        .candidate_fault_mask(cm),.checker_fault_mask(hm),.commit_fault_mask(commit_mask),
        .stored_codeword(),.candidate_before_fault(),.candidate_after_fault(),
        .prediction_before_fault(),.prediction_after_fault(),.commit_before_fault(),.commit_after_fault());
    mac_tmr_injectable t(.clk(clk),.rst(rst),.clear(clear),.start(start),
        .operand_a(operand_a),.operand_b(operand_b),.ready(ready[3]),.busy(busy[3]),
        .done(done[3]),.result_valid(valid[3]),.error(error[3]),.accumulator(acc[3]),
        .disagreement(td),.candidate_mask0(tm0),.candidate_mask1(tm1),.candidate_mask2(tm2),
        .state_voter_fault_mask(sv),.candidate_voter_fault_mask(cv));
    integer variant,site,mask,lane,duration,a0,b0,a,b;
    bit disable_injection;
    integer trace,ack,cycle=0,phase=-1;
    string trace_path,ack_path;
    integer before_word,after_word;
    function automatic integer raw0;
        case(variant)
          0:return int'(u.accumulator)&32'h00ffffff;
          1:return int'(s.acc_codeword);
          2:return int'(h.acc_codeword);
          3:return int'(t.lane0.acc_state);
        endcase
        return -1;
    endfunction
    function automatic integer alarm;
        case(variant) 0:return 0; 1:return int'(sc); 2:return int'(hc||hd||hr); 3:return int'(td); endcase
        return -1;
    endfunction
    task automatic sample(input string edge_kind);
        $fwrite(trace,"%s,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            edge_kind,cycle,phase,rst,start,busy[variant],done[variant],valid[variant],error[variant],
            acc[variant],alarm(),raw0(),t.lane1.acc_state,t.lane2.acc_state,
            retry,ready[variant],h.arithmetic_ok,clear);
    endtask
    task automatic tick;
        #1; sample("pre"); clk=1; #1; sample("post"); clk=0; #1; cycle++;
    endtask
    task automatic launch(input integer x,y);
        operand_a=8'(x);operand_b=8'(y);start=1;tick();start=0;
    endtask
    task automatic acknowledge(input integer attempt,physical_mask);
        $fwrite(ack,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cycle,attempt,busy[variant],rst,before_word,after_word,physical_mask);
        $fflush(ack);
    endtask
    // All reads below are the actual DUT state, never the planned manifest value.
    task automatic deposit;
        before_word=0;after_word=0;
        case(site)
          1: case(variant)
            0: begin
                before_word=int'(u.accumulator) & 32'h00ffffff;
                if(!disable_injection) u.accumulator=u.accumulator ^ 24'(mask);
                #1; after_word=int'(u.accumulator) & 32'h00ffffff;
            end
            1: begin
                before_word=int'(s.acc_codeword) & 32'h3fffffff;
                if(!disable_injection) s.acc_codeword=s.acc_codeword ^ 30'(mask);
                #1; after_word=int'(s.acc_codeword) & 32'h3fffffff;
            end
            2: begin
                before_word=int'(h.acc_codeword) & 32'h3fffffff;
                if(!disable_injection) h.acc_codeword=h.acc_codeword ^ 30'(mask);
                #1; after_word=int'(h.acc_codeword) & 32'h3fffffff;
            end
            3: begin
              case(lane)
              0: begin
                before_word=int'(t.lane0.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane0.acc_state=t.lane0.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane0.acc_state) & 32'h00ffffff;
              end
              1: begin
                before_word=int'(t.lane1.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane1.acc_state=t.lane1.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane1.acc_state) & 32'h00ffffff;
              end
              2: begin
                before_word=int'(t.lane2.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane2.acc_state=t.lane2.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane2.acc_state) & 32'h00ffffff;
              end
              endcase
            end
          endcase
          2: case(variant)
            0: begin
                before_word=int'(u.saved_a) & 255;
                if(!disable_injection) u.saved_a=u.saved_a ^ 8'(mask);
                #1; after_word=int'(u.saved_a) & 255;
            end
            1: begin
                before_word=int'(s.saved_a) & 255;
                if(!disable_injection) s.saved_a=s.saved_a ^ 8'(mask);
                #1; after_word=int'(s.saved_a) & 255;
            end
            2: begin
                before_word=int'(h.saved_a) & 255;
                if(!disable_injection) h.saved_a=h.saved_a ^ 8'(mask);
                #1; after_word=int'(h.saved_a) & 255;
            end
            3: begin
              case(lane)
              0: begin
                before_word=int'(t.lane0.saved_a) & 255;
                if(!disable_injection) t.lane0.saved_a=t.lane0.saved_a ^ 8'(mask);
                #1; after_word=int'(t.lane0.saved_a) & 255;
              end
              1: begin
                before_word=int'(t.lane1.saved_a) & 255;
                if(!disable_injection) t.lane1.saved_a=t.lane1.saved_a ^ 8'(mask);
                #1; after_word=int'(t.lane1.saved_a) & 255;
              end
              2: begin
                before_word=int'(t.lane2.saved_a) & 255;
                if(!disable_injection) t.lane2.saved_a=t.lane2.saved_a ^ 8'(mask);
                #1; after_word=int'(t.lane2.saved_a) & 255;
              end
              endcase
            end
          endcase
          3: case(variant)
            0: begin
                before_word=int'(u.saved_b) & 255;
                if(!disable_injection) u.saved_b=u.saved_b ^ 8'(mask);
                #1; after_word=int'(u.saved_b) & 255;
            end
            1: begin
                before_word=int'(s.saved_b) & 255;
                if(!disable_injection) s.saved_b=s.saved_b ^ 8'(mask);
                #1; after_word=int'(s.saved_b) & 255;
            end
            2: begin
                before_word=int'(h.saved_b) & 255;
                if(!disable_injection) h.saved_b=h.saved_b ^ 8'(mask);
                #1; after_word=int'(h.saved_b) & 255;
            end
            3: begin
              case(lane)
              0: begin
                before_word=int'(t.lane0.saved_b) & 255;
                if(!disable_injection) t.lane0.saved_b=t.lane0.saved_b ^ 8'(mask);
                #1; after_word=int'(t.lane0.saved_b) & 255;
              end
              1: begin
                before_word=int'(t.lane1.saved_b) & 255;
                if(!disable_injection) t.lane1.saved_b=t.lane1.saved_b ^ 8'(mask);
                #1; after_word=int'(t.lane1.saved_b) & 255;
              end
              2: begin
                before_word=int'(t.lane2.saved_b) & 255;
                if(!disable_injection) t.lane2.saved_b=t.lane2.saved_b ^ 8'(mask);
                #1; after_word=int'(t.lane2.saved_b) & 255;
              end
              endcase
            end
          endcase
          4: case(variant)
            0: begin
                before_word=int'(u.busy) & 1;
                if(!disable_injection) u.busy=u.busy ^ 1'(mask);
                #1; after_word=int'(u.busy) & 1;
            end
            1: begin
                before_word=int'(s.busy) & 1;
                if(!disable_injection) s.busy=s.busy ^ 1'(mask);
                #1; after_word=int'(s.busy) & 1;
            end
            2: begin
                before_word=int'(h.busy) & 1;
                if(!disable_injection) h.busy=h.busy ^ 1'(mask);
                #1; after_word=int'(h.busy) & 1;
            end
            3: begin
                before_word=int'(t.busy) & 1;
                if(!disable_injection) t.busy=t.busy ^ 1'(mask);
                #1; after_word=int'(t.busy) & 1;
            end
          endcase
          5: case(variant)
            0: begin
                before_word=int'(u.accumulator) & 32'h00ffffff;
                if(!disable_injection) u.accumulator=u.accumulator ^ 24'(mask);
                #1; after_word=int'(u.accumulator) & 32'h00ffffff;
            end
            1: begin
                before_word=int'(s.acc_codeword) & 32'h3fffffff;
                if(!disable_injection) s.acc_codeword=s.acc_codeword ^ 30'(mask);
                #1; after_word=int'(s.acc_codeword) & 32'h3fffffff;
            end
            2: begin
                before_word=int'(h.acc_codeword) & 32'h3fffffff;
                if(!disable_injection) h.acc_codeword=h.acc_codeword ^ 30'(mask);
                #1; after_word=int'(h.acc_codeword) & 32'h3fffffff;
            end
            3: begin
              case(lane)
              0: begin
                before_word=int'(t.lane0.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane0.acc_state=t.lane0.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane0.acc_state) & 32'h00ffffff;
              end
              1: begin
                before_word=int'(t.lane1.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane1.acc_state=t.lane1.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane1.acc_state) & 32'h00ffffff;
              end
              2: begin
                before_word=int'(t.lane2.acc_state) & 32'h00ffffff;
                if(!disable_injection) t.lane2.acc_state=t.lane2.acc_state ^ 24'(mask);
                #1; after_word=int'(t.lane2.acc_state) & 32'h00ffffff;
              end
              endcase
            end
          endcase
        endcase
        acknowledge(0,mask);
    endtask
    task automatic combinational_inject(input integer attempt);
        case(site)
          6: case(variant)
            0: begin
                before_word=int'(u.exact_sum)&32'h01ffffff; forced_sum=25'(before_word^mask);
                if(!disable_injection) force u.exact_sum=forced_sum;
                #1;after_word=int'(u.exact_sum)&32'h01ffffff;
            end
            1: begin
                before_word=int'(s.exact_sum)&32'h01ffffff; forced_sum=25'(before_word^mask);
                if(!disable_injection) force s.exact_sum=forced_sum;
                #1;after_word=int'(s.exact_sum)&32'h01ffffff;
            end
            2: begin
                before_word=int'(h.exact_sum)&32'h01ffffff;
                if(!disable_injection) cm=25'(mask);
                #1;after_word=int'(h.checked_candidate)&32'h01ffffff;
            end
            3: begin
                case(lane)
                  0: begin before_word=int'(t.lane0.clean_candidate);if(!disable_injection) tm0=24'(mask);#1;after_word=int'(t.candidate0);end
                  1: begin before_word=int'(t.lane1.clean_candidate);if(!disable_injection) tm1=24'(mask);#1;after_word=int'(t.candidate1);end
                  2: begin before_word=int'(t.lane2.clean_candidate);if(!disable_injection) tm2=24'(mask);#1;after_word=int'(t.candidate2);end
                endcase
            end
          endcase
          7: begin before_word=int'(h.predicted_residue);if(!disable_injection) hm=3'(mask);#1;after_word=int'(h.checked_prediction);end
          8: begin before_word=int'(h.checked_candidate)&32'h00ffffff;if(!disable_injection) commit_mask=24'(mask);#1;after_word=int'(h.commit_data);end
          9: begin before_word=int'(t.candidate_vote_clean);if(!disable_injection) cv=24'(mask);#1;after_word=int'(t.candidate_vote);end
        endcase
        acknowledge(attempt,mask);
    endtask
    task automatic release_masks;
        release u.exact_sum;release s.exact_sum;
        cm=0;hm=0;commit_mask=0;tm0=0;tm1=0;tm2=0;sv=0;cv=0;#1;
    endtask
    initial begin
        if(!$value$plusargs("variant=%d",variant) || !$value$plusargs("site=%d",site) ||
           !$value$plusargs("mask=%d",mask) || !$value$plusargs("lane=%d",lane) ||
           !$value$plusargs("duration=%d",duration) || !$value$plusargs("a0=%d",a0) ||
           !$value$plusargs("b0=%d",b0) || !$value$plusargs("a=%d",a) || !$value$plusargs("b=%d",b) ||
           !$value$plusargs("trace=%s",trace_path) || !$value$plusargs("ack=%s",ack_path)) $fatal(1,"PILOT_ARGUMENTS");
        disable_injection=$test$plusargs("disable_injection");
        trace=$fopen(trace_path,"w");ack=$fopen(ack_path,"w");
        if(trace==0 || ack==0) $fatal(1,"PILOT_OUTPUT_OPEN");
        $fwrite(trace,"edge,cycle,phase,rst,start,busy,done,valid,error,acc,alarm,raw0,raw1,raw2,retry,ready,arithmetic_ok,clear\n");
        $fwrite(ack,"cycle,attempt,busy,rst,before,after,mask\n");
        rst=1;tick();rst=0;tick();
        phase=0;launch(a0,b0);tick();tick();
        phase=1;launch(a,b);
        if(site>=1 && site<=5) deposit();
        for(integer attempt=0;attempt<6;attempt++) begin
            if(site>=6 && attempt<duration && busy[variant]) combinational_inject(attempt);
            tick();release_masks();
            if(done[variant]) break;
        end
        tick();tick();
        phase=2;launch(3,-2);
        for(integer attempt=0;attempt<6;attempt++) begin tick();if(done[variant]) break;end
        tick();tick();
        phase=3;rst=1;tick();rst=0;tick();launch(1,1);tick();tick();
        $fclose(trace);$fclose(ack);$finish;
    end
endmodule
