# Accumulator-only SECDED — implementation contract

Status: Python and RTL implementations pass initial codec and transaction tests;
see [Python evidence](../research/secded_model_validation.md) and
[RTL evidence](../research/secded_rtl_validation.md). FPGA implementation is pending.
These semantics are the T07 implementation contract, pending team review.
The unprotected core and its reference model remain the comparison baseline.

## Storage format

`model/secded.py` implements a shortened extended Hamming code with even parity.
At the default width, 24 data bits plus five Hamming check bits and one overall
parity bit occupy 30 stored bits.

- Hamming positions are 1 through 29, corresponding to integer bits 0 through 28.
- Positions 1, 2, 4, 8, and 16 are Hamming check bits.
- Data bits fill the remaining positions in ascending order, least significant first.
- Integer bit 29 is overall even parity, covering the entire codeword.
- The codec accepts unsigned bit patterns; the MAC interprets decoded data as
  signed two's complement. Widths are parameterized for reduced-width work.

The syndrome is the XOR of the indices of all set Hamming bits.

| Syndrome | Overall parity | Decoder action |
| --- | --- | --- |
| Zero | Even | Accept unchanged |
| Zero | Odd | Correct overall parity bit |
| Nonzero, present position | Odd | Correct the indicated Hamming bit |
| Nonzero | Even | Report uncorrectable; do not modify |
| Shortened-away position | Odd | Report uncorrectable; do not modify |

`DecodeResult` exposes data, repaired codeword, syndrome, correction status,
uncorrectable status, and the zero-based corrected bit index. Data returned on
an uncorrectable indication is raw diagnostic data and must not be consumed.
Status describes the decoder's decision, not the true number of injected flips.
There is no guarantee for three or more flips; miscorrection and escapes remain
possible. The protection guarantee assumes functioning encoder/decoder logic.

## Transaction and repair behavior

`model/mac_secded.py` implements `SecdedMacModel`. It uses the baseline's signed
wrapping arithmetic, acceptance/commit timing, reset/clear priorities, and seven
returned values: pre-edge ready, post-edge busy, done, valid, error, accumulator,
and ready. Supported widths match the RTL relationship: operand width >= 2 and
accumulator width >= twice the operand width.

- Reset initializes an encoded zero and aborts pending work.
- Idle clear initializes an encoded zero, including after an uncorrectable fault.
- Every other idle edge checks stored state and writes back a single-bit repair.
  This includes the operand-acceptance edge; no extra cycle is introduced.
- At completion, decode the stored accumulator again. If usable, calculate from
  corrected data, wrap, and encode the new value. This overwrites any corrected
  storage fault. Success emits `done=1, result_valid=1, error=0`.
- An uncorrectable indication at completion emits `done=1, result_valid=0,
  error=1`, drops the pending operation, and leaves the codeword unchanged.
- Idle uncorrectable state is retained. No unsolicited completion/error pulse is
  emitted. Requests can still be accepted, but fail at completion if the fault
  remains. Reset or idle clear explicitly discards the damaged accumulator.
- `corrected` is a separate model attribute and an RTL output pulsed when an
  edge repairs stored state or commits using corrected state. It clears on the
  next edge unless that edge performs another correction.
- Readback decodes combinationally without writeback. It can therefore show a
  corrected value before the next scrub edge. On an uncorrectable indication,
  readback is diagnostic only. Successful `result_valid` qualifies MAC results.
- `error` is zero outside a failed completion; there is no retry in this variant.

The Python constructor starts at encoded zero for convenience. The hardware
still requires synchronous reset before use.

## RTL integration

`rtl/secded_encoder.sv` and `rtl/secded_decoder.sv` are combinational modules.
`rtl/mac_secded.sv` instantiates them around the accumulator storage register.
All three include `rtl/secded_functions.vh` to derive the number of check bits.
Add these files to the design sources and make `rtl/` an include directory.
The default parameters are OPERAND_WIDTH=8 and ACC_WIDTH=24; 4/8 is also tested.

The MAC has the baseline ports plus the registered `corrected` output. Its
`error` output uses code 1 for a rejected uncorrectable accumulator state; codes
2 and 3 are reserved. Decode, arithmetic, and encode occupy one combinational
path between acceptance and completion. The retained cycle count is verified in
simulation; whether it meets a target clock period requires implementation.

`acc_codeword` is the actual storage register (30 bits by default). A simulator
visibility comment lets the C++ harness XOR it between edges and inspect the
result. There are no hardware injection ports in the production RTL. A board
fault-injection facility requires a separate, explicitly evaluated test design.

## Injection boundary and remaining work

`inject_accumulator_fault(mask)` XORs a nonzero mask into the stored codeword
between model edges and returns before/after words as a firing acknowledgement.
It includes data and check bits and rejects masks outside the storage width.
An upset persists until repair, reset, clear, or a successful update. Calling the
method repeatedly can model repeated upsets, but not an electrically stuck bit.

This is a storage-injection hook, not a calibrated campaign harness. Operands,
product, control, encoder, decoder, and result interface are outside this model's
protection boundary. Arithmetic corruption followed by correct encoding can
produce a valid codeword containing the wrong answer.

Initial verification covers all 30 single-bit positions and all 435 double-bit
pairs over representative data; reduced-width exhaustive received-word checks;
idle repair; faults between acceptance and completion; failed commit preservation;
reset and clear priorities; and fault-free equivalence to `MacModel`.
Reproduce Python checks with `make test-secded` and RTL checks with
`make test-secded-rtl test-secded-small`. RTL checks inspect raw stored codewords
as well as outputs, and acknowledge that every requested injection changed the
intended bits. Next work is review and FPGA integration with measured area/timing
and an adapted capture checker. These simulations do not establish physical
fault coverage or timing closure.
