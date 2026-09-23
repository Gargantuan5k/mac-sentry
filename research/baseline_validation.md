# Initial baseline validation — 2026-09-23

Reproduce with `make all` from the repository root. The default seed is 20260923.
Tool versions and source/artifact SHA-256 values are recorded under each build
directory in `provenance.json`; no Git commit is available in this workspace.

| Check | Observed result |
| --- | --- |
| Python arithmetic/protocol unit tests | 6 passed |
| Signed-wrap equation enumeration | 140,288 accumulator/operand/modulus cases passed |
| 8-bit operands / 24-bit accumulator RTL | 155,320 cycles matched reference |
| 4-bit operands / 8-bit accumulator RTL | 22,712 cycles matched reference |
| Verilator `--Wall` lint | Passed; only intentionally discarded wrap bit has a local unused-signal annotation |
| Yosys generic synthesis and `check -assert` | Passed; zero reported structural problems |

Both RTL regressions include all operand pairs, signed extrema, accumulated
positive/negative overflow, deterministic dot products, randomized idle/clear/
reset/start controls, input changes while busy, held start, and reset cancellation.
The exhaustive operand sweep visits all operand pairs, not all 24-bit accumulator
states. The exhaustive residue tests validate an equation, not checker hardware.

The default generic Yosys netlist contains 886 primitive cells: 42 flip-flop
cells and 844 combinational cells. No latches or memories are present. These are
technology-independent synthesis counts, not standard-cell area, FPGA utilization,
timing, power, routed feasibility, or a tapeout fit estimate. The arithmetic is
currently one combinational multiplier/add path between capture and commit.

Raw outputs live in `build/w8_a24/` and `build/w4_a8/`; these are disposable and
ignored by Git. Re-running a configuration overwrites its outputs, so archive a
run directory before conducting a later comparative campaign. The provenance
file inventories present artifacts; it does not prove every artifact was created
in a single invocation. Run `make all` to regenerate the complete default set.

No protected variant, fault injection, formal proof, target physical implementation,
hardware board demonstration, or research novelty assessment is part of this
validation. Those remain explicit subsequent milestones.
