"""Check ILA edge alignment, failure detection and incomplete-capture handling."""
import csv
from pathlib import Path
import tempfile
import unittest

from model.mac import MacModel
from scripts.archive_fpga_run import analyze_capture, SIGNALS, WIDTHS


class CaptureTests(unittest.TestCase):
    def capture(self, inputs):
        model = MacModel()
        rows = []
        busy = done = valid = error = 0
        for index, (rst, clear, start, a, b) in enumerate(inputs):
            rows.append([index, index, 0, rst, clear, start, a, b,
                         int(not (rst or clear or busy)), busy, done, valid, error, model.accumulator])
            _, busy, done, valid, error, _, _ = model.step(rst, clear, start, a, b)
        return rows

    def analyze(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'waveform.csv'
            with path.open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['Sample in Buffer', 'Sample in Window', 'TRIGGER', *SIGNALS])
                writer.writerow(['Radix - UNSIGNED', 'UNSIGNED', 'UNSIGNED', *(['HEX']*11)])
                for row in rows:
                    writer.writerow(row[:3] + [format(value & ((1 << width)-1), 'x')
                                               for value, width in zip(row[3:], WIDTHS)])
            return analyze_capture(path, 'fixture')

    def test_signed_mac_and_changed_busy_inputs(self):
        rows = self.capture([(0, 0, 1, 3, -4), (0, 0, 1, 99, 99), (0, 0, 0, 0, 0)])
        samples, events, failures, summary = self.analyze(rows)
        self.assertEqual(samples[0]['operand_b'], -4)
        self.assertEqual(events[0]['observed_acc'], -12)
        self.assertEqual(events[0]['status'], 'PASS')
        self.assertEqual(summary['complete_mac_transactions'], 1)
        self.assertEqual(failures, [])

    def test_corrupted_commit_fails(self):
        rows = self.capture([(0, 0, 1, 3, -4), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)])
        rows[2][-1] = -11
        _, events, failures, _ = self.analyze(rows)
        self.assertEqual(events[0]['status'], 'FAIL')
        self.assertEqual(failures[0]['signal'], 'accumulator')

    def test_idle_is_not_a_mac_pass(self):
        rows = self.capture([(0, 0, 0, 6, 7)] * 4)
        _, events, failures, summary = self.analyze(rows)
        self.assertEqual(events, [])
        self.assertEqual(failures, [])
        self.assertEqual(summary['complete_mac_transactions'], 0)

    def test_cutoff_and_sample_gap_are_incomplete(self):
        rows = self.capture([(0, 0, 1, 3, -4), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)])
        self.assertEqual(self.analyze(rows[:2])[1][0]['status'], 'INCOMPLETE')
        rows[1][0] += 10
        self.assertEqual(self.analyze(rows)[1][0]['status'], 'INCOMPLETE')

    def test_reset_aborts_pending_mac(self):
        rows = self.capture([(0, 0, 1, 3, -4), (1, 0, 0, 0, 0), (0, 0, 0, 0, 0)])
        _, events, failures, _ = self.analyze(rows)
        self.assertEqual(events[0]['action'], 'reset_aborted_mac')
        self.assertEqual(events[0]['status'], 'PASS')
        self.assertEqual(events[0]['observed_acc'], 0)
        self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main()
