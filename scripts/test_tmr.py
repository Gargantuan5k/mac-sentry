#!/usr/bin/env python3
"""M5 directed verification. Unique raw evidence; no physical/coverage claims."""
import argparse
import csv
import copy
import re
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['rtl/mac_tmr_lane.sv', 'rtl/mac_tmr.sv', 'rtl/mac_tmr_injectable.sv',
           'rtl/mac_tmr_datapath.vh', 'tests/tmr_tb.sv', 'tests/tmr_gate_tb.sv',
           'model/mac_tmr.py', 'model/mac.py', 'tests/test_tmr.py',
           'scripts/test_tmr.py', 'Makefile', 'spec/tmr_mac.md']


def control_coverage(records):
    """Count sampled input/state crosses, not intended stimulus or cycle totals."""
    counts = dict.fromkeys(('reset_start_idle', 'reset_start_busy', 'reset_busy',
        'clear_start_idle', 'clear_busy', 'start_busy', 'start_after_done',
        'held_start_accept'), 0)
    previous = None
    for row in records:
        rst, clear, start, busy, done = (int(row[k]) for k in
                                       ('rst', 'clear', 'start', 'busy', 'done'))
        accept = not rst and not clear and not busy and start
        cases = dict(reset_start_idle=rst and start and not busy,
                     reset_start_busy=rst and start and busy,
                     reset_busy=rst and busy,
                     clear_start_idle=not rst and clear and start and not busy,
                     clear_busy=not rst and clear and busy,
                     start_busy=not rst and start and busy,
                     start_after_done=accept and done,
                     held_start_accept=accept and previous is not None and
                         int(previous['start']) and int(row['cycle'])==int(previous['cycle'])+1)
        for case, hit in cases.items():
            counts[case] += int(bool(hit))
        previous = row
    missing = [case for case, hits in counts.items() if not hits]
    if missing:
        raise ValueError('TMR_CONTROL_COVERAGE: missing '+','.join(missing))
    return counts


def check_control_trace(rows, schema, kind):
    records = [dict(zip(schema[kind], row[1:])) for row in rows if row[0]==kind]
    # Also require random-only coverage: directed examples cannot hide a locked PRNG.
    return {phase: control_coverage([r for r in records if phase=='all' or r['phase']=='1'])
            for phase in ('all', 'random')}


def inspect_redundancy(data, coarse, ow, aw):
    top = data['modules']['mac_tmr']
    lanes = {n:c for n,c in top['cells'].items() if 'mac_tmr_lane' in c['type']}
    if set(lanes) != {'lane0','lane1','lane2'}:
        raise ValueError('TMR_REDUNDANCY: expected three lane instances')
    outputs = {p:[] for p in ['state_word','candidate']}
    evidence = {}
    for name, cell in lanes.items():
        lane = data['modules'][cell['type']]
        before = coarse['modules'][cell['type']]
        for op in ['$mul','$add']:
            if sum(c['type']==op for c in before['cells'].values()) != 1:
                raise ValueError('TMR_REDUNDANCY: missing lane arithmetic '+name+op)
        registers = {n:c for n,c in lane['cells'].items() if 'DFF' in c['type'].upper()}
        qbits = [b for c in registers.values() for b in c['connections']['Q']]
        ownership = {}
        for reg, width in [('acc_state',aw),('saved_a',ow),('saved_b',ow)]:
            bits = lane['netnames'][reg]['bits']
            if len(bits)!=width or len(set(bits))!=width or not set(bits)<=set(qbits):
                raise ValueError('TMR_REDUNDANCY: missing raw register bits '+name+reg)
            ownership[reg] = bits
        if len(set(sum(ownership.values(),[]))) != aw+2*ow or len(qbits)!=aw+2*ow:
            raise ValueError('TMR_REDUNDANCY: merged lane register bits')
        for p in outputs:
            bits = cell['connections'][p]
            if len(bits)!=aw or not all(isinstance(b,int) for b in bits):
                raise ValueError('TMR_REDUNDANCY: constant or missing output')
            outputs[p].append(set(bits))
        if not any(c['type'].startswith('$_') and 'DFF' not in c['type'].upper()
                   for c in lane['cells'].values()):
            raise ValueError('TMR_REDUNDANCY: missing mapped logic')
        evidence[name] = dict(type=cell['type'], registers=ownership, dff_bits=len(qbits),
                              mapped_cells=len(lane['cells']), coarse_mul=1, coarse_add=1)
    for p, sets in outputs.items():
        if any(sets[i]&sets[j] for i in range(3) for j in range(i)):
            raise ValueError('TMR_REDUNDANCY: aliased lane outputs '+p)
    # Check top-level combinational paths from every lane's outputs to feedback.
    drivers = {}
    for c in top['cells'].values():
        if 'mac_tmr_lane' in c['type'] or 'DFF' in c['type'].upper():
            continue
        inputs = {b for p,bs in c['connections'].items() if c['port_directions'][p]=='input' for b in bs}
        for p,bs in c['connections'].items():
            if c['port_directions'][p]=='output':
                for b in bs: drivers[b]=inputs
    feedback = lanes['lane0']['connections']['feedback']
    if any(c['connections']['feedback']!=feedback for c in lanes.values()):
        raise ValueError('TMR_REDUNDANCY: feedback wiring differs')
    ancestors = set(feedback)
    todo = list(feedback)
    while todo:
        for b in drivers.get(todo.pop(),set())-ancestors:
            ancestors.add(b);todo.append(b)
    if not all(bits<=ancestors for sets in outputs.values() for bits in sets):
        raise ValueError('TMR_REDUNDANCY: voter missing lane influence')
    return dict(lanes=evidence, expanded_lane_dff_bits=3*(aw+2*ow),
                independent_output_buses=True, all_lanes_reach_feedback=True,
                limitation='Generic hierarchy evidence only; recheck after target mapping/flattening/placement.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs',type=int,choices=[1,2],default=2)
    p.add_argument('--verilator',default='verilator');p.add_argument('--yosys',default='yosys')
    args=p.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    base=ROOT/'build/tmr';base.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run_',dir=base))
    print('M5 evidence: '+str(out.relative_to(ROOT)),flush=True)
    hashes={}
    for name in SOURCES:
        content=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(content).hexdigest()
        dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    (out/'source_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    commands=[]
    (out/'trace_schema.json').write_text(json.dumps({
        'pre':['cycle','rst','clear','start','busy','done','valid','state0','state1','state2',
               'a0','a1','a2','b0','b1','b2','candidate_mask0','candidate_mask1','candidate_mask2',
               'state_voter_mask','candidate_voter_mask','phase'],
        'post':['cycle','busy','done','valid','raw0','raw1','raw2','readback','disagreement'],
        'inject':['cycle','lane','site_0state_1a_2b','mask','before','after'],
        'control_inject':['cycle','site','before','after'],
        'gate_pre':['cycle','rst','clear','start','busy','done','valid','a','b','readback','phase'],
        'gate_post':['cycle','busy','done','valid','readback','disagreement'],
        'phase':'0 directed clean, 1 random clean, 2 directed fault tests',
        'radix':'state/operand/mask/word values hexadecimal; cycle/control/lane/site decimal',
        'timing':'pre before rising edge, post after; between-edge injections have current completed-cycle count'
    },indent=2)+'\n')
    def run(name,argv,marker=None):
        log=out/(name+'.log')
        with log.open('w') as f:
            r=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        text=log.read_text()
        commands.append(dict(name=name,argv=argv,returncode=r.returncode,
            expected_failure=marker,ended_utc=datetime.now(timezone.utc).isoformat()))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if marker is None:
            if r.returncode: raise RuntimeError(name+'\n'+text[-18000:])
        else:
            # Only the first assertion diagnostic can establish a negative control.
            first=next((l for l in text.splitlines() if 'Assertion failed' in l),'')
            diagnostic=first.partition('Assertion failed in ')[2].partition(': ')[2]
            if r.returncode==0 or diagnostic!=marker:
                raise RuntimeError(name+' wrong negative-control diagnostic\n'+text[-18000:])
        return text
    run('verilator_version',[args.verilator,'--version']);run('yosys_version',[args.yosys,'-V'])
    run('python_version',['python3','--version'])
    print(run('model',['python3','-m','unittest','discover','-s','tests','-p','test_tmr.py','-v']),flush=True)
    def compile_sim(name,root,ow,aw,marker=None):
        obj=out/(name+'_obj')
        run(name+'_compile',[args.verilator,'--binary','--timing','--Wall','-Wno-TIMESCALEMOD',
            '-CFLAGS','-O0','-j',str(args.jobs),'-I'+str(root/'rtl'),'--top-module','tmr_tb',
            '-GOPERAND_WIDTH='+str(ow),'-GACC_WIDTH='+str(aw),'--Mdir',str(obj),
            *[str(root/s) for s in ['rtl/mac_tmr_lane.sv','rtl/mac_tmr.sv',
                                  'rtl/mac_tmr_injectable.sv','tests/tmr_tb.sv']]])
        log=run(name+'_simulation',[str(obj/'Vtmr_tb'),'+trace='+str(out/(name+'_trace.csv'))],marker)
        if marker is None and 'PASS TMR' not in log: raise RuntimeError('missing success marker')
        if marker is None:
            rows=list(csv.reader((out/(name+'_trace.csv')).open()))
            schema=json.loads((out/'trace_schema.json').read_text())
            for row in rows:
                if row[0] not in ('pre','post','inject','control_inject') or len(row)!=1+len(schema[row[0]]):
                    raise RuntimeError('malformed raw trace '+repr(row))
                if row[0]=='inject' and (int(row[5],16)^int(row[6],16))!=int(row[4],16):
                    raise RuntimeError('archived injection acknowledgement mismatch')
            counts={kind:sum(row[0]==kind for row in rows) for kind in ('pre','post','inject','control_inject')}
            report=dict(re.findall(r'(cycles|storage_acks|control_acks|candidate_acks|voter_acks)=(\d+)',log))
            if counts!={'pre':int(report['cycles']),'post':int(report['cycles']),
                        'inject':int(report['storage_acks']),'control_inject':int(report['control_acks'])}:
                raise RuntimeError('trace/event count mismatch')
            candidate_acks = voter_acks = 0
            for row in rows:
                if row[0]!='pre': continue
                r = dict(zip(schema['pre'], row[1:]))
                if int(r['rst']): continue
                if int(r['busy']):
                    candidate_acks += sum(int(r[f'candidate_mask{i}'],16)!=0 for i in range(3))
                    voter_acks += int(r['candidate_voter_mask'],16)!=0
                elif not int(r['clear']):
                    voter_acks += int(r['state_voter_mask'],16)!=0
            if (candidate_acks,voter_acks)!=(int(report['candidate_acks']),int(report['voter_acks'])):
                raise RuntimeError('trace/sampled combinational acknowledgement count mismatch')
            counts.update(candidate_acks=candidate_acks,voter_acks=voter_acks,
                          control_coverage=check_control_trace(rows,schema,'pre'))
            (out/(name+'_trace_counts.json')).write_text(json.dumps(counts,indent=2)+'\n')
        print(log.splitlines()[0],flush=True)
    summary={}
    src=out/'sources'
    for ow,aw in [(8,24),(4,8),(2,4)]:
        name=f'w{ow}_a{aw}'
        compile_sim(name,src,ow,aw)
        rtl=[str(src/s) for s in ['rtl/mac_tmr_lane.sv','rtl/mac_tmr.sv']]
        run(name+'_lint',[args.verilator,'--lint-only','--Wall','-I'+str(src/'rtl'),
            '--top-module','mac_tmr','-GOPERAND_WIDTH='+str(ow),'-GACC_WIDTH='+str(aw),*rtl])
        prefix='read_verilog -sv -I'+str(src/'rtl')+' '+' '.join(rtl)+'; chparam -set OPERAND_WIDTH '+str(ow)+' -set ACC_WIDTH '+str(aw)+' mac_tmr; hierarchy -top mac_tmr; proc; opt; '
        run(name+'_synth',[args.yosys,'-Q','-T','-p',prefix+
            'write_json '+str(out/(name+'_coarse.json'))+'; synth -top mac_tmr -flatten; check -assert; stat; write_json '+
            str(out/(name+'_netlist.json'))+'; write_verilog -noattr '+str(out/(name+'_netlist.v'))])
        summary[name]=inspect_redundancy(json.loads((out/(name+'_netlist.json')).read_text()),
            json.loads((out/(name+'_coarse.json')).read_text()),ow,aw)
        (out/'redundancy.json').write_text(json.dumps(summary,indent=2)+'\n')
        obj=out/(name+'_gate_obj')
        run(name+'_gate_compile',[args.verilator,'--binary','--timing','-Wno-TIMESCALEMOD',
            '-j',str(args.jobs),'--top-module','tmr_gate_tb','-GOW='+str(ow),'-GAW='+str(aw),
            '--Mdir',str(obj),str(out/(name+'_netlist.v')),str(src/'tests/tmr_gate_tb.sv')])
        log=run(name+'_gate_simulation',[str(obj/'Vtmr_gate_tb'),
                                       '+trace='+str(out/(name+'_gate_trace.csv'))])
        if 'PASS TMR generic netlist' not in log: raise RuntimeError('gate success missing')
        rows=list(csv.reader((out/(name+'_gate_trace.csv')).open()))
        schema=json.loads((out/'trace_schema.json').read_text())
        for row in rows:
            if row[0] not in ('gate_pre','gate_post') or len(row)!=1+len(schema[row[0]]):
                raise RuntimeError('malformed gate trace '+repr(row))
        cycles=int(re.search(r'cycles=(\d+)',log)[1])
        if [r[0] for r in rows]!=['gate_pre','gate_post']*cycles:
            raise RuntimeError('gate trace/event count mismatch')
        if any(int(rows[2*i][1])!=i or int(rows[2*i+1][1])!=i+1 for i in range(cycles)):
            raise RuntimeError('gate trace continuity mismatch')
        (out/(name+'_gate_trace_counts.json')).write_text(json.dumps(dict(cycles=cycles,
            control_coverage=check_control_trace(rows,schema,'gate_pre')),indent=2)+'\n')
        print(log.splitlines()[0],flush=True)
    mutations=[
        ('no_feedback_repair','rtl/mac_tmr_lane.sv','else acc_state <= feedback;',
         'else if (busy) acc_state <= feedback;','TMR_RAW_STATE cycle=13132'),
        ('lane0_instead_of_vote','rtl/mac_tmr_datapath.vh',
         '(candidate0 & candidate1) | (candidate0 & candidate2) | (candidate1 & candidate2)',
         'candidate0','TMR_VOTER cycle=13131'),
        ('no_candidate_xor','rtl/mac_tmr_datapath.vh','lane_candidate0 ^ candidate_mask0',
         'lane_candidate0 ^ (candidate_mask0 & 0)','TMR_CANDIDATE_XOR cycle=13137'),
        ('no_storage_injection','tests/tmr_tb.sv',
         'dut.lane0.acc_state=dut.lane0.acc_state ^ AW\'(mask);',
         'dut.lane0.acc_state=dut.lane0.acc_state;','TMR_STORAGE_ACK'),
        ('saved_operand_not_captured','rtl/mac_tmr_lane.sv','saved_a <= operand_a;',
         'saved_a <= operand_a ^ {{(OPERAND_WIDTH-1){1\'b0}},1\'b1};','TMR_SAVED_OPERANDS cycle=3'),
        ('reset_retains_state','rtl/mac_tmr_lane.sv','if (rst) begin\n            acc_state <= 0;',
         'if (rst) begin\n            acc_state <= acc_state;','TMR_RAW_STATE cycle=10'),
    ]
    for name,path,before,after,marker in mutations:
        root=out/(name+'_sources');shutil.copytree(src,root)
        dest=root/path;text=dest.read_text()
        if text.count(before)!=1: raise RuntimeError('ambiguous mutation '+name)
        dest.write_text(text.replace(before,after))
        compile_sim(name,root,2,4,marker)
    # Shared reset and every lane both ignore reset+start in this isolated mutant.
    root=out/'reset_loses_to_start_sources';shutil.copytree(src,root)
    for path in ['rtl/mac_tmr_lane.sv','rtl/mac_tmr_datapath.vh']:
        dest=root/path;content=dest.read_text()
        if content.count('if (rst) begin')!=1: raise RuntimeError('ambiguous reset mutation')
        dest.write_text(content.replace('if (rst) begin','if (rst && !start) begin'))
    compile_sim('reset_loses_to_start',root,2,4,'TMR_SAVED_OPERANDS cycle=10')
    # The same priority defect must also be caught after actual generic synthesis.
    run('reset_loses_to_start_gate_synth',[args.yosys,'-Q','-T','-p',
        'read_verilog -sv -I'+str(root/'rtl')+' '+str(root/'rtl/mac_tmr_lane.sv')+' '+str(root/'rtl/mac_tmr.sv')+
        '; chparam -set OPERAND_WIDTH 2 -set ACC_WIDTH 4 mac_tmr; synth -top mac_tmr -flatten; check -assert; write_verilog -noattr '+
        str(out/'reset_loses_to_start_netlist.v')])
    obj=out/'reset_loses_to_start_gate_obj'
    run('reset_loses_to_start_gate_compile',[args.verilator,'--binary','--timing','-Wno-TIMESCALEMOD',
        '-j',str(args.jobs),'--top-module','tmr_gate_tb','-GOW=2','-GAW=4',
        '--Mdir',str(obj),str(out/'reset_loses_to_start_netlist.v'),str(src/'tests/tmr_gate_tb.sv')])
    run('reset_loses_to_start_gate_simulation',[str(obj/'Vtmr_gate_tb'),
        '+trace='+str(out/'reset_loses_to_start_gate_trace.csv')],'gate clean oracle cycle=4')
    # Exercise the reachability check with intact lanes but bypassed feedback.
    bypass=copy.deepcopy(json.loads((out/'w2_a4_netlist.json').read_text()))
    cells=bypass['modules']['mac_tmr']['cells']
    for lane in ('lane0','lane1','lane2'):
        cells[lane]['connections']['feedback']=cells['lane0']['connections']['candidate'][:]
    (out/'voter_bypass.json').write_text(json.dumps(bypass,indent=2)+'\n')
    try:
        inspect_redundancy(bypass,json.loads((out/'w2_a4_coarse.json').read_text()),2,4)
    except ValueError as e:
        if str(e)!='TMR_REDUNDANCY: voter missing lane influence': raise
        summary['voter_bypass_control']=dict(expected_rejection=str(e),
            evidence_kind='mutated netlist JSON auditor test, not synthesized hardware')
    else: raise RuntimeError('redundancy auditor accepted voter bypass')
    # Real unpreserved synthesis, not a fabricated missing-instance JSON fixture.
    root=out/'unpreserved_sources';shutil.copytree(src,root)
    for path in ['rtl/mac_tmr_lane.sv','rtl/mac_tmr_datapath.vh']:
        dest=root/path;dest.write_text(dest.read_text().replace('(* keep_hierarchy = "yes" *)',''))
    run('unpreserved_synth',[args.yosys,'-Q','-T','-p',
        'read_verilog -sv -I'+str(root/'rtl')+' '+str(root/'rtl/mac_tmr_lane.sv')+' '+str(root/'rtl/mac_tmr.sv')+
        '; chparam -set OPERAND_WIDTH 2 -set ACC_WIDTH 4 mac_tmr; synth -top mac_tmr -flatten; check -assert; stat; write_json '+str(out/'unpreserved.json')])
    unpreserved=json.loads((out/'unpreserved.json').read_text())
    try: inspect_redundancy(unpreserved,{},2,4)
    except ValueError as e:
        if str(e)!='TMR_REDUNDANCY: expected three lane instances': raise
        collapsed=sum(len(c['connections']['Q']) for c in unpreserved['modules']['mac_tmr']['cells'].values()
                      if 'DFF' in c['type'].upper())
        if collapsed>=3*(4+2*2): raise RuntimeError('merging control did not collapse storage')
        summary['unpreserved_control']=dict(expected_rejection=str(e),total_dff_bits=collapsed,
                                          protected_lane_dff_bits=24)
    else: raise RuntimeError('redundancy auditor accepted missing replicas')
    (out/'redundancy.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Hash all retained evidence, including negative sources and raw failed traces.
    artifact_hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob('*') if p.is_file() and '_obj/' not in str(p.relative_to(out))}
    (out/'artifact_sha256.json').write_text(json.dumps(artifact_hashes,indent=2)+'\n')
    print('PASS M5 model/RTL/negative controls/lint/generic synth inspection: '+str(out.relative_to(ROOT)))


if __name__=='__main__': main()
