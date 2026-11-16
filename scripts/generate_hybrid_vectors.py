#!/usr/bin/env python3
"""Reproducible conventional-hybrid checks and explicit escape traces."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.mac import signed
from model.mac_hybrid import HybridMacModel, expected_residue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operand-width', type=int, default=8)
    parser.add_argument('--acc-width', type=int, default=24)
    parser.add_argument('--max-retries', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261106)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ow, aw, retries = args.operand_width, args.acc_width, args.max_retries
    if not (2 <= ow <= 8 and 2*ow <= aw <= 30 and 0 <= retries <= 8):
        parser.error('runner supports operand widths 2..8, accumulator 2*ow..30, retries 0..8')
    model = HybridMacModel(ow, aw, max_retries=retries)
    rows, sections, escapes = [], {}, []
    cycles = checks = storage_events = attempt_fault_events = 0
    rng = random.Random(args.seed)
    limit = (1 << aw)-1

    def mark(name):
        sections[name] = len(rows)-sum(sections.values())

    def cycle(rst=0, clear=0, start=0, a=0, b=0, storage=0, candidate=0,
              checker=0, commit=0, clean=0, baseline=None):
        nonlocal cycles, storage_events, attempt_fault_events
        if storage:
            before, after = model.inject_accumulator_fault(storage)
            assert before ^ after == storage
            storage_events += 1
        eligible = bool(model.pending is not None and not rst and
                        not model.codec.decode(model.codeword).uncorrectable)
        if eligible and (candidate or checker or commit):
            attempt_fault_events += 1
        pre_word, pre_acc = model.codeword, model.accumulator
        expected = model.step(rst, clear, start, a, b, candidate_fault=candidate,
                              checker_fault=checker, commit_fault=commit)
        if baseline is not None:
            assert tuple(baseline) == expected, 'clean hybrid differs from baseline'
        row = (rst, clear, start, a, b, storage, candidate, checker, commit, clean,
               int(eligible), pre_word, pre_acc, *expected, int(model.corrected),
               int(model.detected), int(model.retried), model.retry_count, model.codeword)
        rows.append('M ' + ' '.join(map(str, row)))
        cycles += 1
        return expected

    def check(acc, a, b, candidate):
        nonlocal checks
        row = (acc % (1 << aw), a % (1 << ow), b % (1 << ow),
               candidate % (1 << (aw+1)), expected_residue(acc, a, b), candidate % 7)
        rows.append('C '+' '.join(map(str, row)))
        checks += 1

    cycle(rst=1, clean=1)
    mark('reset')
    if ow == 2 and aw == 4:
        for acc in range(-8, 8):
            for a in range(-2, 2):
                for b in range(-2, 2):
                    for candidate in range(-16, 16):
                        check(acc, a, b, candidate)
    elif ow == 4 and aw == 8:
        for acc in range(-128, 128):
            for a in range(-8, 8):
                for b in range(-8, 8):
                    check(acc, a, b, acc+a*b)
    for _ in range(1000):
        acc = rng.randrange(-(1 << (aw-1)), 1 << (aw-1))
        a, b = rng.randrange(-(1 << (ow-1)), 1 << (ow-1)), rng.randrange(-(1 << (ow-1)), 1 << (ow-1))
        exact = acc+a*b
        check(acc, a, b, exact)
        for bit in range(aw+1):
            check(acc, a, b, signed((exact % (1 << (aw+1))) ^ (1 << bit), aw+1))
    mark('standalone_checker')
    baseline = args.baseline.read_bytes()
    manifest = json.loads(args.baseline.with_suffix('.json').read_text())
    assert hashlib.sha256(baseline).hexdigest() == manifest['vector_sha256']
    assert (manifest['operand_width'], manifest['acc_width']) == (ow, aw)
    lines = baseline.decode().splitlines()
    assert len(lines) == manifest['cycles']
    for line in lines:
        values = list(map(int, line.split()))
        assert len(values) == 12
        cycle(*values[:5], clean=1, baseline=values[5:])
    mark('baseline_replay')

    # Every candidate bit, both a one-attempt transient and a persistent upset.
    for bit in range(aw+1):
        for persistent in (False, True):
            cycle(rst=1)
            cycle(start=1, a=1, b=1)
            cycle(candidate=1 << bit)
            for _ in range(retries):
                cycle(candidate=(1 << bit) if persistent else 0)
            cycle()
    mark('candidate_bits_and_retry_bound')
    for mask in range(1, 8):
        cycle(rst=1)
        cycle(start=1, a=1, b=-1)
        cycle(checker=mask)
        for _ in range(retries+1):
            cycle()
    mark('checker_corruption')
    for bit in range(model.codec.code_width):
        cycle(rst=1)
        cycle(start=1, a=1, b=1)
        cycle(storage=1 << bit, candidate=1)
        for _ in range(retries+1):
            cycle()
    # All double-bit storage errors terminate with code 1.
    for first in range(model.codec.code_width):
        for second in range(first+1, model.codec.code_width):
            cycle(rst=1)
            cycle(start=1, a=1, b=1)
            cycle(storage=(1 << first) | (1 << second))
            cycle(clear=1)
    mark('storage_faults')

    def escape(name, a, b, candidate=0, checker=0, commit=0):
        cycle(rst=1)
        cycle(start=1, a=a, b=b)
        result = cycle(candidate=candidate, checker=checker, commit=commit)
        expected = signed(signed(a, ow)*signed(b, ow), aw)
        assert result[3] == 1 and result[5] != expected
        escapes.append(dict(name=name, record=len(rows), expected=expected, observed=result[5],
                            candidate_mask=candidate, checker_mask=checker, commit_mask=commit))

    escape('modulo_7_collision', 0, 0, candidate=7)
    escape('correlated_candidate_and_prediction', 1, 1, candidate=1, checker=1)
    escape('post_check_commit_corruption', 1, 1, commit=1)
    mark('known_silent_escapes')
    # Changed inputs and clear while busy must not alter retry operands/state.
    cycle(rst=1)
    cycle(start=1, a=1, b=-1)
    cycle(clear=1, start=1, a=0, b=0, candidate=1)
    cycle(rst=1, candidate=1)
    cycle()
    mark('reset_during_retry')

    # Audit regressions: literal protocol/arithmetic assertions supplement model
    # replay. These use only normal MACs to seed state, never a hidden preload.
    def expect_cycle(expected, **inputs):
        # Generate the edge even if Python assertion optimization is enabled.
        actual = cycle(**inputs)
        if actual != expected:
            raise AssertionError(f'audit cycle: expected {expected}, observed {actual}')

    def status(corrected, detected, retried, count):
        assert (model.corrected, model.detected, model.retried, model.retry_count) == (
            corrected, detected, retried, count)

    # Reset before every possible attempt, including the final allowed attempt.
    for rejected in range(retries+1):
        cycle(rst=1)
        cycle(start=1, a=1, b=-1)
        for attempt in range(rejected):
            expect_cycle((0, 1, 0, 0, 0, 0, 0), candidate=1, clear=1, start=1)
            status(False, True, True, attempt+1)
        expect_cycle((0, 0, 0, 0, 0, 0, 0), rst=1, clear=1, start=1, candidate=1, checker=1, commit=1)
        status(False, False, False, 0)
        expect_cycle((1, 0, 0, 0, 0, 0, 1))
    mark('audit_reset_at_each_attempt')

    cycle(rst=1)
    cycle(start=1, a=1, b=1)
    expect_cycle((0, 0, 1, 1, 0, 1, 1))
    seed_word = model.codeword
    cycle(start=1, a=1, b=-1)
    # Repair source1 even when the first rejection is terminal (MAX_RETRIES=0).
    for attempt in range(retries+1):
        again = attempt < retries
        expect_cycle((0, int(again), int(not again), 0, 0 if again else 2, 1, 0),
                     storage=4 if attempt == 0 else 0, candidate=1,
                     clear=1, start=1)
        status(attempt == 0, True, again, min(attempt+1, retries))
        assert model.codeword == seed_word
    expect_cycle((1, 0, 0, 0, 0, 1, 1))  # pulses clear; no queued busy request
    status(False, False, False, retries)
    expect_cycle((0, 0, 0, 0, 0, 0, 0), clear=1, start=1)
    status(False, False, False, 0)
    expect_cycle((1, 0, 0, 0, 0, 0, 1))
    mark('audit_repair_and_exhaustion')

    # Exhaust the extra-attempt budget, then succeed or encounter a double error
    # on the last allowed edge. Busy clear/start and live operands cannot replace
    # the saved 1*(-1), cancel the transaction, or queue a later request.
    for double_error in (False, True):
        cycle(rst=1)
        cycle(start=1, a=1, b=1)
        expect_cycle((0, 0, 1, 1, 0, 1, 1))
        seed_word = model.codeword
        cycle(start=1, a=1, b=-1)
        for attempt in range(retries):
            expect_cycle((0, 1, 0, 0, 0, 1, 0), candidate=1, clear=1, start=1)
            status(False, True, True, attempt+1)
            assert model.codeword == seed_word
        if double_error:
            # Parity bits0/1: raw data remains1, but is invalid diagnostic data.
            expect_cycle((0, 0, 1, 0, 1, 1, 0), storage=3, candidate=1, clear=1, start=1)
            assert model.codeword == seed_word ^ 3
        else:
            expect_cycle((0, 0, 1, 1, 0, 0, 0), clear=1, start=1)
            assert model.codeword == 0
        status(False, False, False, retries)
        expect_cycle((1, 0, 0, 0, 0, int(double_error), 1))
        status(False, False, False, retries)
    cycle(rst=1)
    mark('audit_final_attempt_and_double_error_priority')

    for _ in range(4000):
        cycle(rst=int(rng.randrange(70) == 0), clear=int(rng.randrange(20) == 0),
              start=rng.randrange(2), a=rng.randrange(1 << ow), b=rng.randrange(1 << ow),
              storage=(1 << rng.randrange(model.codec.code_width)) if rng.randrange(30) == 0 else 0,
              candidate=(1 << rng.randrange(aw+1)) if rng.randrange(3) == 0 else 0,
              checker=rng.randrange(8) if rng.randrange(10) == 0 else 0)
    cycle(rst=1)
    mark('seeded_faults_and_controls')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(str(len(rows))+'\n'+'\n'.join(rows)+'\n')
    record = dict(schema=1, variant='conventional_hybrid', operand_width=ow, acc_width=aw,
                  max_retries=retries, seed=args.seed, records=len(rows), mac_cycles=cycles,
                  residue_checks=checks, storage_injections=storage_events,
                  active_attempt_fault_events=attempt_fault_events, sections=sections,
                  known_silent_escapes=escapes,
                  vector_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                  baseline_sha256=manifest['vector_sha256'])
    args.output.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
