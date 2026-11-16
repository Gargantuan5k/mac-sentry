## How it works

MAC Sentry computes `accumulator <- accumulator + A * B` for signed 8-bit operands
and a wrapping signed 24-bit accumulator. Team: Siddharth Vivek, Tejas Singh Kohli
and Arohi Mehta. This candidate combines three synthesizable protections:

- A 30-bit shortened extended Hamming codeword stores the 24-bit accumulator.
  SECDED corrects a single stored bit and detects two. Idle scrubbing repairs
  correctable storage; an uncorrectable source terminates with an invalid result.
- A modulo-7 checker independently predicts the arithmetic residue and compares
  it with the full signed 25-bit candidate before truncation. An intact checker
  detects single-bit changes to that candidate; multiples-of-seven errors can
  collide.
- A mismatch prevents candidate commit and permits two retries, for at most
  three attempts. Exhaustion terminates with an invalid result. Reusing the same
  hardware and saved operands does not guarantee recovery from persistent faults.

The production interface has no intentional fault-injection pins. TMR and FPGA
debug hardware are comparison/experiment designs and are absent from this macro.
Shared operands, control, checker, encoder, snapshot and commit/readback are not
independently protected. Higher-weight storage errors may miscorrect; correlated
faults and post-check faults may escape. In particular, storage corruption between
core commit and wrapper capture can produce a wrong snapshot with valid status.
Digital injection/local physical checks do not establish radiation qualification.

The target clock is 20 MHz with a 2x2 SKY130 tile. Clock and host inputs must be
synchronous. All bidirectional pads are inputs (`uio_oe=0`, `uio_out=0`). The byte
operand is `ui_in[7:0]`, command is `uio_in[3:0]`, strobe is `uio_in[4]`, and
`uio_in[7:5]` must be zero. `uo_out[7:0]` retains the command response.

## How to test

Hold `ena=1`; sample `rst_n=0` on at least one rising clock edge. Release reset,
then sample strobe low on an enabled edge to arm requests. For every command,
present data/opcode while the clock is low, sample strobe low on one rising
edge, then high on the next. Read the response after the high-strobe edge.
Holding strobe high executes only once. Meet input timing; there is no asynchronous
bus synchronizer. Do not gate the clock. Our local timing envelope uses input
delays 1..4 ns and output delays 0..4 ns relative to the 50 ns clock.

| Opcode | Command | Response or action |
| --- | --- | --- |
| 0 | STATUS | Status byte described below |
| 1 | LOAD_A | Save signed operand byte; response 00 |
| 2 | LOAD_B | Save signed operand byte; response 00 |
| 3 | START | Require both operands; response 00 on acceptance |
| 4 | CLEAR | Clear accumulator, operands and status; response 00 |
| 5, 6, 7 | RESULT_LO, MID, HI | Read retained 24-bit result snapshot |
| 8 | DETAIL | Retry count/history and operand-loaded flags |

STATUS bits are busy[0], completed[1], valid[2], core error[4:3], corrected[5],
arithmetic mismatch detected[6], and sticky protocol error[7]. Core error 1 means
uncorrectable SECDED; error 2 means arithmetic retry exhaustion. DETAIL contains
retry count[1:0], retried[2], A loaded[3], B loaded[4]; upper bits are zero.

Illegal encodings return E1, writes while busy return E2, and START with a missing
operand returns E3. These are command response codes, distinct from core errors.
Rejections set sticky protocol error and are not queued. Reads are allowed while
busy and expose the prior snapshot. START consumes the loaded flags and clears
transaction history but preserves the prior snapshot and protocol error. CLEAR,
reset or deselection clear all state. Failed transactions retain the prior
successful snapshot; check valid before interpreting it as a new result.

Example: CLEAR; LOAD_A=34; LOAD_B=55; START; poll STATUS until busy=0 and
completed=1. Require valid=1 and error=0, then read RESULT_LO/MID/HI: 1870.
Load 15 and 10 and repeat without CLEAR: the next result is 2020. Assemble bytes
as `lo | mid<<8 | hi<<16`; subtract `2^24` if bit 23 is set. Do not START or CLEAR
between the three reads. A clean START reaches wrapper completion two clock
periods later; retries can extend this to four. A STATUS on the capture edge
returns pre-edge state, so keep polling. Reset or `ena=0` aborts without completion;
hold a clock edge to clear state and rearm with strobe low after reenabling.

Local pin-level tests cover signed extrema, both wrapping directions, random
accumulation and protocol/reset/abort behavior. Official gate-level CI runs the
same pin-only tests. SDF simulation and final sign-off remain separate gates.

## External hardware

A Tiny Tapeout demoboard or a synchronous host that drives the documented byte
interface and clock. No external memory or peripheral is required. Intentional
on-silicon radiation/fault testing requires a separately reviewed test procedure;
the chip does not expose the FPGA experiment injection interface.
