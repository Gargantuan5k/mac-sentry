# SECDED ZedBoard test project

Project: `../mac_sentry_secded_fpga`, part `xc7z020clg484-1`.
This is an instrumented accumulator-storage experiment. The production SECDED
core has no hardware injection interface. The test variant and production core
share `mac_secded_datapath.vh`; production ties its injection controls to zero.

## Design sources

Reference these repository files without copying them into the Vivado project:

```text
rtl/secded_encoder.sv
rtl/secded_decoder.sv
rtl/secded_functions.vh
rtl/mac_secded_datapath.vh
rtl/mac_secded_injectable.sv
fpga/zedboard/zedboard_secded_top.sv
```

`mac_secded.sv` may remain in the project as an unused production variant. Set
`zedboard_secded_top` as top. Classify `.sv` as SystemVerilog and `.vh` as Verilog
Header. The two headers are included inside modules; do not mark them as global
includes. Add `rtl/` to the source include directories. For the sibling layout:

```tcl
set mac_repo [file normalize [file join [get_property DIRECTORY [current_project]] .. mac_sentry]]
set_property include_dirs [list [file join $mac_repo rtl]] [get_filesets sources_1]
```

Add `fpga/zedboard/zedboard_100mhz.xdc` as a constraint source. It defines Y9,
LVCMOS33, and a 10 ns `sys_clk`. Do not duplicate this clock definition in another
XDC. The VIO, ILA, MAC and request edge detectors all use `clk_100mhz`.
Open Elaborated Design to check hierarchy, then synthesize and implement. Review
debug hub clock connection, DRC, routed setup/hold/pulse-width slack, and timing
coverage before generating/using the bitstream. Record unresolved warnings.

Never add `tests/zedboard_debug_models.sv` to the Vivado design; those modules
stand in for the vendor debug IP only in local behavioral tests.

## Debug IP configuration

Create VIO component `vio_secded`: 4 inputs and 7 outputs.

| VIO output | Signal | Width | Initial value |
| --- | --- | ---: | --- |
| 0 | rst | 1 | 1 |
| 1 | clear | 1 | 0 |
| 2 | start_request | 1 | 0 |
| 3 | operand_a | 8 | 0 |
| 4 | operand_b | 8 | 0 |
| 5 | inject_request | 1 | 0 |
| 6 | inject_mask | 30 | 0 |

VIO inputs 0–3: ready (1), busy (1), accumulator (24), error (2).

Create ILA component `ila_secded`: Native, 16 probes, depth 1024, input pipeline
0, one comparator per probe, data-and-trigger probes. Disable Capture Control,
Advanced Trigger, Trigger In and Trigger Out.

| ILA probe | Signal | Width |
| --- | --- | ---: |
| 0 | rst | 1 |
| 1 | clear | 1 |
| 2 | start_pulse | 1 |
| 3 | operand_a | 8 |
| 4 | operand_b | 8 |
| 5 | ready | 1 |
| 6 | busy | 1 |
| 7 | done | 1 |
| 8 | result_valid | 1 |
| 9 | error | 2 |
| 10 | accumulator | 24 |
| 11 | corrected | 1 |
| 12 | inject_pulse | 1 |
| 13 | inject_mask | 30 |
| 14 | inject_fired | 1 |
| 15 | stored_codeword | 30 |

## Hardware injection semantics

The wrapper converts rising levels of start_request and inject_request into
one-cycle requests. Return each request to zero before using it again. Hold both
at zero during reset and reset release. Set mask/operands in a separate VIO update
before raising the corresponding request.

A nonzero injection request is accepted only at an idle edge with reset/clear
low. It writes `stored_codeword XOR inject_mask`, pulses `inject_fired`, and
suppresses correction and start acceptance for that edge. Injection takes
priority over a simultaneous start. Ready is low during an accepted injection.
The discarded start must be requested again. Zero masks do nothing. Requests
during busy/reset/clear do not fire and are not queued.

The next ordinary idle edge repairs a correctable upset and asserts `corrected`.
An uncorrectable stored word remains damaged until clear/reset or an explicit
further alteration. A subsequent MAC request completes with done=1, valid=0 and
error=1, preserving the damaged codeword. Idle detection alone does not pulse
error. The VIO display may miss any one-cycle pulse; use ILA.

This setup does not inject during an in-flight operation. Between-acceptance-
and-completion injections remain covered by the portable RTL simulation harness.
Do not describe this board setup as covering those timing cases or all fault classes.

## First captures after implementation

Use full consecutive capture, depth 1024 and trigger position 512. ILA samples
pre-edge values: a register change caused by one edge appears at the next sample.

1. Reset, release reset, and capture normal MAC operations. For example, 34×55
   gives 1870; a subsequent 15×10 gives 2020. Use signed decimal operands.
2. With a known accumulator and ready=1, set injection mask to hexadecimal `4`
   (data bit at codeword index 2). Arm on inject_pulse=1, then raise the request.
   Observe the raw word XOR by 4, inject_fired, then storage repair and corrected.
   Decoded accumulator readback can remain correct throughout.
3. Repeat from a clean known state using hexadecimal `20000000` to flip overall
   parity. This should also repair without changing the arithmetic value.
4. From a clean state, use hexadecimal `14` (codeword indices 2 and 4, both data
   positions). Capture the injection and persistent damaged storage. Lower the
   injection request; arm a second capture on start_pulse=1 and request a MAC.
   Expect done=1, result_valid=0, error=1, with the damaged word preserved.
5. Clear while idle; verify encoded zero, then run a successful MAC again.

Export both raw `.ila` and `.csv` captures with meaningful names. The existing
archive analyzer uses the unprotected model and cannot certify these injection
traces. A protected capture analyzer is still required. Record instrumented
resource/timing results separately from production-core cost comparisons.

## Local validation

`make test-secded-board` exercises the actual board wrapper with behavioral VIO
and ILA stand-ins. Initial run passed all 30 single-bit and 435 double-bit storage
injections at accumulator 1870, correction/writeback, failed MAC preservation,
clear recovery, one-shot request behavior, zero masks, concurrent start/injection,
busy rejection, and reset/clear priorities. This is simulation evidence only.
Raw outputs are in `build/secded_board/`.
