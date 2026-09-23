import unittest

from model.mac import MacModel, mac, predicted_residue, signed


class ArithmeticTests(unittest.TestCase):
    def test_directed_arithmetic(self):
        for acc, a, b, expected in [
            (0, -128, -128, 16384), (0, -128, 127, -16256),
            (8388607, 1, 1, -8388608), (-8388608, -1, 1, 8388607),
            (8388600, 127, 127, -8372487), (42, 0, -128, 42),
        ]:
            with self.subTest(acc=acc, a=a, b=b):
                self.assertEqual(mac(acc, a, b), expected)

    def test_signed_bit_patterns(self):
        self.assertEqual(signed(255, 8), -1)
        self.assertEqual(signed(128, 8), -128)
        self.assertEqual(signed(-129, 8), 127)

    def test_exhaustive_signed_wrap_equation(self):
        # Includes narrow accumulators with multiple wraps: q is not just a flag.
        for ow, aw in [(3, 3), (3, 6), (4, 8)]:
            for modulus in (3, 7):
                for acc in range(-(2 ** (aw - 1)), 2 ** (aw - 1)):
                    for a in range(-(2 ** (ow - 1)), 2 ** (ow - 1)):
                        for b in range(-(2 ** (ow - 1)), 2 ** (ow - 1)):
                            actual = mac(acc, a, b, ow, aw) % modulus
                            expected = predicted_residue(acc, a, b, ow, aw, modulus)
                            self.assertEqual(actual, expected, (ow, aw, modulus, acc, a, b))

    def test_documented_four_bit_boundaries(self):
        for acc, a, b, value, residue in [(7, 1, 1, -8, 6), (-8, -1, 1, 7, 0), (6, 2, 2, -6, 1), (-6, -2, 2, 6, 6)]:
            self.assertEqual(mac(acc, a, b, 4, 4), value)
            self.assertEqual(predicted_residue(acc, a, b, 4, 4, 7), residue)


class ProtocolTests(unittest.TestCase):
    def test_latching_and_busy_rejection(self):
        m = MacModel()
        self.assertEqual(m.step(start=1, a=3, b=-4), (1, 1, 0, 0, 0, 0, 0))
        self.assertEqual(m.step(start=1, clear=1, a=99, b=99), (0, 0, 1, 1, 0, -12, 0))
        self.assertEqual(m.step(), (1, 0, 0, 0, 0, -12, 1))

    def test_reset_aborts_and_clear_wins(self):
        m = MacModel()
        m.step(start=1, a=4, b=5)
        self.assertEqual(m.step(rst=1, start=1), (0, 0, 0, 0, 0, 0, 0))
        self.assertEqual(m.step(clear=1, start=1, a=4, b=5), (0, 0, 0, 0, 0, 0, 0))
        self.assertEqual(m.step(), (1, 0, 0, 0, 0, 0, 1))


if __name__ == "__main__":
    unittest.main()
