#!/usr/bin/env python3
"""Bounded RTL mechanism pilot. No physical event distribution or rate inference."""
import argparse
from collections import Counter, defaultdict
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ('unprotected', 'secded', 'hybrid', 'tmr')
SITES = {0:'none',1:'accumulator_data',2:'saved_a',3:'saved_b',4:'busy_control',
         5:'ecc_check_or_multibit',6:'candidate',7:'predicted_residue',8:'postcheck_commit',9:'candidate_voter'}
RTL = ['mac_unprotected.sv','secded_encoder.sv','secded_decoder.sv','mac_secded.sv',
       'signed_residue7.sv','mac_residue7_check.sv','mac_hybrid_injectable.sv',
       'mac_tmr_lane.sv','mac_tmr_injectable.sv']

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')

def wrap(x):
    return (x+(1<<23)) % (1<<24) - (1<<23)

def code_bit(bit):
    return [p-1 for p in range(1,30) if p & (p-1)][bit]

def manifest(seed, per_site):
    rng = random.Random(seed)
    trials = []
    def add(v, site, mask=0, expected=None, stratum='calibration', **kw):
        row = dict(id=len(trials), variant=v, site=site, site_name=SITES[site], mask=mask,
                   lane=0, duration=1, a0=0,b0=0,a=1,b=1,seed=seed,stratum=stratum,
                   timing='after_accept_before_attempt0', observation_attempt_limit=6,
                   expected_class=expected)
        row.update(kw); trials.append(row)
    # Literal known outcomes independent of the classifier and protected models.
    for v in range(4):
        add(v,0,expected='clean')
        add(v,1,1<<(code_bit(0) if v in (1,2) else 0),
            expected='silent_escape' if v==0 else 'recovery')
        add(v,2,1,expected='recovery' if v==3 else 'silent_escape')
        add(v,6,1,expected='recovery' if v>=2 else 'silent_escape')
        add(v,4,1,expected='timeout')
    for v in (1,2):
        add(v,5,3,expected='detected_failure')
        add(v,5,7,expected='silent_escape') # actual SECDED triple-bit miscorrection
    add(2,6,1,duration=3,expected='detected_failure')
    add(2,6,7,a=0,b=0,expected='silent_escape')
    add(2,7,1,duration=3,expected='detected_failure')
    add(2,8,1,expected='silent_escape')
    add(3,9,1,expected='silent_escape')
    # Matched trials: same operands/bit/duration, one uniformly selected TMR lane.
    for site in (0,1,2,3,6):
        for pair in range(per_site):
            kw = dict(a0=rng.randrange(-128,128),b0=rng.randrange(-128,128),
                      a=rng.randrange(-128,128),b=rng.randrange(-128,128),
                      lane=rng.randrange(3),duration=rng.choice((1,3)) if site==6 else 1,
                      pair=f'{site}:{pair}',logical_bit=rng.randrange(8 if site in (2,3) else 24))
            for v in range(4):
                bit=code_bit(kw['logical_bit']) if site==1 and v in (1,2) else kw['logical_bit']
                add(v,site,0 if site==0 else 1<<bit,stratum='clean_sample' if site==0 else 'matched_functional',**kw)
    # No synthetic pooled "whole design" denominator. Protection populations differ.
    for v,site,width in ((1,5,6),(2,5,6),(2,7,3),(2,8,24),(3,9,24)):
        for _ in range(per_site):
            bit=rng.randrange(width)
            physical_bit=[0,1,3,7,15,29][bit] if site==5 else bit
            add(v,site,1<<physical_bit,stratum='protection',logical_bit=bit,
                a0=rng.randrange(-128,128),b0=rng.randrange(-128,128),
                a=rng.randrange(-128,128),b=rng.randrange(-128,128),
                duration=rng.choice((1,3)) if site==7 else 1)
    return trials

def read_csv(path):
    with path.open() as f:
        return [{k:(v if k=='edge' else int(v)) for k,v in r.items()} for r in csv.DictReader(f)]

def validate_manifest(trials, per_site):
    """Check the declared populations and matching independently of outcomes."""
    if len(trials)!=29+25*per_site or [t['id'] for t in trials]!=list(range(len(trials))):
        raise ValueError('MANIFEST_DENOMINATOR')
    if sum(t['stratum']=='calibration' for t in trials)!=29 or any(t['stratum']=='calibration' and not t['expected_class'] for t in trials):
        raise ValueError('MISSING_LITERAL_CALIBRATION')
    pairs=defaultdict(list); protection=Counter()
    data_positions=(2,4,5,6,8,9,10,11,12,13,14,16,17,18,19,20,21,22,23,24,25,26,27,28)
    for t in trials:
        if t['stratum'] in ('matched_functional','clean_sample'):pairs[t['pair']].append(t)
        elif t['stratum']=='protection':protection[t['variant'],t['site']]+=1
    if len(pairs)!=5*per_site or protection!={k:per_site for k in ((1,5),(2,5),(2,7),(2,8),(3,9))}:
        raise ValueError('MANIFEST_POPULATION')
    for group in pairs.values():
        if len(group)!=4 or {t['variant'] for t in group}!={0,1,2,3}:raise ValueError('UNMATCHED_VARIANTS')
        fields=('a0','b0','a','b','lane','duration','logical_bit','site','timing','seed')
        if len({tuple(t[k] for k in fields) for t in group})!=1:raise ValueError('UNMATCHED_WORKLOAD')
        for t in group:
            bit=t['logical_bit']
            if t['site']==1 and t['variant'] in (1,2):bit=data_positions[bit]
            if t['mask']!=(0 if t['site']==0 else 1<<bit):raise ValueError('UNMATCHED_LOGICAL_BIT')

def analyze(trial, trace, acks):
    """Fail closed on incomplete evidence; classify against intended arithmetic."""
    pre = [r for r in trace if r['edge']=='pre']
    post = [r for r in trace if r['edge']=='post']
    if not pre or len(pre)!=len(post) or [r['cycle'] for r in pre]!=list(range(len(pre))) or [r['cycle'] for r in post]!=list(range(len(pre))):
        raise ValueError('TRACE_CONTINUITY')
    if any(a['phase']!=b['phase'] for a,b in zip(pre,post)):
        raise ValueError('TRACE_PHASE')
    if post[-1]['phase']!=3 or post[-1]['busy'] or post[-1]['done'] or post[-1]['valid']:
        raise ValueError('CAPTURE_CUTOFF')
    if any(r['valid'] and not r['done'] or r['error'] and not r['done'] for r in post):
        raise ValueError('STATUS_WITHOUT_COMPLETION')
    seed_value=wrap(trial['a0']*trial['b0'])
    expected=wrap(seed_value+trial['a']*trial['b'])
    warm=[r for r in post if r['phase']==0 and r['done']]
    if len(warm)!=1 or not warm[0]['valid'] or warm[0]['error'] or warm[0]['acc']!=seed_value:
        raise ValueError('WARMUP_ORACLE')
    recovery=[r for r in post if r['phase']==3 and r['done']]
    if len(recovery)!=1 or not recovery[0]['valid'] or recovery[0]['error'] or recovery[0]['acc']!=1:
        raise ValueError('RESET_RECOVERY_ORACLE')
    target=[r for r in post if r['phase']==1]
    terminal=[r for r in target if r['done']]
    launches=[r for r in pre if r['phase']==1 and r['start'] and r['ready'] and not r['rst']]
    if len(launches)!=1 or len(terminal)>1:
        raise ValueError('TRANSACTION_BOUNDARY')
    launch=launches[0]['cycle']
    latency=terminal[0]['cycle']-launch if terminal else None
    if terminal and not 1<=latency<=(3 if trial['variant']==2 else 1):
        raise ValueError('RETRY_BOUND')
    if terminal and target[-1]['cycle']!=terminal[0]['cycle']+2:
        raise ValueError('TERMINAL_TAIL')
    if not terminal and len(target)!=9:raise ValueError('TIMEOUT_WINDOW')
    required=0 if trial['site']==0 else (min(trial['duration'],latency or 6) if trial['site']>=6 else 1)
    ack_ok=len(acks)==required
    for n,a in enumerate(acks):
        edge=pre[a['cycle']] if 0<=a['cycle']<len(pre) else None
        ack_ok &= (a['before']^a['after'])==trial['mask']==a['mask'] and a['mask']!=0
        ack_ok &= a['cycle']==launch+1+n and a['attempt']==n and a['rst']==0
        ack_ok &= bool(edge and edge['phase']==1 and edge['rst']==0)
        ack_ok &= a['busy']==(0 if trial['site']==4 else 1)
        if trial['site']==4:
            ack_ok &= a['before']==1 and a['after']==0
        if trial['site'] in (1,5) and edge:
            field='raw'+str(trial['lane']) if trial['variant']==3 else 'raw0'
            ack_ok &= edge[field]==a['after']
        if trial['site']==8 and edge:
            ack_ok &= edge['arithmetic_ok']==1
    successor=[r for r in post if r['phase']==2 and r['done']]
    if len(successor)>1:
        raise ValueError('SUCCESSOR_BOUNDARY')
    for completion in terminal+successor:
        if completion['valid'] and completion['error'] or not completion['valid'] and not completion['error']:
            raise ValueError('TERMINAL_PROTOCOL')
    successor_base=expected if terminal and terminal[0]['valid'] else seed_value
    escaped=any(r['valid'] and r['acc']!=expected for r in terminal) or any(
        r['valid'] and r['acc']!=wrap(successor_base-6) for r in successor)
    alarm=any(r['alarm'] or r['error'] for r in trace if r['phase'] in (1,2))
    result=dict(expected=expected,observed=terminal[0]['acc'] if terminal else None,
                latency=latency,requested=int(trial['site']!=0),acknowledged=int(ack_ok and required>0),
                ack_events=len(acks),required_ack_events=required,alarm=alarm,
                successor=successor,terminal=terminal)
    if not ack_ok:
        result['classification']='unacknowledged'
    elif escaped:
        # An alarm/rejection/timeout must not hide a later accepted wrong result.
        result['classification']='silent_escape'
    elif not terminal:
        # Six full attempt edges plus two idle observations are retained.
        result['classification']='timeout'
    else:
        t=terminal[0]
        if trial['site']==0 and (alarm or not t['valid']):
            result['classification']='false_alarm'
        elif not t['valid']:
            result['classification']='detected_failure'
        elif len(successor)!=1:
            result['classification']='timeout'
        elif not successor[0]['valid'] or successor[0]['error']:
            result['classification']='detected_failure' if trial['site'] else 'false_alarm'
        else:
            result['classification']='recovery' if trial['site'] else 'clean'
    return result

def summarize(trials, results):
    if len(trials)!=len(results):raise ValueError('DENOMINATOR_MISMATCH')
    groups=defaultdict(list)
    for t,r in zip(trials,results):
        groups[f"{t['stratum']}/{VARIANTS[t['variant']]}/{t['site_name']}"].append(r)
    return {key:dict(planned=len(rows),requested=sum(r.get('requested',0) for r in rows),
                     acknowledged=sum(r.get('acknowledged',0) for r in rows),
                     outcomes=dict(Counter(r['classification'] for r in rows))) for key,rows in sorted(groups.items())}

def trial_failure(trial, result):
    """Fault outcomes are measurements; clean controls and calibration are gates."""
    expected = trial['expected_class'] or ('clean' if trial['site']==0 else None)
    observed = result['classification']
    if observed in ('unacknowledged', 'infrastructure_or_harness_failure') or expected and observed!=expected:
        return dict(id=trial['id'], expected=expected, observed=observed)
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--jobs',type=int,default=2);ap.add_argument('--verilator',default='verilator')
    ap.add_argument('--seed',type=int,default=20261107);ap.add_argument('--per-site',type=int,default=16)
    args=ap.parse_args()
    if not 1<=args.jobs<=2 or not 1<=args.per_site<=64: ap.error('jobs 1..2; per-site 1..64')
    parent=ROOT/'build/pilot';parent.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run_',dir=parent));print(out,flush=True)
    sources=[*ROOT.glob('rtl/*'),ROOT/'tests/pilot_tb.sv',ROOT/'scripts/pilot_campaign.py',ROOT/'Makefile']
    hashes={}
    for p in sources:
        if p.is_file():
            rel=p.relative_to(ROOT);dst=out/'sources'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
            hashes[str(rel)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(out/'source_sha256.json',hashes)
    trials=manifest(args.seed,args.per_site)
    write_json(out/'manifest.json',dict(schema=1,created=datetime.now(timezone.utc).isoformat(),seed=args.seed,python_version=sys.version,
        per_site=args.per_site,widths=[8,24],max_retries=2,kind='RTL abstract seeded pilot; calibration separate',
        distribution='stratified uniform logical bit and signed operand draws; uniform TMR lane; single upset or 1/3 attempt transient',
        trials=trials))
    cmd=[args.verilator,'--binary','--timing','-j',str(args.jobs),'-Wno-TIMESCALEMOD','--top-module','pilot_tb',
         '-I'+str(out/'sources/rtl'),'--Mdir',str(out/'obj'),*[str(out/'sources/rtl'/s) for s in RTL],str(out/'sources/tests/pilot_tb.sv')]
    write_json(out/'compile_command.json',cmd)
    compile_error=None
    try:
        validate_manifest(trials,args.per_site)
        (out/'version.txt').write_text(subprocess.check_output([args.verilator,'--version'],text=True,timeout=10))
        with (out/'compile.log').open('w') as f:
            code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=180).returncode
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        code=1;compile_error=str(e)
    write_json(out/'compile_exit.json',dict(returncode=code,reason=compile_error))
    results=[]; failures=[]
    def run_trial(t,folder,extra=()):
        folder.mkdir(); command=[str(out/'obj/Vpilot_tb'),*[f'+{k}={t[k]}' for k in ('variant','site','mask','lane','duration','a0','b0','a','b')],
            '+trace='+str(folder/'trace.csv'),'+ack='+str(folder/'ack.csv'),*extra]
        write_json(folder/'command.json',command)
        try:
            with (folder/'simulation.log').open('w') as f:
                proc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=10)
        except (OSError,subprocess.TimeoutExpired) as e:
            write_json(folder/'exit.json',dict(returncode=None,reason=str(e)))
            raise
        write_json(folder/'exit.json',dict(returncode=proc.returncode))
        if proc.returncode: raise ValueError('SIMULATION_FAILED')
        trace=read_csv(folder/'trace.csv');acks=read_csv(folder/'ack.csv')
        return analyze(t,trace,acks),trace,acks
    for t in trials:
        try:
            if code: raise ValueError('COMPILATION_FAILED: '+str(compile_error or code))
            r,_,_=run_trial(t,out/f"trial_{t['id']:04d}")
            failure=trial_failure(t,r)
            if failure:failures.append(failure)
        except (ValueError,KeyError,TypeError,csv.Error,OSError,subprocess.TimeoutExpired) as e:
            r=dict(classification='infrastructure_or_harness_failure',reason=str(e),requested=int(t['site']!=0),acknowledged=0)
            failures.append(dict(id=t['id'],reason=str(e)))
        r['id']=t['id'];results.append(r)
        with (out/'trials.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
    # Actual non-fired RTL control must be rejected, even if its result is correct.
    controls=[]
    if not code:
        try:
            clean_sample=next(t for t in trials if t['stratum']=='clean_sample')
            for outcome in ('false_alarm','silent_escape','timeout','detected_failure'):
                observed=trial_failure(clean_sample,dict(classification=outcome))
                expected=dict(id=clean_sample['id'],expected='clean',observed=outcome)
                if observed!=expected:raise ValueError('CLEAN_SAMPLE_GATE_'+outcome)
                controls.append(dict(name='clean_sample_gate_'+outcome,expected=expected,observed=observed))
            if trial_failure(clean_sample,dict(classification='clean')) is not None:
                raise ValueError('CLEAN_SAMPLE_GATE_REJECTS_CLEAN')
            for name,field,expected in [('unmatched_workload','a','UNMATCHED_WORKLOAD'),('unmatched_bit','mask','UNMATCHED_LOGICAL_BIT')]:
                damaged=copy.deepcopy(trials)
                # First sampled fault tuple, one implementation only.
                row=next(t for t in damaged if t['stratum']=='matched_functional')
                row[field]^=1
                write_json(out/f'negative_{name}.json',damaged)
                try:validate_manifest(damaged,args.per_site)
                except ValueError as e:
                    if str(e)!=expected:raise ValueError('WRONG_MANIFEST_REJECTION '+str(e))
                    controls.append(dict(name=name,rejected=str(e)))
                else:raise ValueError('MANIFEST_CONTROL_ESCAPED')
            for index in (1,3,6,8,11,13,16,18):
                t=trials[index];r,_,_=run_trial(t,out/f'negative_nonfired_{index}',('+disable_injection',))
                if r['classification']!='unacknowledged':raise ValueError('NONFIRED_CONTROL_ESCAPED')
                controls.append(dict(name=f'nonfired_{index}',result=r))
            # Mutate retained real observations; each classifier control is archived.
            clean=trials[0];tr=read_csv(out/'trial_0000/trace.csv');ack=[]
            variants=[]
            wrong=copy.deepcopy(tr)
            for row in wrong:
                if row['edge']=='post' and row['phase']==1 and row['valid']:row['acc']+=1
            variants.append(('wrong_valid','silent_escape',wrong,ack))
            false=copy.deepcopy(tr)
            for row in false:
                if row['phase']==1 and row['valid']:row['alarm']=1
            variants.append(('false_alarm','false_alarm',false,ack))
            latent=copy.deepcopy(tr)
            for row in latent:
                if row['phase']==2 and row['valid']:row['acc']+=1
            variants.append(('latent_wrong_valid','silent_escape',latent,ack))
            rejected_then_wrong=copy.deepcopy(tr)
            for row in rejected_then_wrong:
                if row['phase']==1 and row['valid']:
                    row['valid']=0;row['error']=1
            variants.append(('rejection_then_wrong_valid','silent_escape',rejected_then_wrong,ack))
            for name,expected,rows,acks in variants:
                write_json(out/f'negative_{name}.json',dict(trial=clean,trace=rows,acks=acks))
                observed=analyze(clean,rows,acks)['classification']
                if observed!=expected:raise ValueError('CLASSIFICATION_CONTROL_'+name)
                controls.append(dict(name=name,expected=expected,observed=observed))
            for name,rows,expected in [('missing_tail',[r for r in tr if r['phase']!=3],'CAPTURE_CUTOFF'),('gap',tr[2:],'TRACE_CONTINUITY')]:
                write_json(out/f'negative_{name}.json',dict(trial=clean,trace=rows,acks=[]))
                try:analyze(clean,rows,[])
                except ValueError as e:
                    if str(e)!=expected:raise ValueError('WRONG_TRACE_REJECTION '+str(e))
                    controls.append(dict(name=name,rejected=str(e)))
                else:raise ValueError('INCOMPLETE_CONTROL_ESCAPED')
            injected=trials[1];tr=read_csv(out/'trial_0001/trace.csv');acks=read_csv(out/'trial_0001/ack.csv')
            for name in ('missing_ack','wrong_delta','wrong_mask','wrong_edge'):
                damaged=copy.deepcopy(acks)
                if name=='missing_ack':damaged=[]
                elif name=='wrong_delta':damaged[0]['after']=damaged[0]['before']
                elif name=='wrong_mask':damaged[0]['mask']^=1
                else:damaged[0]['cycle']+=1
                write_json(out/f'negative_{name}.json',dict(trial=injected,trace=tr,acks=damaged))
                observed=analyze(injected,tr,damaged)['classification']
                if observed!='unacknowledged':raise ValueError('ACK_CONTROL_'+name)
                controls.append(dict(name=name,observed=observed))
            # Real missing-tool control proves infrastructure failures retain the
            # entire planned denominator. The child skips controls after failure.
            command=[sys.executable,str(ROOT/'scripts/pilot_campaign.py'),'--jobs','1',
                     '--per-site','1','--verilator',str(out/'intentionally_absent_verilator')]
            proc=subprocess.run(command,capture_output=True,text=True,timeout=20)
            (out/'negative_missing_tool.log').write_text(proc.stdout+proc.stderr)
            child=json.loads(proc.stdout.splitlines()[-1]);child_path=Path(child['evidence'])
            retained=[json.loads(line) for line in (child_path/'trials.jsonl').read_text().splitlines()]
            expected_count=54 # 29 literal calibrations + 25 one-per-site samples
            if proc.returncode!=1 or len(retained)!=expected_count or any(r['classification']!='infrastructure_or_harness_failure' or 'intentionally_absent_verilator' not in r.get('reason','') for r in retained):
                raise ValueError('FAILED_DENOMINATOR_CONTROL')
            controls.append(dict(name='missing_tool_denominator',command=command,returncode=proc.returncode,
                                 evidence=str(child_path),planned=expected_count,retained=len(retained)))
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:failures.append(dict(control_failure=str(e)))
    write_json(out/'controls.json',controls)
    write_json(out/'summary.json',dict(planned=len(trials),recorded=len(results),groups=summarize(trials,results),failures=failures))
    write_json(out/'artifact_sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and 'obj' not in p.parts})
    print(json.dumps(dict(evidence=str(out),trials=len(trials),failures=failures)))
    return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
