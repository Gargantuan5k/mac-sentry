# mac_sentry

Portable RTL and reproducible verification for the soft-error-resilient integer
MAC research project. The starting implementation is the **unprotected comparison
baseline**, with signed 8-bit operands and a wrapping 24-bit accumulator.

The authoritative project and execution plans are in
[`../sop_docs`](../sop_docs/). The initial FPGA target is ZedBoard
(`xc7z020clg484-1`); its Vivado project is in `../mac_sentry_fpga`.
This repository contains the portable code and verification/archive tools.

The unprotected baseline has simulation coverage and a recorded ZedBoard MAC
transaction. SECDED, arithmetic checking, retry, and protected commit logic are
not implemented yet. Hardware functional results and timing closure are separate
checks; inspect each run's evidence before making a claim.

## Dependencies

| Workflow | Requirements |
| --- | --- |
| Python model, capture analysis and archiving | Python 3.10+; no pip packages |
| `make` targets and vector generation | Make and Python |
| Local RTL simulation and lint | Verilator; C++ compiler for simulation |
| Generic synthesis | Yosys with ABC |
| Vivado simulation | Vivado with XSim and Zynq-7000 support |
| FPGA testing | ZedBoard, power, USB JTAG, Vivado Hardware Manager and cable drivers |

The FPGA project uses Vivado 2025.2.1. Run terminal commands from this repository's
root. Tcl blocks run in Vivado's Tcl Console with your FPGA project open.

The examples assume this sibling-directory layout, anywhere on your computer:

```text
workspace/
├── mac_sentry/             # This repository
└── mac_sentry_fpga/        # Your Vivado project (.xpr)
```

The FPGA project is separate from this repository; supply your own project with
the wrapper and debug IP described below. In each new Vivado session, locate the
repository relative to the open project's directory:

```tcl
set mac_repo [file normalize [file join [get_property DIRECTORY [current_project]] .. mac_sentry]]
if {![file exists [file join $mac_repo rtl mac_unprotected.sv]]} {
    error "Repository not found: adjust the relative path used to set mac_repo."
}
```

If you use another layout, change `.. mac_sentry` to the relative path from your
Vivado project directory to this repository, and adjust terminal `--project`
arguments accordingly. `file join` handles platform path separators and spaces.

## Local verification

```sh
make all          # Python tests, two RTL configurations, lint, generic synthesis
make test         # Python tests and RTL regressions
make lint
make synth        # Technology-independent synthesis, not ASIC PPA or board timing
make test-rtl SEED=42
make test-rtl OPERAND_WIDTH=4 ACC_WIDTH=8
```

## Vivado behavioral simulation

[`tests/mac_tb.sv`](tests/mac_tb.sv) replays the Python vectors and checks arithmetic
and protocol signals each cycle. A mismatch stops simulation with diagnostics.

1. Run `make vectors` in this repository (only Python and Make are needed).
2. Open your `mac_sentry_fpga` Vivado project. For the ZedBoard, select part
   `xc7z020clg484-1`.
3. In the Vivado Tcl Console, set `mac_repo` as above, then source the setup script:

   ```tcl
   source [file join $mac_repo scripts setup_vivado_sim.tcl]
   ```

4. Select **Run Simulation > Run Behavioral Simulation**. The script configures
   **Run All**; if a simulation was already open, close it and relaunch.

The script sets simulation top to `mac_tb`, references the original sources, and
replaces simulation generics/XSim options with the 8/24 baseline configuration.
No connected board or pin constraints are needed for this simulation.

Expected default result:

```text
PASS: 155320 cycles matched the Python reference (SystemVerilog testbench)
```

Run the full 1.5532 ms of simulated time, not just an initial 1000 ns. Use signed
decimal radix for operands and accumulator. Keep `mac_tb.sv` in **Simulation
Sources**. For 4/8, change both generics and vector path/count to match generated
vectors. Local outputs under `build/w8_a24/` and `build/w4_a8/` are overwritten on
reruns; FPGA run archives below are preserved separately.

## How to test on FPGA

Use VIO for manual inputs and ILA for cycle-by-cycle observation in the existing
`../mac_sentry_fpga` project.

### 1. Confirm the hardware build

The design top is `zedboard_mac_top`; `mac_tb` remains the simulation top.
The wrapper connects the portable MAC, `vio_mac`, and `ila_mac` to the same
100 MHz clock, and converts a VIO `start_request` rising transition into one
`start_pulse`. Holding the request high must not repeatedly launch operations.
There is no request queue: issue requests only while `ready=1`.

The board XDC must include all three constraints:

```tcl
set_property PACKAGE_PIN Y9 [get_ports clk_100mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_100mhz]
create_clock -name sys_clk -period 10.000 [get_ports clk_100mhz]
```

The pin and I/O standard follow the
[ZedBoard master constraints](https://github.com/Digilent/digilent-xdc/blob/master/Zedboard-Master.xdc).
`create_clock` describes the oscillator to timing analysis; it does not generate
a clock. Pin assignment alone does not constrain timing. After changing the XDC,
rerun synthesis and implementation, review post-route setup/hold timing,
unconstrained paths and DRC, then regenerate the bitstream. A successful manual
test or bitstream generation alone does not establish timing closure.

In Hardware Manager, open the target and program the device with the `.bit` and
matching `.ltx` from the same build. Open the VIO and ILA dashboards.

### 2. Set VIO inputs and reset

The wrapper uses these VIO probe mappings (directions are relative to VIO):

| Probe | Width | Signal | Initial IP output value |
| --- | ---: | --- | ---: |
| `probe_out0` | 1 | `rst` | 1 |
| `probe_out1` | 1 | `clear` | 0 |
| `probe_out2` | 1 | `start_request` | 0 |
| `probe_out3` | 8 | `operand_a` | 0 |
| `probe_out4` | 8 | `operand_b` | 0 |
| `probe_in0` | 1 | `ready` | — |
| `probe_in1` | 1 | `busy` | — |
| `probe_in2` | 24 | `accumulator` | — |
| `probe_in3` | 2 | `error` | — |

Set and apply `rst=1`, `clear=0`, and `start_request=0`. Set operand radix to
hexadecimal and apply `operand_a=03`, `operand_b=FC` (signed 3 and -4).
Then apply `rst=0`. Confirm `ready=1`, `busy=0`, `accumulator=0`, and `error=0`.
Keep `start_request=0` until the ILA is waiting for its trigger. Keep operands
stable before launching; apply operand changes separately from the start request.

### 3. Configure and arm the ILA

The Native ILA is built with 1024 samples and zero input pipeline stages. Its
probes must have these names/connections so the archive analyzer can identify them:

| Probe | Signal | Width |
| --- | --- | ---: |
| `probe0` | `rst` | 1 |
| `probe1` | `clear` | 1 |
| `probe2` | `start_pulse` | 1 |
| `probe3` | `operand_a` | 8 |
| `probe4` | `operand_b` | 8 |
| `probe5` | `ready` | 1 |
| `probe6` | `busy` | 1 |
| `probe7` | `done` | 1 |
| `probe8` | `result_valid` | 1 |
| `probe9` | `error` | 2 |
| `probe10` | `accumulator` | 24 |

With the ILA stopped, use **ILA Core Properties / Capture Mode Settings** to set
one capture window, data depth 1024, and trigger position 512. Alternatively,
for this single-ILA design, run in Vivado's Tcl Console:

```tcl
set mac_ila [get_hw_ilas]
if {[llength $mac_ila] != 1} {error "Select the intended ILA explicitly; expected one core"}
set_property CONTROL.WINDOW_COUNT 1 $mac_ila
set_property CONTROL.DATA_DEPTH 1024 $mac_ila
set_property CONTROL.TRIGGER_POSITION 512 $mac_ila
```

In **Trigger Setup**, use just `start_pulse == 1`. Use unconditional capture
(every clock), not conditional storage or multiple windows. The analyzer requires
consecutive samples. Position 512 preserves 512 samples before the trigger,
the trigger sample, and 511 samples after it. At 100 MHz the full window is
10.24 microseconds. See
[AMD ILA control properties](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/run_hw_ila).

Click **Run Trigger**, not **Run Trigger Immediate**. Wait for **Waiting for
Trigger** before changing the VIO start request. The ILA cannot recover events
that happened before it was armed.

### 4. Launch and inspect the operation

In VIO, change `start_request` from 0 to 1 and apply it. Wait for the ILA capture
to complete and its waveform to display. Zoom around the trigger marker; set
operands and accumulator to signed decimal radix.

For the first test, expect:

| Sample | `start_pulse` | `busy` | `done` | `result_valid` | Accumulator |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trigger | 1 | 0 | 0 | 0 | 0 |
| Next | 0 | 1 | 0 | 0 | 0 |
| Following | 0 | 0 | 1 | 1 | -12 |

The ILA samples before register updates caused by that same edge become visible.
This accounts for the ordering above. The 24-bit hexadecimal result is `FFFFF4`.
`done` and `result_valid` last one clock, so inspect them in ILA rather than
expecting to see their pulses on VIO's interactive display.

### 5. Save, analyze, and archive the capture

Select the completed capture. In the **Vivado Tcl Console**, run:

```tcl
source [file join $mac_repo scripts export_ila_capture.tcl]
mac_save_ila [file join $mac_repo results captures signed_mac_001]
```

This saves `.ila` and `.csv`. Use a new base name if either already exists.
Save before taking another capture; automatic backup may retain only the latest.

Then, in a **terminal at the repository root**, run:

```sh
python3 scripts/archive_fpga_run.py \
  --project ../mac_sentry_fpga \
  --capture results/captures/signed_mac_001.ila \
  --output results/runs/zedboard_baseline_001
```

Use the same capture name in both commands. Choose a new capture/run suffix if
either name already exists; dates in run IDs are optional. For this
test, `tests.csv` should contain a `mac` row with initial accumulator 0, operands
3 and -4, expected and observed accumulator -12, and status PASS.
`capture_summary.csv` should show one complete MAC transaction; `mismatches.csv`
should have only its header. Inspect manifest warnings as well: a captured MAC
PASS does not imply the timing report passed or establish earlier state history.

### 6. Repeat and troubleshoot

- For another operation, apply `start_request=0`, change/apply operands, re-arm
  the ILA, wait for the trigger, then apply `start_request=1`.
- To test accumulation, continue from -12 with operands `02` and `05`; expect
  -2 (`FFFFFE`). Save with a new capture name.
- To test idle clear, keep the request low and trigger on `clear == 1` instead.
  Arm before asserting clear, capture the accumulator becoming zero, then return
  clear to zero. Restore the start trigger for later MAC tests.
- A waveform with no request/completion and zero complete MAC transactions is
  idle evidence only. Re-arm before raising the request; avoid Immediate Trigger.
- If stuck waiting, confirm `rst=0`, `clear=0`, and that the request was actually
  applied low before raising it. Confirm the trigger is on `start_pulse`.
- INCOMPLETE means the capture lacks consecutive samples through the event's end;
  check trigger position and unconditional storage. FAIL requires inspecting
  `mismatches.csv` and the corresponding waveform, not relabeling the result.

## Results structure and lifecycle

Every future archive should use `--output results/runs/<new-run-id>`, as in the
capture command above. The script compacts the archive automatically:

```text
results/
├── README.md                       # Index refreshed by the compaction utility
├── builds/
│   └── <content-hash>.zip           # Shared bitstream, probes, checkpoint, reports
├── runs/
│   └── <date>_<variant>_<board>_<sequence>/
│       ├── README.md               # Findings and evidence limits
│       ├── tests.csv               # Observed events: PASS / FAIL / INCOMPLETE
│       ├── capture_summary.csv     # Sample, transition and transaction counts
│       ├── mismatches.csv          # Expected versus observed signal values
│       ├── test_plan.csv           # Suggested tests; not measured results
│       ├── manifest.json           # Original file hashes, provenance, warnings
│       ├── storage.json            # ZIP locations, member paths and ZIP hashes
│       ├── sources.zip             # This run's source/IP/XDC/project snapshot
│       ├── source_changes.patch    # Tracked changes at archive time
│       └── captures/               # Original ILA/CSV and decoded sample data
└── captures/                       # Incoming exports awaiting archival; optional
```

### Run lifecycle

Follow FPGA steps 3–5: **arm → operate → export → archive → inspect CSVs**.
Keep each completed run unchanged; a new capture or build gets a new run ID.
Repeat `--capture` to include several recordings in one run. `test_plan.csv`
contains suggested tests, never measured results.

The script reads the existing Vivado project and artifacts; it does not program
or drive the board. It archives `impl_1` by default (`--impl-run` selects another).
If `--capture` is omitted, it reads saved `.ila` files in the project's
`.hw/backup/`, which may contain only the latest recording. Explicit capture
selection is preferable for a named experiment.

Build ZIPs are shared only when all included artifact/report paths and hashes
match. Each run retains its own source snapshot. `storage.json` maps original
paths such as `build/…` and `sources/…` to their ZIPs; open those ZIPs to inspect
or extract individual files. Original manifests and measurements remain intact.
The archived XPR retains original paths; consult `project_references` in the
manifest when relocating it.

### Integrity, cleanup and backup

Verify all runs without changing them:

```sh
python3 scripts/compact_fpga_results.py --verify-only
```

Optionally remove incoming exports already preserved byte-for-byte in a run and
refresh the run index:

```sh
python3 scripts/compact_fpga_results.py
```

The compactor verifies original file hashes and ZIP contents before removing
redundant originals. New archives are already compressed; this command is not
required after every run.

**Back up the entire `results/` directory, including `builds/`.** A run directory
alone references shared build ZIPs. Run archives, build ZIPs, and incoming captures
are Git-ignored; a repository commit does not back them up.

### What the evidence establishes

The analyzer assumes named probes, 8/24 arithmetic, zero ILA input pipeline
stages, and consecutive samples. It checks captured transitions against Python;
it uses the observed initial accumulator without proving earlier history.
Source snapshots identify files at archive time, not necessarily the files used
to produce the programmed bitstream. Collecting build files with a capture does
not independently establish their association.

Timing warnings, including nonzero `no_clock` or unconstrained-endpoint counts,
remain in the manifest. A functional PASS does not imply timing closure, and
absence of these particular warnings is not full sign-off. Resource reports
include VIO, ILA, debug hub and wrapper; they describe the instrumented design.

## Implementation

| Path | Purpose |
| --- | --- |
| [`rtl/mac_unprotected.sv`](rtl/mac_unprotected.sv) | Synthesizable parameterized baseline, one operation in flight |
| [`spec/mac_interface_and_fault_model.md`](spec/mac_interface_and_fault_model.md) | Arithmetic, handshake, reset/clear, latency, planned fault boundaries |
| [`model/mac.py`](model/mac.py) | Independent integer and transaction reference; signed-wrap residue oracle |
| [`tests/`](tests/) | Python tests, C++/Verilator harness and SystemVerilog/XSim testbench |
| [`scripts/generate_vectors.py`](scripts/generate_vectors.py) | Directed, exhaustive operand-pair, dot-product, and seeded stimuli |
| [`scripts/setup_vivado_sim.tcl`](scripts/setup_vivado_sim.tcl) | Configure the existing Vivado project for baseline simulation |
| [`scripts/export_ila_capture.tcl`](scripts/export_ila_capture.tcl) | Export the selected completed ILA capture |
| [`scripts/archive_fpga_run.py`](scripts/archive_fpga_run.py) | Analyze captured samples and create a compact run archive |
| [`scripts/compact_fpga_results.py`](scripts/compact_fpga_results.py) | Verify archives, deduplicate evidence and clean archived staging exports |
| [`research/decision_log.md`](research/decision_log.md) | Implemented scope, tool availability, and outstanding plan gates |
| [`research/baseline_validation.md`](research/baseline_validation.md) | Initial checks, measured generic cell counts, and evidence limits |

The default core captures operands on `start && ready`, then commits on the next
rising edge. `done` and `result_valid` pulse for one cycle. Requests during busy
are ignored; synchronous reset aborts. See the specification before integration.

## Next milestone

Close the baseline's timing-evidence gaps, review the interface contract, then
implement the shortened 30-bit SECDED codec and accumulator-only baseline.
The prior-art review and novelty gate remain open; consult the plans in
`../sop_docs/` for subsequent comparisons and fault campaigns.
