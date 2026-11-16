"""Conventional SECDED + modulo-7 arithmetic check + bounded retry reference.

The full signed ACC_WIDTH+1 candidate is checked before truncation. Fault masks
are experimental hooks, not production inputs. See spec/hybrid_mac.md.
"""
from dataclasses import dataclass, field

from model.mac import signed
from model.mac_secded import SecdedMacModel


def expected_residue(acc, a, b):
    return (acc % 7 + (a % 7) * (b % 7)) % 7


@dataclass
class HybridMacModel(SecdedMacModel):
    max_retries: int = 2
    retry_count: int = field(init=False, default=0)
    retried: bool = field(init=False, default=False)
    detected: bool = field(init=False, default=False)

    def __post_init__(self):
        super().__post_init__()
        if self.max_retries < 0:
            raise ValueError('max_retries must be nonnegative')

    def step(self, rst=0, clear=0, start=0, a=0, b=0, *,
             candidate_fault=0, checker_fault=0, commit_fault=0):
        for mask, width in ((candidate_fault, self.acc_width+1),
                            (checker_fault, 3), (commit_fault, self.acc_width)):
            if not 0 <= mask < (1 << width):
                raise ValueError('fault mask outside its injection site width')
        ready_before = int(not (rst or clear or self.pending is not None))
        done = valid = error = 0
        self.corrected = self.retried = self.detected = False
        if rst:
            self.codeword, self.pending, self.retry_count = 0, None, 0
        elif self.pending is not None:
            decoded = self.codec.decode(self.codeword)
            if decoded.uncorrectable:
                self.pending = None
                done, error = 1, 1
            else:
                self.corrected = decoded.corrected
                self.codeword = decoded.codeword  # repair valid source state, even on rejection
                x, y = self.pending
                acc = signed(decoded.data, self.acc_width)
                exact = acc + x * y
                candidate = signed((exact % (1 << (self.acc_width+1))) ^ candidate_fault,
                                   self.acc_width+1)
                prediction = expected_residue(acc, x, y) ^ checker_fault
                if prediction > 6 or candidate % 7 != prediction:
                    self.detected = True
                    if self.retry_count < self.max_retries:
                        self.retry_count += 1
                        self.retried = True
                    else:
                        self.pending = None
                        done, error = 1, 2
                else:
                    data = (candidate % (1 << self.acc_width)) ^ commit_fault
                    self.codeword = self.codec.encode(data)
                    self.pending = None
                    done = valid = 1
        elif clear:
            self.codeword, self.retry_count = 0, 0
        else:
            decoded = self.codec.decode(self.codeword)
            if decoded.corrected:
                self.codeword, self.corrected = decoded.codeword, True
            if start:
                self.pending = (signed(a, self.operand_width), signed(b, self.operand_width))
                self.retry_count = 0
        busy = int(self.pending is not None)
        return ready_before, busy, done, valid, error, self.accumulator, int(not (rst or clear or busy))
