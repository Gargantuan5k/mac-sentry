"""Portable evidence checks reject corrupt bytes and unsupported promoted claims."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import check_published_results as published


class PublishedResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'published'
        shutil.copytree(published.ROOT / 'results/published', self.root)

    def refresh(self, relative):
        path = self.root / relative
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest['files'][relative]['bytes'] = path.stat().st_size
        manifest['files'][relative]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root / 'manifest.json').write_text(json.dumps(manifest))

    def rewrite_json(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))
        self.refresh(relative)

    def test_complete_package_replays_without_build_tree(self):
        result = published.verify(self.root)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['pilot']['trials'], 429)
        self.assertEqual(result['asic']['prechecks'], 15)
        self.assertEqual(result['fpga_cost']['timing_closed'], 0)
        self.assertFalse((self.root / 'build').exists())

    def test_missing_reference_layout_cannot_be_omitted_from_outer_manifest(self):
        relative = 'data/asic/project/src/runs/R2/final/klayout_gds/tt_um_mac_sentry.klayout.gds'
        (self.root / relative).unlink()
        manifest = json.loads((self.root / 'manifest.json').read_text())
        del manifest['files'][relative]
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Missing/nonregular evidence'):
            published.verify(self.root)

    def test_layout_tampering_rejected_even_with_updated_outer_hash(self):
        relative = 'data/asic/project/src/runs/R2/final/klayout_gds/tt_um_mac_sentry.klayout.gds'
        path = self.root / relative
        data = bytearray(path.read_bytes())
        data[12] ^= 1
        path.write_bytes(data)
        self.refresh(relative)
        with self.assertRaisesRegex(ValueError, 'Reference layout identity mismatch'):
            published.verify(self.root)

    def test_changed_raw_bytes_fail_manifest_hash(self):
        p = self.root / 'data/asic/gls_positive.log'
        p.write_text(p.read_text() + 'changed')
        with self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
            published.verify(self.root)

    def test_unlisted_file_and_symlink_are_rejected(self):
        extra = self.root / 'data/unlisted.txt'
        extra.write_text('not enrolled')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            published.verify(self.root)
        extra.unlink()
        existing = self.root / 'data/asic/gls_positive.log'
        target = Path(self.tmp.name) / 'external.txt'
        target.write_bytes(existing.read_bytes())
        existing.unlink()
        existing.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            published.verify(self.root)

    def test_promoted_signoff_rejected_even_with_updated_hash(self):
        self.rewrite_json('data/asic/result.json', lambda d: d.update(signoff=True))
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            published.verify(self.root)

    def test_skipped_precheck_rejected_even_with_updated_hash(self):
        rel = 'data/asic/tt/precheck/reports/results.xml'
        path = self.root / rel
        path.write_text(path.read_text().replace('<testcase name="Magic DRC" time="57.18" />',
                                                '<testcase name="Magic DRC"><skipped /></testcase>'))
        self.assertIn('<skipped', path.read_text())
        self.refresh(rel)
        with self.assertRaisesRegex(ValueError, 'failure/error/skip'):
            published.verify(self.root)

    def test_nonzero_physical_metric_cannot_hide_behind_pass_result(self):
        for relative in ('data/asic/physical_summary.json',
                         'data/asic/project/src/runs/R2/final/metrics.json'):
            self.rewrite_json(relative, lambda d: d.update(magic__drc_error__count=1))
        with self.assertRaisesRegex(ValueError, 'required zero metric'):
            published.verify(self.root)

    def test_lost_trial_rejected_even_with_updated_hash(self):
        rel = 'data/pilot/trials.jsonl'
        path = self.root / rel
        path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
        self.refresh(rel)
        with self.assertRaisesRegex(ValueError, 'denominator/identity'):
            published.verify(self.root)

    def test_trace_fabrication_rejected_even_with_updated_hash(self):
        rel = 'data/pilot/trial_0000/trace.csv'
        path = self.root / rel
        rows = path.read_text().splitlines()
        row = rows[1].split(',')
        row[1] = '99'  # The first pre-edge must be cycle zero.
        rows[1] = ','.join(row)
        path.write_text('\n'.join(rows) + '\n')
        self.refresh(rel)
        with self.assertRaisesRegex(ValueError, 'TRACE_CONTINUITY'):
            published.verify(self.root)

    def test_timing_failure_cannot_be_promoted(self):
        def promote(rows):
            rows[0]['status'] = 'closed'
        self.rewrite_json('data/fpga_cost/results.json', promote)
        with self.assertRaisesRegex(ValueError, 'timing failure was hidden'):
            published.verify(self.root)

    def test_historical_source_mutation_rejected_with_updated_outer_hash(self):
        rel = 'data/asic/sources/rtl/mac_hybrid.sv'
        path = self.root / rel
        path.write_text(path.read_text() + '\n// source changed\n')
        self.refresh(rel)
        with self.assertRaisesRegex(ValueError, 'Historical source hash mismatch'):
            published.verify(self.root)


if __name__ == '__main__':
    unittest.main()
