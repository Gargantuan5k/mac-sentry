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
