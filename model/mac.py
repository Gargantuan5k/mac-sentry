"""Integer specification; deliberately independent of RTL bit slicing."""

from dataclasses import dataclass


def signed(value: int, width: int) -> int:
    if width < 1:
        raise ValueError("width must be positive")
    half = 2 ** (width - 1)
    return (value + half) % (2**width) - half


def mac(acc: int, a: int, b: int, operand_width: int = 8, acc_width: int = 24) -> int:
    return signed(signed(acc, acc_width) + signed(a, operand_width) * signed(b, operand_width), acc_width)


def predicted_residue(acc: int, a: int, b: int, operand_width: int, acc_width: int, modulus: int) -> int:
    """Signed-wrap equation oracle, not a fault-independent hardware checker.

    q is derived from exact arithmetic here. A future hardware checker must
    explicitly assess its dependency on the datapath's overflow information.
    """
    if modulus < 2:
        raise ValueError("modulus must be at least two")
    s, x, y = signed(acc, acc_width), signed(a, operand_width), signed(b, operand_width)
    exact = s + x * y
    q = (exact + 2 ** (acc_width - 1)) // (2**acc_width)
    return (s % modulus + (x % modulus) * (y % modulus) - q * (2**acc_width % modulus)) % modulus


@dataclass
class MacModel:
    operand_width: int = 8
    acc_width: int = 24
    accumulator: int = 0
    pending: tuple[int, int] | None = None

    def step(self, rst: int = 0, clear: int = 0, start: int = 0, a: int = 0, b: int = 0) -> tuple[int, ...]:
        """Return pre-edge ready, then post-edge busy/done/valid/error/acc/ready."""
        ready_before = int(not (rst or clear or self.pending is not None))
        done = 0
        if rst:
            self.accumulator, self.pending = 0, None
        elif self.pending is not None:
            x, y = self.pending
            self.accumulator = mac(self.accumulator, x, y, self.operand_width, self.acc_width)
            self.pending = None
            done = 1
        elif clear:
            self.accumulator = 0
        elif start:
            self.pending = (signed(a, self.operand_width), signed(b, self.operand_width))
        busy = int(self.pending is not None)
        ready_after = int(not (rst or clear or busy))
        return ready_before, busy, done, done, 0, self.accumulator, ready_after
