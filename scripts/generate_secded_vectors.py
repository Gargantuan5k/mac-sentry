#!/usr/bin/env python3
"""Generate codec and cycle checks, including acknowledged storage upsets."""
import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.mac_secded import SecdedMacModel
from model.secded import SecdedCodec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operand-width', type=int, default=8)
    parser.add_argument('--acc-width', type=int, default=24)
    parser.add_argument('--seed', type=int, default=20261014)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ow, aw = args.operand_width, args.acc_width
    if not (2 <= ow <= 8 and 2 * ow <= aw <= 30):
        parser.error('require 2 <= operand width <= 8 and 2*operand width <= acc width <= 30')
    codec = SecdedCodec(aw)
    model = SecdedMacModel(ow, aw)
    rng = random.Random(args.seed)
    rows, sections = [], {}
    injections = mac_cycles = codec_checks = 0

    def mark(name):
        sections[name] = len(rows) - sum(sections.values())

    def codec_row(data, received):
        nonlocal codec_checks
        result = codec.decode(received)
        rows.append('C ' + ' '.join(map(str, (data, received, codec.encode(data),
                    result.data, result.codeword, result.syndrome,
                    int(result.corrected), int(result.uncorrectable)))))
        codec_checks += 1

    def cycle(rst=0, clear=0, start=0, a=0, b=0, mask=0, baseline=None):
        nonlocal injections, mac_cycles
        if mask:
            before, after = model.inject_accumulator_fault(mask)
            if before ^ after != mask:
                raise RuntimeError('model injection did not fire')
            injections += 1
        before_word, before_acc = model.codeword, model.accumulator
        expected = model.step(rst, clear, start, a, b)
        if baseline is not None and tuple(baseline) != expected:
            raise RuntimeError('fault-free protected model differs from baseline vector')
        rows.append('M ' + ' '.join(map(str, (rst, clear, start, a, b, mask,
                    before_word, before_acc, *expected, int(model.corrected), model.codeword))))
        mac_cycles += 1

    def op(a, b):
        cycle(start=1, a=a, b=b)
        cycle()

    # First edge establishes a known reset state in the hardware simulator.
    cycle(rst=1)
    mark('initial_reset')
    limit = (1 << aw) - 1
    values = [0, limit, 1, 1 << (aw - 1), (1 << (aw - 1)) - 1,
              0xAAAAAA & limit, 0x555555 & limit, 0x123456 & limit]
    values += [rng.randrange(1 << aw) for _ in range(32)]
    for data in values:
        word = codec.encode(data)
        codec_row(data, word)
        for bit in range(codec.code_width):
            codec_row(data, word ^ (1 << bit))
        for first, second in combinations(range(codec.code_width), 2):
            codec_row(data, word ^ (1 << first) ^ (1 << second))
    # Covers shortened-away syndromes and beyond-guarantee decoder behavior.
    for received in range(1 << codec.code_width) if aw <= 8 else (
            rng.randrange(1 << codec.code_width) for _ in range(2000)):
        codec_row(0, received)
    mark('standalone_codec')

    baseline_manifest = json.loads(args.baseline.with_suffix('.json').read_text())
    if (baseline_manifest['operand_width'], baseline_manifest['acc_width']) != (ow, aw):
        raise ValueError('baseline widths differ')
    baseline_bytes = args.baseline.read_bytes()
    if hashlib.sha256(baseline_bytes).hexdigest() != baseline_manifest['vector_sha256']:
        raise ValueError('baseline hash differs')
    baseline_rows = baseline_bytes.decode().splitlines()
    if len(baseline_rows) != baseline_manifest['cycles']:
        raise ValueError('baseline row count differs')
    for row in baseline_rows:
        values = list(map(int, row.split()))
        if len(values) != 12:
            raise ValueError('malformed baseline row')
        cycle(*values[:5], baseline=values[5:])
    mark('baseline_fault_free_replay')

    # Reach three different states through normal operations; no state preload.
    for operands in ((0, 0), (1, -1), ((1 << (ow - 1)) - 1, 2)):
        for phase in ('idle', 'acceptance', 'completion'):
            masks = [1 << bit for bit in range(codec.code_width)]
            masks += [(1 << first) | (1 << second)
                      for first, second in combinations(range(codec.code_width), 2)]
            for mask in masks:
                cycle(rst=1)
                op(*operands)
                if phase == 'idle':
                    cycle(mask=mask)
                    cycle(start=1, a=1, b=1)
                elif phase == 'acceptance':
                    cycle(start=1, a=1, b=1, mask=mask)
                else:
                    cycle(start=1, a=1, b=1)
                cycle(mask=mask if phase == 'completion' else 0)
                cycle()  # Status must clear; a double fault must remain stored.
                op(-1, 1)  # Repeated failure or continued useful arithmetic.
                cycle(clear=1, start=1)
                op(1, 1)  # Recovery after explicit clear.
    mark('enumerated_storage_faults')

    for mask in (1, 3, 1 << (codec.code_width - 1)):
        cycle(rst=1)
        op(2, -2)
        cycle(start=1, a=3, b=-4)
        cycle(clear=1, start=1, a=7, b=7, mask=mask)
        cycle(clear=1)
        cycle(start=1, a=3, b=-4)
        cycle(rst=1, clear=1, start=1, mask=mask)
        cycle()
    mark('fault_reset_clear_priorities')

    for _ in range(3000):
        mask = 0
        if rng.randrange(4) == 0:
            mask = 1 << rng.randrange(codec.code_width)
            if rng.randrange(2):
                mask |= 1 << rng.randrange(codec.code_width)
        cycle(rst=int(rng.randrange(50) == 0), clear=int(rng.randrange(20) == 0),
              start=rng.randrange(2), a=rng.randrange(1 << ow),
              b=rng.randrange(1 << ow), mask=mask)
    cycle(rst=1)
    mark('seeded_storage_and_protocol')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f'{len(rows)}\n' + '\n'.join(rows) + '\n')
    manifest = dict(schema=1, variant='secded', operand_width=ow, acc_width=aw,
                    code_width=codec.code_width, seed=args.seed, records=len(rows),
                    mac_cycles=mac_cycles, codec_checks=codec_checks,
                    injections=injections, sections=sections,
                    vector_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                    baseline_sha256=baseline_manifest['vector_sha256'])
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
