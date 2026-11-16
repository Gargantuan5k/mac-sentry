import unittest

from model.mac_secded import SecdedMacModel
from scripts.secded_capture import analyze_samples


def capture(commands):
    model = SecdedMacModel()
    model.codeword = model.codec.encode(1870)
    busy = done = valid = error = fired = 0
    rows = []
    for i, command in enumerate(commands):
        c = dict(rst=0, clear=0, start_pulse=0, operand_a=15, operand_b=10,
                 inject_pulse=0, inject_mask=0)
        c.update(command)
        inject = bool(not (c['rst'] or c['clear'] or busy) and c['inject_pulse'] and c['inject_mask'])
        rows.append(dict(c, sample=i, window_sample=i,
            ready=int(not (c['rst'] or c['clear'] or busy or inject)), busy=busy,
            done=done, result_valid=valid, error=error, accumulator=model.accumulator,
            corrected=int(model.corrected), inject_fired=fired, stored_codeword=model.codeword))
        if inject:
            model.inject_accumulator_fault(c['inject_mask'])
            model.corrected = False
            busy = done = valid = error = 0
        else:
            _, busy, done, valid, error, _, _ = model.step(c['rst'], c['clear'],
                c['start_pulse'], c['operand_a'], c['operand_b'])
        fired = int(inject)
    return rows


class SecdedCaptureTests(unittest.TestCase):
    def test_injection_and_idle_repair(self):
        rows = capture([dict(inject_pulse=1, inject_mask=4), {}, {}, {}])
        _, events, failures, summary = analyze_samples(rows, 'single')
        self.assertEqual(failures, [])
        self.assertEqual([(e['action'], e['status']) for e in events],
                         [('inject_1_bits', 'PASS'), ('idle_repair', 'PASS')])
        self.assertEqual(summary['complete_mac_transactions'], 0)

    def test_double_rejection_clear_recovery(self):
        rows = capture([dict(inject_pulse=1, inject_mask=0x14), {},
                        dict(start_pulse=1), {}, {}, dict(clear=1), {},
                        dict(start_pulse=1), {}, {}])
        _, events, failures, _ = analyze_samples(rows, 'double')
        self.assertEqual(failures, [])
        rejected = next(e for e in events if e['action'] == 'mac_rejected')
        self.assertEqual(rejected['status'], 'PASS')
        self.assertEqual(events[-1]['observed_acc'], 150)

    def test_missing_ack_or_broken_storage_is_not_pass(self):
        for field in ('inject_fired', 'stored_codeword', 'corrected'):
            rows = capture([dict(inject_pulse=1, inject_mask=4), {}, {}, {}])
            index = 2 if field == 'corrected' else 1
            rows[index][field] ^= 1
            _, events, failures, _ = analyze_samples(rows, 'broken')
            self.assertTrue(failures)
            self.assertIn('FAIL', [e['status'] for e in events])

    def test_double_error_cannot_claim_success(self):
        rows = capture([dict(inject_pulse=1, inject_mask=0x14), {},
                        dict(start_pulse=1), {}, {}])
        rows[-1]['result_valid'] = 1
        rows[-1]['error'] = 0
        _, events, failures, _ = analyze_samples(rows, 'bad_commit')
        self.assertTrue(failures)
        self.assertEqual(events[-1]['status'], 'FAIL')

    def test_blocked_start_and_no_arithmetic(self):
        rows = capture([dict(clear=1), dict(clear=1, start_pulse=1), dict(clear=1)])
        _, events, failures, summary = analyze_samples(rows, 'clear_held')
        self.assertEqual(failures, [])
        self.assertEqual(summary['complete_mac_transactions'], 0)
        self.assertTrue(any(e['status'] == 'BLOCKED' for e in events))

    def test_cutoff_gap_and_unknown_pending_history(self):
        rows = capture([dict(start_pulse=1), {}, {}, {}])
        self.assertEqual(analyze_samples(rows[:2], 'short')[1][0]['status'], 'INCOMPLETE')
        rows[1]['window_sample'] = 30
        self.assertEqual(analyze_samples(rows, 'gap')[1][0]['status'], 'INCOMPLETE')
        unknown = capture([dict(start_pulse=1), {}, {}, {}])[1:]
        result = analyze_samples(unknown, 'unknown')
        self.assertEqual(result[3]['unchecked_transitions'], 1)
        self.assertEqual(result[3]['complete_mac_transactions'], 0)


if __name__ == '__main__':
    unittest.main()
