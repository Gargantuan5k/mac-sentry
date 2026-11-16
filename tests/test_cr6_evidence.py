"""Controls for historical packaging and the reviewed /proc cleanup race."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from scripts.copy_evidence import digest
from scripts.restore_archived_run import restore
from scripts.fpga_cost import group_members, stop_group


class CR6EvidenceTests(unittest.TestCase):
    def test_hash_bound_relocation_and_immutable_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'old'; src.mkdir()
            (src / 'raw').write_bytes(b'FAIL\x00\xff\n')
            original = Path('/historical/run')
            (src / 'link').symlink_to(original / 'raw')
            hashes = dict(raw=digest(src / 'raw'), link=digest(src / 'raw'))
            (src / 'artifact_sha256.json').write_text(json.dumps(hashes))
            manifest_bytes = (src / 'artifact_sha256.json').read_bytes()
            entries = restore(src, root / 'new', root / 'copy.json', original)
            self.assertEqual((root / 'new/link').read_bytes(), (src / 'raw').read_bytes())
            self.assertFalse((root / 'new/link').is_symlink())
            self.assertEqual(entries['link']['original_link'], '/historical/run/raw')
            self.assertEqual((src / 'artifact_sha256.json').read_bytes(), manifest_bytes)
            self.assertTrue((src / 'link').is_symlink())
            with self.assertRaises(FileExistsError):
                restore(src, root / 'new', root / 'copy.json', original)
            (src / 'raw').write_text('fabricated PASS')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                restore(src, root / 'bad', root / 'bad.json', original)

    def test_links_cannot_escape_explicit_run_or_omit_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'old'; src.mkdir()
            (src / 'raw').write_text('raw')
            (src / 'artifact_sha256.json').write_text('{}')
            (src / 'link').symlink_to('/historical/run/raw')
            with self.assertRaisesRegex(ValueError, 'link hash mismatch'):
                restore(src, root / 'new', root / 'copy.json', Path('/historical/run'))
            with self.assertRaisesRegex(ValueError, 'outside explicit'):
                restore(src, root / 'new', root / 'copy.json', Path('/other/run'))

    def test_exiting_process_race_and_normal_exit_signals(self):
        stat = Mock()
        stat.read_text.side_effect = ProcessLookupError('exited during stat read')
        with patch('scripts.fpga_cost.Path.glob', return_value=[stat]):
            self.assertEqual(group_members(123), [])
        proc = Mock(pid=123, returncode=0)
        with patch('scripts.fpga_cost.group_members', return_value=[]), patch('scripts.fpga_cost.os.killpg') as kill:
            result = stop_group(proc)
            self.assertTrue(result['quiescent'])
            self.assertEqual(result['signals'], [])
            kill.assert_not_called()
