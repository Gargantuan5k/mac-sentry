"""Provenance Git commands must explicitly avoid index refreshes."""
import subprocess
import unittest
from unittest.mock import patch

from scripts import archive_fpga_run


class ReadOnlyGitTests(unittest.TestCase):
    def test_all_archive_git_reads_disable_index_refresh(self):
        for arguments, output in [
            (('diff', 'HEAD', '--'), 'diff --git a/rtl/core.sv b/rtl/core.sv\n'),
            (('status', '--porcelain'), ' M rtl/core.sv\n'),
            (('rev-parse', 'HEAD'), '0123456789abcdef\n'),
        ]:
            with self.subTest(arguments=arguments), patch.object(
                    archive_fpga_run.subprocess, 'run',
                    return_value=subprocess.CompletedProcess([], 0, output, '')) as run:
                self.assertEqual(archive_fpga_run.git(*arguments), output.strip())
                run.assert_called_once_with(
                    ['git', '--no-optional-locks', '-c', 'diff.autoRefreshIndex=false',
                     '-C', str(archive_fpga_run.ROOT), *arguments],
                    capture_output=True, text=True, check=False)

    def test_failed_git_read_is_not_recorded_as_successful_output(self):
        with patch.object(archive_fpga_run.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 128, 'partial output', 'failure')):
            self.assertIsNone(archive_fpga_run.git('diff', 'HEAD', '--'))


if __name__ == '__main__':
    unittest.main()
