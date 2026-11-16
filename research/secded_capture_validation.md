> Historical research record. Stage names and local `build/` paths below identify the original experiments; they are not clone prerequisites. Start with the [current project overview](../docs/project_overview.md) and [portable results](../docs/results.md).

# SECDED capture audit — 2026-11-06

Offline analysis of seven previously saved ZedBoard captures. No new board activity
was performed. The checker now supports `archive_fpga_run.py --variant secded`.
It reconstructs transitions from observed initial idle storage, then uses the
SECDED model without reseeding it on each sample. It verifies raw XOR/fired,
repair/corrected, busy/completion/valid/error, decoded readback and raw storage.
Unknown pending history and discontinuities are explicitly left unchecked.

Six automated capture tests cover repair, double-error rejection/clear recovery,
missing acknowledgement, corrupted raw state/correction, invalid success after
double error, clear-blocked start, capture gaps/cutoffs and unknown pending history.
The existing baseline archive tests remain passing.

## Saved evidence

Source captures: `results/captures/secded_zedboard_001/`.
New immutable archive: `results/runs/2026-11-06_secded_saved_captures_001/`.

| Capture | Measured finding |
| --- | --- |
| A1 | 0 + 34*55 =1870; valid completion |
| A2 | 1870 +15*10 =2020; valid completion |
| A3 | Clear held high; start BLOCKED, no MAC completion |
| A4 | 0 +(-128)*(-128)=16384; valid completion |
| B1 | Raw data-bit XOR4 acknowledged, then repaired; decoded1870 retained |
| B2 | Hamming parity XOR1 acknowledged, then repaired; decoded1870 retained |
| B3 | Overall parity XOR0x20000000 acknowledged, then repaired; decoded1870 retained |

Each capture has 1024 samples/1023 checked transitions: **7161 checked transitions,
zero mismatches, zero unknown-history transitions**. Eleven events include three
successful MACs, three injections, three repairs, one clear and one blocked start.
An injection-only capture intentionally contains no complete MAC transaction;
that archive warning is not evidence of arithmetic failure.

Reports collected from `impl_secded_perf` include route/post-route-physopt timing:
WNS +0.227ns, WHS +0.052ns, WPWS +3.750ns, no_clock0 and unconstrained endpoints0.
The build used Performance_ExplorePostRoutePhysOpt at 100 MHz. Known DRC warnings
(debug-hub LUT/no-load and absent PS7) still require review; these measurements
are not an assertion of complete sign-off or production-core cost.

The archive contains hashes, raw captures, source snapshot, build/report evidence
and deduplicated ZIP references. Association of the historical programmed device
with the collected build is not independently established. Snapshotting current
sources also does not prove they produced the historical bitstream.
All four existing run archives passed `compact_fpga_results.py --verify-only`.

A3 must be repeated with clear released. C1/C2 double-error and D recovery captures
are missing. Follow [the board checklist](../spec/board_validation_backlog.md).
