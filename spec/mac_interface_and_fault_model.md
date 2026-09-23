# Portable MAC contract, revision 0

This is the initial implementation contract for `mac_unprotected`, based on the
17 September project plan and 18 September execution plan in `../../sop_docs/`.
It is a working specification pending team review, not a recorded T03 sign-off.

## Arithmetic

Defaults: signed two's-complement 8-bit operands, signed 24-bit accumulator.
The full 16-bit signed product is sign-extended before addition. Only the final
sum wraps; there is no saturation, rounding, or product truncation.

```
T = signed(accumulator) + signed(a) * signed(b)
y = ((T + 2^(ACC_WIDTH-1)) mod 2^ACC_WIDTH) - 2^(ACC_WIDTH-1)
```

The RTL supports `OPERAND_WIDTH >= 2` and `ACC_WIDTH >= 2*OPERAND_WIDTH`.
The current C++/vector runner supports operand widths 2–8 and accumulator widths
up to 30; regressions run 8/24 and 4/8. Other configurations are unvalidated.
Under the supported RTL width relationship, ACC_WIDTH+1 bits hold the exact sum.

## Interface and clock behavior

All inputs belong to one clock domain. Control is synchronous to the rising edge.
The host must provide normal setup/hold timing; no clock crossing is implemented.
Drive `rst` high for at least one rising edge before use. Initial register values
before that reset are unspecified.

| Signal | Meaning |
| --- | --- |
| `rst` | Active-high synchronous reset; aborts pending work and clears accumulator/status |
| `clear` | Clears accumulator at an idle rising edge; overrides `start`; ignored while busy |
| `start` | Request accepted on a rising edge only if `ready` is high immediately before it |
| `operand_a`, `operand_b` | Signed inputs captured at acceptance; may change afterward |
| `ready` | Combinational `!rst && !clear && !busy` |
| `busy` | One transaction is pending; deasserts at completion |
| `done` | One-cycle completion pulse, including failure for future protected variants |
| `result_valid` | One-cycle successful-result pulse; always equals `done` in this baseline |
| `error[1:0]` | Always zero in the unprotected baseline; future status definitions below |
| `accumulator` | Committed state, continuously visible; updates only on reset, idle clear, or successful completion |

Priority at a rising edge is **reset → complete pending work → idle clear → accept
start → hold**. `start` and `clear` during busy are discarded, not queued. They
will take effect at a later idle edge if the host keeps them asserted. A reset
aborts without `done`, `result_valid`, or error.

| Rising edge | Inputs / state before edge | State after edge |
| --- | --- | --- |
| N | `ready=1`, `start=1`, a=3, b=-4 | operands captured, `busy=1`; accumulator unchanged |
| N+1 | `busy=1`; inputs may change | accumulator decreases by 12, `done=1`, `result_valid=1`, `busy=0` |
| N+2 | `ready=1`; optional next request | completion pulses clear; next request can be captured |

Acceptance-to-completion latency is one clock period. Initiation interval is two
clock periods, hence at most one useful MAC per two cycles. `done` describes the
previous transaction even when `ready` is high; it is not a pending-request flag.
The accumulator remains available after the valid pulse, until another state
update. There is no output backpressure, operand-load bus, or accumulator-load
command in the portable core. Board wrappers will add host transfers separately.

## Reserved recovery behavior

Protected variants are not implemented yet. Their target external contract is:
`done=1, result_valid=1, error=0` on success; `done=1, result_valid=0` with a
nonzero error on terminal failure; error zero outside the completion pulse.
Reserve error 1 for detected uncorrectable state, 2 for retry exhaustion, and 3
for a detected protocol/control integrity failure. Reserve a default of two
retries beyond the initial attempt (three total attempts). A detected rejected
candidate must never commit. Reset remains the only operation that may abort
busy work. Retry timing, correction indicators, protected operands, idle
scrubbing, and validation-state encoding require a later specification revision
with the protected implementation. These reservations are not tested guarantees.

## Signed residue equation

The software oracle uses mathematical nonnegative modulo:

```
q = floor((T + 2^(W-1)) / 2^W)
r_y = (r_s + r_a*r_b - q*(2^W mod m)) mod m
```

Tests exhaust accumulator/operand combinations for 3/3, 3/6, and 4/8 widths,
at moduli 3 and 7. The narrow 3/3 case exercises multiple wraps even though that
configuration is outside the RTL contract. Computing `q` from exact arithmetic
is an equation-validation oracle, not an independent fault detector. Choosing
a hardware modulus or deriving protected overflow information is deferred.

## Fault model and outcome taxonomy

The current executable regression is fault-free. This unprotected design has no
guaranteed detection, correction, or recovery; `error=0` cannot certify a result
under a fault. No injection coverage or radiation tolerance is claimed.

The planned comparison will distinguish:

| Fault class | Planned semantics |
| --- | --- |
| Register upset | Flip a stored data/check/control bit at a documented edge; persists until overwritten or repaired |
| Logic transient | Perturb a declared combinational site for a declared interval relative to sampling |
| Multiple-bit fault | Explicit set of simultaneous flips; separate from single-bit statistics |
| Repeated/persistent fault | Repeat or hold the fault across attempts to test bounded termination |
| Protection/control fault | Include decoders, checker, wrap adjustment, commit enable, status, retry, and voters |

Initial RTL experiments exclude analog effects, clock/reset distribution faults,
external input corruption before acceptance, FPGA configuration-memory errors,
and physical spatial correlation. Shared dependencies must be recorded for each
variant. Faults must acknowledge that they actually fired. Requested but unfired
injections are invalid trials, not successful recoveries.

Classify valid trials as correct/masked, corrected/recovered, detected
unrecoverable, silent data corruption, or timeout. Record false alarms separately.
Observe subsequent transactions for latent state errors. Record location,
bit/mask, duration, transaction/cycle, seed, build hash, expected result, actual
status, and observation window. Denominators and uncertainty are required before
reporting fault rates. Fault-free equation tests establish no fault coverage.
