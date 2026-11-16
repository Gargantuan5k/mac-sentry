# Tiny Tapeout protected MAC interface

`asic/rtl/tt_um_mac_sentry.sv` instantiates the production `mac_hybrid` with signed
8-bit operands, a wrapping signed 24-bit accumulator and MAX_RETRIES=2. The core
arithmetic is unchanged. This is the accepted M1 RTL interface for SKY130/TTSKY26d,
not shuttle acceptance or physical sign-off. A separate submission scaffold and
exporter now provide the official repository layout; see
[submission packaging](../docs/tapeout_package.md). Run from the repository root:

```sh
make test-asic-interface JOBS=2
```

Every invocation retains a new `build/asic_interface/run_*/` directory containing
source snapshots/SHA-256, exact command arrays, tool versions, compilation,
simulation, negative-control and generic synthesis logs plus netlist/result JSON.
Failures remain in their own directories. The target exits nonzero on a failed
check. No container, network, package installation or publishing is needed.

## Official reference and integration boundary

The local reference is `build/asic-tools/vendor/ttsky-verilog-template`, resolved commit
`a42e6662fab316e93b4e26399e21d41664a460b7`. Its `src/project.v` defines the port
shape below; `.github/workflows/gds.yaml` selects `tt-gds-action@ttsky26d` and
sky130A. The locally pinned action is
`395eedb3eeec3c2f4961c3b04ff2cf87f5525636`; support tools are
`9d13ff3e3e6202090740110438c6a10c1d62ca0f`. These identities and archive hashes
are recorded in `build/asic-tools/vendor/sources.json`; they describe the supplied
reference, not a fresh check of upstream shuttle policy.

The source uses the exact official digital ports and active-high uio output
enables; the top name is `tt_um_mac_sentry`. No analog/power ports or extra debug
ports are added. M1 changed no template flow configuration. The current CR2 flow
uses the previously recovered 50 ns target and 2x2 tile, with stronger checks and
repair settings documented in [validation](validation.md). Current hardening,
GLS and TT prechecks require host evidence; metadata alone is not completion. See
[prepared environment](../docs/asic_setup.md) for the distinct hardening and
precheck PDK pins and immutable container-launch requirement.

Production source list (SystemVerilog, include directory `rtl/`):

```text
rtl/secded_encoder.sv
rtl/secded_decoder.sv
rtl/signed_residue7.sv
rtl/mac_residue7_check.sv
rtl/mac_hybrid.sv
asic/rtl/tt_um_mac_sentry.sv
```

Also provide `rtl/secded_functions.vh` and `rtl/mac_hybrid_datapath.vh` as include
files. No injectable core, testbench, simulation force, FPGA debug IP or alternate
unprotected implementation is part of this synthesis list.

## Pins and electrical timing contract

| Port / bits | Direction | Meaning |
| --- | --- | --- |
| `ui_in[7:0]` | in | Byte data, used by LOAD_A/B only; two's complement |
| `uio_in[3:0]` | in | Command opcode |
| `uio_in[4]` | in | Command strobe, sampled one-shot |
| `uio_in[7:5]` | in | Reserved; must all be zero on a request |
| `uo_out[7:0]` | out | Registered response byte; held until next command |
| `uio_out[7:0]` | out path | Always zero |
| `uio_oe[7:0]` | enable path | Always zero: all eight bidirectional pads are inputs |
| `clk` | in | Only clock, host-synchronous, rising edge sampling |
| `rst_n` | in | Active-low synchronous state reset |
| `ena` | in | Active-high selection; low synchronously aborts and clears state |

No asynchronous bus synchronizer or SPI clock recovery is provided. A host must
drive data/opcode/strobe before the rising edge and satisfy setup/hold; change
inputs on falling edges for a conservative host implementation. Outputs become
valid after the rising edge and normal propagation delay. Clock frequency and
I/O delays require physical timing verification in M2.

Drive rst_n=0 for at least one rising edge before use (also works with ena=0).
Core and wrapper reset together; no completion is generated for aborted work.
While rst_n=0 **or** ena=0, uo_out is combinationally forced to zero and uio stays
input-only. State clearing still requires a clock edge: a low glitch between
edges only masks output and is not an abort. Do not gate `clk` in this wrapper.
After enabling/releasing reset, sample strobe=0 on one enabled rising edge to
arm commands. A high strobe carried across reset/deselection cannot launch.

For each command: sample strobe=0 at one rising edge, then present opcode/data
and sample strobe=1 at the next edge; read the response after that edge. Holding
strobe high, even while changing opcode/data, executes only once. Every accepted
or rejected request consumes the arm. Minimum command spacing is two cycles.
Inputs while disabled are discarded; no queue or replay exists.

## Commands and response bytes

| Opcode | Name | Accepted behavior / response |
| ---: | --- | --- |
| 0 | STATUS | Return status byte below; no side effects |
| 1 | LOAD_A | Latch ui byte and mark A loaded; return 00 |
| 2 | LOAD_B | Latch ui byte and mark B loaded; return 00 |
| 3 | START | Require both loaded; capture MAC into core; return 00 |
| 4 | CLEAR | Clear accumulator, snapshot, loaded flags and all status; return 00 |
| 5 | RESULT_LO | Return snapshot bits 7:0 |
| 6 | RESULT_MID | Return snapshot bits 15:8 |
| 7 | RESULT_HI | Return snapshot bits 23:16 |
| 8 | DETAIL | Return retry/load detail below |
| 9–15 | reserved | Reject; return E1 |

Any nonzero reserved control bit rejects **any** command with E1. Legal LOAD_A,
LOAD_B, START and CLEAR while busy reject with E2, including the edge that
captures completion into wrapper status. Idle START missing either operand
rejects with E3. Priority: reset/disabled → illegal encoding → busy write →
missing operand → accepted command. All rejections set sticky protocol_error and are not queued. They do not
assert core start/clear or themselves change operands/snapshot; in-flight work
and idle scrubbing continue normally. Reads are always
available when enabled, including while busy. The E1/E2/E3 codes are command
responses, **not** core errors. Read data can equal these bytes: interpret in
context of the opcode just sent.

LOAD_A/B may occur in either order; repeated loads replace that operand. START
consumes both loaded flags; each MAC needs fresh loads. CLEAR invalidates both.
START clears terminal/retry/correction/detection history but preserves the prior
result snapshot and sticky protocol_error. Only CLEAR/reset/disable clears
protocol_error. Reads never acknowledge or erase status.

STATUS bits:

| Bit | Meaning |
| ---: | --- |
| 0 | busy: transaction accepted, terminal core pulse not yet captured by wrapper |
| 1 | completed: sticky terminal completion (success **or** failure) |
| 2 | valid: completed successful result |
| 4:3 | core error: 0 success, 1 SECDED uncorrectable, 2 arithmetic retries exhausted; 3 reserved |
| 5 | corrected: at least one observed SECDED correction since START/CLEAR/reset |
| 6 | detected: at least one arithmetic mismatch in this transaction |
| 7 | protocol_error: at least one rejected host request since CLEAR/reset |

DETAIL bits 1:0 are the number of retries granted (0..2); bit2 is sticky
`retried`; bit3 is A loaded; bit4 is B loaded; bits7:5 are zero. Events/count are
captured one edge after the corresponding core pulse, including intermediate
retry edges. Corrected also observes idle scrubs; it is diagnostic, not a claim
that every physical fault was repaired. START/CLEAR override prior correction
history on their edge. Final transaction status persists until the next accepted
START/CLEAR/reset; operand loads do not clear it.

Correction timing follows the same registered pulse rule: if an idle repair
occurs on edge K, the wrapper observes its pulse at K+1. START/CLEAR at K+1
overrides that old pulse. A START on K itself repairs the source while accepting
operands; its new correction pulse is observed at K+1 during the transaction.
CLEAR on K instead discards the damaged state and emits no repair pulse.

## Completion and coherent readback

If START is accepted at edge N, a clean core commits at N+1. The wrapper captures
its result and terminal status at N+2. With two rejected attempts, core termination
is N+3 and wrapper capture N+4. Thus normal wrapper busy lasts 2..4 periods after
START; this is not a queue and does not change the core's 1..3-attempt contract.
Reset/disable can abort at any edge without completion.

A STATUS command on the wrapper capture edge returns **pre-edge** busy/status;
the following STATUS sees completed. All reads use pre-edge registers. Poll
until busy=0 and completed=1, inspect valid/error, then read low/mid/high and
assemble `lo | mid<<8 | hi<<16`; subtract 2^24 if bit23 is set. Do not launch a
new transaction or CLEAR/reset between byte reads. With this host sequencing,
all bytes belong to one stable result. Reads during busy return the prior
snapshot; a sequence straddling completion is not an atomic snapshot operation.

On a failed operation the wrapper keeps the last successful snapshot, but sets
valid=0 and completed=1. This value is historical, not the damaged core's live
diagnostic decode and not a valid result of the failed MAC. CLEAR/reset produces
zero with completed=valid=0. Terminal failed state can be recovered with CLEAR
and fresh operand loads. Retry exhaustion also preserves the logical accumulator.

Example, starting from reset and an enabled low-strobe arming edge:

```text
LOAD_A 03 -> 00; LOAD_B FC -> 00; START -> 00
poll STATUS until bit0=0 and bit1=1: clean expected 06
DETAIL -> 00
RESULT_LO -> F4; RESULT_MID -> FF; RESULT_HI -> FF  (-12)
LOAD_A 02; LOAD_B 05; START; poll -> 06; result -> FE FF FF (-2)
CLEAR -> 00; STATUS -> 00; DETAIL -> 00; result -> 00 00 00
```

Every semicolon implies a new low/high strobe sequence; ui is ignored for reads,
START and CLEAR. A legal command always produces its response on its request
edge: no response-ready handshake is necessary on this synchronous interface.

## Verification and limits

The Verilator regression is two-state RTL simulation.
`tests/asic_interface_tb.sv` transfers all operands/results through the pins and
uses an independent integer multiply/add/wrap oracle. It checks signed extremes,
both 24-bit wrap directions via 513 actual MAC transactions, malformed commands,
missing operands, held strobes, busy writes at completion and during active retries, no queue, consumption
of operands, reset/disable/rearming, and persistent terminal readback. Fault
checks force the **production instance** candidate in simulation and XOR its
actual raw storage between edges; eligibility, changed values and preserved or
repaired codewords are asserted before checking host status. Transient retry,
three-attempt exhaustion, SECDED single repair and double-error failure (including changed diagnostic data
that must not replace the retained snapshot), recovery,
and reset in retry are directed mechanism tests, not random fault coverage.
The regression also checks nonzero output masking/restoration between clock
edges, all four malformed START encodings 23/43/83/0B with both operands loaded,
sticky protocol_error through a legal START, all three prior snapshot bytes on
a clean capture edge, and twenty pin reads across replayed retry transactions.
For persistent candidate XOR1 over -12 + 1*1, reachable command edges N+2..N+5
return STATUS 01/41/41/52 and DETAIL 00/05/06/06 respectively. Each result byte
continues to read F4/FF/FF; raw state remains unchanged through exhaustion.
A clean successor verifies the retained logical accumulator.
Nine separate recovery cases start with nonzero snapshot1 and terminal
exhaustion52/06, double-error0A/00 or repair26/00; each applies CLEAR, rst_n
reset or clocked ena disable, then reads STATUS00, DETAIL00 and all three zero
result bytes **before** another START. Raw storage must also be zero; a clean
successor then verifies recovery. Six idle-injection cases acknowledge raw XOR4,
verify repair and sticky STATUS26 with unchanged DETAIL18 (both operands loaded)
and result1, and check START/CLEAR after history is observed, on the delayed
correction-pulse edge, and on the raw repair edge itself. A START on the repair
edge yields result7 and STATUS26; the other START cases yield result7/STATUS06.
Two harness controls require failure for a wrong result byte and a missing
candidate injection. Thirteen isolated wrapper mutations must fail for named
assertions: omitted output masking, bypassed launch legality, aliased START,
busy-read rejection, protocol_error cleared by START, live result readback, and
premature retry detail; correction observation restricted to pending operations;
and five separate omissions of CLEAR's error, count, corrected, detected or
retried reset assignment. Mutant sources, hashes, compiler logs and expected/actual
failure diagnostics are retained alongside the normal run. Production-only strict lint and generic synthesis check the
exact port shape, zero pad drivers and retained protected-core instance.

The host interface, operand registers, snapshot, status and control are not ECC
protected. The underlying conventional hybrid retains shared source/operand,
checker/control/encoder dependencies and the documented modulo collisions,
correlated faults and post-check commit escapes. Existing core limitation tests
remain unchanged. In particular, a double storage upset after core commit but
before wrapper capture can put invalid diagnostic decode into the snapshot
while valid=1: the core exposes no uncorrectable readback qualifier to the
wrapper. This one-cycle commit-to-capture window is an explicit unprotected
boundary, not covered by the retained-failure-snapshot guarantee. No fabricated injection capability is exposed to software;
on-silicon deliberate-fault testing needs a separately reviewed mechanism.
There is no radiation-tolerance claim, routed PPA, GLS, physical timing, shuttle
precheck or board/silicon result in M1. Those are pending M2/external gates.

## CR2 accepted scoped physical-flow result

Run `make test-asic-flow JOBS=2` on the prepared supervisor host. The separate
[validation record](validation.md) pins the 50 ns clock, 2x2 tile, host timing,
all corners and electrical checks, flow/PDK versions and evidence paths.
Attempt 1 host routing remains FAIL on four slew corners. Attempt 2 host
run_c5xb3gza passed: worst setup +12.03 ns and hold +0.080 ns at max_ss; zero
setup/hold/slew/cap/fanout violations at all nine corners; zero DRC/LVS/XOR/antenna
counts; 15/15 prechecks; zero-delay pin-only GLS 777 transactions, 2 aborts,
15,642 samples, with both negative controls failing as intended. All run files
are hashed in the current handoff. CR2 is accepted in the supplied runner state;
SDF simulation, full sign-off, submission, board/silicon and prior-art are NOT RUN.
