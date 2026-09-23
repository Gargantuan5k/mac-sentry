#!/usr/bin/env python3
"""Generate deterministic cycle expectations from the independent Python model."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.mac import MacModel  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operand-width", type=int, default=8)
    parser.add_argument("--acc-width", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--random-cycles", type=int, default=20000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ow, aw = args.operand_width, args.acc_width
    if not (2 <= ow <= 8 and 2 * ow <= aw <= 30) or args.random_cycles < 0:
        parser.error("vector runner supports 2 <= operand width <= 8, 2*operand width <= accumulator width <= 30, nonnegative random cycles")
    rng = random.Random(args.seed)
    m = MacModel(ow, aw)
    rows, sections = [], {}
    lo, hi = -(2 ** (ow - 1)), 2 ** (ow - 1) - 1

    def cycle(rst=0, clear=0, start=0, a=0, b=0):
        expected = m.step(rst, clear, start, a, b)
        rows.append(" ".join(map(str, (rst, clear, start, a, b, *expected))))

    def op(a, b):
        cycle(start=1, a=a, b=b)
        # Change operands and assert start while busy: neither may affect this transaction.
        cycle(start=1, a=hi, b=lo)

    def mark(name):
        sections[name] = len(rows) - sum(sections.values())

    cycle(rst=1, start=1, clear=1)
    cycle()
    cycle(clear=1, start=1, a=hi, b=hi)
    for a in (lo, lo + 1, -1, 0, 1, hi):
        for b in (lo, lo + 1, -1, 0, 1, hi):
            op(a, b)
            cycle()
    cycle(start=1, a=hi, b=hi)
    cycle(rst=1)  # Abort immediately before commit.
    cycle()
    cycle(start=1, a=2, b=-2)
    cycle(clear=1, start=1)  # Clear while busy is ignored.
    cycle(clear=1)
    for _ in range(8):
        cycle(start=1, a=1, b=1)  # Held start accepts every other edge.
    cycle()
    mark("directed_protocol_and_extrema")

    # Cross both accumulator boundaries from reset; no backdoor state loading.
    for a, b in ((lo, lo), (lo, hi)):
        cycle(clear=1)
        for _ in range((2 ** (aw - 1)) // abs(a * b) + 3):
            op(a, b)
    mark("positive_and_negative_wrap_streams")

    cycle(clear=1)
    for a in range(lo, hi + 1):
        for b in range(lo, hi + 1):
            op(a, b)
    mark("exhaustive_operand_pairs")

    cycle(clear=1)
    # A deterministic integer dot product, repeated without clearing to retain history.
    for _ in range(16):
        for i in range(64):
            op((i * 17 % (hi - lo + 1)) + lo, (i * 29 % (hi - lo + 1)) + lo)
    mark("dot_product")

    for _ in range(args.random_cycles):
        cycle(rst=int(rng.random() < .01), clear=int(rng.random() < .05),
              start=int(rng.random() < .7), a=rng.randint(lo, hi), b=rng.randint(lo, hi))
    cycle()
    cycle()
    mark("seeded_protocol_noise")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(rows) + "\n")
    manifest = {"schema": 1, "variant": "unprotected", "operand_width": ow,
                "acc_width": aw, "seed": args.seed, "cycles": len(rows), "sections": sections,
                "faults_injected": 0, "vector_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "columns": "rst clear start a b ready_before busy done result_valid error accumulator ready_after".split()}
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Generated {len(rows)} cycles: {args.output}")


if __name__ == "__main__":
    main()
