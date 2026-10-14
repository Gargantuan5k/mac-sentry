# Initial SECDED Python validation — 2026-10-14

`make test-model` passed all 29 tests (14 new SECDED tests and 15 existing tests).
The measured unittest duration was 3.759 seconds. No codec or MAC model changes
were required by this run. The source contract is
[secded_accumulator.md](../spec/secded_accumulator.md).

## Reproduce

Run from the repository root with Python 3.10+ and Make:

```sh
make test-secded  # 14 SECDED tests
make test-model  # All 29 Python tests, including SECDED
```

Without Make, the subset command is:

```sh
python3 -m unittest discover -s tests -p 'test_*secded.py' -v
```

The recorded run used `make test-model`. Its raw log is
`build/secded_model/tests.log`; `build/secded_model/provenance.json` records the
command, Python version, UTC start time, exit code, source hashes, and log hash.
These local build artifacts are ignored by Git. The Make commands run tests but
do not regenerate that provenance file or save logs automatically.

## Checks and observed results

| Check | Observed result |
| --- | --- |
| Known encoding/layout | Hand-derived 4-bit words and default-width low/high data-bit words matched; even parity checks passed |
| Default codec, no fault | 40 data patterns round-tripped with clean status |
| Default codec, one flipped bit | All 30 positions for each of 40 patterns: 1,200 corrections restored original data/codeword and reported the correct bit |
| Default codec, two flipped bits | All 435 pairs for each of 40 patterns: 17,400 detections; no correction or codeword mutation |
| Small-code distance oracle | Every received word for data widths 1–6: 3,536 words classified against all valid codewords by Hamming distance; codeword uniqueness and minimum distance >= 4 checked |
| Shortening boundary | Odd-parity syndromes 30 and 31 rejected without repair |
| Beyond the guarantee | Explicit triple-flip miscorrection and four-flip escape reproduced |
| MAC single-bit repair | 6 accumulator states × 30 bits × idle/acceptance/completion phases: 540 cases repaired with correct status and writeback |
| MAC double-bit rejection | 6 states × 435 pairs × idle/completion injection phases: 5,220 failed transactions preserved damaged storage and cleared terminal status on the next edge |
| Fault-free cycle equivalence | 5,000 randomized cycles each at 8/24 and 4/8 matched every returned baseline signal; seed 20261014 |
| Directed arithmetic | Signed extrema, positive/negative accumulator wrap, and the 1870 + 15 × 10 = 2020 sequence passed after a single stored-bit upset |
| Protocol and recovery | Reset abort, idle clear priority, busy clear/start rejection, operand capture, repeated failure, clear recovery, and repeated single-bit repair passed |
| Input boundaries | Invalid dimensions and out-of-range codewords/data/masks rejected; invalid injection left state intact |

The default codec patterns are eight directed values plus 32 values generated
with seed 20261014. MAC injection states are 0, 1, -1, signed maximum, signed
minimum, and 0x555555. Injection assertions check the exact before/after XOR.
Readback is checked to leave storage untouched before an edge repairs it.

## Interpretation and limits

These are deterministic software checks, not a physical fault campaign. The
24-bit data space is sampled; only the listed small codes exhaust all received
words. The small-code distance oracle enumerates encoder-produced valid words,
with separate known-word, parity, uniqueness, and distance checks to reduce
shared implementation assumptions.

MAC equivalence uses `MacModel`, whose arithmetic helper is also used by the
protected model; directed numerical expectations provide additional checks.
Faults cover stored accumulator data/check bits. Decoder, encoder, operands,
arithmetic and control faults are outside this test scope. No radiation tolerance,
FPGA configuration protection, area, clock frequency, or RTL equivalence is
established. T07 remains open pending RTL implementation and verification,
implementation evidence, and review.
