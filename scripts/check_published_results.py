#!/usr/bin/env python3
"""Verify the portable historical evidence package without build data or agents.

Hashes establish consistency with the committed manifest, not an external digital
signature. Semantic controls retain failures and replay the recorded pilot traces.
No hardware, synthesis, network or installed PDK is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import pilot_campaign

VARIANTS = {'unprotected', 'secded', 'hybrid', 'tmr'}
PRECHECKS = {'Magic DRC', 'KLayout FEOL', 'KLayout BEOL', 'KLayout offgrid',
    'KLayout pin label overlapping drawing', 'KLayout zero area', 'KLayout Checks',
    'Pin check', 'Boundary check', 'Power pin check', 'Layer check', 'Cell name check',
    'urpm/nwell check', 'Analog pin check', 'Verilog syntax check'}
ASIC_STAGES = {'harden', 'physical', 'precheck', 'precheck_xml', 'gls', 'gls_positive',
               'gls_negative_observation', 'gls_negative_arithmetic'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_file(root, relative):
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts and rel.as_posix() == relative,
            'Unsafe evidence path: ' + relative)
    path = root / rel
    require(path.resolve().is_relative_to(root.resolve()), 'Evidence path escapes package')
    require(path.is_file() and not path.is_symlink(), 'Missing/nonregular evidence: ' + relative)
    require(not any(p.is_symlink() for p in path.parents if p != root and p.is_relative_to(root)),
            'Symlink evidence parent')
    return path


def read_json(path):
    return json.loads(path.read_text())


def check_sources(folder, entries):
    require(bool(entries), 'Empty historical source inventory')
    for relative, expected in entries.items():
        source = safe_file(folder / 'sources', relative)
        require(digest(source) == expected, 'Historical source hash mismatch: ' + relative)


def check_asic(folder):
    result = read_json(folder / 'result.json')
    require(result.get('status') == 'PASS' and result.get('errors') == [], 'ASIC stages failed')
    require(set(result.get('stages', {})) == ASIC_STAGES and
            all(v.get('status') == 'PASS' for v in result['stages'].values()), 'ASIC required stage missing/failing')
    require(result.get('sdf_annotated') is False and result.get('signoff') is False,
            'Historical ASIC scope changed')
    require(result.get('required_precheck_count') == 15, 'Precheck requirement changed')
    provenance = read_json(folder / 'provenance.json')
    require(provenance.get('clock_ns') == 50 and provenance.get('tile') == '2x2' and
            provenance.get('sdf_annotated') is False, 'Historical ASIC configuration changed')
    check_sources(folder, provenance['source_sha256'])
    cases = ET.parse(folder / 'tt/precheck/reports/results.xml').getroot().findall('.//testcase')
    require(len(cases) == 15 and {c.get('name') for c in cases} == PRECHECKS,
            'Precheck executed case coverage differs')
    require(all(c.find(tag) is None for c in cases for tag in ('failure', 'error', 'skipped')),
            'Precheck failure/error/skip retained')
    positive = (folder / 'gls_positive.log').read_text()
    require(re.search(r'M2_GLS_PASS transactions=777 aborts=2 samples=15642\b', positive) is not None,
            'GLS sample/transaction evidence differs')
    commands = read_json(folder / 'commands.json')
    names = [c['name'] for c in commands]
    require(len(names) == len(set(names)), 'Duplicate ASIC command record')
    by_name = {c['name']: c for c in commands}
    for name in ('tt_environment', 'tt_metadata', 'librelane_version', 'hardening_input_access',
                 'harden', 'precheck_input_access', 'precheck', 'iverilog_version', 'vvp_version',
                 'gls_compile', 'gls_positive'):
        require(name in by_name and by_name[name].get('returncode') == 0 and
                by_name[name].get('expected_failure') is None, 'ASIC command did not pass: ' + name)
    for name, marker in {'gls_negative_observation': 'M2_GLS_COMPARE sample=100',
                         'gls_negative_arithmetic': 'M2_GLS_ORACLE'}.items():
        command = by_name.get(name, {})
        require(isinstance(command.get('returncode'), int) and command['returncode'] != 0 and
                command.get('expected_failure') == marker and marker in (folder / (name + '.log')).read_text(),
                'GLS negative control did not fire: ' + name)
    metrics = read_json(folder / 'project/src/runs/R2/final/metrics.json')
    require(read_json(folder / 'physical_summary.json') == metrics, 'ASIC summary differs from raw final metrics')
    for name in ('design__instance_unmapped__count', 'synthesis__check_error__count',
                 'design__inferred_latch__count', 'design__lint_error__count', 'route__drc_errors',
                 'magic__drc_error__count', 'klayout__drc_error__count', 'magic__illegal_overlap__count',
                 'design__lvs_error__count', 'design__xor_difference__count',
                 'design__critical_disconnected_pin__count', 'design__power_grid_violation__count',
                 'route__antenna_violation__count'):
        require(metrics.get(name) == 0, 'ASIC required zero metric missing/nonzero: ' + name)
    diagnostics = read_json(folder / 'physical_diagnostics.json')
    require(len(diagnostics.get('corners', {})) == 9, 'ASIC corner coverage differs')
    for name, corner in diagnostics['corners'].items():
        require(corner.get('violating_pins') == [], 'ASIC violating pins: ' + name)
        for stem in ('timing__setup__ws', 'timing__hold__ws'):
            slack = corner['metrics'].get(stem + '__corner:' + name)
            require(isinstance(slack, (int, float)) and math.isfinite(slack) and slack >= 0,
                    'ASIC negative/missing slack: ' + name)
        for stem in ('timing__setup_vio__count', 'timing__hold_vio__count',
                     'design__max_slew_violation__count', 'design__max_cap_violation__count',
                     'design__max_fanout_violation__count', 'timing__unannotated_net_filtered__count'):
            require(corner['metrics'].get(stem + '__corner:' + name) == 0,
                    'ASIC physical violation/missing metric: ' + stem)
    return {'status': 'PASS', 'prechecks': 15, 'corners': 9,
            'gls_transactions': 777, 'sdf_annotated': False, 'full_signoff': False}


def check_pilot(folder):
    manifest = read_json(folder / 'manifest.json')
    trials = manifest['trials']
    rows = [json.loads(line) for line in (folder / 'trials.jsonl').read_text().splitlines()]
    require(manifest.get('widths') == [8, 24] and manifest.get('max_retries') == 2 and
            manifest.get('seed') == 20261107 and manifest.get('per_site') == 16, 'Pilot configuration changed')
    pilot_campaign.validate_manifest(trials, 16)
    require(len(trials) == len(rows) == 429 and [r.get('id') for r in rows] == list(range(429)),
            'Pilot denominator/identity mismatch')
    require(read_json(folder / 'compile_exit.json')['returncode'] == 0, 'Pilot compile failed')
    check_sources(folder, read_json(folder / 'source_sha256.json'))
    for trial, row in zip(trials, rows):
        retained = folder / f"trial_{trial['id']:04d}"
        require(read_json(retained / 'exit.json')['returncode'] == 0, 'Pilot trial failed')
        replay = pilot_campaign.analyze(trial, pilot_campaign.read_csv(retained / 'trace.csv'),
                                        pilot_campaign.read_csv(retained / 'ack.csv'))
        replay['id'] = trial['id']
        require(replay == row, 'Pilot raw-trace replay mismatch: ' + str(trial['id']))
        require(pilot_campaign.trial_failure(trial, row) is None,
                'Pilot calibration/acknowledgement failure: ' + str(trial['id']))
    summary = read_json(folder / 'summary.json')
    require(summary.get('planned') == summary.get('recorded') == 429 and summary.get('failures') == [],
            'Pilot summary denominator/failure mismatch')
    require(summary['groups'] == pilot_campaign.summarize(trials, rows), 'Pilot grouped outcomes mismatch')
    controls = read_json(folder / 'controls.json')
    require(len(controls) == 25 and len({c['name'] for c in controls}) == 25, 'Pilot control coverage differs')
    control = next(c for c in controls if c['name'] == 'missing_tool_denominator')
    require(control.get('planned') == control.get('retained') == 54 and control.get('returncode') == 1,
            'Pilot failed-infrastructure denominator was lost')
    return {'trials': 429, 'controls': 25, 'outcomes': dict(Counter(r['classification'] for r in rows)),
            'scope': 'Digital RTL mechanism pilot; no radiation rate inference'}


def check_cost(folder):
    results = read_json(folder / 'results.json')
    manifest = read_json(folder / 'manifest.json')
    require(len(results) == 4 and {r['variant'] for r in results} == VARIANTS, 'Cost variant coverage differs')
    require(manifest.get('variants') == ['unprotected', 'secded', 'hybrid', 'tmr'] and
            manifest.get('period_ns') == 10 and manifest.get('max_dsp') == 0,
            'Cost experiment policy differs')
    check_sources(folder, manifest['source_sha256'])
    for row in results:
        require(row.get('returncode') == 0 and row.get('complete') == '1' and
                row.get('status') == 'failure_to_close', 'Historical timing failure was hidden')
        slacks = [float(row[k]) for k in ('setup_slack_ns', 'hold_slack_ns', 'pulse_width_slack_ns')]
        require(all(math.isfinite(v) for v in slacks) and min(slacks) < 0, 'Cost timing classification unsupported')
        require(all(row.get(k, -1) >= 0 for k in ('lut', 'ff', 'dsp')), 'Cost utilization missing')
        require(row.get('part') == 'xc7z020clg484-1' and row.get('dsp_policy') == 'max_dsp_0', 'Cost part/DSP policy differs')
        require(read_json(folder / row['variant'] / 'result.json') == row, 'Cost per-variant result differs')
    summary = read_json(folder / 'summary.json')
    require(summary.get('results') == results and summary.get('failures') == [] and
            summary.get('process_groups_quiescent') is True, 'Cost execution summary differs')
    controls = read_json(folder / 'controls.json')
    require(len(controls) == 21 and all(c.get('expected') == c.get('observed') for c in controls),
            'Cost negative controls differ')
    return {'variants': 4, 'controls': 21, 'timing_closed': 0, 'scope': 'Core-only OOC, not board timing'}


def check_reference_layout(package, manifest):
    base = 'data/asic/project/src/runs/R2/final/'
    gds = base + 'klayout_gds/tt_um_mac_sentry.klayout.gds'
    pnl = base + 'pnl/tt_um_mac_sentry.pnl.v'
    lef = base + 'lef/tt_um_mac_sentry.lef'
    reference = manifest.get('reference_layout', {})
    require(reference.get('top') == 'tt_um_mac_sentry' and
            set(reference.get('files', {})) == {gds, pnl, lef},
            'Reference layout file coverage differs')
    for relative, identity in reference['files'].items():
        path = safe_file(package, relative)
        require(identity == manifest['files'].get(relative) and digest(path) == identity.get('sha256'),
                'Reference layout identity mismatch: ' + relative)
    data = (package / gds).read_bytes()
    require(len(data) >= 10 and data[:4] == bytes.fromhex('00060002') and
            data[-4:] == bytes.fromhex('00040400'),
            'Reference GDS HEADER/ENDLIB framing differs')
    require(b'tt_um_mac_sentry' in data and
            re.search(r'\bmodule\s+tt_um_mac_sentry\s*\(', (package / pnl).read_text()) and
            re.search(r'^MACRO tt_um_mac_sentry\s*$', (package / lef).read_text(), re.M),
            'Reference deliverable top names differ')
    return {'files': 3, 'top': 'tt_um_mac_sentry',
            'scope': 'Historical file integrity/basic syntax only; not a new DRC/LVS/signoff run'}


def verify(package):
    package = Path(package)
    require(package.is_dir() and not package.is_symlink(), 'Missing/nonregular evidence package')
    manifest = read_json(safe_file(package, 'manifest.json'))
    require(manifest.get('schema') == 1 and bool(manifest.get('files')), 'Unsupported/empty evidence inventory')
    entries = manifest['files']
    actual = set()
    for path in (package / 'data').rglob('*'):
        require(not path.is_symlink(), 'Symlink in published data')
        if path.is_file():
            actual.add(path.relative_to(package).as_posix())
    require(actual == set(entries), 'Published data inventory has missing or unlisted members')
    for relative, record in entries.items():
        require(relative.startswith('data/'), 'Evidence outside data tree')
        path = safe_file(package, relative)
        require(path.stat().st_size == record.get('bytes') and digest(path) == record.get('sha256'),
                'Published evidence hash/size mismatch: ' + relative)
    data = package / 'data'
    board_runs = list((data / 'board').iterdir())
    require(len(board_runs) == 4 and all(p.is_dir() for p in board_runs), 'Board archive coverage differs')
    with (data / 'board/2026-11-06_secded_saved_captures_001/tests.csv').open(newline='') as stream:
        board = list(csv.DictReader(stream))
    require(any('A3' in row.get('capture', '') and row.get('status') == 'BLOCKED' for row in board),
            'Historical blocked A3 outcome missing')
    return {'status': 'PASS', 'files': len(entries), 'reference_layout': check_reference_layout(package, manifest),
            'asic': check_asic(data / 'asic'),
            'pilot': check_pilot(data / 'pilot'), 'fpga_cost': check_cost(data / 'fpga_cost'),
            'board_summary_archives': 4,
            'scope': 'Published historical evidence consistency; no new implementation/hardware validation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'results/published')
    args = parser.parse_args()
    try:
        result = verify(args.package)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({'status': 'FAIL', 'reason': str(error)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
