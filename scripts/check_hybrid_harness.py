#!/usr/bin/env python3
"""Require the hybrid runner to reject corrupted or incomplete test evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def require_rejection(result, record, diagnostic):
    """Match the failing assertion, never the unconditional DUT-state tail."""
    first_line = result.stderr.splitlines()[0] if result.stderr else ''
    pattern = (rf'FAIL record {record}: {re.escape(diagnostic)}: '
               r'expected -?\d+, observed -?\d+')
    if result.returncode != 1 or re.fullmatch(pattern, first_line) is None:
        raise RuntimeError(f'unexpected response: {result.stdout}{result.stderr}')


def busy_reset_index(records):
    """Find reset overriding a pending transaction in the clean baseline replay.

    C rows do not clock the MAC. The preceding M row's post-edge busy is the
    current pre-edge busy. Clean replay plus no storage injection gives a usable
    source, so removing the reset qualification alone changes eligibility.
    """
    previous = None
    for index, row in enumerate(records):
        fields = row.split()
        if fields[0] != 'M':
            continue
        if (previous is not None and int(previous[15]) == 1
                and int(previous[10]) == 1 and int(fields[10]) == 1
                and int(fields[1]) == 1 and int(fields[6]) == 0
                and fields[12] == previous[25]):
            return index
        previous = fields
    raise RuntimeError('no busy reset with clean source in vectors')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--vectors', type=Path, required=True)
    args = parser.parse_args()
    lines = args.vectors.read_text().splitlines()
    records = lines[1:]
    # Retain even failed controls; unique directories avoid overwriting earlier evidence.
    evidence = Path(tempfile.mkdtemp(prefix='harness_negative_', dir=args.vectors.parent))
    print(f'Negative-control evidence: {evidence}')
    identity = dict(runner_sha256=hashlib.sha256(args.runner.read_bytes()).hexdigest(),
                    vectors_sha256=hashlib.sha256(args.vectors.read_bytes()).hexdigest(),
                    checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (evidence / 'identity.json').write_text(json.dumps(identity, indent=2)+'\n')

    def reject(name, changed, count, diagnostic):
        path = evidence / (name + '.txt')
        path.write_text(str(count) + '\n' + '\n'.join(changed) + '\n')
        result = subprocess.run([str(args.runner.resolve()), str(path)], capture_output=True, text=True)
        (evidence / (name + '.stdout.log')).write_text(result.stdout)
        (evidence / (name + '.stderr.log')).write_text(result.stderr)
        (evidence / (name + '.json')).write_text(json.dumps(dict(
            command=[str(args.runner.resolve()), str(path.resolve())],
            exit_code=result.returncode, required_diagnostic=diagnostic,
            required_record=len(changed),
            input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()), indent=2)+'\n')
        require_rejection(result, len(changed), diagnostic)
        print(f'PASS negative control: {name} ({diagnostic})')

    def mutate(name, predicate, column, value, diagnostic, *, index=None):
        if index is None:
            index = next(i for i, row in enumerate(records) if predicate(row.split()))
        changed = records[:index+1]
        fields = changed[-1].split()
        fields[column] = str(value(int(fields[column])))
        changed[-1] = ' '.join(fields)
        reject(name, changed, len(changed), diagnostic(fields) if callable(diagnostic) else diagnostic)

    mutate('wrong_residue', lambda f: f[0] == 'C', 5, lambda x: x ^ 1, 'predicted residue')
    mutate('missing_storage_flip', lambda f: f[0] == 'M' and int(f[6]) != 0,
           6, lambda x: 0, 'pre word')
    mutate('missing_candidate_flip', lambda f: f[0] == 'M' and int(f[7]) != 0 and int(f[11]) == 1,
           7, lambda x: 0, lambda f: 'busy' if int(f[15]) else 'valid')
    mutate('false_ineligible_attempt',
           lambda f: f[0] == 'M' and int(f[11]) == 1 and int(f[7]) != 0,
           11, lambda x: 0, 'attempt eligibility')
    mutate('false_eligible_reset', None, 11, lambda x: 1, 'attempt eligibility',
           index=busy_reset_index(records))
    mutate('missing_checker_flip',
           lambda f: f[0] == 'M' and int(f[8]) != 0 and int(f[11]) == 1
                     and int(f[7]) == 0 and int(f[9]) == 0,
           8, lambda x: 0, lambda f: 'busy' if int(f[15]) else 'valid')
    mutate('missing_commit_flip',
           lambda f: f[0] == 'M' and int(f[9]) != 0 and int(f[17]) == 1,
           9, lambda x: 0, 'accumulator')
    reject('truncated_vectors', records[:2], int(lines[0]), 'record count')


if __name__ == '__main__':
    main()
