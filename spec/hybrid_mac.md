# Conventional hybrid: SECDED + modulo-7 check + bounded retry

This implemented comparison architecture is separate from `mac_unprotected` and
`mac_secded`. It is also distinct from the future independently protected commit
architecture. A separate [TMR baseline](tmr_mac.md) provides a redundancy comparison.
See the [current project overview](../docs/project_overview.md) and
[published results](../docs/results.md) for the measured scope and remaining work.

## Arithmetic and protection boundary

For decoded signed accumulator A and saved signed operands a,b, compute the full
signed candidate T = A + a*b in ACC_WIDTH+1 bits. Supported configurations require
OPERAND_WIDTH >= 2 and ACC_WIDTH >= 2*OPERAND_WIDTH. Under these conditions the
full sum fits; the normal result is its low ACC_WIDTH bits, interpreted as signed.

Predict r = (A mod 7 + (a mod 7)*(b mod 7)) mod 7 using narrow residue arithmetic.
Separately reduce the full candidate modulo 7. Commit only if both canonical
residues (0..6) agree. Encoding 7 on the predicted side is rejected.

Checking the full sum **before truncation** avoids trusting an overflow flag or
carry to adjust a wrapped result. In general `(T mod 2^W) mod 7` differs from
`T mod 7`; comparing an unadjusted wrapped residue would reject correct overflow.
The RTL reducer sums 3-bit chunks because 2^3 mod 7 = 1, then subtracts
2^WIDTH mod 7 for negative two's-complement inputs. Python uses integer `% 7`,
providing a different implementation of the same mathematics.

All single-bit flips in the full candidate change its signed numeric value by
±2^k, which is never divisible by 7, so an intact checker detects those flips.
Multiple-bit errors whose numeric change is a multiple of 7 can escape.
This is not a guarantee about arbitrary physical faults in multiplier internals.

## Transaction contract

Default parameters: OPERAND_WIDTH=8, ACC_WIDTH=24, MAX_RETRIES=2.
The storage format and decode/idle-scrub policy are those of
[the SECDED contract](secded_accumulator.md). Production ports add `detected`,
`retried`, and `retry_count` to the SECDED interface. No production fault ports.

| Event at rising edge | Outcome visible after edge |
| --- | --- |
| Synchronous reset | Abort pending work; clear storage, operands, status and retry count |
| Idle clear | Clear storage and retry count; start not accepted |
| Idle start, reset/clear low | Save operands, busy=1; retry_count=0 |
| Busy, uncorrectable storage | done=1, valid=0, error=1, busy=0; damaged word retained |
| Busy, matching residue | Encode and commit low ACC_WIDTH candidate bits; done=1, valid=1, error=0, busy=0 |
| Busy, mismatch, retry budget available | Preserve logical accumulator; detected=1, retried=1, increment count; remain busy, done=0 |
| Busy, mismatch, budget exhausted | Preserve logical accumulator; detected=1, retried=0, done=1, valid=0, error=2, busy=0 |

`MAX_RETRIES` counts **extra attempts**, not the initial attempt. Default is at
most three attempts. Zero disables retry. A clean transaction retains the baseline
capture-edge / next-edge-completion schedule; each rejected attempt adds one clock.
An intact single-error-corrected source codeword is written back even if arithmetic
is rejected; `corrected=1` on that edge. A later double error terminates retry.
The logical-preservation contract assumes the SECDED correction is valid within
its fault model. Beyond two flipped storage bits, a miscorrection can instead
scrub wrong data on a rejected attempt. The R4 capture regression demonstrates
raw7 decoded/scrubbed to encoded1 while all three candidates are rejected:
error2/valid0 with accumulator1, starting from zero. A later clean launch can
return valid13 instead of the trusted-zero result12. These are explicit failures
of preservation/trust under the unsupported multi-bit fault, not protection
successes; the analyzer records ESCAPE and retains taint until reset/idle clear.
See the [rejection-scrub checklist](hybrid_fpga_setup.md#rejection-scrub-and-continuation--hardware-not-run).

`done`, `result_valid`, `error`, `corrected`, `detected`, and `retried` are cleared
on the next edge unless a new event asserts them. `retry_count` remains available
after completion until reset, idle clear, or the next accepted start. Starts and
clear during busy are ignored, including retry cycles; reset always aborts.
`ready = !rst && !clear && !busy`. Operands are saved once and reused for retry.
A persistent fault produces bounded failure, not a promise of correction.

## Experimental injection interface

`mac_hybrid_injectable` shares `mac_hybrid_datapath.vh` with production. It exposes:

| Site | Width | Meaning |
| --- | ---: | --- |
| candidate_fault_mask | ACC_WIDTH+1 | XOR full arithmetic candidate before residue observation |
| checker_fault_mask | 3 | XOR predicted residue before comparison |
| commit_fault_mask | ACC_WIDTH | XOR accepted data after checking, before SECDED encoding |
| Stored codeword (simulation access) | CODE_WIDTH | XOR actual registered data/check bits between edges |

Combinational masks matter at a busy attempt edge; they do not queue or mutate
storage by themselves. A mask on one attempt is transient; holding it across all
attempts models persistent corruption at that site. The C++ harness checks the
before/after XOR at each site and raw stored state. Injection counts are not
independent random physical fault trials or coverage percentages.

The M0 audit additionally checks vector eligibility against the DUT's pre-edge
busy/reset/source-decode state. An active-attempt fault event means one or more
nonzero masks on a busy, non-reset edge with usable source storage. It does not
mean every affected wire was committed: a commit mask can be visible on a
rejected attempt. Idle/reset/uncorrectable-source mask rows remain checked and
retained in the vectors but are excluded from that active-attempt count.

## Explicit limits and expected escapes

The decoded accumulator and saved operands are shared by the main calculation
and predictor. ECC decode/control, operand registers, checker, comparator, retry
counter, encoder, commit controls, configuration memory and external interfaces
are not independently protected. Errors affecting a shared input consistently may
escape both paths. Retry reuses the same hardware and inputs.

The regression intentionally demonstrates these wrong-but-valid outcomes:

| Starting state / transaction | Fault | Expected limitation |
| --- | --- | --- |
| A=0, 0*0 | candidate XOR 7 | Candidate 7 has residue 0; commits wrong result 7 |
| A=0, 1*1 | candidate XOR 1 and prediction XOR 1 | Both become 0; commits wrong result 0 |
| A=0, 1*1 | commit XOR 1 | Check passes for 1, then encoder stores wrong data 0 with valid ECC |

These are passing **limitation tests**, not successfully corrected errors. No
persistent redundant accumulator residue or protected atomic commit is implemented.
No claim of research novelty, complete fault coverage, physical radiation tolerance,
FPGA timing closure, or tapeout readiness follows from this baseline.

## Sources and reproduction

Production synthesis sources: `secded_encoder.sv`, `secded_decoder.sv`,
`signed_residue7.sv`, `mac_residue7_check.sv`, `mac_hybrid.sv`; include directory
`rtl/` for `secded_functions.vh` and `mac_hybrid_datapath.vh`.
`mac_hybrid_injectable.sv` and `tests/hybrid_verify_top.sv` are additional regression
sources. Do not add verification top or fake debug IP to a board build.

Run `make test-hybrid-model test-hybrid-rtl test-hybrid-small test-hybrid-tiny`.
Use `make lint-hybrid synth-hybrid` for strict lint and generic synthesis.
Override `MAX_RETRIES`, `OPERAND_WIDTH`, `ACC_WIDTH`, and `SEED` as needed.
Vectors, exact expected escapes, source/artifact hashes and tool versions are in
`build/hybrid_w<OW>_a<AW>_r<R>/`; reruns overwrite that configuration's artifacts.
Hybrid harness negative controls retain their mutated vectors, stdout, stderr,
exit codes and input/runner hashes in unique `harness_negative_*` subdirectories.
The M0 baseline and candidate evidence are separately preserved under
`build/m0_audit/`; see [audit progress](../docs/results.md).
See [validation](../research/hybrid_validation.md) and
[board backlog](board_validation_backlog.md) for measured results and pending work.

## Tiny Tapeout integration (M1)

The separate [SKY130 byte-interface wrapper](../asic/README.md) instantiates this
production core at 8/24/MAX_RETRIES=2 without arithmetic changes. It retains
terminal status for host readback, adds one capture cycle to externally visible
busy, and synchronously resets the core when deselected. The core contract
above is unchanged; the wrapper protocol defines additional host restrictions.
No ASIC physical, board or silicon result is implied by interface simulation.


## M3 instrumented board integration

[Hybrid FPGA setup](hybrid_fpga_setup.md) defines a separate fixed 8/24/retries2
clocked sequencer and ZedBoard top. Production ports and timing remain unchanged.
The shared datapath now has an idle storage-XOR hook, tied to zero by production
and the original injectable wrapper; only the new board core enables it on an
accepted launch. Raw storage XOR takes that edge's scrub slot while operands
are saved, so decoding/repair/rejection occurs on the next busy edge. Arithmetic
masks are latched and selected by attempt bitmap, with sampled-site acknowledgement.
No extra production fault port or protected-commit claim is introduced. Board
implementation/timing/hardware remain NOT RUN. R4 provides the accepted variable-latency
capture repair described in the setup guide. CR2 physical repair is accepted for
its scoped checks. CR6 is accepted at sequence 8 with review02 PASS, host pilot
run_e46nd7_8 and cost run_wei9weaj; see the exact source and portable publications
in the [handoff](../docs/project_overview.md).
CF focused acceptance/review and the complete 13-gate final regression remain open.
Failed M4/M6 are not relabeled accepted.
