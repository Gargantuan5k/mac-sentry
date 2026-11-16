# Selected historical capture compatibility fixtures

These are **PARTIAL selected fixtures**, not complete FPGA build archives or new
hardware measurements. They retain unchanged bytes from two original archives:
one unprotected ILA capture and seven SECDED ILA captures, each archive's original
manifest, and its four expected analysis CSV files. No BIT/LTX, full raw archive,
source/build ZIP or independent capture/build identity proof is supplied here.

The collection `manifest.json` records SHA-256, size and original location for
all 18 selected original files. The originals' manifests separately bind every
selected ILA/CSV hash. Absolute paths inside original manifests are historical
metadata, not paths required at runtime. Keep original manifests unchanged: they
also list omitted files and do **not** describe this subset as a complete archive.

`scripts/test_hybrid_capture.py` requires and hash-checks this collection before
compiling or running tests. Its existing legacy compatibility checks reanalyze
all eight ILA inputs and compare the old measured CSV outputs; no test is skipped
when a fixture is missing. Baseline additive columns must remain empty. SECDED
measured CSVs remain byte-exact, and its test plan uses the separately preserved
`../m7_secded_test_plan.csv` reference for the accepted later plan additions.
That reference is an unperformed test plan, not additional measured evidence.

The blocked A3 signed operation and missing double-error/recovery observations
remain limitations. See `docs/results.md` and the board backlog for current scope.
