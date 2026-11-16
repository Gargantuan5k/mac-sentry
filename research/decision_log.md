> Historical research record. Stage names and local `build/` paths below identify the original experiments; they are not clone prerequisites. Start with the [current project overview](../docs/project_overview.md) and [portable results](../docs/results.md).

# Implementation decisions and kickoff status

Current status (R4 continuation, 7 November 2026): M0/M1/M3/M5/M7 accepted;
M2 skipped (owner-deferred), M4/M6 failed. R4 is a repair candidate awaiting
host tests/review; R6 blocked, R2 pending. See [handoff](../docs/project_overview.md).
All entries below retain their dated attempt scope; older pending-review and
NOT RUN statements do not override subsequent accepted state or the documented
unaccepted M2/M6 host runs. No new board, physical sign-off or novelty gate passed.


## 2026-09-23 — portable baseline kickoff

Basis: `../../sop_docs/mac_research_execution_and_task_assignments.md` (18 Sep)
and `../../sop_docs/radiation_hardened_mac_project_plan.md` (17 Sep).

- Start in the empty `mac_sentry` workspace with the portable baseline and trusted
  reference, following the first three working days of the execution plan.
- Use the planned 8/24 signed wrapping arithmetic, with 4/8 as a scaling check.
- Use a two-edge transaction (capture, then commit), one in flight, to make later
  retry/state protection integrations explicit. The initial core interface has
  synchronous reset/idle clear; byte transfers belong in a future wrapper.
- The user explicitly deferred FPGA board selection and requested portable RTL
  first. No board-specific IP, pin assignments, or clock constraints were added.
- Keep original planning documents unchanged. Implementation documentation and
  disposable build artifacts live here. The planned sibling Vivado project
  `../rad_hard_soapbox` was not present at kickoff.
- Available tools: Verilator 5.046, Yosys 0.58 (157aabb58), Python and g++.
  Generated provenance records the exact runtime versions and source hashes.
- The provided `.git` directory contains no Git repository metadata. No commit
  identity is available; provenance records null Git fields and source hashes.
- Generic Yosys synthesis is an initial structural feasibility check. A board,
  target process/library, corners, clock target, placement/routing flow, and
  timing/energy evidence are still required for T05's full completion criteria.

## Historical kickoff task evidence and open work (2026-09-23)

| Plan task | Current implementation scope | Still required |
| --- | --- | --- |
| T01 | Local tool inventory; board deferred by user | Named owners, availability, compute/budget, eventual board |
| T03 | Revision 0 arithmetic/interface/fault-model document | Team review/sign-off; protected timing/status refinement |
| T04 | Independent reference, directed regression, exhaustive reduced-width residue equations | Cross-review/sign-off; protected retry/failure tests when implemented |
| T05 | Baseline RTL, simulation, generic synthesis flow | Target FPGA/ASIC implementation, mapped area/timing, review |
| T02/T06 | No new literature review or novelty decision | Closest full-text comparisons, conventional failing trace, faculty gate |
| T07 onward | Not implemented | SECDED, other baselines, calibrated injection, protected mechanism and physical evidence |

Execution-plan tasks require evidence and reviewer sign-off; no task is marked
formally complete merely because this initial implementation runs.

## 2026-10-14 — T07 Python model kickoff

- Added a parameterized shortened extended Hamming codec and a separate
  accumulator-only SECDED cycle model. The default storage format is 30 bits
  for 24 data bits. Existing baseline code is preserved.
- Proposed idle correction writeback and decode-before-commit semantics, with
  failed commits retaining the damaged codeword. No retry is included.
- Added an explicit stored-codeword XOR injection hook with before/after
  acknowledgement. This is not yet a calibrated fault campaign.
- Details and limits: [SECDED model contract](../spec/secded_accumulator.md).
- No tests added or run in this step. T07 verification, protected RTL, hardware
  integration, and reviewer sign-off remain outstanding.

## 2026-10-14 — T07 initial Python verification

- Added 14 SECDED codec/model tests. `make test-model` passes all 29 Python
  tests, including existing baseline and archive tooling checks.
- The codec checks use hand-derived codewords and an exhaustive distance oracle
  for small codes, in addition to default-width single/double fault enumeration.
- Transaction checks cover correction writeback, failed commit preservation,
  status pulses, reset/clear, and baseline equivalence. No model fixes were needed.
- Reproduce the SECDED subset with `make test-secded`; counts and limitations
  are recorded in [the validation record](secded_model_validation.md).
- T07 is still in progress: protected RTL, RTL fault injection, implementation
  evidence, and reviewer sign-off remain outstanding.

## 2026-10-14 — T07 RTL implementation and simulation

- Added separate parameterized SECDED encoder, decoder, and `mac_secded` core.
  The MAC implements the Python contract and exposes a registered correction
  pulse. Accumulator-only protection retains the two-edge transaction schedule.
- The simulation harness mutates the actual stored codeword between edges and
  checks the before/after XOR, raw storage, decoded readback, and protocol outputs.
  Injection adds no production hardware ports or muxes.
- Default 8/24 and reduced 4/8 RTL simulations matched Python, including baseline
  vector replay, enumerated storage faults, and codec tests. Both widths passed
  strict lint and Yosys synthesis with structural checks. All 29 Python tests pass.
- Harness negative controls reject a wrong codec expectation, a missing injection,
  and a truncated vector file. See [RTL validation](secded_rtl_validation.md) for
  counts, reproduction commands, and scope limits.
- `make all` now includes both variants; dedicated SECDED targets remain available.
  T07 target implementation evidence and review are still outstanding. FPGA
  wrapper/capture integration is next; no protected board result is claimed.

## 2026-10-14 — SECDED board test integration

- Added a separate synthesizable `mac_secded_injectable` module and ZedBoard
  wrapper matching the user's 4-input/7-output VIO and 16-probe ILA configuration.
- Shared the MAC update logic in `mac_secded_datapath.vh`; production ties the
  injection controls to zero and retains its original ports and semantics.
- Board injection is an idle-edge XOR of actual stored data/check bits. It
  acknowledges accepted nonzero masks, postpones scrubbing until the next edge,
  and discards requests while busy/reset/clear. It does not inject in-flight work.
- Board-wrapper simulation passed 465 enumerated single/double masks plus
  request and priority checks. Production regressions are rerun after sharing
  the datapath. User performs the Vivado project setup and target implementation.
- Setup and probe mapping: [SECDED FPGA setup](../spec/secded_fpga_setup.md).
  The archive analyzer still needs protected semantics; no board result is claimed.

## 2026-11-06 — offline implementation resumed; conventional hybrid baseline

- Added SECDED-aware ILA analysis and compact archiving via `--variant secded`,
  including raw codeword, injection acknowledgement, repair and failed completion.
  Seven existing captures matched 7161 transitions; A3 is explicitly BLOCKED,
  not a signed-MAC success. Archived preserved evidence and verified all four runs.
- Implemented the T08 conventional hybrid as a separate model/RTL core:
  SECDED source storage, modulo-7 full signed-sum check, and bounded retry
  (default two extra attempts). Modulus7 is an initial comparison choice, not
  an optimized/final protection choice. Check before truncation avoids an
  overflow-adjustment dependency; post-check commit remains deliberately unprotected.
- Explicitly tested modulo collisions, correlated prediction/candidate corruption,
  and corruption after checking. All demonstrate wrong-but-valid escapes as
  expected. Shared source operands/decoder, controller and checker are not hardened.
- `make all` passed 45 Python tests, three-variant RTL regressions, SECDED wrapper
  simulation, strict lint and generic synthesis. Hybrid tested 8/24,4/8,2/4 and
  retry budgets 0/1/2/3; harness negative controls passed. See
  [hybrid validation](hybrid_validation.md) for counts and reproducible commands.
- Fixed C++ port-width masking in all three simulation harnesses after reduced-width
  hybrid checks exposed retained high bits on negative operands. Existing baseline
  and SECDED RTL were unchanged; their regressions were rerun.
- Board unavailable. Added [a detailed pending test record](../spec/board_validation_backlog.md)
  with exact SECDED capture steps and hybrid sequencer/debug requirements and tests.
  No new board results, hybrid routed timing, physical fault coverage, novelty
  approval or tapeout readiness is claimed. T08 TMR/fair-cost comparison and
  T09 protected commit remain pending. Existing Vivado projects were not modified.

## 2026-11-07 — M0 staged audit and baseline reproduction

- Reproduced the unchanged starting verification with all five required commands,
  then reran the final candidate. All passed locally; host acceptance and
  independent review are pending. See [M0 progress](../docs/results.md)
  for exact commands, counts, source hashes and preserved raw artifacts.
- Fixed a demonstrated harness accounting defect: a vector could falsely mark
  an injected busy attempt ineligible while the runner printed PASS. The runner
  now verifies eligibility against DUT busy/reset/source-decode state.
- Retained all original vector rows/tests and added directed retry/repair/reset
  cases and four negative controls. Hybrid negative inputs/output and identities
  now survive reruns in separate directories. 47 Python tests and all six hybrid
  configurations passed; production RTL, models and public contracts are unchanged.
- Historical board results remain historical; A3 and double-error/recovery gaps
  persist. No physical run, routed PPA, novelty, or tapeout acceptance is claimed.

## 2026-11-07 — M0 negative-control review repair

- Accepted both review must-fix findings: anchored each negative-control failure
  to its target record and exact assertion, and selected a pending clean
  transaction for reset eligibility rather than idle reset. Production RTL,
  models and public contracts remain unchanged.
- Added four unittest regressions; fresh `make all` passed 51 tests. All five M0
  commands passed locally, with 48 hybrid controls across six configurations.
  A separately compiled no-reset harness mutant and an unrelated pre-word
  mismatch verify control specificity. See [progress](../docs/results.md)
  for raw evidence, source identities and explicit correction of earlier claims.
- Independent re-review and supervisor acceptance are pending. No board, physical
  PPA, tapeout or novelty gate is completed by this repair.

## 2026-11-07 — M1 protected Tiny Tapeout byte interface

- M0 is accepted in the supplied runner state. M1 wraps the unchanged production
  8/24/MAX_RETRIES=2 hybrid using the pinned official SKY26d port shape. The
  [protocol](../asic/README.md) defines signed byte loads, consumed operand flags,
  busy/invalid rejection, retained result and error/retry/correction readback.
- `ena=0` synchronously aborts and clears core/wrapper, with masked outputs and
  sampled-low rearming. The host bus is synchronous; wrapper control/status and
  snapshot are not independently protected. A byte-read sequence must not span
  a new transaction or clear/reset.
- Tests use actual host transactions for wrap and simulation-only access to the
  production instance for acknowledged faults. No injection ports, alternate
  debug core or unprotected submission candidate were added. See
  [M1 progress](../docs/results.md) for exact local evidence and acceptance status.
- Physical flow, tile/clock choices, routed PPA, gate-level tests, shuttle
  prechecks, faculty/novelty review and all hardware measurements remain pending.
  No purchase, submission, publication, main-checkout or sibling-project action.

## 2026-11-07 — M1 review test repairs

- Accepted all three M1 test-quality findings; production core and wrapper RTL
  are unchanged. Added nonzero between-edge output masking, loaded malformed
  START cases, and exact pin readback on replayed retry/capture edges.
- Added seven isolated wrapper mutation controls, preserving expected failures
  and the preliminary compile failure with source/tool identity. See
  [progress](../docs/results.md) for final commands and observed results.
- Documented the unprotected commit-to-capture double-upset window. These tests
  establish RTL protocol behavior only; acceptance/re-review, physical flow,
  board actions and all research novelty/coverage claims remain pending.

## 2026-11-07 — M1 second review test repairs

- Accepted the two remaining status-test findings. Added nine terminal-fault
  recovery cases that observe CLEAR/reset/disable through all readback registers
  before START, plus six idle-scrub/pulse-priority cases with actual raw XOR and
  repair acknowledgement. Production wrapper/core arithmetic remain unchanged.
- Added six targeted wrapper mutations: five individual CLEAR fault-history
  omissions and a correction observer incorrectly gated by pending. Tests must
  reject each at its specified assertion; compilation failure is not evidence.
  Exact local outcomes and source identity are in the current progress entry.
- All old tests, failed reviews and raw evidence remain. External acceptance and
  independent re-review are still required. Board actions remain NOT RUN; M2,
  physical sign-off, research/novelty and submission gates are unchanged.

## 2026-11-07 — M3 staged hybrid board experiment

- Added a separate clocked 8/24/retries2 ZedBoard sequencer/top and create-only
  Vivado Tcl. Real storage XOR occurs at accepted launch; candidate/checker/commit
  masks latch and apply to selected attempts. Sampled-site acknowledgements
  distinguish rejected arithmetic, unusable source and actual corrupt commit.
- Existing production ports/latency remain; the shared storage hook is tied off
  in production and the original injectable wrapper. No sibling project changes.
- `make test-hybrid-board JOBS=2` passed locally: H1–H15, independent per-edge
  oracle, all storage singles/pairs, full candidate-bit sweep, priority/recovery,
  probe wiring, generic synthesis and five exact-diagnostic negative controls.
  Counts, source identities and all failed development evidence are in
  [M3 progress](../docs/results.md).
- No board or routed timing result is claimed. Launch-only storage timing and
  physical H9/H10 stimulus limits are explicit in [setup](../spec/hybrid_fpga_setup.md).
  M4 capture analysis, M2 physical blockers and research/novelty gates remain.
  Independent review and host fixed acceptance still decide M3 acceptance.


## 2026-11-07 — M3 review evidence correction

- The prior M3 probe-wiring statement was too broad: VIO outputs were not directly
  compared. Add all 11 per-edge pin checks and operand/reset-abort swap controls.
- H9's zero starting state could not prove word clearing. Seed1 through a real
  clean MAC before reset and abort at each attempt, observe raw/decoded zero
  before a successor, and reject isolated storage-retention mutants.
- These are test-evidence repairs; functional RTL and the known modulo,
  correlated-checker and post-check commit escapes remain unchanged. See the
  current progress entry for observed results, hashes and external review gates.
  Hardware/Vivado, physical sign-off, campaigns and novelty remain unverified.


## 2026-11-07 — M5 conventional datapath TMR candidate

- Triplicate saved operands, multiplier, adder and accumulator; retain common
  transaction control, state/candidate voters and feedback distribution. This
  is datapath TMR, not full-system TMR or a proposed novelty mechanism.
- Every idle edge scrubs voted state; commit feeds the voted candidates to all
  lanes. Saved operands are overwritten on acceptance/reset, not scrubbed.
- Disagreement is diagnostic only; overlapping multiple-lane faults and shared
  voter/input/control faults can produce wrong-valid results or lost work.
- Preserve lane hierarchy and inspect real generic synthesized register/logic
  ownership; an unpreserved control demonstrates merging. Target mapping and
  physical independence require later evidence. See progress for actual runs.
- M5 only: no M2/M4 candidate sources were supplied or imported. The supervisor
  still decides acceptance after fixed host gates and independent review.


## 2026-11-07 — M5 review evidence repair

- Review found no core defect but rejected degenerate control stimulus. Preserve
  the TMR model/RTL; repair RTL/gate stimulus and require trace-counted priority
  crosses, with directed nonzero-state tests and an exact reset/start mutant.
- Prior cycle totals are not priority coverage. Current evidence and source
  hashes appear in the newest overnight progress entry; independent re-review
  and host acceptance remain pending. No physical or novelty claim changes.

## 2026-11-07 — M7 accepted-state reconciliation

M0/M1/M3/M5 acceptance is established by the supplied runner and read-only review
verdicts. Earlier milestone entries describe their attempt-time state. M2 is
owner-deferred, M4/M6 failed. M7 documents current sources and evidence only;
no functional RTL/model/test changes or failed-feature imports are made.
The repaired unaccepted M6 results are now recorded in pilot_validation.md with
original source hashes and timing failures; they are not accepted M5 costs.
The hybrid remains a conventional comparison, with explicit silent escapes.
Physical-board work, prior-art/faculty gates and complete sign-off stay pending.

## R4 continuation — capture classification (2026-11-07T17:42:30.120994+00:00)

Accepted M7 remains the base; original M2 skipped and M4/M6 failed are unchanged.
R4 integrates only relevant preserved M4 capture sources, repairs the unusable
launch-state false PASS, and updates current usage/status. The two-launch raw7
misclassification now has a real-RTL archive regression and usable-source control.
ESCAPE / hybrid_unusable_source_valid explicitly means validity cannot establish
correctness from that source; diagnostic arithmetic is not an independent oracle.
The checker does not protect hardware or establish physical fault coverage.
Evidence paths/commands and remaining review gates are in overnight progress.
Prior-art/faculty, physical-board and silicon gates remain NOT RUN.

## 2026-11-08 — R4 rejected-scrub classification repair (unaccepted)

An error2/invalid result does not establish state preservation beyond SECDED's
fault model. Real RTL with storage7 and candidate1 on all attempts scrubs data1
while rejecting every candidate; a later usable word can return valid13. The
R4 analyzer now checks rejected state and carries captured corruption taint
until reset/idle clear. The original valid-result-only fix was rejected by
review and remains historical. Synthetic CSV/archive controls cover both
review sequences and recovery, with independent guard-removal mutations.
No RTL protection, archive schema or milestone acceptance is changed. Physical
board, silicon and prior-art/faculty review remain NOT RUN.

## CR2 completion repair — 2026-11-08

The supplied state accepts R4's capture repair; original M4 remains failed.
The physical candidate follows the preserved M2 slew/fanout diagnosis with
unchanged 50 ns/2x2 target, tighter buffering/CTS and all-corner checks. The
[ASIC validation record](../asic/validation.md) separates failed historical route
metrics, new diagnostic GLS and pending current host physical tests. No RTL,
protection contract, prior-art, novelty, board or sign-off claim changes.


## CR2 attempt 2 host-feedback repair — 8 November 2026

Host run_us59qtx3 establishes a completed but FAILED physical route: four slew
corners fail, while clock fanout, required physical metrics, all15 prechecks and
zero-delay GLS/controls pass. Source/report identities and weak-driver diagnosis
are in asic/validation.md and build/cr2_slew_repair/diagnosis.json. Excluding
clkbuf_1/buf_1 and tightening GRT repair margin requires a fresh complete host
flow; no closure, novelty or acceptance is inferred. Accepted RTL/M7/R4 and
all prior milestone verdicts remain unchanged. Board/silicon/prior-art NOT RUN.

## CR2 attempt 3 — measured closure and handoff reconciliation, 8 November 2026

Host run_c5xb3gza passed the required protected flow, TT prechecks and zero-delay
GLS on unchanged attempt 2 sources. [ASIC validation](../asic/validation.md)
records +12.03 ns setup / +0.080 ns hold at max_ss, zero required physical
violations, 15/15 prechecks and 777 transactions / 2 aborts / 15,642 samples,
with both GLS negative controls. Attempt 1 remains FAIL. The independent review
confirmed this evidence but rejected missing documentation and artifact hashes;
this revision reconciles them without changing implementation or tests.
Independent CR2 acceptance, SDF simulation, full sign-off, prior-art/faculty,
physical board/silicon and submission remain pending. No novelty claim changes.

## CR6_1794085081502364837 — 2026-11-08T03:30:09.631435+00:00

The supplied state accepts R4 and CR2 separately; original M2/M4/M6/R6/R2
verdicts remain historical. CR6 integrates the exact repaired TMR RTL and bounded
pilot/cost flow, with strict regular-file evidence packaging and two reviewed
process-cleanup corrections. Full historical M6/R6 source/manifests remain
unchanged in lossless copies; current source differences and all denominators
are published in pilot_validation.md. No closure/ranking/radiation or novelty
claim follows. Fresh host gates and independent CR6 review remain required;
prior-art/faculty, physical board/silicon and submission remain NOT RUN.
