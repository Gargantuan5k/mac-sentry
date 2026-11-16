"""Controls for the portable export; no Git operations or external installations."""
from pathlib import Path
import io
import json
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from scripts import package_project, provenance, check_environment


class PackageTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'project_manifest.json').write_text(json.dumps({'schema': 1,
            'root_files': ['README.md', 'project_manifest.json'], 'directories': ['rtl', 'docs'],
            'additional_paths': [], 'exclude': ['docs/overnight_*', '__pycache__', '*.pyc', '.env*', '.venv']}))
        (root / 'README.md').write_text('portable reference')
        (root / 'rtl').mkdir(); (root / 'rtl/core.sv').write_text('module core; endmodule')
        (root / 'docs').mkdir(); (root / 'docs/guide.md').write_text('guide')
        (root / 'docs/overnight_private.md').write_text('must stay local')
        (root / 'docs/.env').write_text('PRIVATE_FIXTURE')
        (root / 'docs/.env.dev').write_text('PRIVATE_FIXTURE')
        (root / 'docs/.venv').mkdir(); (root / 'docs/.venv/cache').write_text('PRIVATE_FIXTURE')
        (root / 'build').mkdir(); (root / 'build/cache').write_text('must stay local')
        (root / 'overnight').mkdir(); (root / 'overnight/private').write_text('must stay local')

    def test_export_contains_only_selected_inputs_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root); output = root / 'build/package.tar.gz'
            manifest = package_project.export(root, output)
            self.assertEqual(set(manifest['files']), {'README.md', 'project_manifest.json', 'rtl/core.sv', 'docs/guide.md'})
            self.assertEqual(package_project.verify(output), manifest)
            with self.assertRaises(FileExistsError): package_project.export(root, output)

    def test_link_and_missing_required_file_fail_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            (root / 'rtl/link').symlink_to(root / 'README.md')
            with self.assertRaisesRegex(ValueError, 'Symlinks'): package_project.source_files(root)
            (root / 'rtl/link').unlink(); (root / 'README.md').unlink()
            with self.assertRaises(FileNotFoundError): package_project.source_files(root)

    def test_symlink_parent_in_additional_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp); root = outer / 'source'; root.mkdir(); self.fixture(root)
            private = outer / 'private'; (private / 'published').mkdir(parents=True)
            (private / 'published/marker').write_text('must not be exported')
            (root / 'results').symlink_to(private, target_is_directory=True)
            p = root / 'project_manifest.json'; cfg = json.loads(p.read_text())
            cfg['additional_paths'] = ['results/published']; p.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError, 'escapes|Symlinks'):
                package_project.source_files(root)

    def test_tampered_or_unenrolled_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root); output = root / 'build/original.tar.gz'
            package_project.export(root, output)
            for attack in ('tamper', 'extra', 'traversal', 'symlink'):
                bad = root / ('bad-' + attack + '.tar.gz')
                with tarfile.open(output) as src, tarfile.open(bad, 'w:gz') as dst:
                    for member in src:
                        data = src.extractfile(member).read()
                        if attack == 'tamper' and member.name.endswith('README.md'):
                            data = b'fabricated'; member.size = len(data)
                        dst.addfile(member, io.BytesIO(data))
                    if attack in ('extra', 'traversal', 'symlink'):
                        name = 'mac_sentry/unexpected' if attack != 'traversal' else 'mac_sentry/../escape'
                        member = tarfile.TarInfo(name)
                        if attack == 'symlink': member.type = tarfile.SYMTYPE; member.linkname = '/outside'
                        dst.addfile(member)
                with self.subTest(attack=attack), self.assertRaises(ValueError): package_project.verify(bad)

    def test_public_selection_has_no_agent_or_local_build_files(self):
        root = Path(__file__).resolve().parents[1]
        selected = package_project.source_files(root)
        self.assertIn('tools/container_runtime.py', selected)
        self.assertIn('results/published/manifest.json', selected)
        self.assertNotIn('docs/overnight_handoff.json', selected)
        self.assertNotIn('scripts/check_overnight_handoff.py', selected)
        self.assertNotIn('tests/test_overnight_handoff.py', selected)
        self.assertFalse(any(p.startswith(('build/', 'overnight/', '.git/')) for p in selected))


class PortableInfrastructureTests(unittest.TestCase):
    def test_provenance_git_reads_cannot_refresh_index(self):
        with patch.object(provenance.subprocess, 'run') as run:
            run.return_value.returncode = 0; run.return_value.stdout = 'revision\n'
            self.assertEqual(provenance.command('git', 'status', '--porcelain'), 'revision')
            self.assertEqual(run.call_args.args[0], ('git', '--no-optional-locks', '-c', 'diff.autoRefreshIndex=false', 'status', '--porcelain'))

    def test_environment_missing_tool_fails_without_installs(self):
        with patch.object(check_environment.shutil, 'which', return_value=None), patch.object(check_environment.subprocess, 'run') as run:
            result = check_environment.inspect('asic')
            self.assertEqual(result['status'], 'FAIL'); run.assert_not_called()
            self.assertFalse(result['tools']['podman']['ok'])


if __name__ == '__main__': unittest.main()
