`timescale 1ns/1ps
// Clean oracle for the actual technology-independent mapped production netlist.
module tmr_gate_tb;
    parameter integer OW=8, AW=24;
    reg clk=0,rst=1,clear=0,start=0;
    reg signed [OW-1:0] operand_a=0,operand_b=0;
    wire ready,busy,done,result_valid,disagreement;
    wire [1:0] error;
    wire signed [AW-1:0] accumulator;
    mac_tmr dut(.*);
    integer acc=0,a=0,b=0,seed=503,expected_done,cycles=0,trace,phase=0;
    bit pending=0;
    string trace_path;
    task automatic tick;
        #2;
        if(ready!==!(rst||clear||pending) || busy!==pending)
            $fatal(1,"gate ready cycle=%0d",cycles);
        $fwrite(trace,"gate_pre,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0h,%0h,%0h,%0d\n",
            cycles,rst,clear,start,busy,done,result_valid,operand_a,operand_b,accumulator,phase);
        expected_done=0;
        if(rst) begin acc=0;pending=0;a=0;b=0;end
        else if(pending) begin
            acc=(acc+a*b)&((1<<AW)-1);pending=0;expected_done=1;
        end else if(clear) acc=0;
        else if(start) begin a=int'(operand_a);b=int'(operand_b);pending=1;end
        clk=1;#2;cycles++;
        if(busy!==pending || done!==(expected_done!=0) || result_valid!==(expected_done!=0) ||
            ready!==!(rst||clear||pending) || error!==0 || disagreement!==0 ||
            (int'(accumulator)&((1<<AW)-1))!=acc)
            $fatal(1,"gate clean oracle cycle=%0d",cycles);
        $fwrite(trace,"gate_post,%0d,%0d,%0d,%0d,%0h,%0d\n",
            cycles,busy,done,result_valid,accumulator,disagreement);
        clk=0;#2;
    endtask
    initial begin
        if(!$value$plusargs("trace=%s",trace_path)) $fatal(1,"gate trace path required");
        trace=$fopen(trace_path,"w");
        if(trace==0) $fatal(1,"gate trace open failed");
        tick(); rst=0;
        operand_a=1;operand_b=1;start=1;tick();start=0;tick(); // seed nonzero
        rst=1;start=1;tick();rst=0;start=0;tick(); // idle reset beats start
        start=1;tick();start=0;tick(); // seed nonzero again
        start=1;tick();rst=1;tick();rst=0;start=0;tick(); // busy reset beats start/commit
        start=1;tick();start=0;tick();
        clear=1;start=1;tick();clear=0;start=0;tick(); // idle clear beats start
        start=1;tick();clear=1;tick(); // busy completion beats clear/start
        clear=0;start=0;tick();tick(); // busy start was not queued
        start=1;tick();tick();tick();tick(); // held start, post-done acceptance
        start=0;tick();tick();
        phase=1;
        for(integer cycle=0;cycle<9000;cycle++) begin
            seed=seed*1664525+1013904223;
            operand_a=OW'(seed>>8);operand_b=OW'(seed>>16);
            seed=seed*1664525+1013904223;rst=(seed[31:25]==0);
            seed=seed*1664525+1013904223;clear=(seed[31:27]==0);
            seed=seed*1664525+1013904223;start=seed[31];
            tick();
        end
        $fclose(trace);
        $display("PASS TMR generic netlist OW=%0d AW=%0d cycles=%0d",OW,AW,cycles);$finish;
    end
endmodule
