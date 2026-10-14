#!/usr/bin/env python3
"""Negative controls: the RTL runner must reject bad or incomplete evidence."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--vectors', type=Path, required=True)
    args = parser.parse_args()
    lines = args.vectors.read_text().splitlines()
    records = lines[1:]
    codec_index = next(i for i, row in enumerate(records) if row.startswith('C '))
    injection_index = next(i for i, row in enumerate(records)
                           if row.startswith('M ') and int(row.split()[6]) != 0)
    with tempfile.TemporaryDirectory(prefix='secded_harness_') as tmp:
        def reject(name, changed, count, diagnostic):
            path = Path(tmp) / (name + '.txt')
            path.write_text(str(count) + '\n' + '\n'.join(changed) + '\n')
            result = subprocess.run([str(args.runner.resolve()), str(path)],
                                    capture_output=True, text=True)
            if result.returncode != 1 or diagnostic not in result.stderr:
                raise RuntimeError(f'{name}: unexpected runner response: {result.stdout}{result.stderr}')
            print(f'PASS negative control: {name} ({diagnostic})')

        changed = records[:codec_index + 1]
        fields = changed[-1].split()
        fields[3] = str(int(fields[3]) ^ 1)
        changed[-1] = ' '.join(fields)
        reject('wrong_codec_expectation', changed, len(changed), 'encoded word')

        changed = records[:injection_index + 1]
        fields = changed[-1].split()
        fields[6] = '0'  # Cancel the injected flip, retaining the expected corrupted state.
        changed[-1] = ' '.join(fields)
        reject('missing_injection', changed, len(changed), 'stored word before edge')

        reject('truncated_vectors', records[:2], int(lines[0]), 'record count')


if __name__ == '__main__':
    main()
