# MAC Sentry

Signed integer multiply–accumulate hardware with four comparison implementations:
**unprotected**, **SECDED accumulator**, **SECDED + modulo-7 checking + bounded
retry**, and **datapath TMR**. Defaults are signed 8-bit operands and a wrapping
24-bit accumulator. This repository contains the RTL, Python reference models,
testbenches, FPGA/ASIC integration, experiment tools and selected measured results.

Start with the [project overview](docs/project_overview.md),
[recorded results and limitations](docs/results.md), and
[dependency requirements](requirements/README.md). The
[standalone validation record](docs/standalone_validation.md) lists the executed
checks and their limits. No agent software, credentials,
old build directory, sibling repository or PDK checkout is needed for model tests.

## Clone and run

After cloning the repository, run commands from its root. Python 3.10+ is enough
for reference models, capture analysis and verification of the published evidence:

```sh
python3 scripts/check_environment.py --profile python
make test-model
make test-evidence
```

The core Python tools use only the standard library; `requirements.txt` therefore
has no third-party packages. For RTL work, install Make, Verilator, a C++ compiler,
and Yosys with ABC. See [requirements](requirements/README.md) and the recorded
[toolchain versions](requirements/toolchain.json), then run:

```sh
make check-environment
make all JOBS=2
make test-asic-interface JOBS=2
make test-hybrid-board JOBS=2
make test-tmr JOBS=2
make test-hybrid-capture JOBS=2
make test-pilot JOBS=2
```

Use two build workers by default, with one heavy FPGA/ASIC process at a time.
These commands generate their own ignored `build/` outputs. They do not need
pre-existing experiment files. `make all` covers Python discovery, baseline,
SECDED and hybrid RTL, lint and generic synthesis; the other commands above cover
the separate interface, board harness, TMR, capture and pilot workflows.

## Choose an experiment

| Task | Command / guide |
| --- | --- |
| Baseline vectors and RTL | `make vectors test-rtl` |
| SECDED model / RTL | `make test-secded test-secded-rtl test-secded-small` |
| Hybrid models / RTL | `make test-hybrid-model test-hybrid-rtl test-hybrid-small test-hybrid-tiny` |
| Retry/width variant | `make test-hybrid-rtl OPERAND_WIDTH=2 ACC_WIDTH=4 MAX_RETRIES=0` |
| Generic synthesis | `make synth synth-secded synth-hybrid` |
| TMR functional/netlist checks | `make test-tmr JOBS=2` |
| Seeded, matched fault pilot | `make test-pilot JOBS=2`; `python3 scripts/pilot_campaign.py --help` |
| FPGA core cost/timing comparison | `make test-fpga-cost VIVADO=vivado JOBS=2` |
| Vivado simulation / board setup | [FPGA workflow](docs/fpga_workflow.md), [SECDED setup](spec/secded_fpga_setup.md), [hybrid setup](spec/hybrid_fpga_setup.md) |
| Protected SKY130 physical flow | [ASIC setup](docs/asic_setup.md), then `make test-asic-flow JOBS=2` |
| Verify existing compact evidence | `make test-evidence` |

Supported arithmetic constraints and fault semantics are defined in
[the interface specification](spec/mac_interface_and_fault_model.md),
[SECDED](spec/secded_accumulator.md), [hybrid](spec/hybrid_mac.md), and
[TMR](spec/tmr_mac.md). A new experiment retains its actual source/tool identities
and outcome, including failed timing closure and non-fired injections.

## FPGA and ASIC dependencies

Vivado is installed separately with Zynq-7000 support; put `vivado` on PATH or
pass its executable through `VIVADO`. Board target: ZedBoard `xc7z020clg484-1`.
The supplied hybrid project script creates a new project and generates real
VIO/ILA IP; simulation stand-ins are never hardware implementation sources.
Follow the [board backlog](spec/board_validation_backlog.md) for exact cases,
expected signals, trigger/capture settings and unperformed tests.

The ASIC flow uses the protected hybrid and the Tiny Tapeout byte interface in
[`asic/`](asic/README.md). Its external Python environments, vendor sources,
containers and **two distinct SKY130 revisions** are specified in
[`requirements/`](requirements/README.md) and [ASIC setup](docs/asic_setup.md).
Installation is explicit and isolated; core tests never download or install tools.
No PDKs, tool binaries, proprietary Vivado installation or agents belong in Git.

## Tiny Tapeout submission repository

Keep this research repository and its comparison experiments separate from the
small production submission repository. Generate that repository's contents with:

```sh
make test-tapeout-package
make package-tapeout
python3 build/distribution/mac-sentry-tinytapeout/scripts/check_package.py
```

The export has root-level `info.yaml`, production `src/`, pin-level `test/`,
datasheet `docs/info.md` and official `.github/workflows/`. It has no `.git`
directory and does not publish anything. Use `scripts/export_tapeout.py --output
build/distribution/another-candidate` for subsequent exports; existing directories
are never overwritten. See [package integration and remaining gates](docs/tapeout_package.md)
before publication. The research repository URL still does not satisfy the
portal's root metadata requirement; use the separate submission repository URL
after its contents have been reviewed and published. SDF, team licensing/sign-off,
hosted CI and actual submission remain separate gates.

## Existing results and limits

[`results/published/`](results/published/) contains a compact hash-checked selection
of actual ASIC, FPGA, pilot and comparison evidence. It works on a fresh clone.
The [results guide](docs/results.md) explains origins, historical source identities,
what each check establishes, and how to access/transfer larger local artifacts.
Published results are historical measurements, not a claim that every future tool
or code version produces the same output.

The implemented ASIC checks passed for the recorded protected build, including
15 prechecks and zero-delay gate-level simulation; **SDF simulation and full
sign-off remain open**. All four recorded FPGA OOC comparison rows failed timing
closure. The baseline was demonstrated on ZedBoard and selected SECDED tests were
captured; later hybrid/TMR hardware validation remains incomplete. Digital fault
injection does not establish a physical radiation cross section or universal
correction. Shared logic, modulo collisions, higher-weight ECC errors and
post-check commit faults remain explicit limitations.

## Repository layout and distribution

```text
rtl/           production and fault-injectable RTL, ECC and residue logic
model/         Python arithmetic and protection reference models
tests/         Python, C++ and SystemVerilog verification
fpga/zedboard/ board wrappers, sequencer and constraints
asic/          protected Tiny Tapeout wrapper, flow settings and interface
scripts/       vectors, experiments, capture analysis, packaging and verification
tools/         standalone container runtime, precheck image and ASIC setup
requirements/  external tool/PDK pins and installation requirements
spec/          behavior contracts and board procedures
research/      historical scientific decisions and validation records
docs/          current project, setup, workflow and results guides
results/published/ small reviewed reports/trials distributed with the source
build/         ignored generated outputs, installed tools and large local evidence
```

The source-package selection is explicit in `project_manifest.json`. Export and
verify a self-contained source archive without committing or requiring Git:

```sh
make package
python3 scripts/package_project.py --verify build/distribution/mac_sentry.tar.gz
```

The exporter refuses overwrites; choose another `--output` for a later archive.
It includes no agent/supervisor files, private settings, raw local FPGA archives,
PDKs or generated build trees. `.gitignore` makes the same separation for a future
commit. For large raw captures, BIT/LTX files and GDS, use a separately backed-up
artifact archive rather than ordinary Git. One compact reference KLayout GDS, its mapped netlist and LEF are included in
`results/published/` with their original hashes, so teammates can inspect the
existing layout directly. Duplicate layouts, full intermediate flows and raw
FPGA archives stay external. New candidates can be regenerated with the physical flow.
