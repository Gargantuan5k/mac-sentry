"""Proposed cycle model for accumulator-only SECDED; no protected RTL yet."""

from dataclasses import dataclass, field

from model.mac import mac, signed
from model.secded import SecdedCodec


@dataclass
class SecdedMacModel:
    operand_width: int = 8
    acc_width: int = 24
    codeword: int = field(init=False, default=0)
    pending: tuple[int, int] | None = field(init=False, default=None)
    corrected: bool = field(init=False, default=False)
    codec: SecdedCodec = field(init=False)

    def __post_init__(self) -> None:
        if self.operand_width < 2 or self.acc_width < 2 * self.operand_width:
            raise ValueError("require operand_width >= 2 and acc_width >= 2*operand_width")
        self.codec = SecdedCodec(self.acc_width)
        self.codeword = self.codec.encode(0)

    @property
    def accumulator(self) -> int:
        """Decoded readback; uncorrectable data is diagnostic, not a valid result."""
        return signed(self.codec.decode(self.codeword).data, self.acc_width)

    def inject_accumulator_fault(self, mask: int) -> tuple[int, int]:
        """XOR stored bits immediately between step calls; return before/after.

        Bit zero is Hamming position 1, including check bits. This models a
        persistent register upset until overwritten or repaired, not a logic
        transient. Nonzero masks acknowledge an actual stored-bit change.
        """
        if not 0 < mask < 2**self.codec.code_width:
            raise ValueError("fault mask must be nonzero and fit the codeword")
        before = self.codeword
        self.codeword ^= mask
        return before, self.codeword

    def step(self, rst: int = 0, clear: int = 0, start: int = 0,
             a: int = 0, b: int = 0) -> tuple[int, ...]:
        """Same seven-value tuple as MacModel; corrected is a separate pulse.

        Priority: reset, pending completion, idle clear, idle scrub/acceptance.
        A rejected transaction leaves the stored codeword untouched. There is
        no retry, sticky failure latch, or operand/arithmetic/control protection.
        """
        ready_before = int(not (rst or clear or self.pending is not None))
        done = valid = error = 0
        self.corrected = False
        if rst:
            self.codeword = self.codec.encode(0)
            self.pending = None
        elif self.pending is not None:
            decoded = self.codec.decode(self.codeword)
            x, y = self.pending
            self.pending = None
            done = 1
            if decoded.uncorrectable:
                error = 1
            else:
                result = mac(signed(decoded.data, self.acc_width), x, y,
                             self.operand_width, self.acc_width)
                self.codeword = self.codec.encode(result % (2**self.acc_width))
                self.corrected = decoded.corrected
                valid = 1
        elif clear:
            self.codeword = self.codec.encode(0)
        else:
            decoded = self.codec.decode(self.codeword)
            if decoded.corrected:
                self.codeword = decoded.codeword
                self.corrected = True
            if start:
                self.pending = (signed(a, self.operand_width), signed(b, self.operand_width))
        busy = int(self.pending is not None)
        ready_after = int(not (rst or clear or busy))
        return ready_before, busy, done, valid, error, self.accumulator, ready_after
