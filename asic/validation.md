# Protected SKY130 validation

The protected hybrid wrapper has completed the implemented local physical flow,
15 shuttle prechecks, and zero-delay gate-level simulation with independent
arithmetic expectations and deliberately failing observation/arithmetic controls.
The fresh recorded run is `run_ym_hhxr_` from 8 November 2026.

The public, hash-bound selection of its actual reports, configurations and source
identities is in [published results](../docs/results.md). Use `make test-evidence`
to verify that selection without an ignored local build tree. The complete GDS,
parasitics, intermediate physical data and raw historical archives are retained
locally under `build/asic_flow/` and backed up/transferred separately. They are
not prerequisites for executing a new flow from this repository.

The physical contract remains a 50 ns trial clock and 2x2 tile, with all nine
required process/RC corner checks and the original electrical limits. Passing
these implemented checks is not full sign-off or submission approval. The result
explicitly records `sdf_annotated=false` and `signoff=false`; SDF simulation,
full-chip power/IR checks, complete shuttle acceptance and silicon validation
remain open. Earlier failed physical candidates remain failed historical results.

## Reproduce a fresh run

Prepare the pinned external tools, both distinct PDK revisions and local container
images using [ASIC setup](../docs/asic_setup.md), then run:

```sh
make test-asic-interface JOBS=2
make test-asic-flow JOBS=2
```

Every invocation creates a new `build/asic_flow/run_*/` directory, preserving
source/config copies, tool and PDK identities, raw commands/logs, physical
checks, precheck XML, gate-level simulation and negative controls. It does not
promote a cached result. Preparation-only mode never reports physical PASS.
The container helper is `tools/container_runtime.py`; no agent CLI, supervisor,
private `.context`, or old overnight snapshot is needed.

The November source migration changes tooling paths and standalone lifecycle
management; published historical results retain their original source hashes.
A new validation run has its own source identity and must not be represented as
the identical historical execution. Detailed supervisor-era notes remain in the
original local history, outside the public source package.
