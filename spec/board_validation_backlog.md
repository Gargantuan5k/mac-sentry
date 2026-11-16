# Board validation backlog — resume here when the ZedBoard is available

These procedures preserve the exact inputs, fault masks, triggers and expected
observations needed for the next board session. Existing observations are
separated from unperformed cases below. The
[project overview](../docs/project_overview.md) and
[published results](../docs/results.md) describe the current delivered scope.
No new physical board tests were performed during the standalone packaging work.
Do not turn an expected result or simulation into a hardware PASS.

## Existing evidence and priority

Seven saved SECDED captures were analyzed and archived as
`results/runs/2026-11-06_secded_saved_captures_001/`:
A1, A2, A4 demonstrate arithmetic; B1/B2/B3 demonstrate raw single-bit injection
and repair. A3 is BLOCKED because clear remained high. C/D are not present.
All 7,161 adjacent transitions matched the SECDED model; this does not fill the
missing tests. The archive snapshots available artifacts, but does not independently
prove which bitstream was programmed when the older captures were taken.

**First board session:** repeat A3 correctly, then capture C1/C2/D1/D2 and reset
recovery. Re-run A1/A2/A4/B1/B2/B3 if a fresh, explicitly associated build is needed.
The existing `zedboard_secded_top` is ready for these tests. Hybrid testing uses the accepted M3 integration below but still requires
a real build/timing review; do not load hybrid RTL into the existing SECDED
project and assume its IP/probe definitions still match.

## Preparation and capture procedure

1. Open the separate `mac_sentry_secded_fpga` project. Preserve the unprotected
   project. Follow [SECDED setup](secded_fpga_setup.md) for sources and probe map.
2. Use the intended completed implementation, previously `impl_secded_perf`
   with `Performance_ExplorePostRoutePhysOpt`. Review current routed setup, hold,
   pulse-width, clock coverage and DRC. Previous +0.227 ns setup / +0.052 ns hold
   margins are historical; they do not certify a changed build.
3. Record source revision plus dirty changes, Vivado version, part, XDC, run name,
   strategy, bitstream and matching probe file. Program that `.bit`/`.ltx` pair
   immediately before the experiment and record names/hashes in session notes.
4. Use one ILA window, depth 1024, trigger position 512, pipeline stages 0,
   unconditional consecutive samples. Use the 16 probes in the setup guide.
   `corrected` and `stored_codeword` are **ILA** probes, not VIO inputs.
5. VIO: set/apply `rst=1`, `clear=0`, `start_request=0`, `inject_request=0`,
   `inject_mask=0`; then apply rst=0. Confirm ready=1, busy=0, accumulator=0.
   "Apply" means commit the edited VIO output value to the device.
6. Before each operation: lower/apply the corresponding request, set/apply
   operands or mask separately, arm ILA, wait for trigger, then raise/apply request.
   Save the waveform before another capture. Holding a request high fires once.
   Reset/clear must be released before raising start.

ILA shows pre-edge values. For start: trigger sample has start_pulse=1,busy=0;
next sample busy=1; following sample done=1,valid=1 with the committed result.
For idle injection: trigger sample inject_pulse=1; next sample inject_fired=1
and damaged raw word; following sample corrected=1 and repaired word for a single
error. Decoded accumulator can remain correct throughout single-bit repair.
One-cycle error/correction pulses will normally be missed by interactive VIO.

## SECDED tests using the existing build

Use signed decimal operands, hexadecimal masks/raw storage. Every independent
case starts from reset unless its setup explicitly continues an earlier case.
`clear pulse` below means apply clear=1 while idle, then apply clear=0; keep
start_request low through both changes. Re-arm after setup, before the action.

| ID / save name | Setup and trigger | Action | Required observations |
| --- | --- | --- | --- |
| A1_mac_34x55 | Reset; arm start_pulse=1 | a=34,b=55; raise start | 0→1870; done=1,valid=1,error=0 |
| A2_plus15x10 | Continue A1; lower start; arm start_pulse | a=15,b=10; raise start | 1870→2020; one valid completion |
| A3_signed_repeat | Clear pulse, **release clear**, ready=1; arm start_pulse | a=3,b=-4; raise start | 0→-12 (24-bit FFFFF4); valid completion. Old A3 did not run this MAC |
| A4_min_signed | Clear pulse; arm start_pulse | a=-128,b=-128; raise start | 0→16384 |
| B1_single_data | Recreate A1; idle, clean codeword; arm inject_pulse=1 | mask=00000004; raise inject | raw XOR 4, fired=1; next ordinary edge repairs; corrected=1, accumulator=1870 |
| B2_single_hamming | Same clean 1870; lower inject; arm inject_pulse | mask=00000001; raise inject | raw XOR1, fired then corrected; accumulator=1870 |
| B3_single_overall | Same clean 1870; lower inject; arm inject_pulse | mask=20000000; raise inject | raw XOR bit29, fired then corrected; accumulator=1870 |
| C1_double_data | Clean1870; lower inject; arm inject_pulse | mask=00000014; raise inject | two raw flips persist, fired=1, corrected=0. Idle error remains0; decoded data is diagnostic |
| C2_reject_mac | Continue C1 without clear/reset; lower inject/start; arm start_pulse | a=15,b=10; raise start | busy then done=1,valid=0,error=1. Damaged raw word unchanged; must not commit2020 |
| D1_clear_recover | Continue C2; lower requests; arm clear=1 | Apply clear=1; after capture release it | raw word=0, accumulator=0; ready=0 while clear,1 after release |
| D2_mac_after_clear | Continue D1 with clear released; arm start_pulse | a=3,b=4; raise start | valid result12,error=0 |
| E1_reset_recover | Recreate C1 damaged storage; lower requests; arm rst=1 | Apply reset; save; release reset | storage=0,busy=0,status=0; next ordinary MAC succeeds |
| E2_zero_mask | Clean1870; lower inject; arm inject_pulse | mask=0; raise inject | fired=0, no storage change, no correction |
| E3_no_repeat | Clean state; arm start_pulse | a=1,b=1; leave start_request high through capture | exactly one acceptance/completion within recorded window |
| E4_clear_blocks | Idle; apply clear=1; arm start_pulse | Raise start with a=3,b=4 | no busy/completion; storage stays0; analyzer reports BLOCKED as expected |

For C1 at 1870, clean word is hexadecimal 20007473 and damaged word is 20007467;
use captured raw XOR as the primary check. Readback changes do not establish
correction or validity. On C2 capture the short error pulse in ILA, not only VIO.
Reset between unrelated cases; do not silently carry C1 damage into another test.

The existing wrapper cannot reliably schedule in-flight injection, a busy-cycle
request, or reset during its one-cycle operation via manual VIO. Those priorities
are tested in simulation. Board coverage requires a clocked sequencer; do not
claim a manual attempt hit an intended cycle without ILA evidence.

## Save, archive and review

In Vivado Tcl, with `mac_repo` set as in README:

```tcl
source [file join $mac_repo scripts export_ila_capture.tcl]
mac_save_ila [file join $mac_repo results captures secded_session_002 C1_double_data]
```

Change the final name for each capture. The exporter saves both `.ila` and `.csv`
and refuses overwrites. Then from the repository root, for example:

```sh
python3 scripts/archive_fpga_run.py \
  --variant secded --project ../mac_sentry_secded_fpga \
  --impl-run impl_secded_perf \
  --capture results/captures/secded_session_002/C1_double_data.ila \
  --capture results/captures/secded_session_002/C2_reject_mac.ila \
  --output results/runs/secded_zedboard_002
python3 scripts/compact_fpga_results.py --verify-only
```

Add a `--capture` argument for each actual saved capture. Use a new output ID.
Inspect tests.csv, mismatches.csv, capture_summary.csv, and manifest warnings.
A correct C2 yields a passing `mac_rejected` event, not a successful arithmetic MAC.
INCOMPLETE needs recapture; unexplained FAIL/BLOCKED needs investigation.
E4 is deliberately blocked and must be documented as a priority test.
Keep original raw evidence and back up **all results/**, including shared builds/.
Results are Git-ignored. Record actual outcome, capture name, build identity,
trigger settings, expected/observed values and any anomaly for every case.

## Hybrid board integration — M3 accepted, hardware NOT RUN

The hybrid has an accepted clocked sequencer, separate ZedBoard top and
create-only Vivado script. See [M3 setup/probe map](hybrid_fpga_setup.md) for exact
launch settings, timing, build and archive commands. R4 adds the repaired
accepted `--variant hybrid` analyzer with host tests and independent review.
It rejects protection PASS for any valid result from an unusable launch word.
Historical M4 remains failed; software classification is not physical qualification. No board result or 100 MHz timing claim exists.
Preserve existing projects; the script creates a new project inside this checkout.

M3 acceptance covers the first three requirements below; real
Vivado implementation/timing remain NOT RUN and R4 capture analysis is accepted; physical captures remain NOT RUN
before physical qualification. Current implementation and remaining requirements are:

- The accepted `hybrid_fault_sequencer` instantiates `mac_hybrid_board_core`
  using the shared protected datapath at fixed 8/24/MAX_RETRIES=2. It implements
  request-edge detection and latches candidate25, prediction3, post-check commit24
  masks and the three-bit attempt bitmap at launch. Hold configured operands/masks
  stable until launch; use the exact probe/command map in the setup guide.
- The sequencer must apply a mask on exactly the selected busy attempt(s), then
  remove it. Manual VIO toggles cannot create a controlled 10 ns transient.
  Storage injection must mutate the real codeword with an explicit acknowledgement;
  M3 now supports an acknowledged launch-edge raw-storage XOR; arbitrary
  later-retry storage upsets remain simulation-only.
- Capture request, ready/busy/done/valid/error, operands, decoded accumulator,
  raw word, corrected/detected/retried/retry_count, configured/applied masks,
  injection acknowledgement and candidate/prediction before and after injection.
  Implement/check the sequencer in simulation before board use.
- Re-run synthesis/implementation and routed timing for this larger datapath.
  If timing fails, investigate the actual critical path. Changing constraints
  alone does not change the physical 100 MHz clock. Preserve the timing failure.
- Use the R4 `--variant hybrid` capture path for variable latency, retry bounds,
  fault acknowledgements and deliberate escapes. Follow its setup guide and
  inspect tests.csv, mismatches.csv, capture_summary.csv and manifest warnings.
  Keep all raw waveforms. R4 is accepted for software analysis; M4 remains failed.

## Planned hybrid hardware cases (all NOT RUN)

Each test starts from reset unless specified; default retry budget2. Trigger on
start/attempt/fault acknowledgement as appropriate; capture every attempt through
terminal status. Preserve raw storage to prove rejected attempts do not commit.

| ID | Transaction / injected event | Expected outcome |
| --- | --- | --- |
| H1 | Clean34*55, then15*10 | 1870 then2020; baseline latency, count0, no detected/retried |
| H2 | From0,3*4; candidate XOR1 on first attempt only | first attempt rejected with detected=1,retried=1,busy=1,acc0; next completes12,count1 |
| H3 | Same; XOR1 on all attempts | exactly3 rejected attempts, count2; terminal done1,valid0,error2,acc0; no hang |
| H4 | Same; faults on first two attempts only | third attempt valid12,count2 |
| H5 | candidate bits0..24, one at a time on first attempt | each detected and recovered; save applied mask and acknowledgement |
| H6 | From0,2*3; prediction XOR1 gives invalid7 | mismatch/retry; next intact attempt returns6 |
| H7 | Single storage XOR at accepted launch plus first-attempt candidate fault | source repaired and corrected pulse; no arithmetic commit until successful retry |
| H8 | Double storage XOR at accepted launch | first busy attempt terminal error1,valid0; no residue retry; damaged word preserved |
| H9 | Reset during retry | abort, clear state/status/count; no late completion |
| H10 | Change live operands, assert clear/start during retry | original saved transaction used; clear/start ignored while busy |
| H11 | Idle clear after exhausted retry, then clean MAC | count0,state0; next request succeeds |
| H12 | Accumulator wrap at both signed extremes | correct wrapped result with no false residue alarm; seed using a verified sequence, never unacknowledged state edits |
| H13 | From0,0*0, candidate XOR7 | deliberately undetected wrong-valid7 (modulo collision) |
| H14 | From0,1*1, candidate XOR1 plus prediction XOR1 | deliberately undetected wrong-valid0 (correlated fault) |
| H15 | From0,1*1, post-check commit XOR1 | deliberately wrong-valid0 stored with valid ECC (commit vulnerability) |

H13–H15 are expected limitations of the conventional baseline, not recovery PASSes.
Label them as observed silent escapes. Portable core regressions cover
MAX_RETRIES=0/1/3. The accepted M3 board sequencer is fixed at2; other board
retry configurations require further implementation and review, not just a build flag.
These experiments are mechanism tests, not a calibrated radiation campaign.

## M0 audit follow-up — 2026-11-07 (hardware NOT RUN)

M0 reruns are local simulation/software checks, not new board captures. All
previously listed missing cases remain pending; historical A3 remains BLOCKED.
The first physical session still follows the A3, C1/C2, D1/D2 and E1 sequence
above, including release of clear before start and new archive names.

Historical M0 proposals below predate accepted M3 (all hardware NOT RUN).
Use the M3 setup for executable launch-only storage injection; the second
proposal requires later-retry injection hardware that is still unavailable:

- Seed accumulator1 with a verified clean 1*1, then accept 1*(-1). On the first
  busy attempt XOR storage mask4 and candidate mask 1. Expect raw storage repaired
  to the encoded1, corrected=1, detected=1, retried=1, retry_count=1, busy=1,
  done=valid=error=0. Change live operands to0/0 and assert clear/start only while
  busy. The next clean attempt must commit0 using saved operands, done=valid=1,
  error=0, count1, with corrected/detected/retried=0. Release clear/start before
  the next idle edge: there must be no queued transaction.
- Repeat the first rejection, then apply storage mask3 (two Hamming parity bits)
  and candidate mask 1 on the next busy edge. Expect done=1,valid=0,error=1,count1,
  corrected=detected=retried=0; retain the damaged raw codeword. Arithmetic
  eligibility must be0 on this edge even though the candidate XOR is visible.
  Capture one following idle edge to prove error/done clear and count remains1;
  recover with an idle clear pulse before another request.
- Arm before acceptance, use consecutive ILA samples, and capture through the
  terminal edge plus one idle edge. With zero ILA pipeline stages, register
  effects appear in the following sample. Save exact configured/applied masks
  and actual sampled-attempt acknowledgement, not merely a changed XOR wire.
  Archive hybrid exports under a new run identity using `--variant hybrid` and
  the R4 setup guide. SECDED mode cannot validate these transactions. Later-retry
  storage stimulus needs a new reviewed probe/stimulus contract before analysis.

H3/H4 must also verify the last allowed attempt and terminal pulse clearing.
No manually timed VIO toggle is an acceptable substitute for a clocked fault
sequencer. No board execution or hardware coverage is inferred from M0.

### M0 review clarification — reset eligibility (hardware NOT RUN)

The repaired software negative control now requires reset while busy with a
usable source; an idle reset does not establish that reset suppresses an
attempt. Carry this requirement into H9 with the accepted clocked sequencer (hardware still NOT RUN):
reset to 0, release reset, accept 1*1, apply candidate mask 1 on the first busy
edge (expect detected=1/retried=1/count=1, busy=1, accumulator=0), then assert reset
on the next busy edge while mask 1 remains visible. Expect source raw word 0
before reset, attempt acknowledgement=0 on the reset edge, and after it
busy/done/valid/error/count/corrected/detected/retried/storage all zero. Release
reset and the mask, capture one idle edge with no late completion, then accept
1*1 and expect valid=1/accumulator=1 on its next edge.

Arm before acceptance, trigger on the sequencer's busy-reset event, and preserve
consecutive pre-edge ILA samples through recovery. An idle reset capture or XOR
wire change alone is insufficient. Save with `mac_save_ila` under a fresh
`results/captures/hybrid_session_001/H9_busy_reset` base with the accepted M3
hybrid wrapper; retain raw CSV/ILA and use R4 hybrid analysis from the setup
guide. R4 is accepted; original M4 remains failed.
No hybrid hardware, reset-in-flight capture or new board PASS is claimed by M0.

## M1 Tiny Tapeout interface bring-up (all hardware NOT RUN)

This is a separate future harness for `tt_um_mac_sentry`, not a change to the
existing ZedBoard projects. Exact mapping/opcodes/status are in
[asic/README.md](../asic/README.md). No hardware/programming action was performed.
A synchronous host or clocked sequencer must drive ui data and uio opcode/strobe
on falling clk edges and record uo after rising edges. Tie uio[7:5]=0; never drive
uo. All uio_oe bits are 0. Record every rising edge with clk, rst_n, ena, ui, uio,
uo, build identity and capture timestamps; no conditional sample gaps.

1. **TT1 reset and clean signed MAC — NOT RUN.** ena=1, rst_n=0, uio=0 for
   two rising edges; release reset and sample a low strobe edge. Trigger on the
   START request `uio=13` (hex), capture at least 16 preceding and 64 following
   clocks. Each command uses low strobe one edge, then high the next. LOAD_A:
   ui=03,uio=11; LOAD_B: ui=FC,uio=12; START: uio=13. Responses are 00. STATUS
   uio=10 returns busy bit0 until capture; from accepted START edge N, clean
   wrapper completion updates at N+2 (a read at N+2 still sees old busy).
   Poll for 06; DETAIL uio=18 expects00. RESULT uio=15/16/17 expects F4/FF/FF.
   Wait for the entire result before sending new START/CLEAR.
2. **TT2 accumulation/boundaries — NOT RUN.** Continue with 2*5, expect FE/FF/FF
   (-2). CLEAR uio=14, release strobe; STATUS/DETAIL/result all zero. From zero,
   run 512 transactions of ui=80,80 with STATUS=06 each, expect 00/00/80 at the
   end; then FF*01 expects FF/FF/7F. Capture every transaction or split into
   consecutive files with verified boundary continuity; do not infer omitted
   operations. This uses no accumulator preload or unacknowledged injection.
3. **TT3 protocol negatives — NOT RUN.** CLEAR; START without loads expects E3
   and STATUS=80. Try opcode9 and each reserved bit (uio=30,50,90), expect E1.
   CLEAR and LOAD both; hold START strobe high for eight clocks and change
   opcode to CLEAR without a sampled low: exactly one MAC, no CLEAR. Fresh
   START after completion without reloading expects E3. Scheduled LOAD/START/
   CLEAR at N+2 expects E2; prior result remains, no queued operation.
4. **TT4 abort/rearm — NOT RUN.** Accept 1*1 then assert rst_n=0 at N+1; no late
   completion, zero state. Repeat with ena=0 at N+1. Hold strobe high through
   re-enable for four clocks; no command until a low enabled edge followed by
   high. Outputs are zero during reset/disable. Include the actual abort edge
   and recovery MAC; idle reset alone does not prove pending-work abortion.
5. **TT5 fault/status observation — NOT RUN / requires a separately reviewed
   injection mechanism.** The production pins intentionally cannot inject.
   Simulation uses candidate XOR1 for 1*1: first-only yields STATUS46/DETAIL05;
   all three attempts yields STATUS52/DETAIL06, unchanged prior snapshot.
   Storage XOR4 during pending 0*0 over encoded1 gives STATUS26/detail00 and
   raw repair; XOR3 gives STATUS0A/detail00, invalid previous snapshot1 and
   retained damaged raw word. Also use double data mask14 over encoded1:
   live diagnostic data becomes2, but readback must retain snapshot1 with
   valid=0/error1. No on-board fault claim without actual mask,
   raw before/after acknowledgement, attempt alignment and terminal capture.

Archive raw host traces under a **new** directory; do not use the SECDED ILA
analyzer to certify this protocol. Example shell preparation (replace run ID):

```sh
mkdir results/captures/tt_interface_session_001
# Export hardware-tool raw waveform and CSV there as TT1_signed, TT2_wrap, etc.
# Copy the exact bitstream/netlist, constraints, tools and source-hash manifest.
sha256sum results/captures/tt_interface_session_001/* > results/captures/tt_interface_session_001.sha256
```

Do not overwrite that directory or hash file on a later session. Preserve failed,
incomplete, non-fired and timed-out cases with explicit outcomes. A future host
trace checker is still needed; these steps and expected values are a checklist,
not archived hardware PASS results. Existing A3/C/D priorities above are unchanged.

### M1 review additions (all hardware NOT RUN)

Extend TT3: after CLEAR, compute -12 (03*FC), then load 02/05. Independently
exercise malformed START requests uio=33/53/93/1B (request bit already included;
logical command encodings 23/43/83/0B). Each returns E1, DETAIL remains18, and
RESULT remains F4/FF/FF. No busy/completion or raw-state mutation is allowed.
The subsequent legal START13 must produce -2 exactly once, STATUS86 and DETAIL00;
protocol_error survives success. CLEAR14 must return all status to zero.
Use fresh setup for each malformed encoding and preserve each full trace.

Extend TT4: obtain response F4 with RESULT_LO15. Between rising edges pulse ena
low then restore high, then rst_n low then high; observe zero while each is low
and F4 after each restoration, with no clock edge during either pulse. Use an
oscilloscope/logic analyzer that resolves these between-edge changes, not only
clock-sampled capture. Follow with STATUS06 and F4/FF/FF to prove no abort.
Separately clock ena=0 while idle after a successful nonzero MAC: after enabling
and rearming, status/detail/result and accumulator must all be zero.

Extend TT5 only with a separately reviewed clocked injection mechanism: seed -12
via 03*FC; launch 01*01 at N. XOR candidate bit0 on all three attempt edges
N+1..N+3, acknowledge each changed candidate (-11 -> -12), retain raw state.
Replay separately for each requested opcode/edge, sampling low strobe before
each high request. At N+2/N+3/N+4/N+5 respectively expect STATUS01/41/41/52 and
DETAIL00/05/06/06; RESULT_LO/MID/HI remain F4/FF/FF at every edge. N+4 is wrapper
capture, so reads still reflect pre-edge state. Record from at least N-16 through
N+16; terminate as INCOMPLETE if capture misses any attempt or capture edge.
A clean 02*05 successor without clear must yield -2. Also test successful 02*07
over -12: reads on N+2 retain F4/FF/FF; later completed reads yield 02/00/00.
Archive using the fresh-run procedure above. These are directed mechanism checks,
not fault rates. Production pins provide no fault injection or raw-state readout.

### M1 second review additions (all hardware NOT RUN)

TT5 requires a separately reviewed injection mechanism; production Tiny Tapeout
pins do not offer injection or raw readout. For each of CLEAR, rst_n=0 and ena=0,
run each of these three fresh setups (nine traces): CLEAR, seed1 via01*01,
load00/00 and START; (a) XOR candidate1 ->0 on all three eligible attempt edges,
expect STATUS52/DETAIL06; (b) XOR raw mask03 after START and before completion,
expect0A/00 and retained damaged raw word; (c) XOR raw mask04 at the same point,
expect26/00 and repaired raw word. In every setup RESULT remains01/00/00.
Acknowledge exact raw/candidate changes and all attempt edges, then apply the
selected recovery. For reset/disable hold the input low across a rising edge,
restore it and sample strobe low to rearm. **Before any START**, read STATUS00,
DETAIL00, RESULT00/00/00 and verify raw zero if the reviewed harness exposes it.
Only then run02*03 and expect STATUS06, DETAIL00, RESULT06/00/00. Trigger on
recovery, retain at least32 preceding and64 following clocks, including fault
acknowledgement and terminal status; extend capture if necessary, never omit a
failed setup. Archive each trace with the fresh-run procedure above.

Additional idle cases: CLEAR, seed1 via01*01, load02/03, and sample strobe low.
With no pending work, XOR raw mask04 (acknowledge changed word and corrected
decode). Idle edge K repairs the raw word; K+1 observes the correction pulse.
Read STATUS26, DETAIL18, RESULT01/00/00 and repeat STATUS after three idle
clocks to confirm persistence. Replay separately for following START and CLEAR:
START must clear history and finish at STATUS06/DETAIL00/result07/00/00; CLEAR
must leave all readback and raw storage zero. Also replay with START or CLEAR
on K+1 (the arriving old pulse is overridden). Finally replay with START on K
itself: raw repair and operand acceptance coincide, pulse is observed at K+1,
and terminal status is26/detail00/result07/00/00. CLEAR on K instead discards
the damaged word, with no correction pulse or later sticky bit. Trigger on the
injection edge, retain at least16 preceding and64 following clocks, including
all read responses and raw repair. All six cases are NOT RUN on hardware.
No synthesized deliberate-fault mechanism or physical adjacency claim is added.


## M3 checklist update — 2026-11-07 (all hardware NOT RUN)

Use [hybrid setup](hybrid_fpga_setup.md) as the executable settings/capture guide.
The local target `make test-hybrid-board JOBS=2` covers H1–H15 with VIO/ILA
stand-ins, actual XOR/raw storage checks and literal expected outcomes. Exact
local results and source identity are in the M3 progress entry, not this hardware
checklist. No old SECDED A3/C/D gap is closed by these simulations.

The M0 follow-up later-retry storage3 injection is not supported by the board
launch-only hook. H7 injects on the launch edge so the first busy attempt repairs
it; H8 rejects a double upset on that first attempt. Portable hybrid regressions
retain arbitrary between-edge storage injection, including later retry faults.
H9/H10 clock-exact external control changes are simulated; physical execution
needs a reviewed synchronous stimulus source. Manual VIO clicks cannot claim a
10 ns reset/retry/clear experiment. Unfired attempts must be recorded as unfired.

Pending physical sequence: fresh new-project build → timing/DRC/clock review →
BIT/LTX association → H1 clean → H2/H3/H4 retry → H5/H6 arithmetic masks →
H7/H8 storage → recovery/priority cases where controlled → H12 verified wrap →
H13–H15 explicit escapes. Save one raw capture per case (all H5 masks separately),
retain post-terminal sample, source hashes and all warnings. Use the setup
guide's `--variant hybrid` archive procedure (accepted R4) and keep raw exports.
Archive creation is not a passing-test verdict; inspect every event and warning. Research matched TMR costs/protected-commit/campaign/novelty and physical ASIC
sign-off/submission gates remain separate and unfinished.


### M3 review repair: nonzero H9 and probe identity (hardware NOT RUN)

The prior simulation did not compare VIO output pins directly and H9 started
from zero. The repaired target checks each of the 11 output pins on every edge
and tests six independent nonzero H9 setups. Before each reset/abort timing,
reset then run clean01*01 with zero masks and verify accumulator1/raw20000007.
Launch03*04 with attempts7/candidate1 and other masks0. On each selected E1, E2
or E3 edge assert rst or abort_request; require raw0 and accumulator0 immediately
after that edge, cleared status/config/count, four clocks without held-start
replay, then a rearmed clean02*03 successor returning6. The setup guide gives
trigger/cutoff and raw archive commands. This remains a future clock-controlled
hardware test: manual VIO cannot target those 10 ns windows.

Use unequal operand values when validating the real VIO/ILA labels against the
probe map; arithmetic products alone cannot detect an operand swap. Preserve
source, BIT/LTX identities and captures for both reset and abort independently.
Old SECDED A3/double-error/recovery captures remain missing; no simulation closes
those gaps. R4 software acceptance does not establish M2 physical gates;
original M4 remains failed.


## M5 TMR comparison — executable preparation, hardware NOT RUN

The separate [TMR core/model](tmr_mac.md) has no board wrapper, VIO/ILA mapping or
TMR capture analyzer yet. `make test-tmr JOBS=2` creates uniquely named simulation
runs under `build/tmr/` with pre/post-edge raw state, actual XOR acknowledgements,
commands, versions, source hashes and retained negative-control traces. These
are simulation evidence only. M5 host acceptance/review is recorded in runner state.

Before a future board run, implement/review a separate clocked injector and
probe map covering three raw accumulator words, three saved operand pairs,
clean/perturbed candidates, both votes, busy/ready/done/valid/error/disagreement,
and sampled acknowledgements. Implement an appropriate archive decoder; do not
pass a TMR trace to the SECDED or hybrid checker. Reinspect target-synthesized
replicas and routed timing. No commands to program hardware are authorized here.

The following are exact future stimuli at default 8/24. All are **NOT RUN**:

| Case | Sequence / masks | Required observation |
| --- | --- | --- |
| Clean | rst1 for >=1 edge, clear0/start0/masks0; rst0; accept a=03,b=FC | Next edge done1/valid1/error0, all words FFFFF4 |
| Idle repair | Reset; accept1*1, complete; XOR one raw state by000001 between edges in each lane separately | Readback1, raw selected word0 and disagreement1 before scrub; next idle edge all words1 |
| Busy repair | Reset; accept1*1; XOR one raw state by800000 before next edge | XOR ack and divergence observed; completion all words1, done1/valid1/error0 |
| Saved operands | Reset; accept1*1; XOR saved_a or saved_b by80 in one lane | Candidate divergence but commit1; operand fault persists until next accepted start; successor1*1 gives2 |
| Candidate | Reset; accept1*1; XOR candidate000001 in each lane separately at commit | Real wire XOR ack, result1; remove mask and successor gives2 |
| Wrong majority | Reset; XOR state000001 in lanes0 and1 before scrub | Vote1 then all raw words1; no error; limitation, never protection PASS |
| Voter | Reset; accept1*1; candidate-voter output XOR000001 at commit | All words0, valid1/error0: explicit silent escape |
| Control | Reset; accept1*1; change common busy1→0 before commit | Ack, no completion/error within next two edges: dropped work |
| Priority/recovery | Seed1; reset while1*1 pending; later idle clear+start together | Reset aborts to raw zero; clear suppresses launch; release clear then1*1 returns1 |

Trigger on accepted start for busy faults and actual injection acknowledgement
for idle faults; retain >=2 pre-event edges, every intervening edge, the repair
or completion and a clean successor. ILA samples pre-edge values: the write at
edge N appears at sample N+1. Never stop capture at the trigger or terminal edge.
Apply clear low before arming, return start_request low between launches, and
keep reset/clear/injection masks at zero except for the named event. Record both
requested and fired masks, widths, source/build identities and original exports.

Once a reviewed TMR wrapper exists, use the existing create-only export command
with a fresh basename (export only; no TMR classification is currently available):

```tcl
source [file join $mac_repo scripts export_ila_capture.tcl]
mac_save_ila [file join $mac_repo results captures tmr_case_001]
```

Preserve the raw .ila/.csv and matching bit/ltx/reports and hashes unchanged until
a reviewed TMR archive mode exists. Do not claim a hardware PASS from these
planned values. Historical SECDED A3/double-error/recovery, hybrid board tests,
M2 physical gates remain open; R4 software repair is accepted
(original M4 remains failed).


M5 software handoff update: `make test-tmr JOBS=2` and all seven cumulative
commands passed locally; exact runs/counts/hashes are in the final M5 progress
entry. M5 is now accepted in runner state; the following hardware scope remains pending. Every TMR hardware case
above remains **NOT RUN**; this software result does not change the historical
SECDED A3/double-error/recovery gaps or authorize hardware programming.


### M5 review repair and priority captures — 2026-11-07

Attempt1 software counts above did not prove reset/start priority: review found
correlated low-bit random stimulus. The repaired tests add separate high-bit
control draws, directed priority tests, gate traces and mandatory measured cross
counts. See the latest M5 progress entry for actual local results; M5 is now accepted in the supplied runner state. All hardware actions below are **NOT RUN**.

Extend the future TMR Priority/recovery capture with masks0 and a=b=01:
seed accumulator1 with one accepted MAC before each reset/clear check. At idle,
assert rst1/start1 for one edge: raw states0, busy0/done0/valid0. Separately accept
1*1 then assert rst1/start1 on its busy edge: same zero state/status, no completion.
With reset0 and idle state1, assert clear1/start1: state0/busy0/no completion.
For busy clear1/start1 after accepting1*1 from state1, expect state2 and
done1/valid1/error0; release clear/start next edge and confirm no queued work.
Finally reset, release reset/clear and hold start1 for four edges: accept,
complete1, accept while previous done is visible, complete2. Release start and
observe two idle edges without another completion. Trigger on each combined
control event and retain two pre-event and two successor edges. Use the raw
export command above and fresh basenames; no TMR archive PASS mode exists.

M5 repaired software target and all seven cumulative checks passed locally;
see the latest progress entry for measured protocol crosses and source hashes.
M5 host acceptance/re-review is complete in runner state; physical tests are pending. All planned hardware actions stay NOT RUN.

## R4 operator reconciliation — all new hardware NOT RUN

The original failed M4 analyzer falsely passed a storage miscorrection. R4 repairs
that path: use `--variant hybrid` as documented in the setup guide, inspect all
classifications and keep raw exports and exact BIT/LTX/source identities. R4
is accepted in the supplied CR2-entry state; original M4 remains failed. Hardware H9/H10
requires clocked stimulus; launch-only storage XOR cannot inject on a later retry.

M6's repaired host pilot and four-core OOC costs were run, but M6 failed review
and remains failed. CR6 separately accepts that repaired TMR source and flow;
host pilot run_e46nd7_8, cost run_wei9weaj and review02 passed. See [research record](../research/pilot_validation.md)
for historical measurements, accepted host results and matching design/Tcl hashes. All rows fail timing closure; no board-clock or
resilience ranking follows. TMR wrapper/decoder and board physical-independence validation remain pending;
CR6 host OOC redundancy inspection passed for its scoped comparison. A3/C/D, TT1–TT5, H1–H15 and TMR cases above
retain their hardware NOT RUN status except explicitly historical saved captures.
CR2 separately supplies accepted scoped ASIC closure/zero-delay GLS/prechecks.
Prior-art/faculty gates, full sign-off and submission remain pending.


### R4 two-launch storage test — hardware NOT RUN

Follow the [exact R4 sequence](hybrid_fpga_setup.md#r4-storage-miscorrection-regression-and-board-follow-up):
reset/low start, 03×04/storage3/bitmap0 -> raw3/error1, lower start, **no clear**,
03×04/storage4/bitmap0 -> raw7/data1/valid13. Expected second archive event is
ESCAPE / hybrid_unusable_source_valid; the preceding trusted zero implies clean12.
Reset and repeat only the second launch as the usable-source control: valid12,
PASS / hybrid_clean. Trigger each start_pulse, unconditional 44-probe sampling,
retain pre-launch and terminal-plus-successor samples, storage ack bit0 and raw
words. Prefer a single window containing both launches; separate files do not
prove shared state history. Use fresh export names and the hybrid archive command
from the setup guide; never mutate saved captures. The RTL/CSV regression is
synthetic evidence only. Prior-art/faculty, physical board and silicon stay NOT RUN.

### R4 rejected-scrub follow-up — 8 November 2026; hardware NOT RUN

The first R4 candidate passed its tests but failed review on error2 state
preservation and tainted continuation. Follow the [rejection-scrub checklist](hybrid_fpga_setup.md#rejection-scrub-and-continuation--hardware-not-run)
with a continuous 44-probe capture. A: reset, 03×04/storage7/bitmap7/candidate1
-> raw7, then scrubbed20000007, three candidate acknowledgements, error2/acc1:
ESCAPE / hybrid_rejected_state_escape. B: reset, storage3/bitmap0 -> error1,
then no clear/reset, storage4/bitmap7/candidate1 -> error2/acc1, then masks0
-> valid13: ESCAPE / hybrid_tainted_source_valid despite usable encoded data.
Retain start rearm, every retry/ack, terminal and successor. A busy clear must
not restore trust; reset and idle-clear siblings each produce clean12/PASS.
A later state-preserving rejection while tainted must remain non-PASS. Use
fresh R4_rejected_scrub_A_001/B_001 exports and the setup guide's hybrid archive
command. Every board step remains NOT RUN; only synthetic RTL fixtures exist.

Continuous multi-launch board traces additionally require reviewed clocked
request/configuration stimulus; the current sequencer automates fault timing
within one launch only. Manual VIO cannot guarantee two launches within the
10.24-microsecond default window. This stimulus dependency is NOT RUN and is
not implemented by R4. Separate captures can demonstrate each rejected scrub
or an unusable-source valid escape, but cannot establish carried taint or safe
continuation. Do not join files or use conditional sampling to hide gaps.

## CR2 physical-flow handoff — all new board/silicon tests NOT RUN

The current physical candidate uses the production hybrid at 20 MHz (50 ns),
2x2 tiles; it does not change the 100 MHz FPGA test contract. Use the existing
H1–H15/R4 input masks, edge triggers, reset/clear sequencing and archive commands
above when hardware becomes available. No physical capture is replaced by GLS.
Review [ASIC validation](../asic/validation.md) and the supervisor's new routed
reports before considering a silicon test plan. Pin-only GLS checks clean
transactions; it does not establish on-silicon fault injection, radiation response,
submission or complete sign-off. A3 held clear and missing C/D evidence stay open.


CR2 attempt 1 host update (8 November 2026): TT prechecks and zero-delay mapped
GLS passed on run_us59qtx3, but four slew corners failed; that run remains FAIL.
Attempt 2 host run_c5xb3gza subsequently passed all required physical, precheck
and GLS stages at 50 ns / 2x2. Worst setup/hold are +12.03/+0.080 ns at max_ss,
all nine corners have zero setup/hold/slew/cap/fanout violations, physical
DRC/LVS/XOR/antenna counts are zero, and 15/15 prechecks passed. Zero-delay GLS
passed 777 transactions, 2 aborts and 15,642 samples with both negative controls
failing as intended. Its hashed evidence and warnings are in ASIC validation.
CR2 is accepted in the supplied state; SDF simulation and full sign-off remain pending;
no silicon readiness or hardware result follows. This does not alter any A–H
board input, mask, trigger, cycle expectation, reset/clear or archive instruction.
All pending board/silicon cases above remain NOT RUN.

## Historical CR6 preparation (subsequently accepted) — 2026-11-08T03:30:09.631435+00:00

CR6 restores executable software pilot and matched core-only OOC targets; it
does not add a board wrapper or change the pin/probe/transaction contracts above.
Run make test-pilot JOBS=2 for the calibrated 429-trial RTL experiment and
make test-fpga-cost JOBS=2 on the prepared host for four matched core reports.
The [pilot record](../research/pilot_validation.md) separates seeded functional
from protection sites and retains escapes, timeouts and non-fired controls.
Historical host OOC reports fail timing closure for every variant; they cannot
authorize programming or certify a board clock. New CR6 host gates/review remain
required. Accepted R4 archive use and CR2 scoped physical checks are unchanged.

All existing executable hardware inputs, masks, triggers, expected cycles/status,
reset/clear sequences and archive commands above still apply. First physical
session remains A3 then C1/C2/D1/D2 plus reset recovery; H/TT/TMR checks remain
NOT RUN. Save actual raw traces and ACKs in new archives, including escapes and
failed or incomplete trials. No physical board, silicon or prior-art work was run.

### CR6 final evidence packaging (8 November 2026)

Lossless pilot/cost evidence packaging is complete for supervisor validation.
It adds no board measurement and changes none of the executable sequences above.
A3/C/D, hybrid/TT/TMR hardware, physical board and silicon remain NOT RUN.
Use the updated research/pilot_validation.md and handoff inventory for provenance.

## CF lifecycle reconciliation — 2026-11-08T06:57:56.096564+00:00

CF handoff lifecycle checks do not change any board stimulus or measurement.
R4/CR2/CR6 remain accepted in their software/physical-flow scopes; M4/M6 failures
and R6/R2 historical states remain unchanged. Use the current overnight explainer
and the hash-bound source/acceptance inventory when moving to another machine.
Without .context, only the preserved as-of status is checked, not newer acceptance.
CF focused acceptance/review and the full final regression are still required.

Before real hardware work, follow the existing exact mask/trigger/cycle checklist:
release held clear for A3, capture C/D rejection and reset/idle-clear recovery,
preserve raw words and actual ACKs for H cases, and retain terminal-successor
samples. Archive under new run IDs using the already documented commands. Every
new A3/C/D, hybrid, TT and TMR board/silicon action remains NOT RUN. SDF/full sign-off,
prior-art/faculty review and submission remain outside this handoff repair.

## CF feedback01 repair — 2026-11-08T07:11:29.941558+00:00

This review repair changes only handoff consistency checks and current records.
CR6 sequence8/review02 acceptance (host run_e46nd7_8 and run_wei9weaj) supplies no
new board measurements. All inputs, masks, triggers, expected cycles/status,
clear/reset sequencing and archive commands above are unchanged. Repeat A3 with
clear released, then C1/C2/D1/D2 and reset recovery when hardware is available;
all those new captures and hybrid/TT/TMR/silicon tests remain NOT RUN. Preserve
raw ACKs/storage, terminal successors and all failed/incomplete traces in new
archives. Portable checking without .context retains only the frozen as-of
acceptance scope. CF review and all13 final gates remain open; SDF/full sign-off,
prior-art/faculty and submission are not completed by this repair.

## CF_1794122342797745439 — 2026-11-08T07:49:39.610172+00:00

This successor handoff repair reuses the prior candidate while preserving
CF_1794119005467435737 failed. CR6 sequence8, R4 and CR2 acceptance are unchanged.
Use the new as-of snapshot in the final explainer; a relocated checkout without
.context cannot establish subsequent CF acceptance or final regression success.
No board settings or functional source changed. All new board actions remain
NOT RUN: repeat A3 with clear released, then C1/C2/D1/D2 and reset recovery using
the exact masks, triggers, expected cycles and archive commands above. Preserve
raw storage/ACKs and terminal-successor samples in new archives. Hybrid/TT/TMR
and silicon measurements, SDF/full sign-off, prior-art/faculty and submission
remain pending. Local handoff checks cannot complete any of those gates.
