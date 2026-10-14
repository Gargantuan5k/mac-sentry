"""Shortened extended Hamming code, with even parity throughout.

Positions are one-based Hamming indices; integer bit indices are zero-based.
The overall parity bit follows the shortened Hamming word. Codec inputs are
unsigned bit patterns; signed conversion belongs to the MAC model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecodeResult:
    data: int
    codeword: int
    syndrome: int
    corrected: bool
    uncorrectable: bool
    corrected_bit: int | None


@dataclass(frozen=True)
class SecdedCodec:
    data_width: int = 24

    def __post_init__(self) -> None:
        if self.data_width < 1:
            raise ValueError("data_width must be positive")

    @property
    def parity_width(self) -> int:
        count = 0
        while 2**count < self.data_width + count + 1:
            count += 1
        return count

    @property
    def hamming_width(self) -> int:
        return self.data_width + self.parity_width

    @property
    def code_width(self) -> int:
        return self.hamming_width + 1

    @property
    def data_positions(self) -> tuple[int, ...]:
        return tuple(position for position in range(1, self.hamming_width + 1)
                     if position & (position - 1))

    def _check_codeword(self, codeword: int) -> None:
        if not 0 <= codeword < 2**self.code_width:
            raise ValueError(f"codeword must fit in {self.code_width} unsigned bits")

    def extract_data(self, codeword: int) -> int:
        """Extract data without correction or any validity guarantee."""
        self._check_codeword(codeword)
        return sum(((codeword >> (position - 1)) & 1) << bit
                   for bit, position in enumerate(self.data_positions))

    def encode(self, data: int) -> int:
        if not 0 <= data < 2**self.data_width:
            raise ValueError(f"data must fit in {self.data_width} unsigned bits")
        word = sum(((data >> bit) & 1) << (position - 1)
                   for bit, position in enumerate(self.data_positions))
        for parity_bit in range(self.parity_width):
            parity_position = 1 << parity_bit
            parity = 0
            for position in range(1, self.hamming_width + 1):
                if position & parity_position:
                    parity ^= (word >> (position - 1)) & 1
            word |= parity << (parity_position - 1)
        return word | ((word.bit_count() & 1) << self.hamming_width)

    def decode(self, codeword: int) -> DecodeResult:
        """Return decoder classification, not knowledge of the injected fault.

        Single-bit correction and double-bit detection assume a valid original
        codeword and a functioning codec. Three or more flips can escape or be
        miscorrected. On uncorrectable status, data is raw and must not be used.
        """
        self._check_codeword(codeword)
        syndrome = 0
        for position in range(1, self.hamming_width + 1):
            if (codeword >> (position - 1)) & 1:
                syndrome ^= position
        odd_parity = codeword.bit_count() & 1
        corrected_bit = None
        uncorrectable = False
        if odd_parity:
            if syndrome == 0:
                corrected_bit = self.hamming_width
            elif syndrome <= self.hamming_width:
                corrected_bit = syndrome - 1
            else:
                # A shortened-away position cannot represent a single-bit upset.
                uncorrectable = True
        elif syndrome:
            uncorrectable = True
        repaired = codeword
        if corrected_bit is not None:
            repaired ^= 1 << corrected_bit
        return DecodeResult(self.extract_data(repaired), repaired, syndrome,
                            corrected_bit is not None, uncorrectable, corrected_bit)
