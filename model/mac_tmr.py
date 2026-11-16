"""Conventional datapath TMR with shared control/voters, not full-system TMR."""
from model.mac import signed


def vote(words, width):
    """Independent per-bit population count (RTL uses Boolean pair products)."""
    return sum((sum((word >> bit) & 1 for word in words) >= 2) << bit
               for bit in range(width))


class TmrMacModel:
    def __init__(self, operand_width=8, acc_width=24):
        if operand_width < 2 or acc_width < 2 * operand_width:
            raise ValueError('require OW >= 2 and AW >= 2*OW')
        self.operand_width, self.acc_width = operand_width, acc_width
        self.mask = (1 << acc_width) - 1
        self.state = [0, 0, 0]
        self.saved_a, self.saved_b = [0]*3, [0]*3
        self.busy = False

    @property
    def accumulator(self):
        return signed(vote(self.state, self.acc_width), self.acc_width)

    def inject(self, lane, site, mask):
        if lane not in range(3) or site not in ('state', 'saved_a', 'saved_b'):
            raise ValueError('invalid lane/site')
        width = self.acc_width if site == 'state' else self.operand_width
        if not 0 < mask < (1 << width):
            raise ValueError('mask must be nonzero and fit site')
        words = getattr(self, site)
        before = words[lane]
        words[lane] ^= mask
        return before, words[lane]

    def step(self, rst=0, clear=0, start=0, a=0, b=0,
             candidate_masks=(0, 0, 0), state_voter_mask=0, candidate_voter_mask=0):
        if len(candidate_masks) != 3 or any(not 0 <= m <= self.mask for m in
                (*candidate_masks, state_voter_mask, candidate_voter_mask)):
            raise ValueError('invalid combinational mask')
        ready_before = int(not (rst or clear or self.busy))
        done = 0
        candidates = [((s + signed(x, self.operand_width) * signed(y, self.operand_width))
                       & self.mask) ^ m for s, x, y, m in
                      zip(self.state, self.saved_a, self.saved_b, candidate_masks)]
        self.disagreement_before = (len(set(self.state)) > 1 or
                                   (self.busy and len(set(candidates)) > 1))
        if rst:
            self.state = [0]*3
            self.saved_a, self.saved_b = [0]*3, [0]*3
            self.busy = False
        elif self.busy:
            self.state = [vote(candidates, self.acc_width) ^ candidate_voter_mask]*3
            self.busy, done = False, 1
        elif clear:
            self.state = [0]*3
        else:
            self.state = [vote(self.state, self.acc_width) ^ state_voter_mask]*3
            if start:
                self.saved_a = [a & ((1 << self.operand_width)-1)]*3
                self.saved_b = [b & ((1 << self.operand_width)-1)]*3
                self.busy = True
        # State voter is combinational, so its held mask affects readback too.
        readback = signed(vote(self.state, self.acc_width) ^ state_voter_mask, self.acc_width)
        return (ready_before, int(self.busy), done, done, 0, readback,
                int(not (rst or clear or self.busy)))
