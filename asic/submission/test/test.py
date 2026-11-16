"""Independent pin-only oracle, shared by RTL and official gate-level CI.

No hierarchical forces or injectable RTL. These are functional, not SDF tests.
"""
import random
import cocotb
from cocotb.triggers import Timer


class Host:
    def __init__(self, dut):
        self.dut = dut
        self.acc = 0
        self.transactions = 0

    async def tick(self):
        d = self.dut
        d.clk.value = 0
        await Timer(24, unit='ns')
        d.clk.value = 1
        # Sample late in the high phase: official GLS inserts artificial #1
        # delays at each cell. Sampling at +1 ns races propagated clock/data.
        # Keep the same 50 ns period and exact protocol edge counts in RTL/GLS.
        await Timer(20, unit='ns')
        assert int(d.uio_out.value) == 0 and int(d.uio_oe.value) == 0, 'pads must remain inputs'
        value = int(d.uo_out.value)
        await Timer(6, unit='ns')
        d.clk.value = 0
        return value

    async def reset(self):
        d = self.dut
        d.ena.value = 1
        d.rst_n.value = 0
        d.ui_in.value = 0
        d.uio_in.value = 0
        assert await self.tick() == 0
        d.rst_n.value = 1
        await self.tick()
        self.acc = 0

    async def cmd(self, op, data=0, expected=None):
        self.dut.ui_in.value = data & 255
        self.dut.uio_in.value = 0
        await self.tick()
        self.dut.uio_in.value = 0x10 | op
        got = await self.tick()
        if expected is not None:
            assert got == expected, f'op={op} expected={expected:02x} got={got:02x}'
        return got

    async def result(self):
        got = sum([(await self.cmd(5 + i)) << (8 * i) for i in range(3)])
        assert got == self.acc, f'result expected={self.acc:06x} got={got:06x}'

    async def mac(self, a, b):
        await self.cmd(1, a, 0)
        await self.cmd(2, b, 0)
        await self.cmd(8, expected=0x18)
        await self.cmd(3, expected=0)
        # Reads return pre-edge state: completion capture edge still reads busy.
        await self.cmd(0, expected=1)
        await self.cmd(0, expected=6)
        await self.cmd(8, expected=0)
        self.acc = (self.acc + a * b) & 0xffffff
        self.transactions += 1
        await self.result()


@cocotb.test()
async def arithmetic_and_wrap(dut):
    h = Host(dut)
    await h.reset()
    await h.result()
    for a, b in [(34, 55), (15, 10), (-128, 127), (127, -128), (0, -1), (-1, -1)]:
        await h.mac(a, b)
    await h.cmd(4, expected=0)
    h.acc = 0
    for _ in range(512):
        await h.mac(-128, -128)
    assert h.acc == 0x800000, 'positive signed wrap must actually occur'
    await h.mac(-1, 1)
    assert h.acc == 0x7fffff, 'negative signed wrap must actually occur'
    rng = random.Random(20261112)
    for _ in range(256):
        await h.mac(rng.randrange(-128, 128), rng.randrange(-128, 128))
    dut._log.info('PIN_ORACLE_PASS transactions=%d; both signed wraps observed', h.transactions)


@cocotb.test()
async def protocol_reset_and_abort(dut):
    h = Host(dut)
    await h.reset()
    await h.cmd(3, expected=0xe3)  # Missing operands.
    await h.cmd(0, expected=0x80)
    await h.cmd(4, expected=0)
    await h.cmd(9, expected=0xe1)
    await h.cmd(0, expected=0x80)
    await h.cmd(4, expected=0)
    await h.cmd(0x20, expected=0xe1)  # Reserved control bit.
    await h.cmd(4, expected=0)
    await h.mac(3, 4)
    # Strobe remains high after cmd: changing opcode must not execute CLEAR.
    dut.uio_in.value = 0x14
    await h.tick()
    await h.tick()
    await h.result()
    await h.cmd(1, 2, 0)
    await h.cmd(2, 3, 0)
    await h.cmd(3, expected=0)
    await h.cmd(4, expected=0xe2)  # Busy includes the wrapper capture edge.
    await h.cmd(0, expected=0x86)
    h.acc = 18
    await h.result()
    # Fresh start consumes operands but does not clear the protocol error.
    await h.cmd(1, 1, 0)
    await h.cmd(2, 1, 0)
    await h.cmd(3, expected=0)
    dut.ena.value = 0
    assert await h.tick() == 0
    # Carry a high strobe across deselection: it must not launch a command.
    dut.uio_in.value = 0x13
    dut.ena.value = 1
    assert await h.tick() == 0
    assert await h.tick() == 0
    h.acc = 0
    await h.cmd(0, expected=0)
    await h.result()
    await h.cmd(8, expected=0)
    await h.mac(-7, 9)
    await h.reset()
    await h.cmd(0, expected=0)
    await h.result()
    dut._log.info('PIN_PROTOCOL_PASS illegal, held strobe, busy reject, abort, recovery')
