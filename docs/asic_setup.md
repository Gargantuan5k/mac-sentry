# Standalone SKY130 / Tiny Tapeout setup

Run commands from the repository root. Core RTL and interface tests do not need
PDKs or containers. The full physical target needs rootless Podman, Python 3.11,
Icarus Verilog, the pinned vendor/tool cache and two separate SKY130 revisions.
No Codex, Claude, supervisor state, private `.context` or sibling checkout is used.

## Pins and installation boundaries

`requirements/asic-lock.json` records vendor commits/archive SHA-256 values,
LibreLane version and PDK revisions. Host Python packages are in
`requirements/asic-python.txt` and `requirements/asic-metadata.txt`, installed into
separate local environments. The hardening PDK is
`8afc8346a57fe1ab7934ba5a6056ea8b43078e71`; the precheck PDK is
`0536d02d875c8f67dd7cca3902ac457e62f20005`. Both are necessary.
The pinned upstream reference is TTSKY26d; confirm actual shuttle rules before
submission. These are reproducibility pins, not a claim about current availability.

The setup program does nothing except print its plan unless `--execute` is given.
It never runs sudo, changes Git metadata or modifies global Python. It refuses an
existing tools-cache destination. Installation requires network access, sufficient
disk space, a working compiler/tool environment for upstream dependencies, and
working rootless Podman. Image builds may take substantial time. A partial failed
setup remains for diagnosis; choose a new directory for another attempt.

## Prepare a new machine

First inspect the plan:

```sh
python3 scripts/check_environment.py --profile asic
python3 tools/setup_asic.py --python python3.11 --fetch-pdks
```

After reviewing it, explicitly create the default ignored cache and fetch both
PDKs:

```sh
python3 tools/setup_asic.py --python python3.11 --fetch-pdks --execute
```

To reuse an already installed Ciel store, omit `--fetch-pdks` and supply its root:

```sh
python3 tools/setup_asic.py --python python3.11 \
  --pdk-root /path/to/ciel --execute
```

That root must contain `sky130/versions/<revision>/sky130A/SOURCES` for both
revisions. The setup verifies their recorded identities before use. It reads an
existing store; it downloads into the selected store only with `--fetch-pdks`.
For an external tools-cache location, use `--tools /path/to/new/mac-sentry-tools`,
then export `MAC_SENTRY_ASIC_TOOLS=/path/to/new/mac-sentry-tools` for experiments.
No machine-specific path is embedded in the source.

Setup downloads only hash-pinned source archives, creates isolated `venv/` and
`tt-venv/`, pulls/version-checks the selected LibreLane image, and builds the
separate upstream precheck image from `tools/precheck.Containerfile`. It records
actual immutable local image IDs and setup command logs. A rebuild can differ
from the historical precheck image because upstream Python requirements are not
a complete transitive wheel lock. New images must pass their own full validation;
do not copy historical image IDs onto unrelated images or claim byte-identical
reproducibility. The full physical flow uses only recorded local IDs with
`--pull=never` and network disabled.

## Run a fresh physical experiment

```sh
make test-asic-interface JOBS=2
make test-asic-flow JOBS=2
```

A nondefault tools location can be selected per invocation:

```sh
MAC_SENTRY_ASIC_TOOLS=/path/to/mac-sentry-tools make test-asic-flow JOBS=2
```

The flow creates a unique `build/asic_flow/run_*/` and runs hardening, required
physical checks, all 15 shuttle prechecks, and zero-delay functional gate-level
simulation with negative controls. It records source/config copies, tool/PDK/image
identities, exact commands, raw reports, GDS and artifact hashes. It exits nonzero
on failure; it does not reuse a cached PASS. GDS generation alone is not acceptance.

To prepare inputs without executing physical stages:

```sh
python3 scripts/test_asic_flow.py --prepare-only
```

Preparation reports `PREPARED_ONLY`, never physical PASS. Use `--command-timeout`
to set a positive per-command timeout for the full driver. The default is 1800
seconds per command. Run one heavy ASIC/FPGA process at a time on a 16 GiB host.

Each invocation owns a unique container label and marker. The driver bounds its
process groups and cleans up only its labelled containers on completion, failure,
timeout or ordinary interruption. `tools/container_runtime.py` does not allow
detached runs or supply unrestricted container access. Shared tool and PDK inputs
are read-only; only the new evidence output is writable. Do not rename shared
caches while an experiment is running.

## Results and limits

See [the ASIC interface](../asic/README.md), [validation scope](../asic/validation.md),
and [published historical results](results.md). The implemented physical contract
uses a 50 ns trial clock and 2x2 tile. Passing it is not SDF simulation, full-chip
power/IR sign-off, shuttle submission, board validation or silicon validation.
The portable result package deliberately preserves those limitations.
