# MAC Sentry architecture and project map

MAC Sentry develops and compares protection mechanisms for a signed integer
multiply–accumulate unit. Defaults are 8-bit operands and a wrapping signed
24-bit accumulator. The reference operation is `acc <- acc + a*b`, reduced to
24-bit two's-complement representation. Reset is synchronous, idle clear wins
over start, and busy requests are not queued.

## Implemented variants

| Variant | Protection | Scope and limitations |
| --- | --- | --- |
| Unprotected | Ordinary MAC | Arithmetic/protocol comparison baseline |
| SECDED | 24 accumulator data bits encoded in a 30-bit shortened extended Hamming word | Corrects one stored-codeword-bit error; detects two; higher weights can miscorrect; arithmetic/shared logic remains exposed |
| Hybrid | SECDED plus modulo-7 arithmetic checking and bounded retry | Checks the full signed 25-bit candidate before truncation; two retries permit at most three attempts; residue collisions, shared dependencies and post-check faults remain |
| Datapath TMR | Three operand/arithmetic/accumulator lanes with common majority voters and accumulator feedback repair | Covered single-lane faults can be masked; shared voters/control/inputs/clock and wrong majorities remain exposed; operand registers are not scrubbed |

The hybrid rejects an uncorrectable source with invalid result/error 1. Exhausted
arithmetic retries terminate invalid/error 2. Retry reuses the same hardware and
saved operands, so it is not a guarantee of correction for persistent faults.
The published tests retain known escapes rather than counting them as protection
successes. The architecture has no independently protected atomic commit or
persistent redundant accumulator residue.

The Tiny Tapeout production wrapper uses the hybrid core, a byte-oriented
command/result interface and retained readback status. Production pins do not
inject faults. FPGA experiment wrappers add VIO/ILA instrumentation and a
clocked fault sequencer; those experimental hooks do not form the ASIC interface.
The TMR design is a comparison core, not the current ASIC submission candidate.

## Where to work

- `rtl/`: synthesizable cores, protection helpers, and injectable comparisons.
- `model/`: Python arithmetic, SECDED and MAC reference models.
- `tests/`: Python controls, C++/SystemVerilog testbenches and mapped-netlist tests.
- `fpga/zedboard/`: FPGA wrappers, sequencer and board clock constraints.
- `asic/`: Tiny Tapeout wrapper, metadata and physical-flow constraints.
- `scripts/` and `tools/`: public experiment, capture, verification and setup tools.
- `spec/`: interface, fault and recovery contracts plus detailed board procedures.
- `results/published/`: portable measured reports, raw pilot evidence, and one
  reference ASIC GDS with its matching powered netlist and LEF.
- `build/`: ignored generated runs, tools, caches and large local deliverables.

Start with the [main guide](../README.md), then the relevant contracts:
[baseline/fault interface](../spec/mac_interface_and_fault_model.md),
[SECDED](../spec/secded_accumulator.md), [hybrid](../spec/hybrid_mac.md),
[TMR](../spec/tmr_mac.md), [Tiny Tapeout pins](../asic/README.md), and
[board backlog](../spec/board_validation_backlog.md).

## Demonstrated scope and next work

The project has reference models, RTL/injection tests, generic synthesis checks,
a protected ASIC interface and a routed SKY130 implementation. The selected ASIC
run passed its implemented physical checks, 15 shuttle prechecks and zero-delay
functional GLS. The bounded RTL pilot preserves all 429 trials. Four comparable
FPGA core OOC measurements were produced; every row still fails timing closure.
The unprotected MAC and selected SECDED cases have historical ZedBoard evidence.

Remaining work includes timing-clean FPGA builds and the missing board cases,
SDF-annotated simulation and full ASIC sign-off, final submission/packaging review,
additional justified comparative campaigns, and prior-art/faculty review. No
radiation cross section, silicon qualification, complete fault coverage or novelty
claim follows from digital injection and local physical-flow checks. See the
[published results and their limits](results.md) before citing any number.
