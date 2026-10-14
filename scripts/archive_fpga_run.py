#!/usr/bin/env python3
"""Archive a baseline Vivado build and check captured ILA samples. Standard library only."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.mac import MacModel, signed  # noqa: E402

SIGNALS = ('rst', 'clear', 'start_pulse', 'operand_a', 'operand_b',
           'ready', 'busy', 'done', 'result_valid', 'error', 'accumulator')
WIDTHS = (1, 1, 1, 8, 8, 1, 1, 1, 1, 2, 24)
TEST_FIELDS = ('capture', 'sample', 'action', 'initial_acc', 'a', 'b',
               'expected_acc', 'observed_acc', 'status', 'notes')


def write_csv(path, fields, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def read_capture(path):
    """Read Vivado CSV with its radix row; reject missing/unknown signal values."""
    with path.open(newline='') as handle:
        table = list(csv.reader(handle))
    if len(table) < 3 or not table[1][0].startswith('Radix'):
        raise ValueError('Expected a Vivado CSV header, radix row, and samples')
    header, radices = table[:2]
    indices = {}
    for signal in SIGNALS:
        matches = [i for i, name in enumerate(header)
                   if re.fullmatch(re.escape(signal) + r'(?:_\d+)?',
                                   re.sub(r'\[.*\]$', '', name.split('/')[-1]))]
        if len(matches) != 1:
            raise ValueError(f'Expected one named probe for {signal}; found {len(matches)}')
        indices[signal] = matches[0]
    samples = []
    for row_number, row in enumerate(table[2:], 3):
        if len(row) != len(header) or len(radices) != len(header):
            raise ValueError(f'Malformed CSV row {row_number}')
        sample = {'sample': int(row[0]), 'window_sample': int(row[1])}
        for signal, width in zip(SIGNALS, WIDTHS):
            index = indices[signal]
            radix = radices[index].strip().upper().removeprefix('RADIX - ')
            bases = {'HEX': 16, 'BINARY': 2, 'BIN': 2, 'OCTAL': 8,
                     'OCT': 8, 'SIGNED': 10, 'UNSIGNED': 10, 'DECIMAL': 10}
            if radix not in bases:
                raise ValueError(f'Unsupported radix {radix!r} for {signal}')
            value = int(row[index], bases[radix])
            if not -(1 << (width - 1)) <= value < (1 << width):
                raise ValueError(f'Out-of-range {signal} in row {row_number}')
            value &= (1 << width) - 1
            sample[signal] = signed(value, width) if signal in (
                'operand_a', 'operand_b', 'accumulator') else value
        samples.append(sample)
    return samples


def analyze_capture(path, label):
    """ILA samples are pre-edge: inputs in row i determine state in row i+1."""
    samples = read_capture(path)
    failures, events = [], []
    checked = 0

    def contiguous(i):
        return (i + 1 < len(samples)
                and samples[i+1]['sample'] == samples[i]['sample'] + 1
                and samples[i+1]['window_sample'] == samples[i]['window_sample'] + 1)

    def compare(row, field, expected):
        if row[field] != expected:
            failures.append({'capture': label, 'sample': row['sample'],
                             'signal': field, 'expected': expected, 'observed': row[field]})

    model = None
    # The first accumulator value is observed initial state, not a proven history.
    for i, row in enumerate(samples):
        compare(row, 'ready', int(not (row['rst'] or row['clear'] or row['busy'])))
        compare(row, 'error', 0)
        compare(row, 'result_valid', row['done'])
        if model is None and (not row['busy'] or row['rst']):
            model = MacModel(accumulator=row['accumulator'])
        if not contiguous(i):
            model = None
            continue
        if model is not None:
            outputs = model.step(row['rst'], row['clear'], row['start_pulse'],
                                 row['operand_a'], row['operand_b'])
            for field, value in zip(('busy', 'done', 'result_valid', 'error', 'accumulator'), outputs[1:6]):
                compare(samples[i+1], field, value)
            checked += 1

    for i, row in enumerate(samples):
        action, expected, end, status = None, 0, i+1, 'PASS'
        if row['rst']:
            action = 'reset'
        elif not row['busy'] and row['clear']:
            action = 'clear'
        elif row['ready'] and row['start_pulse']:
            action, end = 'mac', i+2
            expected = signed(row['accumulator'] + row['operand_a'] * row['operand_b'], 24)
            if contiguous(i) and samples[i+1]['rst']:
                action, expected = 'reset_aborted_mac', 0
        if action is None:
            continue
        complete = all(contiguous(j) for j in range(i, end))
        if not complete:
            status = 'INCOMPLETE'
        elif any(row['sample'] <= f['sample'] <= samples[end]['sample'] for f in failures):
            status = 'FAIL'
        events.append(dict(zip(TEST_FIELDS, (
            label, row['sample'], action, row['accumulator'], row['operand_a'], row['operand_b'],
            expected, samples[end]['accumulator'] if complete else '', status,
            'Checks captured samples only; prior accumulator history is not established.'))))
    summary = {'capture': label, 'samples': len(samples), 'checked_transitions': checked,
               'observed_events': len(events),
               'complete_mac_transactions': sum(e['action'] == 'mac' and e['status'] != 'INCOMPLETE' for e in events),
               'mismatches': len(failures), 'initial_accumulator': samples[0]['accumulator'],
               'final_accumulator': samples[-1]['accumulator']}
    return samples, events, failures, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=ROOT.parent / 'mac_sentry_fpga',
                        help='Existing Vivado project directory (read only)')
    parser.add_argument('--output', type=Path, required=True, help='New archive directory; never overwritten')
    parser.add_argument('--capture', type=Path, action='append',
                        help='ILA archive or Vivado CSV; repeatable. Default: project .hw/backup/*.ila')
    parser.add_argument('--impl-run', default='impl_1')
    parser.add_argument('--build-store', type=Path,
                        help='Shared build ZIP directory; default: sibling builds/ beside the runs directory')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    xprs = list(project.glob('*.xpr'))
    if len(xprs) != 1:
        parser.error('Project directory must contain exactly one .xpr')
    if output.exists():
        parser.error('Output already exists; choose a new run directory')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.impl_run):
        parser.error('Invalid implementation run name')
    xpr = xprs[0]
    captures = [p.resolve() for p in args.capture] if args.capture else sorted(
        project.glob('*.hw/backup/*.ila'))
    if any(not p.is_file() or p.suffix.lower() not in ('.ila', '.csv') for p in captures):
        parser.error('Capture inputs must be existing .ila or .csv files')
    output.mkdir(parents=True)
    for folder in ('sources/core', 'sources/fpga', 'reports', 'build', 'captures'):
        (output / folder).mkdir(parents=True)
    inventory = []
    warnings = []

    def copy(source, relative):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inventory.append({'original': str(source), 'archived': str(relative),
                          'original_mtime_utc': datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()})

    for folder in ('rtl', 'model', 'tests', 'scripts', 'spec', 'research'):
        for source in sorted((ROOT / folder).rglob('*')):
            if source.is_file() and '__pycache__' not in source.parts:
                copy(source, Path('sources/core') / source.relative_to(ROOT))
    for name in ('README.md', 'Makefile', '.gitignore'):
        copy(ROOT / name, Path('sources/core') / name)
    copy(xpr, Path('sources/fpga') / xpr.name)
    for source in sorted(project.glob('*.srcs/**/*')):
        if source.is_file() and source.suffix.lower() in ('.sv', '.v', '.vhd', '.xdc', '.xci', '.tcl', '.coe', '.mem'):
            copy(source, Path('sources/fpga') / source.relative_to(project))
    # Include external project references too; the original XPR retains its paths.
    referenced = []
    for node in ET.parse(xpr).findall('.//File'):
        value = node.get('Path', '')
        for token, replacement in (('$PPRDIR', str(project)),
                                   ('$PSRCDIR', str(project / (xpr.stem + '.srcs'))),
                                   ('$PRUNDIR', str(project / (xpr.stem + '.runs')))):
            value = value.replace(token, replacement)
        source = Path(value)
        if not source.is_absolute():
            source = project / source
        source = source.resolve()
        if not source.is_file():
            warnings.append(f'Missing project reference: {value}')
        elif source.suffix.lower() in ('.sv', '.v', '.vhd', '.xdc', '.xci', '.dcp', '.mem', '.coe'):
            relative = Path('sources/references') / f'{len(referenced):03d}_{source.name}'
            copy(source, relative)
            referenced.append({'project_path': node.get('Path'), 'archive_path': str(relative)})
    run = project / (xpr.stem + '.runs') / args.impl_run
    for pattern, folder in (('*.rpt', 'reports'), ('*.bit', 'build'), ('*.ltx', 'build'),
                            ('*_routed.dcp', 'build'), ('runme.log', 'reports')):
        for source in sorted(run.glob(pattern)):
            copy(source, Path(folder) / source.name)
    if not list((output / 'build').glob('*.bit')):
        warnings.append('No bitstream found in selected implementation run')

    timing_findings = []
    for report in (output / 'reports').glob('*timing_summary*rpt'):
        text = report.read_text(errors='replace')
        for check in ('no_clock', 'unconstrained_internal_endpoints'):
            match = re.search(r'checking ' + check + r' \((\d+)\)', text)
            if match:
                timing_findings.append({'report': report.name, 'check': check, 'count': int(match[1])})
                if int(match[1]):
                    warnings.append(f'{report.name}: {check}={match[1]}; timing closure is not established')

    events, failures, summaries = [], [], []
    for index, capture in enumerate(captures, 1):
        label = f'{index:03d}_{capture.stem}'
        destination = Path('captures') / label
        (output / destination).mkdir()
        copy(capture, destination / capture.name)
        csv_path = output / destination / capture.name
        if capture.suffix.lower() == '.ila':
            try:
                with ZipFile(capture) as archive:
                    # Copy only known filenames, never extract arbitrary archive paths.
                    for name in ('waveform.csv', 'waveform.vcd', 'probes.ltx'):
                        if name in archive.namelist():
                            (output / destination / name).write_bytes(archive.read(name))
                csv_path = output / destination / 'waveform.csv'
            except (OSError, ValueError, BadZipFile) as exc:
                warnings.append(f'{label}: cannot extract ILA: {exc}')
        try:
            samples, found, errors, summary = analyze_capture(csv_path, label)
            write_csv(output / destination / 'samples_decimal.csv',
                      ('sample', 'window_sample', *SIGNALS), samples)
            events.extend(found)
            failures.extend(errors)
            summaries.append(summary)
            if not summary['complete_mac_transactions']:
                warnings.append(f'{label}: no complete MAC transaction in capture; does not verify arithmetic')
        except (OSError, ValueError, IndexError) as exc:
            warnings.append(f'{label}: capture could not be analyzed: {exc}')
            summaries.append({'capture': label, 'analysis_error': str(exc)})
    write_csv(output / 'tests.csv', TEST_FIELDS, events)
    write_csv(output / 'mismatches.csv', ('capture', 'sample', 'signal', 'expected', 'observed'), failures)
    write_csv(output / 'capture_summary.csv',
              ('capture', 'samples', 'checked_transitions', 'observed_events',
               'complete_mac_transactions', 'mismatches', 'initial_accumulator', 'final_accumulator', 'analysis_error'), summaries)
    write_csv(output / 'test_plan.csv', TEST_FIELDS, [
        dict(zip(TEST_FIELDS, ('', '', 'mac', 0, 3, -4, -12, '', 'NOT_RECORDED', 'Reset before test'))),
        dict(zip(TEST_FIELDS, ('', '', 'mac', -12, 2, 5, -2, '', 'NOT_RECORDED', 'Continue without clear'))),
        dict(zip(TEST_FIELDS, ('', '', 'clear', -2, '', '', 0, '', 'NOT_RECORDED', 'Clear while idle'))),
    ])
    (output / 'source_changes.patch').write_text(git('diff', 'HEAD', '--') or '')
    manifest = {'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'variant': 'unprotected', 'board_reported_by_user': 'ZedBoard',
                'operand_width': 8, 'acc_width': 24, 'nominal_clock_hz': 100_000_000,
                'clock_frequency_basis': 'Board oscillator; not inferred from timing closure',
                'project': str(xpr), 'implementation_run': args.impl_run,
                'git_revision': git('rev-parse', 'HEAD'), 'git_status': git('status', '--porcelain'),
                'source_identity_note': 'Snapshot at archive time; not proof these sources produced the bitstream or capture.',
                'capture_build_identity_note': 'Files collected together; programmed bitstream/capture association not independently verified.',
                'resource_scope': 'Instrumented FPGA design including VIO, ILA, debug hub, and wrapper',
                'timing_findings': timing_findings, 'captures': summaries,
                'warnings': warnings, 'copied_files': inventory, 'project_references': referenced}
    report_headers = []
    for report in sorted((output / 'reports').glob('*.rpt')):
        report_headers.extend(line.strip() for line in report.read_text(errors='replace').splitlines()
                              if line.startswith(('| Tool Version', '| Device', '| Design State')))
    manifest['report_metadata'] = sorted(set(report_headers))
    (output / 'README.md').write_text(
        '# Unprotected MAC hardware archive\n\n'
        'This archive preserves existing artifacts; it does not run or program hardware.\n\n'
        '- `tests.csv`: events actually visible in saved captures, checked against the Python model.\n'
        '- `capture_summary.csv`: sample/transition/event counts. An idle capture is not a MAC test.\n'
        '- `mismatches.csv`: sampled protocol/arithmetic disagreements.\n'
        '- `test_plan.csv`: suggested tests; observations deliberately blank.\n'
        '- `captures/`: original ILA/CSV files and signed-decimal samples.\n'
        '- `reports/`, `build/`: existing implementation evidence, bitstream, probes, routed checkpoint.\n'
        '- `sources/`: archive-time source/IP/XDC snapshot; XPR paths may need relocation.\n'
        '- `manifest.json`: hashes, original locations, timestamps, scope and limitations.\n\n'
        'The checker assumes 8/24 arithmetic, zero ILA input pipeline stages and consecutive samples.\n'
        'Capture boundaries are not joined. Transactions cut off by a boundary are INCOMPLETE.\n'
        'The observed initial accumulator is used as a starting point; its history is not proven.\n'
        'Manual tests reported in conversation are not turned into measured PASS rows.\n\n'
        '## Findings\n\n' + '\n'.join('- ' + warning for warning in warnings) + '\n\n'
        'Preserve this directory unchanged. Create a new archive after another capture/build.\n')
    manifest['file_sha256'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    from compact_fpga_results import compact_run
    compact_run(output, args.build_store or output.parent.parent / 'builds')
    print(f'Archive: {output}')
    print(f'Captures: {len(summaries)}; observed events: {len(events)}; mismatches: {len(failures)}')
    for warning in warnings:
        print('NOTE:', warning)


if __name__ == '__main__':
    main()
