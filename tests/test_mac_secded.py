"""Transaction, repair and rejection checks for accumulator-only protection."""

from itertools import combinations
import random
import unittest

from model.mac import MacModel
from model.mac_secded import SecdedMacModel


STATES = (0, 1, -1, 8388607, -8388608, 0x555555)


def initialized(acc=0, operand_width=8, acc_width=24):
    model = SecdedMacModel(operand_width, acc_width)
    model.step(rst=1)
    # Fixture preload, not a proposed hardware load interface.
    model.codeword = model.codec.encode(acc % (1 << acc_width))
    return model


class SecdedMacTests(unittest.TestCase):
    def test_fault_free_random_cycle_equivalence(self):
        for ow, aw in ((8, 24), (4, 8)):
            rng = random.Random(20261014)
            reference = MacModel(ow, aw)
            protected = SecdedMacModel(ow, aw)
            self.assertEqual(protected.step(rst=1), reference.step(rst=1))
            for cycle in range(5000):
                inputs = dict(rst=int(rng.randrange(100) == 0),
                              clear=int(rng.randrange(20) == 0),
                              start=rng.randrange(2),
                              a=rng.randrange(-(1 << ow), 1 << ow),
                              b=rng.randrange(-(1 << ow), 1 << ow))
                self.assertEqual(protected.step(**inputs), reference.step(**inputs),
                                 (ow, aw, cycle, inputs))
                self.assertFalse(protected.corrected)

    def test_directed_arithmetic_after_single_fault(self):
        for acc, a, b, expected in [(8388607, 1, 1, -8388608),
                                    (-8388608, -1, 1, 8388607),
                                    (0, -128, -128, 16384),
                                    (0, -128, 127, -16256),
                                    (1870, 15, 10, 2020)]:
            model = initialized(acc)
            model.step(start=1, a=a, b=b)
            model.inject_accumulator_fault(1 << 28)
            self.assertEqual(model.step(), (0, 0, 1, 1, 0, expected, 1))
            self.assertTrue(model.corrected)
            self.assertEqual(model.codeword, model.codec.encode(expected % (1 << 24)))

    def test_all_single_bits_idle_acceptance_and_completion(self):
        for acc in STATES:
            for phase in ("idle", "acceptance", "completion"):
                for bit in range(30):
                    with self.subTest(acc=acc, phase=phase, bit=bit):
                        model = initialized(acc)
                        original = model.codeword
                        if phase == "completion":
                            model.step(start=1, a=0, b=-128)
                        before, after = model.inject_accumulator_fault(1 << bit)
                        self.assertEqual((before, after), (original, original ^ (1 << bit)))
                        self.assertEqual(model.accumulator, acc)
                        self.assertEqual(model.codeword, after)  # Readback must not repair.
                        if phase == "acceptance":
                            actual = model.step(start=1, a=0, b=-128)
                            expected = (1, 1, 0, 0, 0, acc, 0)
                        elif phase == "completion":
                            actual = model.step()
                            expected = (0, 0, 1, 1, 0, acc, 1)
                        else:
                            actual = model.step()
                            expected = (1, 0, 0, 0, 0, acc, 1)
                        self.assertEqual(actual, expected)
                        self.assertTrue(model.corrected)
                        self.assertEqual(model.codeword, original)
                        model.step()
                        self.assertFalse(model.corrected)

    def test_all_double_pairs_reject_without_commit(self):
        for acc in STATES:
            for phase in ("idle", "completion"):
                for first, second in combinations(range(30), 2):
                    with self.subTest(acc=acc, phase=phase, bits=(first, second)):
                        model = initialized(acc)
                        if phase == "completion":
                            model.step(start=1, a=3, b=4)
                        mask = (1 << first) | (1 << second)
                        before, damaged = model.inject_accumulator_fault(mask)
                        self.assertEqual(before ^ damaged, mask)
                        if phase == "idle":
                            self.assertEqual(model.step()[:5], (1, 0, 0, 0, 0))
                            self.assertEqual(model.codeword, damaged)
                            self.assertFalse(model.corrected)
                            self.assertEqual(model.step(start=1, a=3, b=4)[:5],
                                             (1, 1, 0, 0, 0))
                        actual = model.step()
                        self.assertEqual(actual[:5], (0, 0, 1, 0, 1))
                        self.assertEqual(actual[6], 1)
                        self.assertIsNone(model.pending)
                        self.assertFalse(model.corrected)
                        self.assertEqual(model.codeword, damaged)
                        self.assertEqual(model.step()[:5], (1, 0, 0, 0, 0))
                        self.assertEqual(model.codeword, damaged)

    def test_repeated_failure_and_clear_recovery(self):
        model = initialized(42)
        model.inject_accumulator_fault(3)
        damaged = model.codeword
        for _ in range(3):
            model.step(start=1, a=5, b=6)
            self.assertEqual(model.step()[:5], (0, 0, 1, 0, 1))
            self.assertEqual(model.codeword, damaged)
        self.assertEqual(model.step(clear=1, start=1), (0, 0, 0, 0, 0, 0, 0))
        self.assertEqual(model.codeword, 0)
        self.assertFalse(model.corrected)
        model.step(start=1, a=5, b=6)
        self.assertEqual(model.step(), (0, 0, 1, 1, 0, 30, 1))

    def test_reset_aborts_damaged_pending_transaction(self):
        for mask in (1, 3):
            model = initialized(42)
            model.step(start=1, a=7, b=8)
            model.inject_accumulator_fault(mask)
            self.assertEqual(model.step(rst=1, clear=1, start=1),
                             (0, 0, 0, 0, 0, 0, 0))
            self.assertFalse(model.corrected)
            self.assertEqual(model.codeword, 0)
            self.assertEqual(model.step(), (1, 0, 0, 0, 0, 0, 1))

    def test_busy_ignores_clear_start_and_new_operands(self):
        model = initialized(42)
        model.step(start=1, a=3, b=-4)
        model.inject_accumulator_fault(1 << 29)
        self.assertEqual(model.step(clear=1, start=1, a=99, b=99),
                         (0, 0, 1, 1, 0, 30, 0))
        self.assertTrue(model.corrected)
        self.assertEqual(model.step(), (1, 0, 0, 0, 0, 30, 1))
        model.step(start=1, a=3, b=-4)
        model.inject_accumulator_fault(3)
        damaged = model.codeword
        self.assertEqual(model.step(clear=1, start=1)[:5], (0, 0, 1, 0, 1))
        self.assertEqual(model.codeword, damaged)  # Busy clear cannot hide failure.
        self.assertEqual(model.step(clear=1), (0, 0, 0, 0, 0, 0, 0))

    def test_repeated_single_upsets_repair_each_time(self):
        model = initialized(-12)
        original = model.codeword
        for _ in range(3):
            model.inject_accumulator_fault(1 << 2)
            self.assertEqual(model.step(), (1, 0, 0, 0, 0, -12, 1))
            self.assertTrue(model.corrected)
            self.assertEqual(model.codeword, original)

    def test_invalid_dimensions_and_injection_masks(self):
        for ow, aw in ((1, 24), (8, 15), (4, 0)):
            with self.assertRaises(ValueError):
                SecdedMacModel(ow, aw)
        model = initialized(42)
        original = model.codeword
        for mask in (0, -1, 1 << 30):
            with self.assertRaises(ValueError):
                model.inject_accumulator_fault(mask)
            self.assertEqual(model.codeword, original)


if __name__ == "__main__":
    unittest.main()
