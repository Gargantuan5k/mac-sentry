> Historical research record. Stage names and local `build/` paths below identify the original experiments; they are not clone prerequisites. Start with the [current project overview](../docs/project_overview.md) and [portable results](../docs/results.md).

# CR6 bounded pilot and matched FPGA cost validation

Accepted milestone: **CR6_1794085081502364837**, supervisor sequence8 with
review02 PASS, 8 November 2026. The supplied state accepts
M0/M1/M3/M5/M7/R4/CR2_1794085081502364837/CR6_1794085081502364837. Original M2 remains skipped, M4/M6
failed, R6 blocked and R2 pending historically. Those verdicts are unchanged.
R4's capture/taint repair and CR2's accepted protected physical flow remain intact.

CR6 integrates the preserved UNACCEPTED pilot, cost/process harness, TMR parent-XOR
repair and corresponding mutation location. Seven files were reused; the Python
cost harness additionally fixes the reviewed process-exit race and writes regular
files for negative-control evidence. Public arithmetic, interface, reset/clear,
retry and voting/repair semantics are unchanged. Shared Makefile and handoff
updates extend the accepted functionality. Current source identities and exact
historical differences are in `build/cr6_repair/historical_audit.json` and the
[handoff inventory](../docs/results.md).

Fresh local `make test-pilot JOBS=2` completed 429/429 trials; all 361 requested
fault trials were acknowledged (393 sampled events), and all 25 controls passed.
Fresh supervisor pilot run_e46nd7_8 records the same 429/429 trials and controls.
Fresh supervisor Vivado run_wei9weaj reproduces the table below with all 21 controls
matching; both runs are cited in accepted CR6 review02 and retained in the handoff
inventory. Historical M6 and R6 host runs below retain their original identity.
All four fresh and historical OOC rows remain failure_to_close. No timing-closure,
resilience/cost ranking, radiation-coverage or statistical-rate claim is made.
Prior-art/faculty, physical board and silicon remain NOT RUN.

## Reproduction and retained failures

Run `make test-pilot JOBS=2` and `make test-fpga-cost JOBS=2` from the workspace
root. An optional separate seed uses `python3 scripts/pilot_campaign.py --jobs 2
--seed 20261108 --per-site 16`. The full thirteen cumulative commands are in the
[handoff](../docs/project_overview.md). Every target creates a unique run with
copied sources, commands, versions, raw observations, failures and SHA256 manifests.
No existing project is opened. At most two build workers and one foreground
Vivado process are used. No board programming, bitstream or sibling project edit.

The pilot records its full planned denominator before compilation. Compilation,
missing tools, failed/timed-out simulations, malformed evidence and unfired
injections retain rows and fail the target. Expected fault-caused escapes,
detected failures and bounded transaction timeouts remain measurements. Directed
calibration and trace mutations are distinct from seeded samples. Calibration
mismatches and non-clean sampled fault-free controls fail the target.

## Predeclared pilot population

Default seed is **20261107**, Python `random.Random`, 8-bit signed operands,
24-bit wrapping accumulator, hybrid MAX_RETRIES=2. Default per-site count is 16;
the CLI bounds it to 1–64. Default total: **429 trials**: 29 directed calibration,
64 clean sampled controls, 256 matched functional faults, and 80 protection faults.
Calibration and classifier mutations never enter the sampled-fault denominators.

Every trial starts with synchronous reset, then an actual clean MAC `a0*b0` to
establish known state; it does not trust an arbitrary decoded launch word. The
independent Python oracle uses integer multiplication/addition and modulo 2^24,
not the protected models or replay of the injected logic. `a0,b0,a,b` are uniform
integers in [-128,127]. This warmup distribution does not span all 24-bit states;
wrap and exhaustive arithmetic coverage remain the existing regression's job.
Each matched tuple is replayed across all four implementations.

| Matched functional site | Sampling and physical injection |
| --- | --- |
| Accumulator data | Uniform logical bit 0–23. Actual unprotected accumulator bit, corresponding non-parity Hamming code bit for SECDED/hybrid, or one uniformly chosen TMR lane's raw state bit |
| Saved operand a or b | Uniform bit 0–7 in actual saved register; one uniformly chosen TMR lane, shared saved register in the other variants |
| Candidate arithmetic | Uniform low bit 0–23, before truncation/encoding/voting. Baseline and SECDED use a simulation-only force on actual `exact_sum`; hybrid/TMR use existing XOR hooks. The hybrid's extra sign bit is excluded from this matched population |

Register upsets occur between acceptance and attempt0, are deposited once, and
persist until RTL repair/overwrite. Candidate masks are held through either one
or three attempted edges, selected uniformly. A core that completes on attempt0
has one sampled event even if duration=3: manifests and results retain both the
requested duration and actual acknowledged count. TMR uses the same random lane
for all matched sites in a tuple; there is no inference of physical adjacency.

| Separate protection stratum | Sampling |
| --- | --- |
| SECDED/hybrid check storage | Uniform choice among five Hamming parity bits and the overall parity bit, one actual stored-bit upset |
| Hybrid predicted residue | Uniform bit 0–2, one or three attempted edges |
| Hybrid post-check commit | Uniform bit 0–23, at the actual accepted commit |
| TMR candidate voter | Uniform bit 0–23 of the shared voted candidate, at commit |

Unprotected has no corresponding added-protection stratum. Do not pool these
unequal populations or interpret their counts as full-design reliability. Busy
control corruption and multi-bit storage are directed calibration only. Decoder,
encoder, retry-counter, comparator, clocks/resets, configuration memory, analog
effects, placed nets and arbitrary correlated failures are not sampled. Existing
hybrid correlated-checker and TMR multiple-lane limitation tests remain required.

## Acknowledgement and observation

`tests/pilot_tb.sv` reads the actual target before and after each deposit/XOR/force.
`ack.csv` records both words, the physical mask, edge, attempt, reset and busy.
The analyzer requires the actual delta to equal the nonzero requested mask,
exactly the expected number of eligible attempt acknowledgements, the right
edge relative to accepted start, and non-reset/busy eligibility. Accumulator and
codeword storage evidence is cross-checked with the next pre-edge raw state. Saved
operand injections have before/after acknowledgement but are not stored as raw
operand fields in trace.csv; they do not receive that additional cross-check. Commit injection additionally
requires the real hybrid arithmetic acceptance signal. Eight real simulations
with injection disabled must be rejected (storage and candidate for every core),
even when their arithmetic is correct. Missing/incorrect acknowledgement and
wrong-edge mutation controls must also be rejected.

`trace.csv` retains every pre/post edge, raw accumulator/codewords or all TMR lane
states, status, diagnostic alarm, retry count and selected interface controls.
The target gets at most six observation attempt edges (normal hybrid bound is
three); a real shared busy1→0 upset calibrates lost-operation timeout. Two idle
edges follow the terminal/timeout window. A fresh `3*(-2)` successor checks latent
state without reset. Finally synchronous reset and a clean `1*1` prove reset
recovery. The parser checks continuity, capture tails, completion protocol,
accepted launch, known warmup/reset results and the documented retry bound.
No interrupted or incomplete capture can become recovery.

## Outcome definitions

Classification is relative to the independently intended clean state, never just
agreement with a replay of corrupted inputs. Every classification retains the
actual status and diagnostic alarm, so a wrong accepted answer with a diagnostic
pulse is still visible as an escape.

| Outcome | Rule |
| --- | --- |
| `clean` | No fault requested; correct primary and successor, no alarm |
| `recovery` | Acknowledged fault; correct primary and successor. Includes masked/no-effect outcomes (e.g. corrupted a multiplied by zero), not a claim that every physical register was repaired |
| `silent_escape` | Wrong result accepted as valid in the primary or successor, including SECDED miscorrection, shared-input, modulo, commit or voter escapes; diagnostic-only disagreement does not make it safe |
| `detected_failure` | Terminal invalid result with error, or detected successor failure, without a wrong-valid successor |
| `timeout` | Missing primary completion within the bounded window, or missing successor completion after a valid primary without a fault-free alarm |
| `false_alarm` | Fault-free sampled/calibration control reports protection alarm/rejection despite clean intended arithmetic |
| `unacknowledged` | Request was absent, wrong, ineligible, or at the wrong edge; invalid experiment retained in denominator and target fails |
| `infrastructure_or_harness_failure` | Compilation/process/evidence/protocol failure; row and reason retained and target fails |

False alarm means fault-free controls here; checker corruption is reported in
its own protection stratum as recovery or detected failure. A wrong-valid result
has precedence over an alarm. A failed primary's valid successor is compared
against the pre-operation state; successful primary successors use the intended
updated state. Raw storage after rejected work is retained even when unusable. A primary
rejection takes precedence over a missing successor: it remains detected_failure
(or false_alarm in a fault-free control), with the empty successor explicitly
retained. It cannot become recovery. Wrong-valid successors take precedence over
all such failure/alarm classifications.

Known outcomes include all four clean controls, state repair/escape, saved-input
escape, candidate masking/retry/escape, each shared busy timeout, SECDED two-bit
rejection and three-bit miscorrection, hybrid retry exhaustion, modulo-7 collision,
post-check commit escape, and TMR voter escape. Additional mutations of real RTL
traces exercise wrong-valid, latent wrong-valid, false-alarm, missing-tail/gap and
acknowledgement rejection; these are labeled classifier controls, not RTL faults.

## Repaired host comparison — measured, unaccepted

Source: `build/m7_handoff/run_umr5_3xg/unaccepted/fpga_cost/run_7h8j0nv2/results.json` and
`build/m7_handoff/run_umr5_3xg/unaccepted/fpga_cost/run_7h8j0nv2/manifest.json`. All rows used Vivado 2025.2.1,
xc7z020clg484-1, 10.000 ns, max_dsp_0, production_core_only_OOC.
These are routed out-of-context results, not board/debug-wrapper totals or ASIC PPA.

| Variant | Packed LUTs | LUT primitives | FFs | DSPs | Setup ns | Hold ns | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| unprotected | 87 | 115 | 43 | 0 | 2.131 | -1.167 | failure_to_close |
| secded | 210 | 240 | 51 | 0 | 0.210 | -1.161 | failure_to_close |
| hybrid | 355 | 381 | 75 | 0 | -4.875 | -1.114 | failure_to_close |
| tmr | 352 | 423 | 200 | 0 | -4.960 | -1.119 | failure_to_close |

All four routed with zero routing errors and all twelve reported timing-coverage
checks zero, yet all are **failure_to_close**. ZPS7-1 remains in each unmodified
DRC report. Roughly −1.1 ns hold at the OOC input boundary limits interpretation;
read setup and hold separately. No useful-throughput, energy, resilience or
protection-overhead ranking follows. This does not certify timing at the pins of
an implemented board wrapper.

The TMR routed check reported 197 physical lane flops representing 120 logical
lane register bits; 72 duplicate accumulator flops remain disclosed. Do not
subtract them without a measured alternative. The retained routed netlist has
zero `_mask` identifiers; the former mask XORs were moved to the parent in M6.
CR6 now adopts that exact TMR repair, with functional retesting. The manifest binds the M6 lane/datapath,
flow scripts and Makefile hashes; these hashes must not be silently replaced
with M5's. All design RTL and Tcl inputs match current CR6; the Makefile and Python cost
harness differ and are separately recorded. Current host gates/review remain required.

`build/m7_handoff/run_umr5_3xg/unaccepted/fpga_cost/run_7h8j0nv2/controls.json` records 21 controls;
`build/m7_handoff/run_umr5_3xg/unaccepted/fpga_cost/run_7h8j0nv2/summary.json` records failures=[],
complete_comparison=true and process_groups_quiescent=true. All control outcomes
match their recorded expected values (including intentional failures); a physical
timing failure remains a failure even if the evidence-generation target exits0.
Timeout control verification used a child that did not terminate itself, required
process-group cleanup and verified quiescence before another foreground launch.
CR6 also repairs the reviewed ProcessLookupError race and normal empty-group
SIGTERM label, with focused unit controls and the real timeout-child control.

## Preserved earlier rejected table

The preceding M6 record is preserved byte-for-byte as
`build/m7_handoff/run_umr5_3xg/unaccepted/M6/pilot_validation_original.md`. Its old TMR row
reported 415 packed LUTs, 199 FFs and −5.842 ns setup; it was instrumented/unmatched
and is not the repaired comparison above. This record does not overwrite or
relabel those earlier measurements. The old document's pending-fresh-run text is
historical and superseded only for the specified host run, not acceptance.

## Pilot boundary and recovery

`build/m7_handoff/run_umr5_3xg/unaccepted/pilot/run_84zhl9gj/summary.json` records 429 planned and 429
recorded trials with failures=[]; retained raw trials are
`build/m7_handoff/run_umr5_3xg/unaccepted/pilot/run_84zhl9gj/trials.jsonl`. The seed/site/timing/duration
manifest and source hashes are retained beside them. Calibration, matched
functional-site comparisons and variant-specific protection-site experiments
remain separate strata; the timeout/silent-escape outcomes are retained rather
than omitted. No pooled rate or radiation/physical adjacency claim is made here.
The final reviewer found the pilot's acknowledgement checks, independent oracle,
literal calibration, denominators and fail-closed analysis sound, but this is
still an unaccepted bounded pilot, not a final statistical study.


## Current local results and historical cross-check

Current pilot: `build/pilot/run_wa0s6tkw/summary.json`, with raw per-trial trace.csv,
ack.csv, process exits and logs; `build/pilot/run_wa0s6tkw/trials.jsonl` retains all
429 outcomes. Seed 20261107, per-site 16. Four clean calibrations plus 64 sampled
clean controls all returned clean. Twenty-five fault calibrations include four
real busy-control timeouts; no failed or timed-out trial was dropped.

The following strata are identical in the current pilot and both historical host
pilots run_84zhl9gj and run_y97lcuqm. Each sampled fault row has planned=requested=
acknowledged=16. Recovery includes masking; it does not certify every physical
register was repaired. No sampled fault row reports timeout or false alarm.

| Stratum / variant / site | Recovery | Silent escape | Detected failure | Total |
| --- | ---: | ---: | ---: | ---: |
| matched_functional/hybrid/accumulator_data | 16 | 0 | 0 | 16 |
| matched_functional/hybrid/candidate | 9 | 0 | 7 | 16 |
| matched_functional/hybrid/saved_a | 1 | 15 | 0 | 16 |
| matched_functional/hybrid/saved_b | 0 | 16 | 0 | 16 |
| matched_functional/secded/accumulator_data | 16 | 0 | 0 | 16 |
| matched_functional/secded/candidate | 0 | 16 | 0 | 16 |
| matched_functional/secded/saved_a | 1 | 15 | 0 | 16 |
| matched_functional/secded/saved_b | 0 | 16 | 0 | 16 |
| matched_functional/tmr/accumulator_data | 16 | 0 | 0 | 16 |
| matched_functional/tmr/candidate | 16 | 0 | 0 | 16 |
| matched_functional/tmr/saved_a | 16 | 0 | 0 | 16 |
| matched_functional/tmr/saved_b | 16 | 0 | 0 | 16 |
| matched_functional/unprotected/accumulator_data | 0 | 16 | 0 | 16 |
| matched_functional/unprotected/candidate | 0 | 16 | 0 | 16 |
| matched_functional/unprotected/saved_a | 1 | 15 | 0 | 16 |
| matched_functional/unprotected/saved_b | 0 | 16 | 0 | 16 |
| protection/hybrid/ecc_check_or_multibit | 16 | 0 | 0 | 16 |
| protection/hybrid/postcheck_commit | 0 | 16 | 0 | 16 |
| protection/hybrid/predicted_residue | 9 | 0 | 7 | 16 |
| protection/secded/ecc_check_or_multibit | 16 | 0 | 0 | 16 |
| protection/tmr/candidate_voter | 0 | 16 | 0 | 16 |

Calibration (29) is separate: clean4, recovery6, silent_escape11,
detected_failure4, timeout4. Thus the complete accounting is clean68,
recovery155, silent_escape184, detected_failure18, timeout4, false_alarm0,
unacknowledged0 and infrastructure_or_harness_failure0. These totals are bookkeeping,
not a pooled fault rate. The separate missing-tool control retains all 54 planned
infrastructure failures and exits1; its path and exact argv are in the main
controls.json. The 25 controls include eight real non-fired injections, four ACK
mutations, four classification mutations, two incomplete traces, two unmatched
manifest controls, four clean-sample gate controls and the missing-tool denominator.

Historical complete copies (originals unchanged):

- M6 cost `build/cr6_repair/historical/fpga_cost/run_7h8j0nv2/`, original 209
  manifest entries verified; M6 pilot `build/cr6_repair/historical/pilot/run_84zhl9gj/`,
  original 2226 manifest entries verified.
- R6 host cost `build/cr6_repair/historical/fpga_cost/run_wpiyr14o/` and pilot
  `build/cr6_repair/historical/pilot/run_y97lcuqm/`; respectively 209 and 2226
  original manifest entries verified. R6 review01 was PASS on technical scope,
  but snapshot archival failed on absolute symlinks, so R6 remains blocked.
  The host cost numbers/21 controls and pilot strata match the M6 values above.

Each cost copy materializes 77 historical absolute symlinks into regular files.
All 154 are bound to the original link's SHA256 and explicitly named original run
root; the old link text, relocated referent, hash and size are recorded in the
new run_*_copy.json files under build/cr6_repair/historical. Old manifests and
archives are byte-identical. Copying is packaging, not experimental validation.
Missing, outside-root or hash-mismatched referents fail closed. No supervisor
safety rule or old archive was changed. New cost controls use regular copies
from creation, so fresh host evidence does not recreate the archival defect.

All RTL, pilot Python/testbench and cost Tcl identities match both retained host
runs. Only current Makefile integration and the Python cost packaging/process
repair differ from those manifests. The full comparisons (including each old and
current SHA256) are in historical_audit.json; source matching alone grants no
acceptance. Current local report reanalysis `build/fpga_cost/analysis_idoxy30g/summary.json`
uses the new lossless M6 copy and checks all reports, production mask elimination,
redundancy and 21 controls (failures=[]). The command is python3 scripts/fpga_cost.py
--jobs 2 --analyze-run build/cr6_repair/historical/fpga_cost/run_7h8j0nv2.
The historical missing-tool children run_1odo7j22 and run_8oxgbp88 are also
copied under build/cr6_repair/historical/pilot, with 54/54 failure rows each;
`build/cr6_repair/historical_children.json` maps the old absolute references to
these new copies. No original controls.json is rewritten.

## Matched cost policy and limits

All four variants use Vivado 2025.2.1, xc7z020clg484-1, 8/24, 10.000ns clock,
0.200ns uncertainty, 0.200/2.000ns min/max input/output delays, max_dsp0,
flatten_hierarchy none and keep_equivalent_registers. Hybrid uses retries 2.
Synthesis/implementation are serial in-memory OOC projects with the same clock
source policy. DONT_TOUCH is added after TMR synthesis for the audited lanes;
canonical register membership and distinct arithmetic are checked after synthesis
and route. This is production-core cost only; no debug/injection wrapper cost,
board pin timing, power, energy or throughput comparison is supplied.

A complete validated report with any negative setup/hold/pulse slack is
failure_to_close, even if the evidence-generation target exits0. Missing tool,
process timeout, nonzero tool exit, missing/unmatched/inconsistent reports,
unrouted nets and retained production hooks remain separate failures and cause
target failure. No later variant launches until the preceding private process
group is quiescent; failed cleanup withholds hashes. Timeout and subsequent
child-PID absence controls execute real processes, not simulated PPA.

Known limits remain: shared saved inputs/source decode, SECDED multi-bit
miscorrection, modulo collisions, correlated checker faults, post-check commit,
shared voters/control and common-lane corruption. Pilot sampling covers no
physical radiation distribution, adjacency, arbitrary protection/control nets or
placed-netlist timing. Larger frozen campaigns, workload/width sensitivity,
confidence intervals under a justified distribution, faulted mapped netlists,
protected commit, faculty/prior-art review and board/silicon validation remain
future work. Hardware checklist inputs/masks/cycles and archive commands remain
in the [board backlog](../spec/board_validation_backlog.md); all unperformed cases
are NOT RUN. Accepted CR2 establishes its scoped physical/precheck/zero-delay GLS
result, not full sign-off or submission readiness. CR6 host gates and review
passed. CF handoff lifecycle acceptance/review and the complete final regression
remain required; final integration is not yet complete.

## Current implementation identity

| Input | Current SHA256 |
| --- | --- |
| rtl/mac_tmr_lane.sv | b1d70ab4694190bdbe7e7cb0b925292ac579449d4a241e6f547897e78e4e7c36 |
| rtl/mac_tmr_datapath.vh | e4a0d48586d690df8fbba40f93ab0e7a25ad0e11e0423943f94a4b80f36f0af3 |
| scripts/test_tmr.py | cfce18bfa07d8fe7386b4c5025e3573d6797ff7edcc86870da1744b804842183 |
| scripts/pilot_campaign.py | f584d3074f8fd39d1bf573db42740f4dae791e65c28abb641fb9b2933f75df9a |
| tests/pilot_tb.sv | 26339e321da193950912eb22e2bb3d14399fca92b88496ee3e9f2ec2ca586653 |
| scripts/fpga_cost.py | 8e8b85dc5f88238aea47368eed61fd33f5ac1b69ea907ada4149182756954a97 |
| scripts/fpga_cost.tcl | d69d80e040fe8e9c45d071c9e6c14fa3d65ee910c474fd9c27eaa16457a98557 |
| Makefile | 19519015891ea4e5a44d75d3518c1ed99b47c4b380c1e20a5902e40934bc713a |

Historical hashes are never replaced; original source snapshots/manifests and
current-difference audit are retained beside the full lossless copies.

## Historical CR6 worker packaging completion (before supervisor acceptance)

The previous worker completed the experiments and lossless copies, then timed
out while finalizing the inventory. Its full build archive-policy scan passed
(133,094 entries; zero symlinks excluding shared tools). The resumed worker
verified the retained regression log hashes, current source hashes and original
historical regular-file bytes, and reran the handoff and 11 focused controls.
See `build/cr6_completion/run_6usi94sf/resume_audit.json` and
`build/cr6_repair/full_build_archive_safety.json`. The final handoff binds the
closed packaging reports and current runner-state snapshot. This is evidence
packaging, not a fresh Vivado/ASIC result or acceptance. All prior-art, board and
silicon gates remain NOT RUN.
