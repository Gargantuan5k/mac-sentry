"""Independent arithmetic expectations and conventional-hybrid recovery limits."""
import random
import unittest

from model.mac import MacModel, signed
from model.mac_hybrid import HybridMacModel, expected_residue


class ResidueTests(unittest.TestCase):
    def test_exhaustive_small_signed_sum_before_wrap(self):
        for acc in range(-8, 8):
            for a in range(-2, 2):
                for b in range(-2, 2):
                    prediction = expected_residue(acc, a, b)
                    self.assertEqual(prediction, (acc+a*b) % 7)
                    for candidate in range(-16, 16):
                        self.assertEqual(candidate % 7 == prediction,
                                         (candidate-(acc+a*b)) % 7 == 0)

    def test_all_single_candidate_bits_detected(self):
        rng = random.Random(20261106)
        for _ in range(100):
            acc = rng.randrange(-8388608, 8388608)
            a, b = rng.randrange(-128, 128), rng.randrange(-128, 128)
            exact = acc + a*b
            for bit in range(25):
                changed = signed((exact % (1 << 25)) ^ (1 << bit), 25)
                self.assertNotEqual(changed % 7, expected_residue(acc, a, b))


class HybridTests(unittest.TestCase):
    def test_fault_free_equivalence(self):
        for ow, aw in ((8, 24), (4, 8)):
            protected, baseline = HybridMacModel(ow, aw), MacModel(ow, aw)
            rng = random.Random(20261106)
            for _ in range(5000):
                args = dict(rst=int(rng.randrange(100) == 0), clear=int(rng.randrange(20) == 0),
                            start=rng.randrange(2), a=rng.randrange(1 << ow), b=rng.randrange(1 << ow))
                self.assertEqual(protected.step(**args), baseline.step(**args))
                self.assertFalse(protected.detected or protected.retried)

    def test_wrap_boundaries(self):
        for acc, a, b, expected in [(8388607, 1, 1, -8388608),
                                    (-8388608, -1, 1, 8388607),
                                    (8388607, -128, -128, -8372225)]:
            m = HybridMacModel()
            m.codeword = m.codec.encode(acc % (1 << 24))
            m.step(start=1, a=a, b=b)
            self.assertEqual(m.step(), (0, 0, 1, 1, 0, expected, 1))

    def test_transient_retry_preserves_operands_and_state(self):
        m = HybridMacModel()
        m.step(start=1, a=34, b=55)
        self.assertEqual(m.step(candidate_fault=1, clear=1, start=1, a=99, b=99),
                         (0, 1, 0, 0, 0, 0, 0))
        self.assertEqual(m.retry_count, 1)
        self.assertTrue(m.detected and m.retried)
        self.assertEqual(m.step(), (0, 0, 1, 1, 0, 1870, 1))
        self.assertFalse(m.detected or m.retried)
        self.assertEqual(m.retry_count, 1)

    def test_bounded_persistent_fault_and_next_request(self):
        for retries in (0, 1, 2, 3):
            m = HybridMacModel(max_retries=retries)
            m.step(start=1, a=3, b=4)
            for attempt in range(retries+1):
                output = m.step(candidate_fault=1)
                self.assertTrue(m.detected)
                self.assertEqual(m.codeword, 0)
                if attempt < retries:
                    self.assertEqual(output[1:5], (1, 0, 0, 0))
                    self.assertTrue(m.retried)
                else:
                    self.assertEqual(output[1:5], (0, 1, 0, 2))
                    self.assertFalse(m.retried)
            self.assertEqual(m.retry_count, retries)
            self.assertEqual(m.step()[1:5], (0, 0, 0, 0))
            m.step(start=1, a=3, b=4)
            self.assertEqual(m.retry_count, 0)
            self.assertEqual(m.step()[5], 12)

    def test_ecc_repair_on_rejected_attempt_and_uncorrectable_termination(self):
        m = HybridMacModel()
        m.step(start=1, a=3, b=4)
        m.inject_accumulator_fault(4)
        m.step(candidate_fault=1)
        self.assertTrue(m.corrected and m.detected and m.retried)
        self.assertEqual(m.codeword, 0)
        m.inject_accumulator_fault(0x14)
        word = m.codeword
        self.assertEqual(m.step()[1:5], (0, 1, 0, 1))
        self.assertEqual(m.codeword, word)

    def test_reset_aborts_retry_and_idle_clear(self):
        m = HybridMacModel()
        m.step(start=1, a=3, b=4)
        m.step(candidate_fault=1)
        self.assertEqual(m.step(rst=1), (0, 0, 0, 0, 0, 0, 0))
        self.assertEqual(m.retry_count, 0)
        m.inject_accumulator_fault(4)
        m.step()
        self.assertTrue(m.corrected)
        m.step(clear=1, start=1)
        self.assertEqual(m.retry_count, 0)
        self.assertEqual(m.codeword, 0)

    def test_checker_corruption_and_invalid_encoding(self):
        m = HybridMacModel()
        m.step(start=1, a=2, b=3)  # predicted residue 6
        m.step(checker_fault=1)   # corrupt prediction to invalid residue 7
        self.assertTrue(m.detected and m.retried)
        self.assertEqual(m.step()[5], 6)

    def test_source_repair_even_on_final_arithmetic_rejection(self):
        for retries in (0, 1, 2, 3):
            with self.subTest(retries=retries):
                m = HybridMacModel(2, 4, max_retries=retries)
                m.step(start=1, a=1, b=1)
                self.assertEqual(m.step()[5], 1)
                original = m.codeword
                m.step(start=1, a=1, b=-1)
                before, after = m.inject_accumulator_fault(4)
                self.assertEqual(before ^ after, 4)
                for attempt in range(retries+1):
                    again = attempt < retries
                    self.assertEqual(m.step(candidate_fault=1, clear=1, start=1),
                                     (0, int(again), int(not again), 0,
                                      0 if again else 2, 1, 0))
                    self.assertEqual(m.codeword, original)
                    self.assertEqual((m.corrected, m.detected, m.retried, m.retry_count),
                                     (attempt == 0, True, again, min(attempt+1, retries)))
                self.assertEqual(m.step(), (1, 0, 0, 0, 0, 1, 1))
                self.assertFalse(m.corrected or m.detected or m.retried)
                self.assertEqual(m.retry_count, retries)

    def test_last_attempt_success_or_double_error_uses_saved_transaction(self):
        for retries in (0, 1, 2, 3):
            for double_error in (False, True):
                with self.subTest(retries=retries, double_error=double_error):
                    m = HybridMacModel(2, 4, max_retries=retries)
                    m.step(start=1, a=1, b=1)
                    self.assertEqual(m.step()[5], 1)
                    original = m.codeword
                    m.step(start=1, a=1, b=-1)
                    for attempt in range(retries):
                        self.assertEqual(m.step(candidate_fault=1, clear=1, start=1),
                                         (0, 1, 0, 0, 0, 1, 0))
                        self.assertEqual(m.codeword, original)
                        self.assertEqual(m.retry_count, attempt+1)
                    if double_error:
                        before, after = m.inject_accumulator_fault(3)
                        self.assertEqual(before ^ after, 3)
                        self.assertEqual(m.step(candidate_fault=1, clear=1, start=1),
                                         (0, 0, 1, 0, 1, 1, 0))
                        self.assertEqual(m.codeword, original ^ 3)
                    else:
                        self.assertEqual(m.step(clear=1, start=1), (0, 0, 1, 1, 0, 0, 0))
                        self.assertEqual(m.codeword, 0)
                    self.assertFalse(m.corrected or m.detected or m.retried)
                    self.assertEqual(m.retry_count, retries)
                    self.assertEqual(m.step(), (1, 0, 0, 0, 0, int(double_error), 1))

    def test_documented_silent_escape_cases(self):
        cases = [
            (0, 0, dict(candidate_fault=7), 7),  # modulo-7 collision
            (2, 3, dict(candidate_fault=1, checker_fault=6), 7),  # correlated faults
            (2, 3, dict(commit_fault=1), 7),  # valid ECC encoding of wrong post-check data
        ]
        for a, b, faults, wrong in cases:
            m = HybridMacModel()
            m.step(start=1, a=a, b=b)
            self.assertEqual(m.step(**faults), (0, 0, 1, 1, 0, wrong, 1))
            self.assertNotEqual(wrong, a*b)
            self.assertFalse(m.detected)
            self.assertFalse(m.codec.decode(m.codeword).uncorrectable)


if __name__ == '__main__':
    unittest.main()
