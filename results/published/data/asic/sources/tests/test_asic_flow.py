"""Fail-closed evidence parser tests; synthetic fixtures are NOT physical results."""
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location('asic_flow', Path(__file__).resolve().parents[1] / 'scripts/test_asic_flow.py')
flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow)


def fixture_metrics():
    metrics = dict.fromkeys(flow.ZERO_METRICS, 0)
    for corner in flow.CORNERS:
        for key in flow.CORNER_ZERO:
            metrics[f'{key}__corner:{corner}'] = 0
        for kind in ('setup', 'hold'):
            metrics[f'timing__{kind}__ws__corner:{corner}'] = 0.1
    for corner in flow.CORNERS:
        metrics[f'timing__unannotated_net__count__corner:{corner}'] = 0
    metrics.update(design__instance__count__stdcell=100,
        design__instance__area__stdcell=1000, design__core__area=60000,
        design__die__bbox='0.0 0.0 334.88 225.76')
    return metrics


def annotation_report(pins, partial=0):
    return ('report_parasitic_annotation -report_unannotated\n' + '=' * 76 + '\n' +
            f'Found {len(pins)} unannotated drivers.\n' + ''.join(' ' + p + '\n' for p in pins) +
            f'Found {partial} partially unannotated drivers.\n' + '=' * 75 + '\n' +
            'check_setup -verbose -unconstrained_endpoints\n')


class FlowEvidenceTests(unittest.TestCase):
    def vendor_fixture(self, root, staged=False):
        # Small synthetic tool inputs exercise real prepare/copy/identity checks;
        # no external process, installed tool, or physical result is involved.
        tools = root / 'build/asic-tools'
        vendor = root / '.context/vendor'
        pins = {name: {'commit': commit} for name, commit in flow.COMMITS.items()}
        roots = [tools / 'vendor'] + ([vendor] if staged else [])
        for folder in roots:
            for rel, content in {
                    'sources.json': json.dumps(pins),
                    'tt-support-tools/precheck/precheck.py': str(folder),
                    'tt-support-tools/tech/fixture.txt': str(folder),
                    'tt-support-tools/project_info.py': str(folder),
                    'ttsky-verilog-template/src/config.json': '{}',
                    }.items():
                path = folder / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        base_sdc = tools / 'venv/lib/python3.11/site-packages/librelane/scripts/base.sdc'
        base_sdc.parent.mkdir(parents=True)
        base_sdc.write_text('synthetic SDC fixture')
        for rev in (flow.HARDEN_PDK, flow.PRECHECK_PDK):
            path = tools / f'pdk/ciel/sky130/versions/{rev}/sky130A/SOURCES'
            path.parent.mkdir(parents=True)
            path.write_text('open_pdks ' + rev)
        (tools / 'setup-manifest.json').write_text(json.dumps({
            'images': {'librelane': 'a' * 64, 'precheck': 'b' * 64}}))
        return tools, vendor

    def test_vendor_staged_preference_and_no_context_prepared_fallback(self):
        for staged in (True, False):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools, vendor = self.vendor_fixture(root, staged)
                expected = vendor if staged else tools / 'vendor'
                out = root / 'output'
                with patch.object(flow, 'TOOLS', tools), patch.object(flow, 'VENDOR', vendor), \
                     patch.dict(flow.os.environ, {}, clear=True):
                    self.assertEqual(flow.resolve_vendor(), expected)
                    flow.prepare(out, 2)
                for rel in ('precheck/precheck.py', 'tech/fixture.txt', 'project_info.py'):
                    self.assertEqual((out / 'tt' / rel).read_text(), str(expected))
                self.assertEqual((out / 'vendor-sources.json').read_bytes(),
                                 (expected / 'sources.json').read_bytes())
                self.assertEqual((root / '.context').exists(), staged)

    def test_damaged_staged_vendor_never_uses_valid_prepared_fallback(self):
        for damage in ('missing_manifest', 'invalid_json', 'missing_precheck',
                       'regular_file', 'broken_symlink'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools, vendor = self.vendor_fixture(root)
                vendor.parent.mkdir()
                if damage == 'regular_file':
                    vendor.write_text('damaged staged path')
                elif damage == 'broken_symlink':
                    vendor.symlink_to(root / 'missing-target', target_is_directory=True)
                else:
                    vendor.mkdir()
                    if damage != 'missing_manifest':
                        (vendor / 'sources.json').write_text('{' if damage == 'invalid_json'
                            else (tools / 'vendor/sources.json').read_text())
                with patch.object(flow, 'TOOLS', tools), patch.object(flow, 'VENDOR', vendor):
                    self.assertEqual(flow.resolve_vendor(), vendor)
                    with self.assertRaises((OSError, json.JSONDecodeError)):
                        flow.prepare(root / 'output', 2)
                self.assertFalse((root / 'output/provenance.json').exists())

    def test_vendor_commit_drift_rejected_in_both_locations(self):
        for staged in (True, False):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools, vendor = self.vendor_fixture(root, staged)
                selected = vendor if staged else tools / 'vendor'
                pins = json.loads((selected / 'sources.json').read_text())
                pins['tt-support-tools']['commit'] = '0' * 40
                (selected / 'sources.json').write_text(json.dumps(pins))
                with patch.object(flow, 'TOOLS', tools), patch.object(flow, 'VENDOR', vendor):
                    with self.assertRaisesRegex(ValueError, '^Vendor commit drift$'):
                        flow.prepare(root / 'output', 2)
                self.assertFalse((root / 'output').exists())

    def test_vendor_identity_disagreement_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools, vendor = self.vendor_fixture(root, staged=True)
            pins = json.loads((vendor / 'sources.json').read_text())
            pins['tt-support-tools']['archive_sha256'] = 'changed fixture identity'
            (vendor / 'sources.json').write_text(json.dumps(pins))
            with patch.object(flow, 'TOOLS', tools), patch.object(flow, 'VENDOR', vendor):
                with self.assertRaisesRegex(ValueError, 'Staged and prepared vendor identities disagree'):
                    flow.prepare(root / 'output', 2)
            self.assertFalse((root / 'output').exists())

    def test_vendor_access_error_does_not_trigger_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools, vendor = self.vendor_fixture(Path(tmp), staged=True)
            with patch.object(flow, 'TOOLS', tools), patch.object(flow, 'VENDOR', vendor), \
                 patch.object(Path, 'lstat', side_effect=PermissionError('fixture access denial')):
                with self.assertRaises(PermissionError):
                    flow.resolve_vendor()

    def test_private_mount_label_and_prepared_image_uid_mapping(self):
        # Regression for the reproduced enforcing-SELinux bind denial and the
        # keep-id Nix big-lock failure. No global label/confinement changes.
        command = flow.container_command(Path('/tmp/run with spaces'), Path('/cache/pdk'),
            'sha256:' + 'a' * 64, '/work', ('python3', '--version'), 2)
        mounts = [command[i + 1] for i, arg in enumerate(command) if arg == '-v']
        self.assertEqual(mounts, ['/tmp/run with spaces:/work:rw,Z', '/cache/pdk:/pdk:ro'])
        self.assertIn('--network=none', command)
        self.assertIn('--pull=never', command)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', command)
        self.assertFalse(any(arg.startswith(('--userns', '--user=', '--privileged', '--security-opt'))
                             for arg in command))
        self.assertEqual(command[-3:], ['sha256:' + 'a' * 64, 'python3', '--version'])

    def test_container_access_probe_preserves_access_errors_and_hash_checks(self):
        # Run the same inline program used in the container. Permission denial
        # is simulated: these tests never chmod/relabel host files.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'config with spaces.json'
            source.write_text('{"fixture": true}')
            marker = root / 'access.txt'
            command = flow.access_probe(str(marker), [(str(source), source)])
            def execute(argv=command):
                output = io.StringIO()
                with patch('sys.argv', ['-c', *argv[3:]]), contextlib.redirect_stdout(output):
                    exec(compile(argv[2], '<container-access-probe>', 'exec'), {})
                return output.getvalue()
            self.assertIn('M2_CONTAINER_ACCESS_OK', execute())
            self.assertIn('not a physical PASS', marker.read_text())
            with self.assertRaises(FileExistsError):
                execute()  # Never overwrite prior probe evidence.
            marker.unlink()
            bad = command.copy(); bad[-1] = hashlib.sha256(b'other config').hexdigest()
            with self.assertRaisesRegex(ValueError, 'M2_INPUT_HASH_MISMATCH'):
                execute(bad)
            self.assertFalse(marker.exists())
            with patch.object(Path, 'read_bytes', side_effect=PermissionError(13, 'Permission denied', str(source))):
                with self.assertRaises(PermissionError):
                    execute()
            self.assertFalse(marker.exists())
            source.unlink()
            with self.assertRaises(FileNotFoundError):
                execute()
            self.assertFalse(marker.exists())

    def test_complete_synthetic_metrics(self):
        flow.validate_metrics(fixture_metrics())

    def test_every_required_metric_missing_or_failed_is_rejected(self):
        good = fixture_metrics()
        keys = flow.ZERO_METRICS + [f'{k}__corner:{c}' for c in flow.CORNERS for k in flow.CORNER_ZERO]
        for key in keys:
            for mutation in ('missing', 1, -1, float('nan'), float('inf'), '0', None, False):
                with self.subTest(key=key, mutation=mutation):
                    bad = copy.deepcopy(good)
                    if mutation == 'missing':
                        del bad[key]
                    else:
                        bad[key] = mutation
                    with self.assertRaises(ValueError):
                        flow.validate_metrics(bad)

    def test_slack_all_corners_and_fit(self):
        for corner in flow.CORNERS:
            for kind in ('setup', 'hold'):
                key = f'timing__{kind}__ws__corner:{corner}'
                for value in (-0.001, float('inf'), float('nan'), None):
                    bad = fixture_metrics(); bad[key] = value
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        flow.validate_metrics(bad)
        for key, value in [('design__instance__count__stdcell', 0),
                           ('design__instance__area__stdcell', 60001),
                           ('design__die__bbox', '0 0 161 111.52')]:
            bad = fixture_metrics(); bad[key] = value
            with self.assertRaises(ValueError):
                flow.validate_metrics(bad)

    def test_precheck_requires_every_case_and_no_failure_or_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'results.xml'
            with self.assertRaises(ValueError):
                flow.validate_precheck(path)
            good = ET.Element('testsuites')
            suite = ET.SubElement(good, 'testsuite')
            for name in sorted(flow.PRECHECKS):
                ET.SubElement(suite, 'testcase', name=name)
            ET.ElementTree(good).write(path)
            flow.validate_precheck(path)
            for name in flow.PRECHECKS:
                for tag in ('missing', 'error', 'failure', 'skipped', 'duplicate'):
                    bad = copy.deepcopy(good)
                    group = bad.find('testsuite')
                    case = next(c for c in group if c.get('name') == name)
                    if tag == 'missing': group.remove(case)
                    elif tag == 'duplicate': group.append(copy.deepcopy(case))
                    else: ET.SubElement(case, tag)
                    ET.ElementTree(bad).write(path)
                    with self.subTest(name=name, tag=tag), self.assertRaises(ValueError):
                        flow.validate_precheck(path)

    def test_physical_artifacts_and_sta_diagnostics_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            config = {'meta': {'librelane_version': '3.0.14'},
                      'STA_CORNERS': flow.CORNERS, 'CLOCK_PERIOD': 50, 'CLOCK_PORT': 'clk'}
            for key in ('RUN_DRT', 'RUN_CTS', 'RUN_MCSTA', 'RUN_SPEF_EXTRACTION',
                        'RUN_MAGIC_DRC', 'RUN_KLAYOUT_DRC', 'RUN_KLAYOUT_XOR', 'RUN_LVS'):
                config[key] = True
            config.update(json.loads((flow.ROOT / 'asic/flow/overrides.json').read_text()))
            config.update(SIGNOFF_SDC_FILE='constraints.sdc', PNR_SDC_FILE='constraints_pnr.sdc')
            (run / 'resolved.json').write_text(json.dumps(config))
            final = run / 'final'; final.mkdir()
            (final / 'metrics.json').write_text(json.dumps(fixture_metrics()))
            files = []
            for fmt, suffix in [('gds', 'gds'), ('lef', 'lef'), ('nl', 'nl.v'),
                                ('pnl', 'pnl.v'), ('def', 'def'), ('sdc', 'sdc')]:
                path = final / fmt / f'{flow.TOP}.{suffix}'
                path.parent.mkdir()
                path.write_text('sky130_fd_sc_hd__clkbuf_16 clkbuf_0_clk (.A(clk), .X(n));\n'
                                'sky130_fd_sc_hd__dfxtp_1 ff (.CLK(n), .Q(q));\n')
                files.append(path)
            for pattern, report in flow.PHYSICAL_REPORTS.items():
                folder = run / pattern.replace('*', '60')
                for name in (report, 'state_out.json'):
                    path = folder / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('synthetic fixture')
                    files.append(path)
            (run / '44-openroad-detailedrouting').mkdir()
            for name in ('reports/antenna.rpt', 'reports/antenna_summary.rpt', 'state_out.json'):
                path = run / '46-openroad-checkantennas-1' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic fixture')
                files.append(path)
            for corner in flow.CORNERS:
                folder = run / '54-openroad-stapostpnr' / corner
                folder.mkdir(parents=True)
                for name in ('checks.rpt', 'max.rpt', 'min.rpt', 'sta.log', 'filter_unannotated.log'):
                    path = folder / name
                    path.write_text(annotation_report([]))
                    files.append(path)
            flow.validate_physical(run)
            for path in files:
                original = path.read_bytes()
                path.unlink()
                with self.subTest(path=path), self.assertRaises(ValueError):
                    flow.validate_physical(run)
                path.write_bytes(original)
            checks = files[-5]
            for diagnostic in ('Warning: unconstrained endpoint\n', '(unconstrained)\n'):
                checks.write_text('check_setup -verbose -unconstrained_endpoints\n' + diagnostic)
                with self.assertRaisesRegex(ValueError, 'STA checks'):
                    flow.validate_physical(run)
            checks.write_text(annotation_report([]))
            # Even clean synthetic metrics must not conceal a forbidden buffer
            # in the real netlist. clkbuf_16 in the positive fixture also proves
            # that the exact clkbuf_1 pattern does not exclude the CTS root.
            netlist = final / 'nl' / f'{flow.TOP}.nl.v'
            original_netlist = netlist.read_text()
            for kind in ('clkbuf_1', 'buf_1', 'clkdlybuf4s25_1',
                         'dlygate4sd3_1', 'dlymetal6s2s_1'):
                netlist.write_text(original_netlist +
                    f'sky130_fd_sc_hd__{kind} weak (.A(q), .X(unused));\n')
                diagnostic = run / 'diagnostic.json'
                with self.subTest(excluded=kind), self.assertRaisesRegex(ValueError, 'Excluded cells remain'):
                    flow.validate_physical(run, diagnostic)
                self.assertEqual(json.loads(diagnostic.read_text())['excluded_cell_instances'],
                                 {'weak': 'sky130_fd_sc_hd__' + kind})
            netlist.write_text(original_netlist)
            flow.validate_physical(run)
            # These literal signoff contracts must survive the tighter PNR split.
            # Positive metric fixtures cannot override a relaxed configuration.
            for key, value in (
                    ('CLOCK_PERIOD', 60), ('MAX_FANOUT_CONSTRAINT', 11),
                    ('MAX_TRANSITION_CONSTRAINT', 0.8),
                    ('MAX_CAPACITANCE_CONSTRAINT', 0.3),
                    ('TIME_DERATING_CONSTRAINT', 0),
                    ('SIGNOFF_SDC_FILE', 'constraints_pnr.sdc'),
                    ('STA_CORNERS', flow.CORNERS[:-1]),
                    ('MAX_SLEW_VIOLATION_CORNERS', ['nom_*']),
                    ('CTS_ROOT_BUFFER', 'sky130_fd_sc_hd__clkbuf_8'),
                    ('EXTRA_EXCLUDED_CELLS', config['EXTRA_EXCLUDED_CELLS'][:-1]),
                    ('GRT_DESIGN_REPAIR_MAX_SLEW_PCT', 30),
                    ('RUN_POST_GRT_DESIGN_REPAIR', False)):
                bad = copy.deepcopy(config); bad[key] = value
                (run / 'resolved.json').write_text(json.dumps(bad))
                with self.subTest(relaxed=key), self.assertRaises(ValueError):
                    flow.validate_physical(run)
            config['RUN_LVS'] = False
            (run / 'resolved.json').write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, 'disabled'):
                flow.validate_physical(run)

    def test_multiple_violations_collected_and_missing_final(self):
        metrics = fixture_metrics()
        metrics['route__drc_errors'] = 4
        key = f'design__max_fanout_violation__count__corner:{flow.CORNERS[0]}'
        metrics[key] = 2
        with self.assertRaises(flow.EvidenceErrors) as raised:
            flow.validate_metrics(metrics)
        self.assertEqual(len(raised.exception.errors), 2)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            diagnostic = run / 'diagnostic.json'
            with self.assertRaises(flow.EvidenceErrors):
                flow.validate_physical(run, diagnostic)
            errors = json.loads(diagnostic.read_text())['errors']
            self.assertTrue(any('metrics.json' in e for e in errors))
            self.assertTrue(any('Missing/ambiguous post-route STA' in e for e in errors))

    def test_failed_harden_or_missing_stage_can_never_pass(self):
        stages = {name: {'status': 'PASS'} for name in flow.REQUIRED_STAGES}
        self.assertEqual(flow.final_result(stages)['status'], 'PASS')
        for name in flow.REQUIRED_STAGES:
            bad = copy.deepcopy(stages)
            bad[name] = {'status': 'FAIL', 'error': 'exit 2'}
            self.assertEqual(flow.final_result(bad)['status'], 'FAIL')
            del bad[name]
            self.assertEqual(flow.final_result(bad)['status'], 'FAIL')

    def test_main_continues_after_failed_harden_and_physical(self):
        # Exercise the actual orchestrator with fake external processes. Synthetic
        # results test control flow only; no fake result enters a real run folder.
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def prepare(out, jobs):
                for rel in ('project/src/config.json', 'pdk/sky130A/SOURCES',
                            'tt/precheck/precheck.py'):
                    path = out / rel; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('synthetic fixture')
                for fmt, suffix in [('gds', 'gds'), ('lef', 'lef'), ('pnl', 'pnl.v')]:
                    path = out / f'project/src/runs/R2/final/{fmt}/{flow.TOP}.{suffix}'
                    path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture')
                return {'librelane': 'fake', 'precheck': 'fake'}, dict.fromkeys(
                    ('librelane', 'precheck'), out / 'pdk')
            calls = []
            def process(argv, **kwargs):
                calls.append(argv)
                kwargs['stdout'].write('3.0.14\n')
                return SimpleNamespace(returncode=2 if '--run-tag' in argv else 0)
            def physical(path, diagnostic):
                flow.write_json(diagnostic, {'errors': ['slew', 'fanout']})
                raise flow.EvidenceErrors(['slew', 'fanout'])
            def gls(out, physical, pdks, run, stage):
                for name in ('gls_positive', 'gls_negative_observation', 'gls_negative_arithmetic'):
                    stage(name, lambda: None)
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'prepare', prepare), \
                 patch.object(flow.subprocess, 'run', process), \
                 patch.object(flow, 'validate_physical', physical), \
                 patch.object(flow, 'validate_precheck'), patch.object(flow, 'execute_gls', gls), \
                 patch.object(flow.os, 'chdir'), patch('sys.argv', ['test_asic_flow.py']), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(flow.main(), 1)
            result, = root.glob('build/asic_flow/run_*/result.json')
            data = json.loads(result.read_text())
            self.assertEqual(data['status'], 'FAIL')
            self.assertEqual(data['stages']['harden']['status'], 'FAIL')
            self.assertEqual(data['stages']['physical']['status'], 'FAIL')
            self.assertEqual(data['stages']['precheck']['status'], 'PASS')
            self.assertEqual(data['stages']['gls_positive']['status'], 'PASS')
            self.assertTrue(any('python precheck.py' in str(arg) for call in calls for arg in call))

    def test_unannotated_only_proven_disconnected_outputs(self):
        corner = flow.CORNERS[0]
        metrics = fixture_metrics()
        metrics[f'timing__unannotated_net__count__corner:{corner}'] = 2
        netlist = ('sky130_fd_sc_hd__conb_1 tie (.LO(lo));\n'
                   'sky130_fd_sc_hd__clkbuf_4 clkload0 (.A(clock));\n')
        pins = ['tie/HI', 'clkload0/X']
        report = annotation_report(pins)
        self.assertEqual(flow.validate_unannotated(report, metrics, corner, flow.cell_instances(netlist)), pins)
        for altered in [netlist.replace('.LO(lo)', '.LO(lo), .HI(real_signal)'),
                        netlist.replace('.A(clock)', '.A(clock), .X(real_clock)'),
                        netlist.replace('conb_1', 'buf_1')]:
            with self.assertRaisesRegex(ValueError, 'connected/unapproved'):
                flow.validate_unannotated(report, metrics, corner, flow.cell_instances(altered))
        for report_bad in [annotation_report(['tie/LO', 'clkload0/X']),
                           annotation_report(pins, partial=1),
                           report.replace('Found 2', 'Found 3'),
                           report.replace(' clkload0/X', ' signal/X'),
                           report.replace('Found 0 partially unannotated drivers.',
                                          'Found 0 partially unannotated drivers.\n hidden/X')]:
            with self.assertRaises(ValueError):
                flow.validate_unannotated(report_bad, metrics, corner, flow.cell_instances(netlist))
        for key in ('timing__unannotated_net__count', 'timing__unannotated_net_filtered__count'):
            for value in (None, 1):
                bad = copy.deepcopy(metrics)
                bad[f'{key}__corner:{corner}'] = value
                with self.assertRaises(ValueError):
                    flow.validate_unannotated(report, bad, corner, flow.cell_instances(netlist))

    def test_clock_diagnostics_include_dummy_and_antenna_loads(self):
        netlist = ('sky130_fd_sc_hd__clkbuf_16 root (.A(clk), .X(n));\n'
                   'sky130_fd_sc_hd__clkbuf_4 leaf (.A(n), .X(l));\n'
                   'sky130_fd_sc_hd__clkbuf_4 clkload0 (.A(n));\n'
                   'sky130_fd_sc_hd__diode_2 antenna (.DIODE(n));\n'
                   'sky130_fd_sc_hd__dfxtp_1 ff (.CLK(l), .Q(q));\n')
        tree = flow.clock_tree(netlist)
        self.assertEqual(tree['root_fanout'], 3)
        self.assertEqual(tree['fanouts']['leaf'], 1)
        self.assertEqual((tree['min_depth'], tree['max_depth']), (2, 2))
        self.assertTrue(tree['balanced_depth'])


if __name__ == '__main__':
    unittest.main()
