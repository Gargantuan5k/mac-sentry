# FPGA results

- `runs/`: one directory per measurement run. Start with `tests.csv`, `capture_summary.csv`, and `manifest.json`.
- `builds/`: compressed build artifacts and reports, shared only when their paths and SHA-256 hashes are identical.
- `captures/`: temporary incoming exports, when present.

Each run keeps raw captures and CSVs directly accessible. `sources.zip` preserves its exact source snapshot. `storage.json` maps original manifest paths to ZIP files; historical run READMEs describe those original paths. Original manifests and recorded outcomes have not been edited.

Back up this entire results directory, including builds. A run copied alone does not contain its shared build ZIP. Archives are ignored by Git.

Verify integrity from the repository root:

```sh
python3 scripts/compact_fpga_results.py --verify-only
```

## Runs

- [2026-10-14_unprotected_zedboard_001](runs/2026-10-14_unprotected_zedboard_001/tests.csv)
- [2026-10-14_unprotected_zedboard_002](runs/2026-10-14_unprotected_zedboard_002/tests.csv)
- [zedboard_sequence_003](runs/zedboard_sequence_003/tests.csv)
