# Standalone package validation — 11 November 2026

A public source export was extracted with **no previous build directory, private
context, agent software or Git metadata**. Its files match the Git-eligible
selection. The complete workflow was executed on Linux x86-64 with the external
host tools listed in `requirements/toolchain.json`. The ASIC flow used the
existing pinned dependency/PDK cache read-only, selected explicitly through
`MAC_SENTRY_ASIC_TOOLS`; it did not need the old supervisor.

## Executed workflow

All twelve target invocations below returned zero. Commands run from the public
export root; the Vivado executable location below is intentionally normalized to
`vivado` on PATH rather than the validation machine's installation path.

| Command | Target outcome |
| --- | --- |
| `make all JOBS=2` | PASS |
| `make test-evidence` | PASS |
| `make test-asic-interface JOBS=2` | PASS |
| `make test-hybrid-board JOBS=2` | PASS |
| `make test-tmr JOBS=2` | PASS |
| `make test-hybrid-capture JOBS=2` | PASS |
| `make test-pilot JOBS=2` | PASS |
| `make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=0 JOBS=2` | PASS |
| `make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=1 JOBS=2` | PASS |
| `make test-hybrid-rtl lint-hybrid synth-hybrid OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=3 JOBS=2` | PASS |
| `make test-asic-flow JOBS=2` | PASS |
| `make test-fpga-cost VIVADO=vivado JOBS=2` | PASS |

The final public source's Python suite separately passed **127 tests** from
another clean export with no ASIC-cache environment variable. Published evidence,
source packaging and environment checks passed there too. Documentation/notices
were added after the implementation checks; final export and hash verification
cover those additions. No RTL, arithmetic models or physical constraints changed.

Two actual clean-export failures were found and fixed: ZIP could not represent
normalized pre-1980 source timestamps, and the capture compatibility test read
ignored local archives. The ZIP writer now clamps metadata while checking exact
original bytes/manifests. The capture target now mandates hash-bound committed
legacy fixtures; every original compatibility assertion remains. Missing or
altered inputs fail. Failed runs were retained, the affected complete target was
rerun, and earlier unaffected HDL results were reused. The final source package
also adds the independently checked reference-layout evidence and its integrity
controls. These are documented incremental checks, not a claim of one uninterrupted
execution from byte-identical final documentation.

## Concrete outcomes and limits

- Baseline/SECDED/hybrid RTL, lint and generic synthesis passed. The protected
  interface, hybrid board harness, TMR simulation/netlist/redundancy tests, capture
  pipeline, bounded 429-trial pilot and retry configurations passed.
- The capture pipeline passed 143 synthetic CSV/ILA fixtures and historical
  baseline/SECDED compatibility checks without ignored local result dependencies.
- Fresh ASIC run `run_ocifu4mh` passed hardening, implemented physical checks,
  15 shuttle prechecks and zero-delay GLS with both required failing controls.
  Its owned-container cleanup passed. It records `sdf_annotated=false` and
  `signoff=false`; it is not full physical sign-off or tapeout submission.
- Fresh FPGA cost run `run_643x34ks` completed its four-variant measurement and
  control workflow. **All four rows report `failure_to_close`.** A successful
  measurement target does not establish timing-clean cores or board bitstreams.
- No new physical board or radiation tests were performed. The distributed
  reference GDS and historical captures retain their original source identities;
  they were not overwritten with the new validation run.

## Dependency setup coverage

The explicit installer and lifecycle were checked with temporary-fixture and
real-process timeout/interruption controls. All three public pinned vendor URLs
were downloaded and verified against their archive SHA-256 values. A no-network,
FROM-only Podman smoke test verified immutable local base-image resolution.
**A fresh pip/PDK/image installation was not executed** during this migration.
Installation still needs the documented external tools and network; its commands
are in [ASIC setup](asic_setup.md), with no automatic global installation.

The full local logs, reviewed repairs and source identities are retained under
ignored `build/standalone-migration/`. They are not clone prerequisites. The
committed [published results](results.md) provide inspectable historical raw
reports, traces, source inputs, reference layout/netlist/LEF and selected capture
fixtures. Run the documented targets for independently generated new evidence.
No Git staging, commits, branch changes or pushes were performed.
