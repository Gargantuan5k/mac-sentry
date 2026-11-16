# Published experiment evidence

This directory is a compact, Git-committable selection of **historical measured
results**. It contains original report/log/configuration/source-input bytes and
raw digital trial observations, copied from the retained local experiment runs.
It is usable after cloning without `build/`, agents, FPGA hardware or a PDK.

From the repository root:

```sh
python3 scripts/check_published_results.py
```

The check hashes every selected data file, checks source-input identities,
replays the 429 pilot trials from retained traces and acknowledgements, and
checks that the physical/precheck/GLS and FPGA timing claims agree with the
retained records. It does not execute implementation tools or establish new
acceptance for the current source. A committed hash manifest is an integrity
record, not an independent digital signature.

- `data/asic/`: protected SKY130 run, physical metrics/diagnostics, input sources,
  resolved constraints/configuration, all 15 shuttle precheck outcomes, and
  zero-delay gate-level positive/negative-control logs, and one reference KLayout
  GDS with its matching final powered netlist (PNL) and LEF.
- `data/pilot/`: 429 seeded RTL trials, per-trial raw CSV traces/acknowledgements,
  grouped outcomes, calibration/negative controls, and source inputs.
- `data/fpga_cost/`: four-variant core-only Vivado OOC measurements, original
  timing/utilization reports, failure classifications, controls and source inputs.
- `data/board/`: summaries/manifests of four original FPGA archives. Large raw
  capture/build archives, bitstreams, source/build ZIPs and checkpoints remain
  outside Git. Eight selected original ILA inputs plus manifests/expected CSVs
  are separately included under `tests/fixtures/legacy_captures/` for mandatory
  compatibility regression; that subset is not a complete archived build.

`manifest.json` lists every selected data member with its SHA-256, size and
original repository-relative location. Original runtime paths inside copied logs
are historical metadata: they are not paths to install or execute on a new machine.
Source hashes describe each historical run, not a claim that every current helper
or document remains byte-identical. Sources under `data/*/sources/` are immutable
historical inputs for inspection; use the main source tree for new experiments.

All four FPGA OOC rows retain timing-closure failures. The ASIC run retains
`sdf_annotated=false` and `signoff=false`. Digital fault injection is not radiation
exposure testing. The recorded board summaries do not establish hybrid/TMR board
qualification or an independently authenticated historical BIT/LTX association.
See [results and limits](../../docs/results.md).

The included reference layout is
`data/asic/project/src/runs/R2/final/klayout_gds/tt_um_mac_sentry.klayout.gds`.
Open it in KLayout to inspect the existing implementation. Matching `pnl/` and
`lef/` files come from the same original run; `reference_layout` in the manifest
binds all three file identities. The verifier checks hashes, GDS HEADER/ENDLIB
framing and top names; these checks do not rerun DRC/LVS or establish sign-off.
Duplicate Magic/GDS variants, complete implementation workspaces, raw FPGA build
archives and tool/PDK caches remain external or can be regenerated with the
documented pinned flow. No tapeout submission or full sign-off is claimed.
