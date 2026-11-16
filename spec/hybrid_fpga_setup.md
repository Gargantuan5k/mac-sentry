# Hybrid ZedBoard experiment setup (M3, accepted R4 capture repair)

Default board design: signed 8-bit operands, wrapping 24-bit accumulator,
MAX_RETRIES=2, ZedBoard xc7z020clg484-1, physical oscillator 100 MHz (Y9,
LVCMOS33, 10 ns constraint). This is a separate instrumented comparison build.
No board is available; **all physical H1–H15 tests are NOT RUN**. Local simulation
and generic synthesis do not establish routed timing or hardware behavior.

## Create a new project

From the assigned repository root, use a never-used path inside this repository:

```sh
vivado -mode batch \
  -source scripts/create_hybrid_project.tcl \
  -tclargs "$PWD/build/hybrid_vivado_session_001" build
```

Omit `build` to create IP/project only. The script refuses existing destinations,
outside-repository paths and open projects. It never opens the baseline or SECDED
sibling project. VIO 3.0 / ILA 6.2 are explicitly generated; only the listed RTL
and clock XDC are design sources. `tests/hybrid_debug_models.sv` is simulation
only and deliberately fails synthesis if accidentally read with SYNTHESIS.
No generated IP is replaced with a stand-in in the real build. Two jobs maximum;
normal Vivado DSP inference is retained and must be reported in comparisons.

The script requests synth_1, impl_1 through bitstream, hierarchical utilization,
min/max timing with unconstrained paths, DRC, methodology and matching hybrid.ltx.
Review all warnings, critical paths, clock coverage, setup/hold/pulse-width and
DRC before hardware use. A 100% run/bitstream alone is not timing closure.
Preserve failures; changing the period does not change the oscillator. Vivado IP
generation, implementation and timing remain NOT RUN in this worker session.

## Launch and fault timing contract

`hybrid_fault_sequencer` wraps a separate board core sharing the production
arithmetic include. Production ports remain unchanged; the added storage hook is
tied to zero in production and in the original injectable wrapper. The existing
portable core's saved inputs, decode, controller, checker and commit limitations
remain. This wrapper is not the ASIC submission core.

Apply VIO settings separately from start. A sampled low then high start_request
launches only when ready=1. On the launch edge E0, the core saves operands and
the sequencer latches both operands, all four masks and the attempt bitmap.
A nonzero storage_mask XORs the **actual registered codeword at E0**, suppressing
that edge's scrub; it does not add a cycle. The first busy attempt E1 decodes the
upset. Single errors are repaired there even if arithmetic retries; doubles
terminate error1 with damaged storage retained. This storage hook is launch-only,
not an idle standalone command or an arbitrary later-retry upset facility.
Later-retry storage injection remains a portable-core simulation capability,
not supported by this board sequencer.

attempt_select bits 0/1/2 select busy attempts E1/E2/E3 respectively; only attempts
actually reached execute. 001 is transient, 011 faults the first two, 111 persists
across all attempts. All three arithmetic masks share this bitmap; independently
timed masks per site are not supported. Unselected and nonbusy edges apply zero.
With usable storage and no other fault source, an unselected attempt succeeds
and ends the transaction. Only a contiguous selected prefix can therefore fire:
001, 011 and 111 exercise one, two and three faulty attempts if the masks cause
rejection; 101 behaves like 001, and 010/100/110 never reach a selected attempt.
A configured nonzero mask for an unreached attempt is **unfired**, not recovered.
Zero masks never acknowledge. Masks and operands changed live during busy cannot
alter the saved experiment. Clear/start while busy are ignored and never queued.
Idle clear wins over start and clears storage, count and saved board settings.

Reset and abort_request both synchronously abort and clear core/configuration;
reset has highest priority. They immediately gate applied masks but state changes
require a clock. After reset/abort, a sampled low start is required before a new
rising request. A held high request across reset, clear or busy cannot replay.
Abort deliberately discards the accumulator; it is not pause/resume.

`inject_fired` is registered evidence of the preceding sampled edge:

| Bit | Acknowledged action |
| ---: | --- |
| 0 | Nonzero launch storage XOR actually scheduled into raw storage |
| 1 | Nonzero candidate XOR sampled on a busy attempt with usable source |
| 2 | Nonzero prediction XOR sampled on a busy attempt with usable source |
| 3 | Nonzero post-check commit XOR on an accepted arithmetic candidate |

`fired_attempt` identifies that sampled attempt (zero-based), even on an attempt
with no firing. Storage launch reports 0. A visible commit XOR on a rejected
attempt has bit3=0; an uncorrectable source suppresses bits1–3 despite visible
combinational XOR. Count set bits **per sample**, not rising transitions: adjacent
fault attempts may keep an acknowledgement high for several cycles. `launched`
is a one-clock acceptance pulse. These acknowledgements are not independently
fault-protected and must be checked against before/after XOR and raw storage.

## Debug probes

All IP uses clk_100mhz; no CDC is introduced. Output directions below are relative
to VIO. Reset defaults to 1, all other outputs default to 0.

| VIO output | Width | Signal |
| --- | ---: | --- |
| probe_out0 | 1 | rst |
| probe_out1 | 1 | clear |
| probe_out2 | 1 | start_request |
| probe_out3 | 8 | operand_a |
| probe_out4 | 8 | operand_b |
| probe_out5 | 3 | attempt_select |
| probe_out6 | 25 | candidate_mask |
| probe_out7 | 3 | checker_mask |
| probe_out8 | 24 | commit_mask |
| probe_out9 | 30 | storage_mask |
| probe_out10 | 1 | abort_request |

| VIO input | Width | Signal |
| --- | ---: | --- |
| probe_in0 | 1 | ready |
| probe_in1 | 1 | busy |
| probe_in2 | 24 | accumulator |
| probe_in3 | 2 | error |
| probe_in4 | 2 | retry_count |

ILA: native, 1024 samples, zero input pipeline stages, all probes data+trigger.

| ILA probe | Width | Signal |
| --- | ---: | --- |
| probe0 | 1 | rst |
| probe1 | 1 | clear |
| probe2 | 1 | start_request |
| probe3 | 8 | operand_a |
| probe4 | 8 | operand_b |
| probe5 | 3 | attempt_select |
| probe6 | 25 | candidate_mask |
| probe7 | 3 | checker_mask |
| probe8 | 24 | commit_mask |
| probe9 | 30 | storage_mask |
| probe10 | 1 | abort_request |
| probe11 | 1 | start_pulse |
| probe12 | 1 | launched |
| probe13 | 1 | ready |
| probe14 | 1 | busy |
| probe15 | 1 | done |
| probe16 | 1 | result_valid |
| probe17 | 2 | error |
| probe18 | 24 | accumulator |
| probe19 | 30 | stored_codeword |
| probe20 | 1 | corrected |
| probe21 | 1 | detected |
| probe22 | 1 | retried |
| probe23 | 2 | retry_count |
| probe24 | 4 | inject_fired |
| probe25 | 2 | fired_attempt |
| probe26 | 8 | latched_a |
| probe27 | 8 | latched_b |
| probe28 | 3 | latched_attempts |
| probe29 | 25 | latched_candidate |
| probe30 | 3 | latched_checker |
| probe31 | 24 | latched_commit |
| probe32 | 30 | latched_storage |
| probe33 | 25 | applied_candidate |
| probe34 | 3 | applied_checker |
| probe35 | 24 | applied_commit |
| probe36 | 25 | candidate_before |
| probe37 | 25 | candidate_after |
| probe38 | 3 | prediction_before |
| probe39 | 3 | prediction_after |
| probe40 | 24 | commit_before |
| probe41 | 24 | commit_after |
| probe42 | 1 | source_usable |
| probe43 | 1 | commit_eligible |

ILA captures **pre-edge** signals. For start_pulse trigger at sample S, S+1 shows
launched=1,busy=1, latched settings and storage XOR acknowledgement; S+2 shows
attempt0 response and its fired bits. Clean done is S+2; one retry ends S+3;
two retries or exhaustion end S+4. Always retain S+5 to see pulse clearing.
Applied masks/before-after values at S+1 correspond to acknowledgements at S+2,
not to the acknowledgement in that same S+1 sample. Consecutive samples are
essential. `accumulator` on an uncorrectable word is diagnostic, never a result.

## Executable board checklist (every hardware case NOT RUN)

1. Record source hashes, Vivado version, part/clock, actual run names, reports,
   bitstream and matching LTX. Program only during an authorized physical session.
2. Set rst=1, clear=0, abort_request=0, start_request=0 and all masks/bitmap=0;
   apply, then release rst. Confirm ready=1,busy=0,raw word=0. Reset requires a
   clock; leave start low through at least one post-reset clock.
3. Before each independent row below, reset as above. For a continuation lower
   start and apply it before changing operands/settings. Apply all settings
   separately while start remains low. Signed operands use two's-complement bytes;
   masks are unsigned hex. Unlisted masks and bitmap are zero.
4. Use one ILA window, unconditional storage, depth1024, trigger position512;
   trigger on start_pulse==1, arm and wait for Waiting for Trigger, then raise
   start. A held request produces one launch. Inspect every edge through S+5.
5. Save each completed capture immediately under a never-used name. Record
   expected and observed state/status and all requested-but-unfired attempts.

| ID | Inputs/settings and sequence | Required observations |
| --- | --- | --- |
| H1 | a=34,b=55; continue a=15,b=10 | 1870 then2020, done/valid S+2, count0 |
| H2 | a=3,b=4; attempts=1,candidate=1 | XOR at S+1; ack bit1/retry/detected at S+2; acc0 until valid12 at S+3,count1 |
| H3 | Same,attempts=7 | Three ack/rejections, count2; done at S+4,valid0,error2,raw word0 |
| H4 | Same,attempts=3 | Two ack/rejections, third clean attempt valid12 at S+4,count2 |
| H5 | Repeat H2 with candidate=1<<k for k=0..24 | Every actual single-bit XOR detected; valid12,count1 |
| H6 | a=2,b=3; attempts=1,checker=1 | Prediction6 XOR1=7, ack bit2, one retry then6 |
| H7 | Seed1 using clean1*1; next a=1,b=-1,attempts=1,candidate=1,storage=4 | At S+1 raw XOR4,ack bit0; S+2 repaired encoded1,corrected/detected/retried1,ack bit1; S+3 accumulator0,result_valid1,count1 |
| H8 | a=3,b=4,storage=3 | Raw XOR3 at S+1; S+2 done1,valid0,error1,count0; raw damaged word retained; no arithmetic firing |
| H9 | Seed1 with clean1*1, confirm raw20000007; launch H3 settings; repeat separately for rst and abort_request on each of E1/E2/E3 | Before abort: busy1, count0/1/2, acc1/raw20000007. After abort: raw0/acc0/status0/config0,count0; no later done or held-start replay; rearm and clean2*3 yields6 |
| H10 | Seed1 with clean1*1, then H4 settings; during retry change operands/masks and raise new start with clear=1; release clear before next idle edge | Original13,count2; no queued request; latched masks unchanged; repeat a busy start with clear0 independently |
| H11 | Complete H3; lower start; idle clear1 then0; clean3*4 | clear zeros word/count/config; next valid12,count0 |
| H12 | 512 clean(-128)*(-128) transactions; then(-1)*1 then1*1 | 511th=8372224; 512th=-8388608; next8388607; next-8388608; no false alarm |
| H13 | a=0,b=0; attempts=1,candidate=7 | Ack bit1, wrong-valid7,count0: modulo escape |
| H14 | a=1,b=1; attempts=1,candidate=1,checker=1 | Ack bits1/2, wrong-valid0,count0: correlated escape |
| H15 | a=1,b=1; attempts=1,commit=1 | Ack bit3, wrong-valid0 encoded as valid SECDED: commit escape |

H9/H10 cannot be reliably driven by a human VIO click within a 10 ns retry window.
They are cycle-exact simulation cases in this milestone; physical execution
requires an additional reviewed synchronous stimulus source or equivalent
clock-controlled test setup. Do not report a manual missed request as coverage.
For each future H9 trace, trigger on the selected reset/abort input, retaining
at least 16 preceding and 64 following consecutive clocks. At pre-edge ILA sample
S+1/S+2/S+3 (for E1/E2/E3 respectively), confirm pending state1 and raw20000007;
the following sample must show zero raw and decoded state before any successor
launch. Release reset/abort, hold start high for four clocks to check no replay,
then sample start low before launching clean2*3 with every mask/bitmap zero.
Retain the successor completion and one following sample. If it lies outside
the window, preserve a separate linked capture; never claim an omitted edge.
H12 is executable by repeated VIO launches (slow); retain each launch and terminal
capture, plus association with the preceding known state. No unacknowledged raw
state seeding is an acceptable replacement.

Additional negative cases: all masks0 with attempts7 gives no fired bits; nonzero
candidate with attempts6 and clean first attempt terminates before those selected
attempts (unfired). Hold start through completion; assert start with idle clear;
release clear without lowering start; none may queue a launch. Capture reset/abort
with a held request, then lower/re-raise to prove rearming. H13–H15 are expected
silent escapes, not successful protection. All board tests remain NOT RUN.

## Export, analyze and archive hybrid captures (accepted R4)

In the physical session's Vivado Tcl console, set `mac_repo` to this checkout:

```tcl
source [file join $mac_repo scripts export_ila_capture.tcl]
mac_save_ila [file join $mac_repo results captures hybrid_session_001 H2_transient]
```

The exporter refuses overwrites. Repeat with a new name per capture. Use the
hybrid analyzer explicitly; the baseline/SECDED two-edge analyzers do not check
this sequencer. In a terminal at the repository root, after the physical session:

```sh
python3 scripts/archive_fpga_run.py --variant hybrid \
  --evidence-kind hardware-capture \
  --project build/hybrid_vivado_session_001 \
  --capture results/captures/hybrid_session_001/H2_transient.ila \
  --output results/runs/hybrid_H2_001
python3 scripts/compact_fpga_results.py --verify-only
```

Use a never-used output directory; repeat `--capture` to archive multiple exports.
CSV inputs are also supported. `.ila` files use their embedded `waveform.csv`;
the original ILA and any companion CSV are retained unchanged. Require all 44
named probes above, Vivado header/radix rows, consecutive buffer AND window sample
indices, zero ILA pipeline stages, and unconditional single-window sampling.
Probe hierarchy, numeric suffixes and bit ranges are accepted; ambiguous/missing
names, unknown/out-of-range values, unsupported radices and malformed rows are
analysis errors, retained with raw inputs and warnings. This mode is fixed to the
M3 8/24/retries2 board, independent of Make's portable width/retry overrides.

`--evidence-kind` is an explicit user provenance label, not independent proof.
Use `synthetic` for simulations/fixtures; omitted labels are `unspecified` and
cannot establish hardware provenance. Synthetic archives have no reported physical
board. Source snapshots at archive time do not prove which sources generated the
programmed BIT/LTX or the capture. Record build-time sources, tool versions,
programmed BIT/LTX hashes and session notes separately. Missing bitstreams/reports
remain warnings. Besides implementation-run files, hybrid mode preserves the
M3 project-root timing/utilization/DRC/methodology reports, hybrid.ltx and
build_identity.txt under distinct m3_ names in reports/ or build/. Their original
paths/hashes remain recorded; missing files are explicit warnings.
Archive creation is preservation, not a passing-test exit code:
the command can succeed while `tests.csv` contains FAIL/INCOMPLETE/ESCAPE or the
summary contains `analysis_error`. Inspect these files and manifest warnings.

The checker replays registered state and predicts each attempt from captured
launch settings, signed full candidate arithmetic, source SECDED decode and
actual raw word. It checks latched/live settings, selected masks, before/after
XOR, source/commit eligibility, raw storage transitions and delayed sampled
acknowledgements. It does not follow observed `done`, retry count or valid to
choose the expected completion edge. Busy input changes are ignored as specified.
Reset/abort clear nonzero state and rearm requests; idle clear wins over start.
Core saved operands survive idle clear even though board configuration clears.
The initial idle word/configuration is observed starting state, not proven history.
A busy prefix without captured acceptance is explicitly unknown/incomplete;
a continuity gap discards replay history and is recorded as a mismatch.
Even an unknown prefix must satisfy local status invariants: error3 and attempt3
are unsupported, retry requires detection/busy, and done requires valid or error.

Retain at least one pre-launch sample to verify the request edge, launch S,
terminal S+2 (clean/double), S+3 (one retry), or S+4 (two retries/exhaustion),
**and the following sample** to check pulse clearing. Reset/abort also need the
post-control state plus its successor; preserve the nonzero seed and rearmed
successor for the full H9 experiment. No capture/window/file boundaries are joined.
A terminal without its successor remains INCOMPLETE, even if its value looks right.

`tests.csv` uses the existing archive columns; hybrid `notes` contains JSON with
predicted outcome, terminal sample, attempt/retry counts, clean arithmetic oracle,
and requested/fired/unfired site-attempt pairs. Disabled arithmetic injection
(nonzero mask with attempt bitmap0) is recorded in notes.warnings. In incomplete captures the
remaining pairs are `unresolved`, not proven unfired. Acknowledgements are counted at
every sampled edge, including adjacent equal values. Requested commit masks on
rejected attempts and arithmetic masks with an unusable source are unfired.
`expected_acc` is the fault-aware prediction; `clean_acc` in notes is the separate
unfaulted result only when `clean_acc_usable=true`. For an unusable or tainted launch word
that number is diagnostic; it cannot certify correctness. `initial_tainted` and
`terminal_tainted` record lost trust separately from SECDED's current usability.
Observed uncorrectable storage, a changed usable source during an attempt, or
a valid arithmetic escape taints subsequent state. Re-encoding or scrubbing it
does not clear taint. Only an observed synchronous reset (including abort) or
idle clear clears it; busy clear is ignored. Gaps also lose trust. An initially
usable idle word is an observed baseline, not proof of its pre-capture history;
separate files never transfer or establish that history.
The legacy `fault_mask` column is the launch storage mask;
arithmetic masks and all raw probes are retained in `samples_decimal.csv` and the
original export. For uncorrectable storage, accumulator is diagnostic only.

| Status / action | Interpretation |
| --- | --- |
| PASS / hybrid_clean, hybrid_retried | Complete observed trace matches contract, source is usable with no observed taint, and result matches arithmetic relative to that decoded starting state; earlier history is not proven |
| PASS / hybrid_exhausted | Matches invalid-result/error2 termination and preserves usable, untainted launch data; not a valid arithmetic success |
| PASS / hybrid_uncorrectable | Matches invalid-result/error1 rejection and retained unusable raw word; diagnostic readback is not trusted and subsequent state remains tainted |
| PASS / hybrid_reset_aborted, hybrid_abort_aborted | Captured abort behavior matches; no completed MAC result |
| UNFIRED | Trace matches but one or more configured site-attempt requests did not fire; inspect the outcome and pair lists, never count as recovery |
| ESCAPE / hybrid_silent_escape | Fault-aware trace matches, but wrong result was accepted valid; a demonstrated limitation, never protection PASS |
| ESCAPE / hybrid_unusable_source_valid | Valid completion from an unusable launch word; no trustworthy starting arithmetic oracle, never PASS even if diagnostic arithmetic coincides |
| ESCAPE / hybrid_rejected_state_escape | Invalid terminal result nevertheless leaves usable changed data, or converts unusable launch storage into usable data; rejection did not preserve trusted state |
| ESCAPE / hybrid_tainted_source_valid | Valid result from state whose earlier observed corruption has not been cleared/reset; a usable codeword does not restore trust |
| ESCAPE / hybrid_tainted_state_rejected | Rejection leaves usable state already tainted by earlier observed corruption; no new data change is needed to withhold PASS |
| FAIL | Captured raw/probe/protocol mismatch; inspect `mismatches.csv` |
| INCOMPLETE | Missing history, gap, cutoff or missing post-terminal sample prevents the claim |
| BLOCKED / hybrid_ignored_start | Request was discarded by busy/reset/clear; not queued or a completed operation |

`capture_summary.csv` preserves existing meanings: complete MAC transactions are
fully observed non-aborted transactions, including rejected/failed/escape outcomes;
this count is **not a PASS count**. Aborts, unknown prefixes and parse failures stay
visible in events/summaries. `test_plan.csv` lists H1–H15 as NOT_RECORDED. Inspect
all outcomes, including captures with no arithmetic, rather than filtering to PASS.
The original unprotected/SECDED archive schemas and historical results are unchanged.

Optional raw-only preservation remains useful before analysis (no acceptance label):

```sh
mkdir -p results/hybrid_raw
# Choose a new archive ID; fail if it already exists.
python3 - <<'PYARCHIVE'
from pathlib import Path
import hashlib, json, zipfile
root=Path('.')
paths=[Path('build/hybrid_vivado_session_001'),Path('results/captures/hybrid_session_001')]
files=sorted(p for base in paths for p in base.rglob('*') if p.is_file())
# Snapshot the actual source tree too; archive immediately after the build,
# before edits, and compare these hashes with the build-time session record.
files += sorted(Path('rtl').glob('*.sv')) + sorted(Path('rtl').glob('*.vh'))
files += sorted(Path('fpga/zedboard').glob('*.sv'))
files += [Path('fpga/zedboard/zedboard_100mhz.xdc'),
          Path('scripts/create_hybrid_project.tcl'),Path('spec/hybrid_fpga_setup.md')]
if not all(base.is_dir() for base in paths) or not files:
    raise SystemExit('Missing actual build/capture directories')
with zipfile.ZipFile('results/hybrid_raw/session_001.zip','x',zipfile.ZIP_DEFLATED) as z:
    hashes={}
    for p in files:
        z.write(p,str(p)); hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('sha256.json',json.dumps(hashes,indent=2))
PYARCHIVE
```

Also preserve repository source snapshot/source hashes at build time, session
notes, programmed BIT/LTX hashes, timing warnings and all failed/unfired cases.
The archive above is raw preservation only, with no analysis or acceptance label.
A source snapshot at archive time does not by itself prove which source built
the programmed bitstream; preserve the separate build-time hashes/session record.
Do not overwrite prior experiments. Back up captures and build evidence together.

## R4 storage-miscorrection regression and board follow-up

R4 is an accepted repair after M7 in the supplied CR2-entry runner state. Original
M4 remains failed; current physical repair requires fresh host checks/review. No physical result
is inferred from CSV fixtures. The exact prior counterexample is now an executable
real-RTL archive test (all corresponding hardware actions **NOT RUN**):

At 100 MHz the default 1024-sample window spans only 10.24 microseconds. Manual
VIO writes cannot guarantee multiple launches inside it. A continuous multi-launch
board experiment requires reviewed clocked request/configuration stimulus, which
this single-launch fault sequencer does not provide. That board dependency is
NOT RUN/not implemented here. The individual second launch below can still show
an unusable starting word and non-PASS result, but separate captures cannot prove
continuous history or carry taint into a later usable-source launch. Do not use
conditional storage or join files to manufacture continuity.

1. Reset with clear/abort/start low, masks/bitmap0; release reset and sample start
   low. Launch a=03,b=04,storage=00000003,bitmap0. At S+1 require raw3 and storage
   ack bit0; at S+2 require done1,valid0,error1,raw3 retained. Retain S+3.
2. **Do not clear or reset.** Lower start for a sampled edge, set storage=00000004
   (other masks and bitmap remain0), arm on start_pulse, then raise start. The
   launch word is unusable raw3. At S+1 raw7 has syndrome0/odd parity and decodes
   as corrected word20000007/data1. At S+2 RTL returns valid13/error0/count0;
   clean arithmetic from the preceding trusted zero would be12. Retain S+3.
   Archive the entire two-launch sequence (or preserve linked raw exports; the
   checker never joins files). The second event must be
   **ESCAPE / hybrid_unusable_source_valid**, observed_acc13, never PASS.
3. Usable-source control: reset and launch the same 03×04/storage4/bitmap0.
   Raw4 is a single-bit upset of zero; at S+2 require valid12 and corrected1.
   Complete archive classification is PASS / hybrid_clean, with storage ack.
4. Additional control: after raw3/error1, launch storage3, returning raw0 and
   valid12. Despite this coincidence with diagnostic arithmetic, classification
   remains ESCAPE / hybrid_unusable_source_valid. Clear/reset is the required
   way to discard unusable state before a trusted continuation.

Use the export/archive commands above with new names such as R4_two_launch_001
and R4_usable_source_001. Preserve both injections, all raw words, acknowledgements,
status and successor samples. Missing acknowledgements/status errors yield FAIL;
missing history or terminal successor yields INCOMPLETE. ESCAPE here also covers
an uncertifiable valid source, without asserting an unknown true pre-fault total.
The direct reset/raw0 XOR7 -> valid13 control separately demonstrates a known
wrong result from a usable starting word. SECDED offers no three-bit guarantee.

### Rejection scrub and continuation — hardware NOT RUN

The 8 November R4 review repair also tests these real-RTL sequences. They expose
an existing limitation of SECDED beyond two flips; the production RTL is unchanged.
Use 03×04 throughout, rearm start low for a sampled edge between launches,
trigger on start_pulse and capture all 44 probes unconditionally in one window.

| Case | Settings / pre-edge samples relative to launch S | Required archive outcome |
| --- | --- | --- |
| A: rejected miscorrection | Reset/release; storage7, bitmap7, candidate1, checker/commit0. S+1 raw7/data1/storage ack1; S+2 scrubbed raw20000007, corrected1, candidate ack2/attempt0, detected/retried1; S+3 candidate ack2/attempt1; S+4 candidate ack2/attempt2, error2, valid0, count2, accumulator1. Retain S+5. | ESCAPE / hybrid_rejected_state_escape, initial0/observed1; all four requested pairs fired |
| A continuation | No reset/idle clear; storage/bitmap/all arithmetic masks0. S+2 valid13/count0; retain S+3. As an additional control, clear may be asserted only on A's busy attempt edges and released before its first idle edge. | ESCAPE / hybrid_tainted_source_valid even though current codeword is usable; busy clear cannot recover trust |
| A reset recovery | Assert reset for an edge with start low, release and sample low; masks/bitmap0; launch. S+2 valid12, retain S+3. | PASS / hybrid_clean |
| B: unusable then scrubbed | Reset/release; storage3/bitmap0 -> raw3/error1 at S+2, retain S+3. Without clear/reset rearm and launch storage4/bitmap7/candidate1. Raw7 and subsequent rejection/scrub match A, ending error2/acc1 at S+4. | First event PASS / hybrid_uncorrectable (taint retained); second ESCAPE / hybrid_rejected_state_escape |
| B continuation | No clear/reset; masks/bitmap0; launch -> valid13 at S+2. | ESCAPE / hybrid_tainted_source_valid; diagnostic clean_acc13 is explicitly unusable as an oracle. The last trusted zero plus 12 would be12. |
| B later rejection | No clear/reset; storage0/bitmap7/candidate1; all attempts reject, error2/acc13 at S+4. | ESCAPE / hybrid_tainted_state_rejected despite unchanged usable data |
| B idle-clear recovery | Start low, clear1 for an idle edge, release clear and sample low; all masks/bitmap0; launch -> valid12 at S+2, retain S+3. | PASS / hybrid_clean |

Export under new names such as R4_rejected_scrub_A_001 and
R4_rejected_scrub_B_001 using the export/archive commands above. Inspect raw
storage, actual acknowledgements, status and successor samples, including the
scrub on the first rejected attempt. Never count an error2 pulse alone as
successful preservation. The A/B rejection operations fit a single launch's
window; the continuous continuation tests require the clocked stimulus dependency
above. A separate capture starting at usable encoded1 can only test arithmetic
relative to that observed baseline; its scoped PASS cannot certify recovery from
the earlier corruption. Every listed board action is NOT RUN.

## Local reproduction and limits

`make test-hybrid-capture JOBS=2` compiles the actual M3 RTL with simulation-only
debug IP, exports pre-edge samples to Vivado-format CSV, and creates/compacts/verifies
a synthetic archive through the normal CLI. Literal outcome/latency expectations
and the independent SystemVerilog arithmetic/codec oracle check clean, retried,
exhausted, uncorrectable, six nonzero reset/abort timings, signed wrap, recovery,
busy changes, unfired attempts and the modulo/correlated/commit escapes. A separate literal RTL sequence
checks the two-launch raw7/result13 counterexample, usable-source result12 and
coincident-result unusable-source control; the old classifier guard is replayed
through archive creation and must fail that literal ESCAPE expectation. The
rejected-scrub sequences and reset/clear recovery siblings above also pass through
CSV and archive creation. Separate copied-analyzer mutations remove rejection
checking or carried trust, reproducing false PASS/acc1 and PASS/acc13 respectively;
literal ESCAPE expectations must reject both. Deliberately damaged
CSV/ILA fixtures test acknowledgements, XOR/raw storage, latch/eligibility probes,
wrong valid/status/retry bound, malformed inputs, gaps, busy prefixes, split
captures and cutoff/pulse clearing. Additional controls cover retained raw state,
false validity and stale acknowledgements after all six nonzero reset/abort
timings, adjacent retry acknowledgements and negative ILA extraction. Negative fixtures must preserve the exact
expected diagnostic in the resulting archive, not merely produce a nonzero exit.
Each run retains raw fixtures, expectations, commands/logs, source/fixture hashes,
checks and the compact archive in a unique `build/hybrid_capture/run_*/`. Failed
runs are retained too. Archive provenance explicitly disables Git index refresh;
the target checks metadata bytes/modes without relying on GIT_OPTIONAL_LOCKS.
The target also reanalyzes historical baseline/SECDED exports in new archives
and compares old fields/values (SECDED measured outputs byte-for-byte), leaving
originals unchanged. The unperformed SECDED plan is compared with a frozen
accepted-M7 reference; it had already grown after the historical capture archive. That is compatibility evidence, not a new board experiment.
These are **synthetic fixtures, not hardware evidence**.
The M3 trace intentionally ends at its last completion; R4 expects that final
transaction to remain INCOMPLETE rather than adding invented trailing samples.


`make test-hybrid-board JOBS=2` compiles the real wrapper/core with local debug-IP
stand-ins, compares all 11 VIO output pins, five VIO input pins and 44 ILA data
probe pins to their documented wrapper signals on every rising edge, runs an independent
integer/SECDED position oracle at every edge,
checks literal H outcomes and actual before/after XOR, and synthesizes the
portable sequencer/core (no debug IP) with Yosys `check -assert`. Tcl-only contract checks verify probe configuration and new-project refusal
rules; they do not run vendor tools. Isolated mutants must fail on exact first
assertions, including the expected cycle and any numeric diagnostic. Each run retains sources/hashes, tools,
commands/exit codes, raw pre-edge probe CSVs and logs in a unique
`build/hybrid_board/run_*/` directory, including failures.

The M3 review found that the earlier test omitted VIO output comparisons and
seeded H9 with zero. The repaired test seeds nonzero state for all six reset/abort
timings and observes raw and decoded clearing before rearming. Nine isolated
controls include operand and reset/abort probe swaps, abort retaining storage,
and busy reset retaining storage. Swaps must fail on the corresponding VIO
output diagnostic; storage-retention controls must fail on the immediate raw
storage-clear diagnostic. These are simulation checks, not physical probe proof.

Storage tests enumerate 30 singles and 435 pairs; candidate tests enumerate all
25 bits. These are directed mechanisms, not calibrated independent radiation
trials. No FPGA PPA, physical adjacency, radiation tolerance, research novelty,
protected commit, gate-level/shuttle acceptance or board result is established.
See docs/overnight_progress.md for actual local outcomes and remaining gates.
