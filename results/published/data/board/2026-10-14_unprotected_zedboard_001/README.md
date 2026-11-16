# Unprotected MAC hardware archive

This archive preserves existing artifacts; it does not run or program hardware.

- `tests.csv`: events actually visible in saved captures, checked against the Python model.
- `capture_summary.csv`: sample/transition/event counts. An idle capture is not a MAC test.
- `mismatches.csv`: sampled protocol/arithmetic disagreements.
- `test_plan.csv`: suggested tests; observations deliberately blank.
- `captures/`: original ILA/CSV files and signed-decimal samples.
- `reports/`, `build/`: existing implementation evidence, bitstream, probes, routed checkpoint.
- `sources/`: archive-time source/IP/XDC snapshot; XPR paths may need relocation.
- `manifest.json`: hashes, original locations, timestamps, scope and limitations.

The checker assumes 8/24 arithmetic, zero ILA input pipeline stages and consecutive samples.
Capture boundaries are not joined. Transactions cut off by a boundary are INCOMPLETE.
The observed initial accumulator is used as a starting point; its history is not proven.
Manual tests reported in conversation are not turned into measured PASS rows.

## Findings

- zedboard_mac_top_timing_summary_routed.rpt: no_clock=2754; timing closure is not established
- zedboard_mac_top_timing_summary_routed.rpt: unconstrained_internal_endpoints=3828; timing closure is not established
- 001_hw_ila_data_1: no complete MAC transaction in capture; does not verify arithmetic

Preserve this directory unchanged. Create a new archive after another capture/build.
