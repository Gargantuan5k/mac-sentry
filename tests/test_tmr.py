import random
import unittest
from model.mac import MacModel, signed
from model.mac_tmr import TmrMacModel, vote
from scripts.test_tmr import control_coverage


class TestTmr(unittest.TestCase):
    def test_control_coverage_rejects_missing_cross(self):
        rows = [dict(cycle=i,rst=r,clear=c,start=s,busy=b,done=d) for i,(r,c,s,b,d) in
                enumerate([(1,0,1,0,0),(1,0,1,1,0),(0,1,1,0,0),
                           (0,1,1,1,0),(0,0,1,0,1)])]
        self.assertTrue(all(control_coverage(rows).values()))
        with self.assertRaisesRegex(ValueError, 'missing reset_start_idle'):
            control_coverage(rows[1:])
        # The reviewed low-bit generator cannot produce reset+start.
        seed=503
        locked=[]
        for cycle in range(1000):
            seed=(seed*1664525+1013904223)&0xffffffff
            locked.append(dict(cycle=cycle,rst=int((seed&127)==0),
                clear=int((seed&31)==1),start=int(bool(seed&2)),busy=0,done=0))
        with self.assertRaisesRegex(ValueError, 'missing reset_start_idle'):
            control_coverage(locked)

    def test_disagreement_before(self):
        for ow,aw in [(8,24),(4,8),(2,4)]:
            dut=TmrMacModel(ow,aw)
            dut.step(); self.assertFalse(dut.disagreement_before)
            dut.state=[1,0,0]
            dut.step(); self.assertTrue(dut.disagreement_before)
            self.assertEqual(dut.state,[0]*3)
            dut.step(); self.assertFalse(dut.disagreement_before)
            dut.step(candidate_masks=(1,0,0)) # idle candidate divergence ignored
            self.assertFalse(dut.disagreement_before)
            dut.step(start=1,a=1,b=1)
            dut.step(candidate_masks=(1,0,0)); self.assertTrue(dut.disagreement_before)
            dut.step(start=1,a=1,b=1)
            dut.step(candidate_masks=(1,1,1))
            self.assertFalse(dut.disagreement_before) # common-mode corruption is invisible

    def test_clean_protocol(self):
        for ow, aw in [(8,24),(4,8),(2,4)]:
            ref, dut, rng = MacModel(ow,aw), TmrMacModel(ow,aw), random.Random(5005)
            for _ in range(12000):
                args = dict(rst=rng.randrange(45)==0, clear=rng.randrange(9)==0,
                            start=rng.randrange(2), a=rng.randrange(1<<ow), b=rng.randrange(1<<ow))
                self.assertEqual(dut.step(**args), ref.step(**args))

    def test_exhaustive_small(self):
        for s in range(16):
            for a in range(4):
                for b in range(4):
                    dut=TmrMacModel(2,4); dut.state=[s]*3
                    dut.step(start=1,a=a,b=b)
                    self.assertEqual(dut.step()[5], signed(s+signed(a,2)*signed(b,2),4))
        for x in range(16):
            for y in range(16):
                for z in range(16):
                    self.assertEqual(vote([x,y,z],4), (x&y)|(x&z)|(y&z))

    def test_every_lane_storage_operand_and_candidate(self):
        for ow, aw in [(8,24),(4,8),(2,4)]:
            for lane in range(3):
                for site, width in [('state',aw),('saved_a',ow),('saved_b',ow)]:
                    for bit in range(width):
                        dut=TmrMacModel(ow,aw)
                        dut.step(start=1,a=1,b=1)
                        before,after=dut.inject(lane,site,1<<bit)
                        self.assertEqual(before^after,1<<bit)
                        self.assertEqual(dut.step()[5],1)
                        self.assertEqual(dut.state,[1]*3)
                        if site!='state':  # saved faults remain until next acceptance
                            self.assertNotEqual(getattr(dut,site)[lane],1)
                        dut.step(start=1,a=1,b=1)
                        self.assertEqual(dut.step()[5],2)
                for bit in range(aw):
                    dut=TmrMacModel(ow,aw); dut.state=[5]*3
                    dut.inject(lane,'state',1<<bit)
                    self.assertEqual(dut.accumulator,5)
                    dut.step(); self.assertEqual(dut.state,[5]*3)
                    dut.step(start=1,a=1,b=1)
                    masks=[0]*3; masks[lane]=1<<bit
                    self.assertEqual(dut.step(candidate_masks=masks)[5],6)

    def test_limits_literal(self):
        dut=TmrMacModel(); dut.state=[1,2,4]
        self.assertEqual(dut.accumulator,0)  # no entire word agrees with vote
        dut.step(); self.assertEqual(dut.state,[0]*3)
        dut.state=[1,1,0]; dut.step()
        self.assertEqual(dut.state,[1]*3)  # wrong majority becomes unanimous
        dut=TmrMacModel(); dut.step(start=1,a=1,b=1)
        self.assertEqual(dut.step(candidate_masks=(1,1,0))[5],0)
        dut=TmrMacModel(); dut.step(start=1,a=1,b=1)
        self.assertEqual(dut.step(candidate_voter_mask=1)[5],0)
        dut=TmrMacModel(); dut.step(state_voter_mask=1)
        self.assertEqual(dut.state,[1]*3)
        dut.step(); self.assertEqual(dut.accumulator,1)
        dut=TmrMacModel(); dut.step(start=1,a=1,b=1)
        dut.busy=False  # common control upset: silently drops operation
        self.assertEqual(dut.step()[2:6],(0,0,0,0))
        dut=TmrMacModel(); dut.step(start=1,a=0,b=1)  # corrupted common input, intended a=1
        self.assertEqual(dut.step()[2:6],(1,1,0,0))

    def test_signed_wrap_literals(self):
        for ow, aw in [(8,24),(4,8),(2,4)]:
            dut=TmrMacModel(ow,aw)
            dut.state=[(1<<(aw-1))-1]*3
            dut.step(start=1,a=1,b=1)
            self.assertEqual(dut.step()[5],-(1<<(aw-1)))
            dut.step(start=1,a=-1,b=1)
            self.assertEqual(dut.step()[5],(1<<(aw-1))-1)

    def test_invalid_injections(self):
        for ow,aw in [(1,4),(3,4)]:
            with self.assertRaises(ValueError): TmrMacModel(ow,aw)
        dut=TmrMacModel()
        for lane,site,mask in [(3,'state',1),(0,'bad',1),(0,'state',0),(0,'saved_a',256)]:
            with self.assertRaises(ValueError): dut.inject(lane,site,mask)
        with self.assertRaises(ValueError): dut.step(candidate_masks=(0,0))
