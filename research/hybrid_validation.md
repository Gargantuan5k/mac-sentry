> Historical research record. Stage names and local `build/` paths below identify the original experiments; they are not clone prerequisites. Start with the [current project overview](../docs/project_overview.md) and [portable results](../docs/results.md).

# Conventional hybrid validation — 2026-11-06

Current status as of CF entry, 8 November 2026: M0/M1/M3/M5/M7/R4/CR2/CR6
are accepted; M2 skipped (owner-deferred), M4/M6 failed. R6 blocked and R2 pending
remain historical. CR6 sequence 8 has a clean review02 PASS with host pilot
run_e46nd7_8 and cost run_wei9weaj; see the source identity and retained publications
in the [handoff](../docs/project_overview.md).
CF focused acceptance/review and the complete 13-gate final regression remain open.
All entries below retain their dated attempt scope; older pending-review and
NOT RUN statements do not override subsequent accepted state or the documented
unaccepted M2/M6 host runs. No new board, physical sign-off or novelty gate passed.


This is the historical implementation record. The separate
[M0 audit and reproduction](../docs/results.md) records fresh staged
runs, the injection-accounting defect and added regressions. Counts below are
preserved for the original tests and are not new overnight or hardware results.

Implemented separate Python and SystemVerilog SECDED + modulo-7 arithmetic check
+ bounded retry cores. Contract: [hybrid MAC](../spec/hybrid_mac.md).
The existing unprotected and SECDED-only RTL implementations are preserved.
No FPGA board was available; no hybrid FPGA timing or hardware result is claimed.
Vivado was not available on PATH in this session.

## Reproduction

```sh
make all
make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=0
make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=1
make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=3
python3 scripts/compact_fpga_results.py --verify-only
```

Default seed: 20260923. Main local artifacts: `build/implementation_regression.log`
and each `build/hybrid_w<OW>_a<AW>_r<R>/` directory, containing vector manifest,
source/tool/artifact provenance, simulation/negative-control logs and (when run)
generic synthesis reports/netlists. These generated outputs are Git-ignored and
are overwritten on rerun. This tracked document records the observed counts.

## Results

`make all` passed: **45 Python tests**, baseline/SECDED/hybrid RTL regressions,
SECDED board-wrapper simulation, strict Verilator lint and Yosys generic synthesis
of all three default-width production cores with `check -assert`.
Ten Python tests specifically cover the hybrid and its protection limits; six
cover SECDED capture analysis. Remaining tests cover previous models/archive tools.

| Operands/accumulator | Extra retries | MAC cycles | Standalone residue checks | Actual storage injections | Active-attempt fault events |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8/24 | 2 | 161598 | 26000 | 616 | 772 |
| 4/8 | 2 | 27268 | 75536 | 240 | 716 |
| 2/4 | 2 | 26514 | 14192 | 191 | 677 |
| 2/4 | 0 | 26464 | 14192 | 191 | 513 |
| 2/4 | 1 | 26489 | 14192 | 191 | 635 |
| 2/4 | 3 | 26539 | 14192 | 191 | 694 |

All rows matched the integer Python oracle and state model. Retry variants 0/1/3
also passed lint and generic synthesis. Counts include directed, baseline replay
and randomized sequences; they are not statistically calibrated fault coverage.
A fault event can apply multiple masks at once. MAC cycles include idle/control.

The standalone checker exhausts all 65536 accumulator/operand combinations at
4/8 and all 8192 accumulator/operand/candidate combinations at 2/4. Each configuration
also tests 1000 random signed inputs with the clean full sum and every candidate
bit flipped. Integrated runs replay the baseline vectors on both instrumented and
production hybrid instances, then test every candidate bit, transient/persistent
faults, retry bounds, every stored single bit/double pair, checker corruption,
reset/clear priorities and mixed seeded sequences.

Each width/retry configuration passed four harness negative controls: wrong
expected residue, missing stored flip, missing candidate flip, and truncated
vector file. The runner rejects malformed rows, unexpected trailing columns and
record-count mismatch. It checks actual injection XORs, pre/post raw storage,
protocol/status pulses and storage stability away from rising edges.

The small-width run initially failed because negative C++ operands were not masked
to the HDL port width: an 8-bit C++ container retained high bits for a 4-bit port.
Fixed the hybrid harness and the same pattern in the two existing C++ harnesses;
all baseline and SECDED regressions were rerun successfully. No arithmetic RTL
change was needed for this failure. The existing exhaustive operand sequences
exercise the regression, including (-8)*(-8) followed by (-8)*(-7) at 4/8.

## Expected limitations observed in RTL

The vector manifest records explicit wrong-but-valid traces for:

- Modulo collision: 0+0*0, candidate XOR7 commits7.
- Correlated fault: 0+1*1, candidate XOR1 and prediction XOR1 commits0.
- After-check fault: 0+1*1, commit XOR1 stores0 with valid ECC.

All produced their expected escapes. They demonstrate the conventional baseline's
limits; they are not successful corrections. Source operands/decoder are shared,
and neither control nor commit is independently protected. Retry does not repair
persistent corruption and does not protect a result that the checker accepts.

## Existing regressions retained

Baseline: 155320 cycles at 8/24 and 22712 at 4/8.
SECDED: 205779 MAC cycles /20640 codec checks /4915 injections at 8/24;
35023 /11872 /1542 at 4/8. SECDED negative controls passed at both widths.
Board-wrapper simulation passed 465 single/double injections plus request/priority
checks. These are simulated board-wrapper results, not additional board captures.
The [SECDED capture audit](secded_capture_validation.md) separately records the
seven historical physical waveforms and missing coverage.

## Historical remaining work (2026-11-06)

The hybrid's generic netlist is synthesizable; this is not mapped FPGA/ASIC PPA,
post-route timing, power, configuration-fault coverage, or tapeout readiness.
No hybrid board wrapper, timed hardware fault sequencer or ILA decoder is included
in this milestone. Implement those next, then use the detailed
[board checklist](../spec/board_validation_backlog.md). T08 remains partial until
TMR and fair comparisons are implemented; T09 protected commit and novelty gates
are not marked complete by this work.


## M3 staged extension — 2026-11-07

The historical “remaining work” statement above described the 6 November state.
M3 now supplies the [separate board sequencer/wrapper](../spec/hybrid_fpga_setup.md),
create-only Vivado Tcl and `make test-hybrid-board`. See the M3 entry in
[overnight progress](../docs/results.md) for observed local checks,
source hashes and preserved failures. No physical ZedBoard or Vivado routed
result is added. Variable-latency capture analysis remains M4; TMR, protected
commit, calibrated comparisons and novelty gates remain unfinished.


## M5 comparison update — 2026-11-07

The earlier statements that TMR is future implementation work are historical.
The staged [TMR contract](../spec/tmr_mac.md), model and RTL now provide a separate
comparison baseline pending host tests/review. Matched cost and calibrated
campaign work remain open; the hybrid implementation and its limitations are
unchanged. No TMR physical/board result or general correction claim is added.

## Historical M7-entry interpretation — 2026-11-07 (superseded by R4 below)

M3 board experiment support and M5 TMR software/generic-netlist work are accepted.
M4 capture analysis failed and is absent from the accepted source; preserve raw
hybrid exports. The false-PASS counterexample and required future fixture are in
the final handoff. M2 is deferred. Repaired M6 host pilot/cost results exist in
the unaccepted record linked from the handoff; all four OOC variants failed timing
closure and TMR used different sources. No accepted fair-cost ranking, physical
board result, protected commit or prior-art/faculty decision follows.

## R4 capture repair — 2026-11-07 (candidate, synthetic only)

This section supersedes the historical M7-entry statement that the analyzer is
absent. R4 restores the preserved M4 pipeline and fixes the reviewed false PASS;
M4 remains failed, while M7 is accepted. The fixed mode is `--variant hybrid`,
with usage, all 44 probes, edge alignment and classification in the
[setup guide](../spec/hybrid_fpga_setup.md). Fresh host gates/review remain required.

A separate SV stimulus drives the real accepted board RTL (simulation debug IP)
through the exact two-launch raw3/error1 then raw7/valid13 sequence. The second
launch has no intervening clear/reset. Its archive classification is
ESCAPE / hybrid_unusable_source_valid; the clean result from trusted zero is12.
The sibling reset/raw0 with the same storage4 launch returns12/PASS. An unusable
source that coincidentally returns12 still cannot PASS, and a direct triple
storage upset from usable zero returns13/hybrid_silent_escape. A copied old guard
produces the reviewed false PASS through the CLI and is rejected by the literal
expected ESCAPE assertion. No hardware protection behavior was changed.

The suite retains clean/retry/exhaustion/uncorrectable/abort cases, three original
arithmetic escapes, all raw/latched/applied probes, sampled injection acknowledgements,
wrong valid/status, gaps/cutoffs/unknown prefixes and parser controls. New controls
cover malformed quoting, corrupt ILA and missing waveform. Attempt and retry
metadata are now asserted. All end-to-end traces pass through CSV parsing and
compact archive creation; expected failures remain archived as failures.
Historical baseline/SECDED reanalysis is a separate compatibility check, never
a new board trial. Exact final run paths/hashes/results are in the R4 progress
entry. Prior-art/faculty, physical board, silicon and sign-off remain NOT RUN.

R4 local result: final capture run build/hybrid_capture/run_vzpw5sav checked all
135 synthetic fixtures, 70 wrong traces and 12 parser/extraction controls. The
old-guard negative archive was rejected for its exact false PASS; usable/unusable
source controls have the literal outcomes above. Historical measured outputs
remain unchanged, while the unperformed plan matches the accepted-M7 reference.
The cumulative commands and retained failed-plan check/correction are detailed
in [progress](../docs/results.md). Fresh host review remains pending.

## R4 rejected-scrub review repair — 2026-11-08; synthetic only

The preceding 135-fixture result is historical and its R4 candidate failed review.
It missed state corruption on error2 and trusted later re-encoded data. The
current 143-fixture run build/hybrid_capture/run_3l4kgxl1 reproduces both review
scenarios with real RTL: raw7 scrubbed to encoded1 on a rejected attempt, error2
with acc1, and a later valid13 from usable but tainted storage. All are non-PASS
ESCAPE events; reset/idle-clear controls return PASS/12. Busy clear is ignored.
Two copied-analyzer mutations independently recover false PASS/1 and PASS/13
and are rejected for those literal classifications. The original two-launch
raw3/raw7 valid13 versus usable clean12, old-guard control, 70 malformed trace
controls, 12 parsing/extraction controls and legacy compatibility checks remain.
Sources, expectations, raw CSV/ILA, acknowledgements, compact archives and
negative diagnostics are retained in that run. No physical measurements or
research novelty claim follow. At that attempt R4 was unaccepted; CR2-entry state now records R4 accepted.
M4 remains failed; physical board,
silicon and prior-art/faculty review remain NOT RUN.
