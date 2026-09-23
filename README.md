# mac_sentry

Portable RTL and reproducible verification for the soft-error-resilient integer
MAC research project. The starting implementation is the **unprotected comparison
baseline**, with signed 8-bit operands and a wrapping 24-bit accumulator.

The authoritative project and execution plans are in
[`../sop_docs`](../sop_docs/). FPGA board selection is deferred; this repository
contains portable code and local build artifacts. FPGA projects will remain
separate, as requested by the plan.

## Run

Requires Python 3.10+, Verilator, a C++ compiler, Make, and Yosys with ABC.
There are no pip dependencies.

```sh
make all          # Python tests, two RTL configurations, lint, generic synthesis
make test         # Functional verification only
make lint
make synth        # Technology-independent synthesis, not ASIC PPA or board timing
make test-rtl SEED=42
make test-rtl OPERAND_WIDTH=4 ACC_WIDTH=8
```

Generated vectors, configuration/seed manifests, simulation/compiler logs, synthesis logs,
netlists, statistics, and source/tool provenance go under `build/w8_a24/` (or the
selected widths). A vector manifest identifies its expected cycle count and
SHA-256. Failure reports identify the first mismatching cycle and signal. Source
hashes provide an identity even when Git metadata is unavailable.

## Implementation

| Path | Purpose |
| --- | --- |
| [`rtl/mac_unprotected.sv`](rtl/mac_unprotected.sv) | Synthesizable parameterized baseline, one operation in flight |
| [`spec/mac_interface_and_fault_model.md`](spec/mac_interface_and_fault_model.md) | Arithmetic, handshake, reset/clear, latency, planned fault boundaries |
| [`model/mac.py`](model/mac.py) | Independent integer and transaction reference; signed-wrap residue oracle |
| [`tests/`](tests/) | Arithmetic/protocol unit tests and cycle-by-cycle Verilator harness |
| [`scripts/generate_vectors.py`](scripts/generate_vectors.py) | Directed, exhaustive operand-pair, dot-product, and seeded stimuli |
| [`research/decision_log.md`](research/decision_log.md) | Implemented scope, tool availability, and outstanding plan gates |
| [`research/baseline_validation.md`](research/baseline_validation.md) | Initial checks, measured generic cell counts, and evidence limits |

The default core captures operands on `start && ready`, then commits on the next
rising edge. `done` and `result_valid` pulse for one cycle. Requests during busy
are ignored; synchronous reset aborts. See the specification before integration.

## Next milestone

Review the initial contract, then implement and verify the shortened 30-bit
SECDED codec and accumulator-only baseline. The conventional hybrid, TMR,
fault-injection harness, and proposed validation/commit mechanism remain future
work. The prior-art review and novelty gate remain open; this repository does
not establish research novelty or radiation hardening.
