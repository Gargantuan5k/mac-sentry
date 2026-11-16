# Datapath TMR comparison contract

This is a separate comparison core, not the Tiny Tapeout submission candidate.
It implements datapath TMR with shared control and voters. Functional, synthesized
netlist and bounded campaign evidence is summarized in the
[project overview](../docs/project_overview.md) and
[published results](../docs/results.md). No universal correction, physical
independence, radiation tolerance or novelty claim is made. FPGA timing closure,
physical board testing and final research review remain open.

## Arithmetic and transaction boundary

`mac_tmr` and `TmrMacModel` default to signed 8-bit inputs and a wrapping 24-bit
accumulator; OW >= 2 and AW >= 2*OW. The exact signed 2*OW product is extended
before addition and the sum is reduced modulo 2^AW. Tests cover 8/24, 4/8, 2/4;
the implementation is not validated at other widths. Synchronous reset aborts
and clears all lane registers and common status. Rising-edge priority is reset,
busy completion, idle clear, idle start, idle scrub. Idle clear suppresses start;
busy clear/start are ignored with no queue. Inputs are captured at acceptance;
the next rising edge commits, with one-cycle done/result_valid and error=0.
Ready is !rst && !clear && !busy. A held start may launch again on a later idle
edge. Clear leaves saved operands unchanged. There is no retry or failure code.

Without faults the existing baseline transaction/readback semantics are preserved.
The additional `disagreement` output is combinational: unequal state words, or
unequal candidate words while busy. It is not latched, does not reject work, and
cannot certify that the majority is correct. After repair/commit it normally
falls; observe it before the sampling edge. `result_valid` denotes a completed
vote, not a fault-proof answer. `error` remains zero even on wrong-majority cases.

## What is replicated and how repair works

Each of three `mac_tmr_lane` instances contains its own saved a and b registers,
signed multiplier, wrapping adder, and AW-bit accumulator register. The operands
share external input wires, clock and capture controls but have distinct stored
copies. Each lane calculates from its own raw accumulator and saved operands.

Two common AW-bit Boolean majority functions are used: one for stored state,
one for candidates. Each output bit is (x&y)|(x&z)|(y&z). The state voter drives
readback; the shared busy mux selects candidate vote for commit or state vote
for idle feedback. Every non-reset/non-clear edge writes the selected feedback
to all three accumulator registers, including an idle start edge. This repairs
an isolated state upset on the next edge, while readback can already mask it.
A state upset between acceptance and completion instead changes one candidate;
the other two candidates mask it and the commit overwrites all three states.
A candidate transient in one lane is similarly masked at the commit edge.

Saved operand upsets are masked by candidate voting but are **not scrubbed**:
they remain in that lane until another accepted start or reset. Accumulator
repair does not claim operand repair. A repeated candidate transient in one lane
can remain masked across operations; a permanent physical fault is not modeled.
An upset after the feedback write in one accumulator is handled at the next
scrub/commit; a shared corrupted feedback value poisons every accumulator.

Common dependencies are both voters, feedback mux/distribution, busy/done/valid,
ready logic, reset/clear/start/busy distribution, input wires, clock, power and
external result interface. Each lane has its own local capture and reset/clear
write-selection gates, driven by those common controls. The shared signals and
voters are not independently protected. Control
corruption can drop a transaction without a completion or produce an incorrect
completion. No fail-stop guarantee or timeout detector is implemented.

## Multiple faults and explicit limitations

One arbitrarily corrupted lane word can be masked when the other two lane
calculations agree and the shared dependencies work. This is not a guarantee
for any arbitrary two faults or even a single fault in a shared dependency.
The directed tests include these literal counterexamples from zero state:

| Fault / operation | Observation |
| --- | --- |
| State words 1, 2, 0 | Readback 0; disjoint bad bits masked and scrubbed |
| State words 1, 2, 4 | Vote 0, which matches none of the words; no rejection |
| State words 1, 1, 0 | Wrong vote 1, then feedback makes all states 1 |
| 1*1 with candidate XOR1 in lanes0/1 | Wrong valid result 0, error0 |
| 1*1 with candidate XOR1 in all lanes | Same wrong result, no lane disagreement |
| 1*1 with candidate-voter output XOR1 | Wrong vote0 is committed to all lanes |
| Idle state-voter output XOR1 | All raw states become1; wrong state survives mask removal |
| Common accepted operand changed from1 to0, b=1 | Valid result0 instead of intended1 |
| Shared busy changed1→0 after accepting1*1 | Operation lost, no done/valid/error |

Two or three divergent lanes may happen to give the right bitwise answer, a
wrong answer, or a word present in no lane. `disagreement` cannot distinguish
these. Overlapping erroneous bits can outvote the healthy lane. Sequential
upsets before repair, correlated faults, voter/control faults and common inputs
invalidate the single-lane assumption. RTL bit indices do not imply physical
adjacency. The bounded CR6 pilot is separate from these directed controls; no final
statistical campaign or physical-fault distribution is claimed.

## Injection and test implementation

Production `mac_tmr` has no fault input ports. `mac_tmr_injectable` shares
`mac_tmr_datapath.vh`, using lane candidate XOR masks and two voter-output XOR
masks that production ties to zero. CR6 places candidate XORs in the parent;
the lane has no fault-mask port. Historical pre-repair M5 netlists retained
24/8/4 candidate-mask XOR/XNOR cells per lane; those counts remain historical.
The repaired historical host routed netlists contain zero mask identifiers;
the cost gate enforces this on each new production netlist. This instrumented core is a simulation
comparison, not a board design. The testbench deposits XORs into the actual
accumulator/saved operand registers between edges, checks before/after words,
and does not hold a force through repair. The controller limitation deposits
busy=0 and acknowledges the real change. Combinational XORs are checked against
actual clean and perturbed wires before sampling. Only non-reset busy candidate
masks and eligible non-reset voter masks count as sampled injections. Raw traces
retain every cycle and injection, including negative-control failures.

`make test-tmr JOBS=2` runs Python model checks, independent integer/bit-count RTL
oracles with clean production/instrumented equivalence, every lane and every
state/operand/candidate bit, idle/acceptance/busy repair, signed wrap, priorities,
repeated faults, successors and literal limitations at all three widths. Small
arithmetic is exhaustive. Isolated source mutants must compile and fail at the
specified first assertion for missing repair, vote, XOR, actual storage firing,
operand capture, reset clearing and reset losing to simultaneous start. The reset/start mutant must also fail the actual synthesized-netlist oracle at
its directed idle reset/start edge. A compilation failure cannot pass a control.
The model has its own fault hooks and independent clean comparison to MacModel.
Its step mask arguments apply through that edge and returned readback; its
`accumulator` property is the unmasked vote (as after releasing the transient).
`disagreement_before` records the pre-edge diagnostic, not a retained hardware
status pulse. Model construction initializes zero for convenience; RTL requires
synchronous reset before use.

## Synthesis boundary

Lane modules and instances carry `keep_hierarchy`. The target runs actual generic
Yosys synthesis (with `-flatten`, respecting kept lane boundaries) on the
production core at all three widths and inspects JSON:
three lane instances, one multiplier and adder per lane before mapping, distinct
AW+2*OW flip-flop bits per instance after mapping, distinct output buses and
paths from every lane to shared feedback. A module definition reused three times
means three physical elaborated instances, not one lane. All lane register bits
must remain connected to flop Q outputs. Synthesized generic netlists also run
clean arithmetic/protocol simulation with directed nonzero-state reset+start,
reset+busy, idle clear+start, busy clear+start, ignored busy requests and held /
post-done starts. RTL and gate random phases use separate PRNG advances and
high-order bits for reset, clear and start. The runner counts eight control
cross-cases from raw pre-edge traces, requires each globally and in the random
phase alone, and retains counts. This replaces the first attempt's degenerate
low-bit control stimulus; its aggregate cycle counts did not prove these cases.
An unpreserved flattened synthesis control
must lose replicas and be rejected by the auditor; its actual collapsed count
is retained. Reports are in unique `build/tmr/run_*/` directories with commands,
versions, source snapshots/hashes, failed logs and artifact hashes. Positive
raw trace row shapes, per-edge counts and stored XOR acknowledgements are
rechecked against the printed counts using the retained `trace_schema.json`.
Sampled candidate/voter acknowledgements are also recounted. A separate mutated
netlist-JSON control bypasses feedback voting to test the auditor's reachability
rejection; it is not synthesized fault-injection evidence. Gate simulation is
clean functional evidence only: netlist single-lane injection is still unperformed.

These are generic-netlist structural observations, not routed PPA or FPGA/ASIC
sign-off. A later mapper may ignore preservation attributes or flatten/merge
logic. Reinspect redundancy after the exact target synthesis, mapping and
physical flow; apply target-specific preservation constraints then if needed.
Historical repaired matched OOC timing/resource reports and the current bounded
RTL pilot are in the measurement record. All four variants fail OOC timing closure.
Placement separation, routing isolation, common infrastructure, energy and full
statistical/netlist fault campaigns remain future work. No TMR
board wrapper/capture decoder is supplied; all TMR board tests are NOT RUN.
