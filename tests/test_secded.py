"""Codec checks against known words and an exhaustive distance oracle."""

from itertools import combinations
import random
import unittest

from model.secded import SecdedCodec


class SecdedCodecTests(unittest.TestCase):
    def test_known_layout_and_even_parity(self):
        # Hand-derived extended (8,4) words pin down mapping independently.
        codec = SecdedCodec(4)
        for data, word in [(0, 0), (1, 0x87), (2, 0x99), (4, 0xAA),
                           (8, 0x4B), (15, 0xFF)]:
            self.assertEqual(codec.encode(data), word)
            self.assertEqual(codec.decode(word).data, data)
        codec = SecdedCodec(24)
        self.assertEqual((codec.parity_width, codec.hamming_width, codec.code_width),
                         (5, 29, 30))
        self.assertEqual(codec.encode(1), 0x20000007)
        self.assertEqual(codec.encode(1 << 23), 0x30008089)
        rng = random.Random(20261014)
        # Independent parity-group membership, expressed as fixed bit masks.
        masks = [sum(1 << (p - 1) for p in range(1, 30) if p & flag)
                 for flag in (1, 2, 4, 8, 16)]
        for _ in range(100):
            word = codec.encode(rng.randrange(1 << 24))
            self.assertEqual(word.bit_count() % 2, 0)
            for mask in masks:
                self.assertEqual((word & mask).bit_count() % 2, 0)

    def test_default_all_single_bits_and_double_pairs(self):
        codec = SecdedCodec()
        rng = random.Random(20261014)
        values = [0, 0xFFFFFF, 0x800000, 0x7FFFFF, 0xAAAAAA, 0x555555,
                  1, 0x123456] + [rng.randrange(1 << 24) for _ in range(32)]
        for data in values:
            word = codec.encode(data)
            clean = codec.decode(word)
            self.assertEqual((clean.data, clean.codeword, clean.syndrome,
                              clean.corrected, clean.uncorrectable, clean.corrected_bit),
                             (data, word, 0, False, False, None))
            for bit in range(30):
                with self.subTest(data=data, bit=bit):
                    decoded = codec.decode(word ^ (1 << bit))
                    self.assertEqual((decoded.data, decoded.codeword, decoded.corrected,
                                      decoded.uncorrectable, decoded.corrected_bit),
                                     (data, word, True, False, bit))
                    self.assertEqual(decoded.syndrome, bit + 1 if bit < 29 else 0)
            for first, second in combinations(range(30), 2):
                with self.subTest(data=data, bits=(first, second)):
                    corrupted = word ^ (1 << first) ^ (1 << second)
                    decoded = codec.decode(corrupted)
                    self.assertTrue(decoded.uncorrectable)
                    self.assertFalse(decoded.corrected)
                    self.assertIsNone(decoded.corrected_bit)
                    self.assertEqual(decoded.codeword, corrupted)

    def test_exhaustive_small_codes_against_distance_oracle(self):
        # Compare every received word to all valid words by Hamming distance.
        # This oracle does not use syndromes or the decoder's classification.
        for width in range(1, 7):
            codec = SecdedCodec(width)
            words = {codec.encode(data): data for data in range(1 << width)}
            self.assertEqual(len(words), 1 << width)
            self.assertGreaterEqual(min((a ^ b).bit_count()
                                        for a, b in combinations(words, 2)), 4)
            for received in range(1 << codec.code_width):
                neighbors = [(word, data) for word, data in words.items()
                             if (word ^ received).bit_count() <= 1]
                self.assertLessEqual(len(neighbors), 1)
                decoded = codec.decode(received)
                if neighbors:
                    word, data = neighbors[0]
                    self.assertEqual((decoded.data, decoded.codeword), (data, word))
                    self.assertFalse(decoded.uncorrectable)
                    self.assertEqual(decoded.corrected, received != word)
                    bit = (word ^ received).bit_length() - 1 if received != word else None
                    self.assertEqual(decoded.corrected_bit, bit)
                else:
                    self.assertTrue(decoded.uncorrectable, (width, received))
                    self.assertFalse(decoded.corrected)
                    self.assertEqual(decoded.codeword, received)

    def test_shortened_positions_and_out_of_guarantee_examples(self):
        codec = SecdedCodec()
        # Three flips with syndrome 30 or 31: neither is a stored position.
        for positions, syndrome in [((1, 2, 29), 30), ((1, 2, 28), 31)]:
            word = sum(1 << (p - 1) for p in positions)
            decoded = codec.decode(word)
            self.assertEqual(decoded.syndrome, syndrome)
            self.assertTrue(decoded.uncorrectable)
            self.assertFalse(decoded.corrected)
            self.assertEqual(decoded.codeword, word)
        # Positions 1,2,3 yield zero syndrome but odd parity: miscorrection.
        triple = codec.decode(0b111)
        self.assertTrue(triple.corrected)
        self.assertFalse(triple.uncorrectable)
        self.assertEqual(triple.data, 1)
        # Adding the overall parity flip produces a different valid codeword.
        escaped = codec.decode(0b111 | (1 << 29))
        self.assertFalse(escaped.corrected or escaped.uncorrectable)
        self.assertEqual(escaped.data, 1)

    def test_reject_out_of_range_inputs(self):
        for width in (0, -1):
            with self.assertRaises(ValueError):
                SecdedCodec(width)
        codec = SecdedCodec()
        for value in (-1, 1 << 24):
            with self.assertRaises(ValueError):
                codec.encode(value)
        for value in (-1, 1 << 30):
            for operation in (codec.decode, codec.extract_data):
                with self.assertRaises(ValueError):
                    operation(value)


if __name__ == "__main__":
    unittest.main()
