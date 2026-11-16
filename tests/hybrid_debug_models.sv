// Simulation only. Not in the Vivado source list.
`ifdef SYNTHESIS
SIMULATION_STAND_INS_MUST_NOT_BE_SYNTHESIZED invalid_build();
`endif
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
module vio_hybrid (
    input wire clk,
    input wire probe_in0,
    input wire probe_in1,
    input wire [23:0] probe_in2,
    input wire [1:0] probe_in3,
    input wire [1:0] probe_in4,
    output reg probe_out0,
    output reg probe_out1,
    output reg probe_out2,
    output reg [7:0] probe_out3,
    output reg [7:0] probe_out4,
    output reg [2:0] probe_out5,
    output reg [24:0] probe_out6,
    output reg [2:0] probe_out7,
    output reg [23:0] probe_out8,
    output reg [29:0] probe_out9,
    output reg probe_out10
);
endmodule
module ila_hybrid (
    input wire clk,
    input wire probe0,
    input wire probe1,
    input wire probe2,
    input wire [7:0] probe3,
    input wire [7:0] probe4,
    input wire [2:0] probe5,
    input wire [24:0] probe6,
    input wire [2:0] probe7,
    input wire [23:0] probe8,
    input wire [29:0] probe9,
    input wire probe10,
    input wire probe11,
    input wire probe12,
    input wire probe13,
    input wire probe14,
    input wire probe15,
    input wire probe16,
    input wire [1:0] probe17,
    input wire [23:0] probe18,
    input wire [29:0] probe19,
    input wire probe20,
    input wire probe21,
    input wire probe22,
    input wire [1:0] probe23,
    input wire [3:0] probe24,
    input wire [1:0] probe25,
    input wire [7:0] probe26,
    input wire [7:0] probe27,
    input wire [2:0] probe28,
    input wire [24:0] probe29,
    input wire [2:0] probe30,
    input wire [23:0] probe31,
    input wire [29:0] probe32,
    input wire [24:0] probe33,
    input wire [2:0] probe34,
    input wire [23:0] probe35,
    input wire [24:0] probe36,
    input wire [24:0] probe37,
    input wire [2:0] probe38,
    input wire [2:0] probe39,
    input wire [23:0] probe40,
    input wire [23:0] probe41,
    input wire probe42,
    input wire probe43
);
endmodule
/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
