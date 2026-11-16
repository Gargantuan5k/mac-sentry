"""Submission export/config controls; these do not certify a new physical run."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load('tapeout_export', ROOT / 'scripts/export_tapeout.py')
checker = load('tapeout_check', ROOT / 'asic/submission/scripts/check_package.py')


class TapeoutPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'candidate'
        self.manifest = exporter.export(ROOT, self.out)

    def ci_fixture(self):
        # Faithful shape of actual official support-tools merge; synthetic only.
        cfg = json.loads((self.out / 'src/config.json').read_text())
        cfg.update(DESIGN_NAME='tt_um_mac_sentry', DIE_AREA='0 0 334.88 225.76',
                   FP_DEF_TEMPLATE='dir::../tt/tech/sky130A/def/tt_block_2x2_pg.def',
                   VERILOG_FILES=['dir::' + Path(x).name for x in exporter.RTL[:6]])
        path = self.out / 'src/config_merged.json'
        path.write_text(json.dumps(cfg))
        lock = json.loads((self.out / 'requirements/asic-lock.json').read_text())
        (self.out / 'tt_submission').mkdir()
        (self.out / 'tt_submission/pdk.json').write_text(json.dumps({
            'PDK': 'sky130A', 'PDK_VERSION': lock['hardening_pdk'],
            'FLOW_VERSION': lock['librelane_version']}))
        return cfg, path

    def test_export_is_standalone_and_rtl_identical(self):
        self.assertEqual(checker.check(self.out)['status'], 'PASS')
        for name in exporter.RTL:
            self.assertEqual((ROOT / name).read_bytes(),
                             (self.out / 'src' / Path(name).name).read_bytes())
        self.assertFalse((self.out / '.git').exists())
        self.assertFalse((self.out / 'overnight').exists())
        self.assertTrue((self.out / '.github/workflows/gds.yaml').is_file())
        self.assertIn('PIN_ORACLE_PASS', (self.out / 'test/test.py').read_text())

    def test_refuses_existing_destination(self):
        with self.assertRaises(FileExistsError):
            exporter.export(ROOT, self.out)

    def test_refuses_export_into_source_or_git(self):
        with self.assertRaises(ValueError):
            exporter.export(ROOT, ROOT / '.git/new-candidate')

    def test_detects_modified_rtl(self):
        with (self.out / 'src/mac_hybrid.sv').open('a') as f:
            f.write('\n// altered\n')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            checker.check(self.out)

    def test_detects_missing_metadata(self):
        (self.out / 'info.yaml').unlink()
        with self.assertRaises(FileNotFoundError):
            checker.check(self.out)

    def test_rejects_symlink_member(self):
        f = self.out / 'src/mac_hybrid.sv'
        f.unlink()
        f.symlink_to(ROOT / 'rtl/mac_hybrid.sv')
        with self.assertRaisesRegex(ValueError, 'Unsafe package'):
            checker.check(self.out)

    def test_official_config_shape_accepted(self):
        self.ci_fixture()
        self.assertTrue(checker.check(self.out, ci=True)['ci_configuration_checked'])

    def test_ci_rejects_corner_or_clock_drift(self):
        cfg, path = self.ci_fixture()
        cfg['CLOCK_PERIOD'] = 20
        path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'CLOCK_PERIOD'):
            checker.check(self.out, ci=True)
        cfg['CLOCK_PERIOD'] = 50
        cfg['STA_CORNERS'].pop()
        path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'STA_CORNERS'):
            checker.check(self.out, ci=True)

    def test_ci_rejects_wrong_pdk(self):
        self.ci_fixture()
        p = self.out / 'tt_submission/pdk.json'
        cfg = json.loads(p.read_text())
        cfg['PDK_VERSION'] = 'wrong'
        p.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'PDK identity'):
            checker.check(self.out, ci=True)

    def test_ci_rejects_wrong_source_or_floorplan(self):
        cfg, path = self.ci_fixture()
        cfg['FP_DEF_TEMPLATE'] = 'tt_block_1x1_pg.def'
        path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'floorplan'):
            checker.check(self.out, ci=True)
        cfg['FP_DEF_TEMPLATE'] = 'tt_block_2x2_pg.def'
        cfg['VERILOG_FILES'].append('dir::mac_unprotected.sv')
        path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'source list'):
            checker.check(self.out, ci=True)


if __name__ == '__main__':
    unittest.main()
