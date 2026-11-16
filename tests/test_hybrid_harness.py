"""Regression tests for the M0 review's false-positive negative controls."""
import subprocess
import unittest

from scripts.check_hybrid_harness import busy_reset_index, require_rejection


class HybridHarnessControlTests(unittest.TestCase):
    def test_commit_control_requires_its_assertion_not_state_tail(self):
        for other in ('pre word', 'busy', 'attempt eligibility', 'pre accumulator'):
            result = subprocess.CompletedProcess([], 1, '',
                f'FAIL record 23: {other}: expected 0, observed 1\n'
                'M ...\ncandidate=1 prediction=1 accumulator=1\n')
            with self.subTest(other=other), self.assertRaises(RuntimeError):
                require_rejection(result, 23, 'accumulator')
        result = subprocess.CompletedProcess([], 1, '',
            'FAIL record 23: accumulator: expected 0, observed 1\n'
            'M ...\ncandidate=1 prediction=1 accumulator=1\n')
        require_rejection(result, 23, 'accumulator')

    def test_rejection_requires_exit_one_and_target_record(self):
        for code, record in ((0, 23), (2, 23), (1, 22)):
            result = subprocess.CompletedProcess([], code, '',
                f'FAIL record {record}: attempt eligibility: expected 1, observed 0\n')
            with self.subTest(code=code, record=record), self.assertRaises(RuntimeError):
                require_rejection(result, 23, 'attempt eligibility')

    def test_reset_selection_skips_idle_and_tracks_only_clocked_rows(self):
        reset = 'M 1 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0'
        accept = 'M 0 0 1 1 1 0 0 0 0 1 0 0 0 1 1 0 0 0 0 0 0 0 0 0 0'
        records = [reset, accept, 'C 0 0 0 0 0 0', reset]
        self.assertEqual(busy_reset_index(records), 3)
        with self.assertRaises(RuntimeError):
            busy_reset_index([reset, reset])

    def test_reset_selection_requires_clean_source(self):
        reset = 'M 1 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0'
        accept = 'M 0 0 1 1 1 0 0 0 0 1 0 0 0 1 1 0 0 0 0 0 0 0 0 0 0'
        for row, column, value in ((0, 10, '0'), (1, 6, '3'), (1, 12, '3')):
            records = [accept, reset]
            fields = records[row].split()
            fields[column] = value
            records[row] = ' '.join(fields)
            with self.subTest(column=column), self.assertRaises(RuntimeError):
                busy_reset_index(records)


if __name__ == '__main__':
    unittest.main()
