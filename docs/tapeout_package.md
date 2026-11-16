# Separate Tiny Tapeout submission package

Implementation plan, 12 November 2026: keep the research repository unchanged in
purpose and export a small, separate submission directory without initializing
Git. Maintain submission-specific workflows, pin-level tests and datasheet under
`asic/submission/`; copy the production RTL byte-for-byte when exporting. No FPGA
debug sources, injectable cores, tools, PDKs or historical build trees belong in
the export. Root `info.yaml` fixes the portal's missing metadata prerequisite.

Preserve the accepted 50 ns / 2x2 configuration, custom host timing, nine corners,
electrical limits and CTS/repair settings. Check the official support-tools merge
against this contract before claiming integration. Keep source hashes and an
inventory so exported RTL drift is visible. Refuse overwriting an existing export.

Validation will cover export integrity and negative controls, independent
pin-level arithmetic/protocol tests in RTL and against the existing routed
netlist, official metadata/port/configuration generation and documentation checks.
Existing physical results stay historical: no new GDS, SDF sign-off, hosted CI
success or submission is implied by preparing this package.

Publication remains a separate user action. No Git metadata, payment or portal
submission will be changed. The team's original-code licensing decision remains
open; copied upstream material retains its license and attribution.

## How to create the new repository contents

From the research checkout:

```sh
make test-tapeout-package
python3 scripts/export_tapeout.py --output build/distribution/mac-sentry-tinytapeout-ready
python3 build/distribution/mac-sentry-tinytapeout-ready/scripts/check_package.py
```

This creates a separate directory, not a Git repository. Publish its **contents**
at the root of a new repository, provisionally named `mac-sentry-tinytapeout`:

```text
mac-sentry-tinytapeout/
  .github/workflows/   gds.yaml, docs.yaml, test.yaml
  info.yaml           production source list, pinout, all three team members
  src/                protected hybrid, helpers, wrapper, include files and SDC
  test/               pin-only cocotb oracle, RTL/GL Makefile and powered harness
  docs/info.md        architecture, exact host protocol and known escapes
  scripts/            package and physical-configuration identity guard
  requirements/       original ASIC tool and vendor pins
  flow_contract.json
  PACKAGE_MANIFEST.json
  README.md, LICENSE, licenses/, .gitignore
```

The research checkout remains the source of truth for production RTL and physical
overrides. Regenerate into a new directory after changes; never hand-edit a
candidate and silently refresh its hashes. The exporter requires only Python's
standard library and the public research sources/evidence, not the local vendor
cache, agents or tools. Exported functional tests are standalone and require
Icarus Verilog, Python 3.11 and the pinned cocotb requirements.

After team licensing/release review, the user can create the GitHub repository and
publish the exported contents, including hidden workflow files. No Git operation
or remote publication is performed by the exporter. Enable Actions/Pages as
required, inspect every official job, then enter the **new repository URL** in
Tiny Tapeout. The research URL still lacks root metadata and is not the submission
URL. A portal registration is not a fabrication revision submission.

## Executed integration checks on 12 November

- Ten export/negative controls passed: byte-identical production RTL, no Git,
  overwrite refusal, missing/tampered/symlink inputs, and clock/corner/source/
  floorplan/PDK drift rejection. Run `make test-tapeout-package` to repeat.
- Official pinned support-tools documentation checks, source discovery, YoWASP
  port checks and `create_user_config()` passed. The generated floorplan is
  `0 0 334.88 225.76` with `tt_block_2x2_pg.def`. Its real merged configuration
  passes our contract guard. The post-build PDK guard was exercised using an
  explicitly constructed identity record matching the local baseline; this was
  **not** a hosted hardening execution or new physical result.
- Two pin-only cocotb tests passed in RTL and against the published historical
  powered routed netlist, using actual SKY130 models. The arithmetic test runs
  775 transactions, both signed wrapping directions and 256 seeded random pairs.
  XML has two executed tests, no failures or skips in each mode. Gate simulation
  uses the template's functional per-cell unit delays, not SDF parasitic delays.
- A deliberately wrong independent arithmetic oracle failed on the result
  assertion as intended. Export/hash checks also reject modified production RTL.
- Full `make all JOBS=2` passed after adding the export controls; its log is
  `build/tapeout-package-regression.log`. No production RTL was changed.

The clean deliverable is `build/distribution/mac-sentry-tinytapeout-ready/`, with
the same 28-file payload hashes as the tested `candidate-v2`. The sibling ZIP
contains those files plus the manifest, including hidden workflow files, and was
read back to verify every member hash. Its SHA-256 is
`99b3354074da0408125d859a4491c7a577d8ebd1274a9cbb21b5189f83deae42`.
The final machine-readable local check summary is
`build/tapeout-package-checks/result.json`.

Evidence is retained under `build/tapeout-package-checks/`, especially
`candidate-v2/rtl.log`, `rtl-results.xml`, `gl.log`, `gl-results.xml`,
`commands.json`, `official-integration.log` and `negative-oracle/`.

The first gate simulation failed because the new test sampled at +1 ns despite
the official harness adding a #1 delay at every cell. The correction samples at
+20 ns, retaining the 50 ns period, same active edges, independent expectations
and all assertions. The failure XML/waveform are preserved as `early-sample-gl-*`;
the corrected RTL and gate tests both pass. Initial official-tool invocations
also needed the prepared tool PATH and a writable `YOWASP_CACHE_DIR`; no package
was installed and no global cache or tool configuration was changed.

## Remaining release gates

The exported scoped LICENSE preserves third-party terms but deliberately does
not choose a license for the team's original work. Resolve that before publication.
SDF timing simulation, complete sign-off/power integration scope, independent
team/faculty review, hosted official CI and actual portal submission remain open.
No shuttle deadline, payment, GitHub access or tile allocation has been confirmed
or changed by this work. Reference workflow and schema were checked against the
[official template](https://github.com/TinyTapeout/ttsky-verilog-template) on
12 November; action/support-tools commits remain explicitly pinned in the export.
