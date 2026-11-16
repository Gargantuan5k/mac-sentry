# Existing results and how to inspect them

The committable [published evidence](../results/published/README.md) is a selected
historical data package. Every selected data member has an original location,
size and SHA-256 in [its manifest](../results/published/manifest.json). The package
contains original source inputs for these runs; those identities are separate
from later tooling/documentation migrations in the main checkout.

```sh
python3 scripts/check_published_results.py
```

This works with the Python standard library and the public project sources,
without an FPGA, ASIC tools, agent runner, PDK, prior `build/`, or access to the
original machine. It checks hashes and important claim consistency and replays
recorded digital trials. It does **not** execute a new physical flow or certify
hardware behavior. New experiments must produce new uniquely identified runs.

## Protected SKY130 implementation

The selected run is `run_ym_hhxr_`, executed on 8 November 2026 using the protected
Tiny Tapeout hybrid wrapper, a 50 ns target clock and a 2x2 tile. The preserved
[result](../results/published/data/asic/result.json) has all eight required stages
passing with `errors=[]`. [Diagnostics](../results/published/data/asic/physical_diagnostics.json)
retain all nine timing corners, zero required setup/hold/slew/capacitance/fanout
violation counts, and explicitly enumerated disconnected-output annotation
exceptions. [Resolved configuration](../results/published/data/asic/project/src/runs/R2/resolved.json)
and [final metrics](../results/published/data/asic/project/src/runs/R2/final/metrics.json)
provide the exact physical conditions and measured quantities.

The [shuttle precheck XML](../results/published/data/asic/tt/precheck/reports/results.xml)
records 15 executed cases with no failures, errors or skips. The pin-only
[zero-delay GLS log](../results/published/data/asic/gls_positive.log) records
777 transactions, two aborts and 15,642 samples. Both deliberately corrupted GLS
controls fail for their intended diagnostics. The full commands, tool/PDK/image
identities, input sources and logs remain in `data/asic/`.

This is implemented local physical-check closure, **not full sign-off**:
`sdf_annotated=false` and `signoff=false` remain explicit. No silicon/radiation
measurement, full-chip power/IR qualification or tapeout submission is established.
One [reference KLayout GDS](../results/published/data/asic/project/src/runs/R2/final/klayout_gds/tt_um_mac_sentry.klayout.gds)
is included so teammates can inspect the existing layout after cloning. The
matching [final powered netlist](../results/published/data/asic/project/src/runs/R2/final/pnl/tt_um_mac_sentry.pnl.v)
and [LEF](../results/published/data/asic/project/src/runs/R2/final/lef/tt_um_mac_sentry.lef)
are from the same original run. Their original paths, sizes and hashes are bound
by the manifest. Portable validation checks file integrity, GDS HEADER/ENDLIB
framing and top names; this is not a new physical/sign-off result. Duplicate GDS
variants and complete raw implementation workspaces remain external, and the
pinned flow can regenerate new candidates.

## Bounded four-variant RTL fault pilot

The [manifest](../results/published/data/pilot/manifest.json) defines 429 trials
with seed 20261107: 29 literal calibration cases and 400 stratified clean/matched/
protection trials. [All observations](../results/published/data/pilot/trials.jsonl),
per-trial traces and actual injection acknowledgements, [grouped results](../results/published/data/pilot/summary.json),
and 25 controls are included. The portable verifier replays the traces and checks
the planned/recorded denominator rather than accepting a summary count alone.

Recovery, detected failure, silent escape, clean behavior and timeout all remain
visible. The strata intentionally differ between protection mechanisms; do not
pool them into a whole-design fault-coverage percentage or claim a universal
resilience ranking. These are defined digital mechanisms and a bounded sampling
experiment, not a physical radiation-event distribution or cross-section study.

## FPGA core cost and timing

The [four-row table](../results/published/data/fpga_cost/results.json) was measured
with Vivado 2025.2.1 on xc7z020clg484-1, at a 10 ns target and with DSPs disabled
for this matched experiment. The core-only OOC scope differs from a board build
with debug IP and normal DSP inference. Raw reports/configuration, process
cleanup evidence, source identities and all 21 controls are included.

| Variant | LUTs | FFs | DSPs | Setup slack (ns) | Hold slack (ns) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Unprotected | 87 | 43 | 0 | +2.131 | -1.167 | failure_to_close |
| SECDED | 210 | 51 | 0 | +0.210 | -1.161 | failure_to_close |
| Hybrid | 355 | 75 | 0 | -4.875 | -1.114 | failure_to_close |
| TMR | 352 | 200 | 0 | -4.960 | -1.119 | failure_to_close |

Successful tool execution and reproducible measurement do not promote these rows
to timing-clean implementations. No deployable board bitstream is implied.

## Historical ZedBoard observations

`data/board/` publishes summaries and original manifests for four saved FPGA
archives. The unprotected core has observed arithmetic captures. The SECDED
archive includes A1/A2/A4 arithmetic and B1/B2/B3 single-storage-bit injection/
repair observations. The intended signed A3 MAC was **BLOCKED** by held clear;
that outcome remains unchanged. Double-error/recovery and later hybrid/TMR board
qualification remain pending. Capture summaries do not independently authenticate
which BIT/LTX pair was programmed for older observations.

The Git package includes [eight selected original ILA compatibility fixtures](../tests/fixtures/legacy_captures/README.md)
(one baseline and seven SECDED), their unchanged original manifests and expected
CSV outputs. The hybrid capture target requires and hash-checks these inputs;
missing or modified fixtures fail rather than skip the legacy checks. This is a
partial selected test dataset, not an authenticated complete hardware archive.
Full raw ILA/CSV archives, shared build ZIPs, bitstreams and checkpoints remain
outside this small Git package. Existing local copies remain under ignored
`results/` and `build/`; full archives need a separate transfer/backup when further
reanalysis is needed. Use the [board backlog](../spec/board_validation_backlog.md)
for exact pending operations, masks, trigger conditions and archive procedure.
