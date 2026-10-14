import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.compact_fpga_results import compact_run, verify_run


class CompactionTests(unittest.TestCase):
    def make_run(self, root, name, source=b'RTL', build=b'bitstream'):
        run = root / 'runs' / name
        files = {'sources/core/rtl/core.sv': source, 'build/core.bit': build,
                 'reports/timing.rpt': b'timing', 'tests.csv': b'status\nPASS\n'}
        for name, data in files.items():
            path = run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (run / 'manifest.json').write_text(json.dumps({'file_sha256': {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}))
        return run

    def test_share_build_preserve_distinct_sources_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_run(root, 'first')
            second = self.make_run(root, 'second', source=b'new RTL snapshot')
            original = (first / 'manifest.json').read_bytes()
            for run in (first, second):
                compact_run(run, root / 'builds')
                self.assertEqual(verify_run(run), 4)
                self.assertFalse((run / 'build').exists())
                self.assertEqual((run / 'tests.csv').read_bytes(), b'status\nPASS\n')
            self.assertEqual(len(list((root / 'builds').glob('*.zip'))), 1)
            self.assertEqual((first / 'manifest.json').read_bytes(), original)
            with ZipFile(second / 'sources.zip') as handle:
                self.assertEqual(handle.read('sources/core/rtl/core.sv'), b'new RTL snapshot')
            compact_run(first, root / 'builds')  # Safe repeat.

    def test_corrupt_input_refuses_compaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.make_run(root, 'first')
            (run / 'build/core.bit').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                compact_run(run, root / 'builds')
            self.assertTrue((run / 'sources/core/rtl/core.sv').exists())

    def test_different_builds_are_not_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, build in (('first', b'one'), ('second', b'two')):
                compact_run(self.make_run(root, name, build=build), root / 'builds')
            self.assertEqual(len(list((root / 'builds').glob('*.zip'))), 2)

    def test_unrecorded_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.make_run(root, 'first')
            extra = run / 'sources/extra.txt'
            extra.write_text('keep me')
            with self.assertRaises(ValueError):
                compact_run(run, root / 'builds')
            self.assertEqual(extra.read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
