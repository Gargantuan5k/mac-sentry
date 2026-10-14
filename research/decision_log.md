# Implementation decisions and kickoff status

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

## Task evidence and open work

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
