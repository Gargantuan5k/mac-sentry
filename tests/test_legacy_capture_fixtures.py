"""Selected legacy ILA compatibility inputs are mandatory, original and hash-bound."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.test_hybrid_capture import ROOT, load_legacy_capture_fixtures


class LegacyCaptureFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'legacy_captures'
        shutil.copytree(ROOT / 'tests/fixtures/legacy_captures', self.folder)
        self.collection = self.folder / 'manifest.json'
        self.manifest = json.loads(self.collection.read_text())
        self.capture = next(name for name in self.manifest['files'] if name.endswith('.ila'))

    def refresh_outer(self, relative):
        data = json.loads(self.collection.read_text())
        path = self.folder / relative
        data['files'][relative]['bytes'] = path.stat().st_size
        data['files'][relative]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.collection.write_text(json.dumps(data))

    def test_complete_selected_fixture_is_independent_of_ignored_archives(self):
        selected = load_legacy_capture_fixtures(self.folder)
        self.assertEqual(len(selected['runs']), 2)
        self.assertEqual(len(selected['files']), 19)  # collection + 18 selected originals
        self.assertEqual(sum(p.suffix == '.ila' for p in selected['files']), 8)
        self.assertTrue(all(p.is_relative_to(self.folder) for p in selected['files']))
        self.assertTrue(self.manifest['scope'].startswith('PARTIAL'))
        for run_id, folder in selected['runs'].items():
            original = json.loads((folder / 'manifest.json').read_text())
            for relative, expected in original['file_sha256'].items():
                path = folder / relative
                if path.is_file():
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
        plan = ROOT / 'tests/fixtures/m7_secded_test_plan.csv'
        provenance = json.loads((ROOT / 'tests/fixtures/m7_secded_test_plan.provenance.json').read_text())
        self.assertEqual(hashlib.sha256(plan.read_bytes()).hexdigest(), provenance['fixture_sha256'])

    def test_missing_collection_is_not_optional(self):
        self.collection.unlink()
        with self.assertRaises(FileNotFoundError):
            load_legacy_capture_fixtures(self.folder)

    def test_missing_capture_is_not_replaced_by_original_machine_archive(self):
        (self.folder / self.capture).unlink()
        with self.assertRaisesRegex(ValueError, 'Missing/nonregular legacy fixture'):
            load_legacy_capture_fixtures(self.folder)

    def test_modified_capture_fails_outer_hash(self):
        path = self.folder / self.capture
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
            load_legacy_capture_fixtures(self.folder)

    def test_refreshed_outer_hash_does_not_bypass_original_capture_identity(self):
        path = self.folder / self.capture
        path.write_bytes(path.read_bytes() + b'changed')
        self.refresh_outer(self.capture)
        with self.assertRaisesRegex(ValueError, 'original manifest hash mismatch'):
            load_legacy_capture_fixtures(self.folder)

    def test_refreshed_outer_hash_does_not_allow_edited_expected_csv(self):
        relative = next(name for name in self.manifest['files'] if name.endswith('/tests.csv'))
        path = self.folder / relative
        path.write_bytes(path.read_bytes() + b'changed')
        self.refresh_outer(relative)
        with self.assertRaisesRegex(ValueError, 'original manifest hash mismatch'):
            load_legacy_capture_fixtures(self.folder)

    def test_lost_original_capture_entry_fails_coverage(self):
        run_id = self.capture.split('/')[0]
        relative = run_id + '/manifest.json'
        path = self.folder / relative
        original = json.loads(path.read_text())
        original['copied_files'] = [r for r in original['copied_files']
                                    if not r['archived'].endswith('.ila')]
        path.write_text(json.dumps(original))
        self.refresh_outer(relative)
        with self.assertRaisesRegex(ValueError, 'capture coverage differs'):
            load_legacy_capture_fixtures(self.folder)

    def test_symlink_and_unlisted_inputs_fail(self):
        path = self.folder / self.capture
        external = Path(self.tmp.name) / 'external.ila'
        path.rename(external)
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Missing/nonregular'):
            load_legacy_capture_fixtures(self.folder)
        path.unlink()
        external.rename(path)
        (self.folder / 'unlisted.txt').write_text('not enrolled')
        with self.assertRaisesRegex(ValueError, 'missing/unlisted'):
            load_legacy_capture_fixtures(self.folder)


if __name__ == '__main__':
    unittest.main()
