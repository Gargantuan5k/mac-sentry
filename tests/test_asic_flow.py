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
    def vendor_fixture(self, root):
        tools = root / 'build/asic-tools'
        vendor = tools / 'vendor'
        pins = {name: {'commit': commit, 'tar_sha256': flow.VENDOR_PINS[name]['tar_sha256']}
                for name, commit in flow.COMMITS.items()}
        for rel, content in {
                'sources.json': json.dumps(pins),
                'tt-support-tools/precheck/precheck.py': 'prepared vendor',
                'tt-support-tools/tech/fixture.txt': 'prepared vendor',
                'tt-support-tools/project_info.py': 'prepared vendor',
                'ttsky-verilog-template/src/config.json': '{}',
                }.items():
            path = vendor / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
        # Exercise discovery rather than a hardcoded Python 3.11 site path.
        base_sdc = tools / 'venv/lib/python3.12/site-packages/librelane/scripts/base.sdc'
        base_sdc.parent.mkdir(parents=True); base_sdc.write_text('synthetic SDC fixture')
        for rev in (flow.HARDEN_PDK, flow.PRECHECK_PDK):
            path = tools / f'pdk/ciel/sky130/versions/{rev}/sky130A/SOURCES'
            path.parent.mkdir(parents=True); path.write_text('open_pdks ' + rev)
        (tools / 'setup-manifest.json').write_text(json.dumps({
            'schema':2,'lock_sha256':flow.digest(flow.LOCK_PATH),'status':'PREPARED', 'images': {'librelane': 'a' * 64, 'precheck': 'b' * 64}}))
        return tools, vendor

    def test_prepared_cache_used_without_agent_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tools,vendor=self.vendor_fixture(root);out=root/'output'
            with patch.object(flow,'TOOLS',tools), patch.dict(flow.os.environ,{},clear=True):
                self.assertEqual(flow.resolve_vendor(),vendor); flow.prepare(out,2)
            self.assertEqual((out/'tt/precheck/precheck.py').read_text(),'prepared vendor')
            self.assertEqual((out/'project/src/base.sdc').read_text(),'synthetic SDC fixture')
            self.assertFalse((root/'.context').exists())
            self.assertIn('tools/container_runtime.py',json.loads((out/'provenance.json').read_text())['source_sha256'])

    def test_damaged_prepared_cache_is_not_masked_by_agent_context(self):
        for damage in ('missing_manifest','invalid_json','missing_precheck','regular_file','broken_symlink'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);tools,vendor=self.vendor_fixture(root)
                staged=root/'.context/vendor';staged.mkdir(parents=True);(staged/'sources.json').write_text((vendor/'sources.json').read_text())
                if damage=='missing_manifest':(vendor/'sources.json').unlink()
                elif damage=='invalid_json':(vendor/'sources.json').write_text('{')
                elif damage=='missing_precheck':(vendor/'tt-support-tools/precheck/precheck.py').unlink()
                else:
                    import shutil
                    shutil.rmtree(vendor)
                    if damage=='regular_file':vendor.write_text('bad')
                    else:vendor.symlink_to(root/'missing')
                with patch.object(flow,'TOOLS',tools):
                    with self.assertRaises((OSError,ValueError)):flow.prepare(root/'output',2)
                self.assertFalse((root/'output/provenance.json').exists())

    def test_vendor_commit_and_archive_drift_rejected(self):
        for field in ('commit','tar_sha256'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);tools,vendor=self.vendor_fixture(root)
                pins=json.loads((vendor/'sources.json').read_text());pins['tt-support-tools'][field]='0'*len(pins['tt-support-tools'][field]);(vendor/'sources.json').write_text(json.dumps(pins))
                with patch.object(flow,'TOOLS',tools),self.assertRaisesRegex(ValueError,'Vendor (commit|archive identity) drift'):flow.prepare(root/'output',2)
                self.assertFalse((root/'output').exists())

    def test_incomplete_or_lock_drifted_cache_cannot_prepare(self):
        for status,schema,lock in [('FAILED',2,'x'),('RUNNING',1,None),('PREPARED',2,'0'*64),('PASS',2,flow.digest(flow.LOCK_PATH)),('PREPARED',1,None)]:
            with self.subTest(status=status,schema=schema),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);tools,_=self.vendor_fixture(root);p=tools/'setup-manifest.json';data=json.loads(p.read_text());data.update(status=status,schema=schema,lock_sha256=lock);p.write_text(json.dumps(data))
                with patch.object(flow,'TOOLS',tools),self.assertRaisesRegex(ValueError,'(not prepared|lock identity drift)'):flow.prepare(root/'output',2)
                self.assertFalse((root/'output/provenance.json').exists())

    def test_base_sdc_discovery_fails_on_missing_or_ambiguous_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools=Path(tmp)
            with patch.object(flow,'TOOLS',tools):
                with self.assertRaisesRegex(ValueError,'Expected one'):flow.base_sdc()
                for version in ('3.11','3.12'):
                    p=tools/f'venv/lib/python{version}/site-packages/librelane/scripts/base.sdc';p.parent.mkdir(parents=True);p.write_text('fixture')
                with self.assertRaisesRegex(ValueError,'Expected one'):flow.base_sdc()

    def test_cleanup_uses_only_run_owner_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);env={'MAC_SENTRY_RUN_ID':'test-own','MAC_SENTRY_CONTAINER_MARKER':str(out/'marker')}
            with patch.object(flow,'run_command') as run:
                self.assertEqual(flow.cleanup_containers(out,env),{'status':'NOT_USED'});run.assert_not_called()
            (out/'marker').write_text('owned')
            with patch.object(flow,'run_command',return_value=0) as run:
                self.assertEqual(flow.cleanup_containers(out,env)['status'],'PASS')
                self.assertEqual(run.call_args.args[0][-3:],['cleanup','--label','test-own'])
            with patch.object(flow,'run_command',return_value=1),self.assertRaisesRegex(RuntimeError,'cleanup failed'):flow.cleanup_containers(out,env)
            self.assertEqual(json.loads((out/'container_cleanup.json').read_text())['status'],'FAIL')

    def test_command_timeout_reaps_own_process_group(self):
        import os,subprocess,sys
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with self.assertRaises(subprocess.TimeoutExpired):
                flow.run_command([sys.executable,'-c','import time; time.sleep(30)'],out,out/'log',os.environ.copy(),0.05)

    def test_interrupted_main_still_cleans_owned_containers_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def interrupted(out,jobs):
                (out/'containers-used').write_text('fixture owner marker')
                raise KeyboardInterrupt('fixture interruption')
            with patch.object(flow,'ROOT',root),patch.object(flow,'prepare',interrupted), \
                 patch.object(flow,'cleanup_containers',return_value={'status':'PASS'}) as cleanup, \
                 patch.object(flow.os,'chdir'),patch('sys.argv',['test_asic_flow.py']),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):flow.main()
            cleanup.assert_called_once()
            out=cleanup.call_args.args[0];env=cleanup.call_args.args[1]
            self.assertEqual(env['MAC_SENTRY_RUN_ID'],'asic-'+out.name)
            self.assertEqual(env['MAC_SENTRY_CONTAINER_MARKER'],str(out/'containers-used'))
            self.assertEqual(json.loads((out/'result.json').read_text())['status'],'FAIL')
            self.assertIn('result.json',json.loads((out/'artifact_sha256.json').read_text()))

    def test_keyboard_interrupt_reaps_command_group(self):
        proc=unittest.mock.Mock(pid=1234);proc.wait.side_effect=KeyboardInterrupt('fixture')
        with tempfile.TemporaryDirectory() as tmp,patch.object(flow.subprocess,'Popen',return_value=proc), \
             patch.object(flow,'stop_group',return_value={'quiescent':True}) as cleanup:
            with self.assertRaises(KeyboardInterrupt):flow.run_command(['fixture'],Path(tmp),Path(tmp)/'log',{},1)
        cleanup.assert_called_once_with(proc)

    def test_private_mount_label_and_prepared_image_uid_mapping(self):
        # Regression for the reproduced enforcing-SELinux bind denial and the
        # keep-id Nix big-lock failure. No global label/confinement changes.
        command = flow.container_command(Path('/tmp/run with spaces'), Path('/cache/pdk'),
            'sha256:' + 'a' * 64, '/work', ('python3', '--version'), 2)
        self.assertEqual(Path(command[1]).parts[-2:], ('tools','container_runtime.py'))
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
            def process(argv, cwd, log, env, timeout):
                calls.append(argv)
                Path(log).write_text('3.0.14\n')
                return 2 if '--run-tag' in argv else 0
            def physical(path, diagnostic):
                flow.write_json(diagnostic, {'errors': ['slew', 'fanout']})
                raise flow.EvidenceErrors(['slew', 'fanout'])
            def gls(out, physical, pdks, run, stage):
                for name in ('gls_positive', 'gls_negative_observation', 'gls_negative_arithmetic'):
                    stage(name, lambda: None)
            with patch.object(flow, 'ROOT', root), patch.object(flow, 'prepare', prepare), \
                 patch.object(flow, 'run_command', process), \
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



class StandaloneSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'tools/setup_asic.py'
        spec=importlib.util.spec_from_file_location('standalone_setup',path)
        cls.setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.setup)

    def archive(self,root,members):
        import tarfile
        path=root/'vendor.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            for name,kind,payload in members:
                info=tarfile.TarInfo(name)
                if kind=='file':
                    data=payload.encode();info.size=len(data);tar.addfile(info,io.BytesIO(data))
                elif kind=='dir':info.type=tarfile.DIRTYPE;tar.addfile(info)
                else:info.type=tarfile.SYMTYPE;info.linkname=payload;tar.addfile(info)
        return path

    def test_archive_extracts_exact_payload_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=self.archive(root,[('repo','dir',''),('repo/src/config.json','file','fixture')]);dest=root/'out'
            self.setup.extract_vendor(archive,dest)
            self.assertEqual((dest/'src/config.json').read_text(),'fixture')
            with self.assertRaises(FileExistsError):self.setup.extract_vendor(archive,dest)

    def test_vendor_archive_rejects_traversal_links_multiple_roots_and_duplicates(self):
        cases=[[('../escape','file','bad')],[('repo/link','link','/etc/passwd')],
               [('one/a','file','a'),('two/b','file','b')],
               [('repo/a','file','a'),('repo/a','file','b')]]
        for members in cases:
            with self.subTest(members=members),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=self.archive(root,members)
                with self.assertRaises(ValueError):self.setup.extract_vendor(archive,root/'out')
                self.assertFalse((root/'out').exists());self.assertFalse((root/'escape').exists())

    def test_vendor_hash_mismatch_cannot_extract_or_record_success_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pins={'fixture':{'commit':'a'*40,'tar_sha256':'0'*64,'url':'https://codeload.github.com/TinyTapeout/fixture/tar.gz/'+'a'*40}}
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                self.setup.fetch_vendor(root,pins,opener=lambda *a,**k:io.BytesIO(b'wrong archive'))
            self.assertFalse((root/'vendor/fixture').exists());self.assertFalse((root/'vendor/sources.json').exists())

    def test_vendor_fetch_checks_payload_and_publishes_exact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=self.archive(root,[('repo/src/config.json','file','fixture')]);data=archive.read_bytes()
            pins={'fixture':{'commit':'a'*40,'tar_sha256':hashlib.sha256(data).hexdigest(),'requested_ref':'pinned','url':'https://codeload.github.com/TinyTapeout/fixture/tar.gz/'+'a'*40}}
            self.setup.fetch_vendor(root,pins,opener=lambda *a,**k:io.BytesIO(data))
            recorded=json.loads((root/'vendor/sources.json').read_text())
            self.assertEqual(recorded['fixture'],{k:v for k,v in pins['fixture'].items() if k!='url'})
            self.assertEqual((root/'vendor/fixture/src/config.json').read_text(),'fixture')

    def test_setup_plan_has_no_network_or_install_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'new'
            with patch.object(self.setup,'fetch_vendor') as fetch,patch.object(self.setup.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.setup.main(['--tools',str(dest)]),0)
            fetch.assert_not_called();run.assert_not_called();self.assertFalse(dest.exists())

    def test_setup_refuses_existing_cache_before_install_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp);(dest/'user-file').write_text('unchanged')
            with patch.object(self.setup,'fetch_vendor') as fetch,patch.object(self.setup.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(FileExistsError):self.setup.main(['--tools',str(dest),'--execute'])
            fetch.assert_not_called();run.assert_not_called();self.assertEqual((dest/'user-file').read_text(),'unchanged')

    def run_setup_fixture(self, root, cleanup_code):
        tools=root/'tools';statuses=[]
        def fetch(dest,pins):
            (dest/'vendor').mkdir();(dest/'vendor/sources.json').write_text(json.dumps(pins))
        def command(argv,log,env,timeout):
            text='';code=0
            if argv[0]=='fixture-python' and '-c' in argv:text='3.11\n'
            if 'inspect' in argv:text=('a' if 'librelane' in argv[3] else 'b')*64+'\n'
            if str(argv[1]).endswith('container_runtime.py'):
                if argv[2]=='run':
                    Path(env['MAC_SENTRY_CONTAINER_MARKER']).write_text('fixture owner')
                    if '-m' in argv:text='LibreLane 3.0.14\n'
                if argv[2]=='cleanup':
                    statuses.append(json.loads((tools/'setup-manifest.json').read_text())['status']);code=cleanup_code
            Path(log).write_text(text);return code
        with patch.object(self.setup,'fetch_vendor',fetch),patch.object(self.setup,'validate_pdks'), \
             patch.object(self.setup,'run_process',command),contextlib.redirect_stdout(io.StringIO()):
            if cleanup_code:
                with self.assertRaisesRegex(RuntimeError,'Setup command failed'):self.setup.main(['--tools',str(tools),'--python','fixture-python','--pdk-root',str(root/'pdk'),'--execute'])
            else:self.assertEqual(self.setup.main(['--tools',str(tools),'--python','fixture-python','--pdk-root',str(root/'pdk'),'--execute']),0)
        return json.loads((tools/'setup-manifest.json').read_text()),statuses

    def test_setup_publication_requires_successful_owned_container_cleanup(self):
        for code in (0,1):
            with self.subTest(cleanup_code=code),tempfile.TemporaryDirectory() as tmp:
                record,statuses=self.run_setup_fixture(Path(tmp),code)
                self.assertEqual(statuses,['RUNNING'])
                self.assertEqual(record['status'],'FAILED' if code else 'PREPARED')
                self.assertEqual(record['images'],{'librelane':'a'*64,'precheck':'b'*64})
                if code:self.assertIn('cleanup',record['reason'])

    def test_setup_command_interrupt_reaps_group(self):
        proc=unittest.mock.Mock(pid=1234);proc.wait.side_effect=KeyboardInterrupt('fixture')
        with tempfile.TemporaryDirectory() as tmp,patch.object(self.setup.subprocess,'Popen',return_value=proc),patch.object(self.setup,'stop_group',return_value={'quiescent':True}) as cleanup:
            with self.assertRaises(KeyboardInterrupt):self.setup.run_process(['fixture'],Path(tmp)/'log',{},1)
        cleanup.assert_called_once_with(proc)

    def test_timeout_kills_term_resistant_descendant_even_after_parent_exits(self):
        import os,subprocess,sys,time
        from tools.process_runtime import group_members
        for runner in ('flow','setup'):
            with self.subTest(runner=runner),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);ready=root/'ready';pid_file=root/'pids'
                child='import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path('+repr(str(ready))+').write_text("ready"); time.sleep(60)'
                parent='import subprocess,sys,time,pathlib,os; p=subprocess.Popen([sys.executable,"-c",'+repr(child)+']); pathlib.Path('+repr(str(pid_file))+').write_text(str(os.getpid())+" "+str(p.pid)); time.sleep(60)'
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        if runner=='flow':flow.run_command([sys.executable,'-c',parent],root,root/'log',os.environ.copy(),1)
                        else:self.setup.run_process([sys.executable,'-c',parent],root/'log',os.environ.copy(),1)
                    self.assertTrue(ready.is_file(),'TERM-resistant child was actually initialized')
                    leader,child_pid=map(int,pid_file.read_text().split())
                    self.assertFalse(any(m['state'] not in ('Z','X') for m in group_members(leader)))
                finally:
                    if pid_file.exists():
                        leader=int(pid_file.read_text().split()[0])
                        try:os.killpg(leader,9)
                        except ProcessLookupError:pass

    def test_successful_leader_exit_cannot_leave_background_descendants(self):
        import os,sys
        from tools.process_runtime import group_members
        for runner in ('flow','setup'):
            with self.subTest(runner=runner),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);ready=root/'ready';pid_file=root/'pids'
                child='import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path('+repr(str(ready))+').write_text("ready"); time.sleep(60)'
                parent='import subprocess,sys,time,pathlib,os; p=subprocess.Popen([sys.executable,"-c",'+repr(child)+']); pathlib.Path('+repr(str(pid_file))+').write_text(str(os.getpid())+" "+str(p.pid)); ready=pathlib.Path('+repr(str(ready))+'); '+"\nwhile not ready.exists(): time.sleep(.01)"
                try:
                    if runner=='flow':self.assertEqual(flow.run_command([sys.executable,'-c',parent],root,root/'log',os.environ.copy(),5),0)
                    else:self.assertEqual(self.setup.run_process([sys.executable,'-c',parent],root/'log',os.environ.copy(),5),0)
                    self.assertTrue(ready.exists());leader=int(pid_file.read_text().split()[0])
                    self.assertFalse(any(m['state'] not in ('Z','X') for m in group_members(leader)))
                finally:
                    if pid_file.exists():
                        try:os.killpg(int(pid_file.read_text().split()[0]),9)
                        except ProcessLookupError:pass

    def test_pdk_pin_identity_and_immutable_image_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pins={'hardening_pdk':'a'*40,'precheck_pdk':'b'*40}
            for rev in pins.values():
                p=root/f'sky130/versions/{rev}/sky130A/SOURCES';p.parent.mkdir(parents=True);p.write_text('open_pdks '+rev)
            self.setup.validate_pdks(root,pins)
            p.write_text('wrong revision')
            with self.assertRaisesRegex(ValueError,'PDK identity'):self.setup.validate_pdks(root,pins)
        self.assertEqual(self.setup.image_id('sha256:'+'a'*64+'\n'),'a'*64)
        for value in ('latest','a'*63,'a'*64+'\n'+'b'*64):
            with self.assertRaises(ValueError):self.setup.image_id(value)

if __name__ == '__main__':
    unittest.main()
