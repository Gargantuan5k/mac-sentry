"""Packaging controls; these are not physical experiment results."""
from pathlib import Path
import json
import tempfile
import unittest
from scripts.copy_evidence import copy_evidence


class EvidenceCopyTests(unittest.TestCase):
    def test_lossless_absolute_links_and_immutable_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'old'; src.mkdir()
            (src / 'failed.log').write_bytes(b'FAIL\x00\xff\n')
            (src / 'absolute').symlink_to(src / 'failed.log')
            (src / 'relative').symlink_to('failed.log')
            (src / 'original_manifest.json').write_text('{"status":"FAIL"}')
            dst = root / 'new'; manifest = root / 'copy.json'
            entries = copy_evidence(src, dst, manifest)
            for name in ('failed.log', 'absolute', 'relative'):
                self.assertEqual((dst / name).read_bytes(), b'FAIL\x00\xff\n')
                self.assertFalse((dst / name).is_symlink())
            self.assertTrue((src / 'absolute').is_symlink())
            self.assertEqual(entries['absolute']['original_link'], str(src / 'failed.log'))
            self.assertEqual(entries['absolute']['sha256'], entries['failed.log']['sha256'])
            self.assertEqual((dst / 'original_manifest.json').read_bytes(),
                             (src / 'original_manifest.json').read_bytes())
            self.assertEqual(json.loads(manifest.read_text())['entries'], entries)
            with self.assertRaises(FileExistsError):
                copy_evidence(src, dst, manifest)

    def test_external_target_requires_explicit_boundary_and_broken_links_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'old'; src.mkdir()
            ext = root / 'external'; ext.mkdir(); (ext / 'raw').write_text('negative evidence')
            (src / 'link').symlink_to(ext / 'raw')
            with self.assertRaisesRegex(ValueError, 'boundaries'):
                copy_evidence(src, root / 'denied', root / 'denied.json')
            copy_evidence(src, root / 'allowed', root / 'allowed.json', [ext])
            (src / 'broken').symlink_to('absent')
            with self.assertRaises(FileNotFoundError):
                copy_evidence(src, root / 'broken_copy', root / 'broken.json', [ext])

    def test_cycles_and_destination_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'old'; src.mkdir()
            with self.assertRaisesRegex(ValueError, 'outside source'):
                copy_evidence(src, src / 'copy', root / 'copy.json')
            (src / 'cycle').symlink_to(src, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'cycle'):
                copy_evidence(src, root / 'copy', root / 'copy.json')
