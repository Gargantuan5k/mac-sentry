// Simulation stand-ins only. NEVER add this file to Vivado design sources.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
module vio_secded (
    input wire clk,
    input wire probe_in0, probe_in1,
    input wire [23:0] probe_in2,
    input wire [1:0] probe_in3,
    output reg probe_out0, probe_out1, probe_out2,
    output reg [7:0] probe_out3, probe_out4,
    output reg probe_out5,
    output reg [29:0] probe_out6
);
endmodule
module ila_secded (
    input wire clk, probe0, probe1, probe2,
    input wire [7:0] probe3, probe4,
    input wire probe5, probe6, probe7, probe8,
    input wire [1:0] probe9,
    input wire [23:0] probe10,
    input wire probe11, probe12,
    input wire [29:0] probe13,
    input wire probe14,
    input wire [29:0] probe15
);
endmodule
/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
