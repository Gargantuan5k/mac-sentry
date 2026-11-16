# MAC Sentry Tiny Tapeout candidate

Protected signed 8-bit multiply–accumulate with a wrapping 24-bit accumulator.
Team: Siddharth Vivek, Tejas Singh Kohli and Arohi Mehta.

This directory is the standalone **submission candidate**, targeting SKY26d,
2x2 tiles and 20 MHz. It is not a claim of sign-off or portal acceptance.
Confirm shuttle availability and closing time in the Tiny Tapeout portal.

## Contents

```text
info.yaml                  root metadata consumed by the submission portal
src/                       six production SV modules, two includes, flow settings
test/                      independent pin-only cocotb tests for RTL and GLS
docs/info.md               datasheet and host protocol
.github/workflows/         official GDS/precheck/GLS/viewer/docs plus RTL test jobs
scripts/check_package.py   exported source hashes and physical-config drift guard
requirements/asic-lock.json original tool/vendor/PDK pins
flow_contract.json         required 50 ns, nine-corner and electrical settings
PACKAGE_MANIFEST.json      exact exported files and original source identities
LICENSE                    licensing status and third-party scope
licenses/                  third-party license text
```

No FPGA IP, fault-injectable core, research campaigns, PDKs, container images,
agent automation or historical build outputs are included. `src/config.json`
preserves the local CTS/repair settings; the official support tools generate the
tile dimensions, source list and pin template, then merge those into the config.
The post-build guard rejects drift in the merged configuration or hardening
tool/PDK identity. Official hosted CI and its artifacts must still be reviewed.

## Local functional checks

Python 3.11, Icarus Verilog, Make and the packages in `test/requirements.txt`:

```sh
python3 scripts/check_package.py
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r test/requirements.txt
make -C test
python -m cocotb_tools.check_results test/results.xml
```

The last command is mandatory: XML failures must not be mistaken for a passing
simulator exit. Tests use only production pins and an independent integer oracle;
they exercise both signed wraps, accumulation, protocol rejection, held strobe,
reset, deselection abort and recovery. They do not deliberately inject physical
faults and do not implement SDF timing validation. The same tests run on the
official powered netlist with `GATES=yes`; the hosted action supplies that netlist
and PDK models. The physical flow itself needs the official CI dependencies.

## Before publication and submission

1. Review authorship and decide an explicit license for the original project
   with the team/faculty. The upstream Apache license is not automatically a
   license grant for MAC Sentry's original RTL.
2. Review the source, interface, unprotected boundaries and physical settings.
   Complete SDF simulation and the outstanding sign-off scope. Approve a frozen
   source/GDS identity; do not infer acceptance from historical local reports.
3. Publish this directory's **contents at the new repository root**, not inside
   another folder. Include hidden `.github` and `.gitignore` files. Enable Actions
   and configure GitHub Pages as required by the official viewer workflow.
4. Require the GDS, precheck, GL test, docs and RTL test jobs to pass. Review the
   actual resulting layout/reports; archive artifact and source identities.
5. Register this new repository URL in the portal. Confirm the shuttle, tile
   allocation/payment, then explicitly submit the approved revision. Later
   changes require a new passing build and another submitted revision.

The exported inventory intentionally detects edits. Make source changes in the
research checkout and export to a **new** directory; do not casually regenerate
hashes in this candidate to hide drift. Existing exports are never overwritten.

Template/action references: https://github.com/TinyTapeout/ttsky-verilog-template
and https://www.tinytapeout.com/guides/advanced-workshop/submit-your-design/ .
The original research repository is https://github.com/Gargantuan5k/mac-sentry .
