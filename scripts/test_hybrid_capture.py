#!/usr/bin/env python3
"""R4 export -> CSV parse -> check -> compact archive, with preserved controls.

Fixtures come from the real M3 RTL plus deliberately malformed copies. Literal
expectations below do not call the analyzer/model to manufacture passing samples.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.hybrid_capture import SIGNALS, WIDTHS
from scripts.test_hybrid_board import SIM
from scripts.compact_fpga_results import verify_run



LEGACY_RUNS = (('unprotected', '2026-10-14_unprotected_zedboard_002'),
               ('secded', '2026-11-06_secded_saved_captures_001'))


def load_legacy_capture_fixtures(folder=None):
    """Mandatory hash-checked selected inputs; never fall back to ignored archives."""
    folder = Path(folder) if folder is not None else ROOT/'tests/fixtures/legacy_captures'
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('Missing/nonregular legacy fixture collection')
    collection = json.loads((folder/'manifest.json').read_text())
    if collection.get('schema') != 1 or set(collection.get('runs', {})) != {r for _, r in LEGACY_RUNS}:
        raise ValueError('Legacy fixture collection/run coverage differs')
    files = collection.get('files', {})
    required = set()
    paths = {}
    def checked(relative):
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts or rel.as_posix() != relative:
            raise ValueError('Unsafe legacy fixture path')
        path = folder/rel
        if not path.resolve().is_relative_to(folder.resolve()) or path.is_symlink() or not path.is_file():
            raise ValueError('Missing/nonregular legacy fixture: ' + relative)
        if any(p.is_symlink() for p in path.parents if p != folder and p.is_relative_to(folder)):
            raise ValueError('Symlink legacy fixture parent')
        item = files.get(relative, {})
        if path.stat().st_size != item.get('bytes') or hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256'):
            raise ValueError('Legacy fixture hash/size mismatch: ' + relative)
        required.add(relative)
        return path
    for variant, run_id in LEGACY_RUNS:
        original = json.loads(checked(run_id+'/manifest.json').read_text())
        captures = [r['archived'] for r in original['copied_files'] if r['archived'].endswith('.ila')]
        expected = 1 if variant == 'unprotected' else 7
        group = collection['runs'][run_id]
        if (original.get('variant') != variant or group.get('variant') != variant or
                group.get('capture_count') != expected or len(captures) != expected or len(set(captures)) != expected):
            raise ValueError('Legacy original capture coverage differs: ' + run_id)
        for relative in [*captures, 'tests.csv', 'mismatches.csv', 'capture_summary.csv', 'test_plan.csv']:
            if relative.endswith('.ila') and not relative.startswith('captures/'):
                raise ValueError('Legacy capture outside capture tree')
            path = checked(run_id+'/'+relative)
            if hashlib.sha256(path.read_bytes()).hexdigest() != original['file_sha256'].get(relative):
                raise ValueError('Legacy original manifest hash mismatch: ' + relative)
        paths[run_id] = folder/run_id
    if any(p.is_symlink() for p in folder.rglob('*')):
        raise ValueError('Symlink in legacy fixture collection')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
              if p.is_file() and p != folder/'README.md' and p != folder/'manifest.json'}
    if set(files) != required or actual != required:
        raise ValueError('Legacy fixture inventory has missing/unlisted files')
    return {'runs': paths, 'files': [folder/'manifest.json', *[folder/name for name in sorted(required)]]}


def export_csv(path, rows):
    with path.open('w',newline='') as f:
        w = csv.writer(f)
        # Hierarchical names and width/suffix decorations exercise real name parsing.
        w.writerow(['Sample in Buffer','Sample in Window','TRIGGER',
                    *[f'zedboard_hybrid_top/{s}_1[{width-1}:0]' if width>1 else f'zedboard_hybrid_top/{s}'
                      for s,width in zip(SIGNALS,WIDTHS)]])
        w.writerow(['Radix - UNSIGNED','UNSIGNED','UNSIGNED',*['HEX']*44])
        for row in rows:
            w.writerow([row['sample'],row['window_sample'],0,
                        *[f'{row[s]&((1<<width)-1):x}' for s,width in zip(SIGNALS,WIDTHS)]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=int,choices=[1,2],default=2)
    parser.add_argument('--verilator',default='verilator')
    args = parser.parse_args()
    legacy_fixtures = load_legacy_capture_fixtures()
    base = ROOT/'build/hybrid_capture'
    base.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run_',dir=base))
    print(f'R4 synthetic evidence: {out.relative_to(ROOT)}',flush=True)
    sources = SIM + ['rtl/mac_hybrid_datapath.vh','rtl/secded_functions.vh',
        'scripts/hybrid_capture.py','scripts/archive_fpga_run.py','scripts/compact_fpga_results.py',
        'scripts/test_hybrid_capture.py','scripts/test_hybrid_board.py','tests/test_git_read_only.py',
        'model/secded.py','model/mac.py','tests/hybrid_capture_tb.sv',
        'tests/fixtures/m7_secded_test_plan.csv','tests/fixtures/m7_secded_test_plan.provenance.json','Makefile']
    sources += [str(p.relative_to(ROOT)) for p in legacy_fixtures['files']]
    hashes = {}
    for name in sources:
        dest = out/'sources'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
        hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (out/'source_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    commands = []

    def run(name,argv,expect=0,env=None):
        record = dict(name=name,argv=argv,returncode=None,expected_returncode=expect,
                      started_utc=datetime.now(timezone.utc).isoformat(),status='RUNNING',
                      git_optional_locks_removed=env is not None and 'GIT_OPTIONAL_LOCKS' not in env)
        commands.append(record)
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        # Stream compiler/archive warnings to disk even if a supervisor interrupts us.
        try:
            with (out/(name+'.log')).open('w') as log_file:
                result = subprocess.run(argv,cwd=ROOT,stdout=log_file,stderr=subprocess.STDOUT,
                                        text=True,env=env)
            record.update(returncode=result.returncode,status='FINISHED')
        except BaseException as exc:
            record.update(status='INTERRUPTED_OR_ERROR',reason=repr(exc))
            raise
        finally:
            record['ended_utc'] = datetime.now(timezone.utc).isoformat()
            (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        output = (out/(name+'.log')).read_text()
        assert result.returncode == expect, (name,result.returncode,output[-5000:])
        return output

    run('python_version',[sys.executable,'--version'])
    run('git_read_only_tests',[sys.executable,'-m','unittest','discover','-s','tests',
                               '-p','test_git_read_only.py','-v'])
    run('verilator_version',[args.verilator,'--version'])
    root = out/'sources'
    run('compile',[args.verilator,'--binary','--timing','--Wall','-Wno-TIMESCALEMOD',
        '-Wno-DECLFILENAME','-CFLAGS','-O0','-j',str(args.jobs),'-I'+str(root/'rtl'),
        '--top-module','zedboard_hybrid_tb','--Mdir',str(out/'obj'),*[str(root/p) for p in SIM]])
    log = run('simulation',[str(out/'obj/Vzedboard_hybrid_tb'),'+trace='+str(out/'rtl_trace.csv')])
    assert 'PASS hybrid board H1-H15 cycles=8014 transactions=1505 storage=465 candidate=76 checker=2 commit=1' in log, log
    table = list(csv.DictReader((out/'rtl_trace.csv').open()))
    assert tuple(table[0])[1:] == SIGNALS
    rows = [dict(sample=int(r['cycle']),window_sample=int(r['cycle']),
                 **{s:int(r[s],16) for s in SIGNALS}) for r in table]
    extra_sim = SIM[:-1] + ['tests/hybrid_capture_tb.sv']
    run('counterexample_compile',[args.verilator,'--binary','--timing','--Wall',
        '-Wno-TIMESCALEMOD','-Wno-DECLFILENAME','-CFLAGS','-O0','-j',str(args.jobs),
        '-I'+str(root/'rtl'),'--top-module','hybrid_capture_tb','--Mdir',str(out/'counterexample_obj'),
        *[str(root/p) for p in extra_sim]])
    extra_log = run('counterexample_simulation',[str(out/'counterexample_obj/Vhybrid_capture_tb'),
                        '+trace='+str(out/'counterexample_trace.csv')])
    assert 'PASS R4 raw3/raw7 result13 versus clean12' in extra_log
    assert 'PASS R4 rejected scrub acc1/error2; tainted continuation13; reset/clear recovery12' in extra_log
    with (out/'counterexample_trace.csv').open() as f:
        extra_rows = [dict(sample=int(r['cycle']),window_sample=int(r['cycle']),
                          **{s:int(r[s],16) for s in SIGNALS}) for r in csv.DictReader(f)]
    fixtures = out/'fixtures'
    fixtures.mkdir()
    expectations = {}
    inputs = []

    def save(name,data,**expect):
        path = fixtures/(name+'.csv')
        export_csv(path,data)
        inputs.append(path)
        expectations[name] = expect
        return path

    def case(name,latency,outcome,status='PASS',acc=None,initial=None,**config):
        i = next(i for i,r in enumerate(rows) if r['start_pulse'] and r['ready']
                 and all(r[k]==(v & ((1<<WIDTHS[SIGNALS.index(k)])-1)) for k,v in config.items()))
        data = [dict(r) for r in rows[i-2:i+latency+2]]
        assert len(data)==latency+4
        # These expected outcomes/latencies are literal contract checks.
        expect = dict(sample=rows[i]['sample'],action='hybrid_'+outcome,status=status,
                      latency=latency,acc=acc,initial=initial)
        save(name,data,**expect)
        return data,expect

    # Preserve the whole real two-launch sequence, plus independent sibling controls.
    starts = [i for i,r in enumerate(extra_rows) if r['start_pulse'] and r['ready']]
    assert len(starts)==15
    literal = [('uncorrectable','PASS',0,True),
               ('unusable_source_valid','ESCAPE',13,False),
               ('clean','PASS',12,True),
               ('uncorrectable','PASS',0,True),
               ('unusable_source_valid','ESCAPE',12,False),
               ('silent_escape','ESCAPE',13,True),
               ('clean','PASS',12,True)]
    for n,(i,(outcome,status,acc,usable)) in enumerate(zip(starts[:7],literal)):
        data = extra_rows[:i+4] if n==1 else extra_rows[max(0,i-2):i+4]
        save('source_case_'+str(n),data,sample=extra_rows[i]['sample'],
             action='hybrid_'+outcome,status=status,acc=acc,initial=0,latency=2,
             source_usable=usable,clean_acc=12,attempts=1,retry_count=0,disabled_mask=(n==6))
    second = starts[1]
    assert extra_rows[second]['stored_codeword']==3
    assert extra_rows[second+1]['stored_codeword']==7
    assert extra_rows[second+1]['source_usable']==1
    assert extra_rows[second+2]['accumulator']==13
    assert extra_rows[second+2]['result_valid']==1
    # Literal independent expectations for review scenarios A/B and recovery.
    # Each capture retains the continuous prefix, including taint and recovery
    # edges; a usable re-encoded word must not erase earlier observed corruption.
    rejected_cases = [
        # n, outcome, status, final acc, initial acc, latency, initial taint
        (7,'rejected_state_escape','ESCAPE',1,0,4,False),
        (8,'tainted_source_valid','ESCAPE',13,1,2,True),
        (9,'clean','PASS',12,0,2,False),
        (10,'uncorrectable','PASS',0,0,2,False),
        (11,'rejected_state_escape','ESCAPE',1,0,4,True),
        (12,'tainted_source_valid','ESCAPE',13,1,2,True),
        (13,'tainted_state_rejected','ESCAPE',13,13,4,True),
        (14,'clean','PASS',12,0,2,False),
    ]
    for n,outcome,status,acc,initial,latency,tainted in rejected_cases:
        i=starts[n]
        save('rejection_case_'+str(n),extra_rows[:i+latency+2],
             sample=extra_rows[i]['sample'],action='hybrid_'+outcome,status=status,
             acc=acc,initial=initial,latency=latency,initial_tainted=tainted,
             terminal_tainted=n not in (9,14),
             fired=([['storage',0]] if n in (7,10,11) else []) +
                   ([['candidate',0],['candidate',1],['candidate',2]] if latency==4 else []))
    for n in (7,11):
        i=starts[n]
        assert extra_rows[i+1]['stored_codeword']==7
        assert extra_rows[i+2]['stored_codeword']==0x20000007
        assert extra_rows[i+2]['corrected']==1
        assert extra_rows[i+4]['error']==2 and extra_rows[i+4]['result_valid']==0
        assert extra_rows[i+4]['accumulator']==1
    assert extra_rows[starts[12]]['source_usable']==1
    assert extra_rows[starts[12]+2]['accumulator']==13
    # Raw3 -> raw7 is observable in the archive, not invented by the replay.
    clean,clean_exp = case('clean',2,'clean',acc=1870,initial=0,operand_a=34,operand_b=55)
    case('accumulate',2,'clean',acc=2020,initial=1870,operand_a=15,operand_b=10)
    retry,retry_exp = case('retry',3,'retried',acc=12,operand_a=3,operand_b=4,attempt_select=1,candidate_mask=1)
    exhausted,exhausted_exp = case('exhausted',4,'exhausted','UNFIRED',acc=0,operand_a=3,operand_b=4,attempt_select=7,candidate_mask=1,commit_mask=1)
    twice,twice_exp = case('two_retries',4,'retried',acc=12,operand_a=3,operand_b=4,attempt_select=3,candidate_mask=1)
    case('checker',3,'retried',acc=6,operand_a=2,operand_b=3,checker_mask=1)
    storage,storage_exp = case('storage_repair',3,'retried',acc=0,initial=1,operand_a=1,operand_b=-1,storage_mask=4)
    double,double_exp = case('uncorrectable',2,'uncorrectable','UNFIRED',operand_a=3,operand_b=4,storage_mask=3)
    escape1,escape1_exp = case('modulo_escape',2,'silent_escape','ESCAPE',acc=7,operand_a=0,operand_b=0,candidate_mask=7)
    escape2,escape2_exp = case('correlated_escape',2,'silent_escape','ESCAPE',acc=0,operand_a=1,operand_b=1,candidate_mask=1,checker_mask=1)
    escape3,escape3_exp = case('commit_escape',2,'silent_escape','ESCAPE',acc=0,operand_a=1,operand_b=1,commit_mask=1)
    case('unreached',2,'clean','UNFIRED',acc=12,operand_a=3,operand_b=4,attempt_select=6)
    case('zero_masks',2,'clean',acc=12,operand_a=3,operand_b=4,attempt_select=7,candidate_mask=0,checker_mask=0,commit_mask=0,storage_mask=0)
    # Select each of the six independently reset/nonzero abort setups by control edge.
    aborted = []
    for control in ('rst','abort_request'):
        for attempt in range(3):
            j = next(j for j,r in enumerate(rows) if r[control] and r['busy'] and r['retry_count']==attempt)
            i = j-attempt-1
            assert rows[i]['start_pulse'] and rows[i]['accumulator']==1
            data = [dict(r) for r in rows[i-2:j+6]]
            expect = dict(sample=rows[i]['sample'],
                          action='hybrid_reset_aborted' if control=='rst' else 'hybrid_abort_aborted',
                          status='UNFIRED',latency=attempt+2,acc=0,initial=1)
            save(f'{control}_attempt{attempt}',data,**expect)
            aborted.append((f'{control}_attempt{attempt}',data,expect))
    # Full trace covers wrap, live busy settings, clear/recovery, all storage singles/pairs.
    save('full_trace',rows,full=True)
    # Preserve standalone .ila ZIP input and extraction path as well as plain CSV.
    ila = fixtures/'clean_zip.ila'
    with ZipFile(ila,'x') as z:
        z.write(fixtures/'clean.csv','waveform.csv')
        z.writestr('probes.ltx','SYNTHETIC fixture; no programmed bitstream')
    inputs.append(ila); expectations['clean_zip']=clean_exp

    def mutate(name,base,expected,index,field,value):
        data = [dict(r) for r in base]
        original = data[index][field]
        assert original != value
        data[index][field]=value
        save(name,data,**dict(expected,status='FAIL',diagnostic=dict(
            sample=data[index]['sample'],signal=field,expected=original,observed=value)))

    for field,value in [('done',0),('result_valid',0),('error',2),('accumulator',1871),
                        ('stored_codeword',0),('retry_count',1)]:
        mutate('wrong_clean_'+field,clean,clean_exp,4,field,value)
    for field,value in [('inject_fired',0),('fired_attempt',1),('detected',0),('retried',0),('retry_count',2)]:
        mutate('wrong_retry_'+field,retry,retry_exp,4,field,value)
    for field,value in [('candidate_before',0),('candidate_after',12),('prediction_before',0),
                        ('prediction_after',0),('commit_before',0),('commit_after',0),
                        ('source_usable',0),('commit_eligible',1),('applied_candidate',0),
                        ('latched_a',9),('latched_b',9),('latched_attempts',0),('latched_candidate',0),
                        ('launched',0),('inject_fired',2)]:
        mutate('wrong_probe_'+field,retry,retry_exp,3,field,value)
    mutate('missing_start',clean,clean_exp,2,'start_pulse',0)
    mutate('early_done',retry,retry_exp,3,'done',1)
    mutate('stuck_done',clean,clean_exp,5,'done',1)
    mutate('missing_storage_ack',storage,storage_exp,3,'inject_fired',0)
    mutate('missing_storage_xor',storage,storage_exp,3,'stored_codeword',0x20000007)
    mutate('missing_repair',storage,storage_exp,4,'corrected',0)
    mutate('false_valid_double',double,double_exp,4,'result_valid',1)
    mutate('wrong_error_double',double,double_exp,4,'error',2)
    mutate('false_valid_exhausted',exhausted,exhausted_exp,6,'result_valid',1)
    mutate('wrong_error_exhausted',exhausted,exhausted_exp,6,'error',1)
    mutate('wrong_bound',exhausted,exhausted_exp,5,'retry_count',3)
    mutate('false_commit_ack',exhausted,exhausted_exp,4,'inject_fired',10)
    mutate('missing_commit_ack',escape3,escape3_exp,4,'inject_fired',0)
    mutate('missing_checker_ack',escape2,escape2_exp,4,'inject_fired',2)
    mutate('wrong_double_raw',double,double_exp,4,'stored_codeword',0)
    mutate('wrong_latched_storage',storage,storage_exp,3,'latched_storage',0)
    mutate('wrong_latched_checker',escape2,escape2_exp,3,'latched_checker',0)
    mutate('wrong_latched_commit',escape3,escape3_exp,3,'latched_commit',0)
    mutate('wrong_applied_checker',escape2,escape2_exp,3,'applied_checker',0)
    mutate('wrong_applied_commit',escape3,escape3_exp,3,'applied_commit',0)
    mutate('missing_checker_xor',escape2,escape2_exp,3,'prediction_after',1)
    mutate('missing_commit_xor',escape3,escape3_exp,3,'commit_after',1)
    # Identical acknowledgements on adjacent retries are separate sampled firings.
    mutate('missing_second_ack',twice,twice_exp,5,'inject_fired',0)
    mutate('late_second_ack',twice,twice_exp,6,'inject_fired',2)
    for name,data,expect in aborted:
        terminal = expect['latency']+2
        mutate('retained_word_'+name,data,expect,terminal,'stored_codeword',0x20000007)
        mutate('false_valid_'+name,data,expect,terminal,'result_valid',1)
        mutate('stale_ack_'+name,data,expect,terminal,'inject_fired',2)
    for name,data,expect in [('retry',retry,retry_exp),('exhausted',exhausted,exhausted_exp)]:
        for length in range(3,len(data)):
            save(f'{name}_cutoff_{length}',data[:length],**dict(expect,status='INCOMPLETE'))
    for length in (3,4,5):
        save('cutoff_'+str(length),clean[:length],**dict(clean_exp,status='INCOMPLETE'))
    for key in ('sample','window_sample'):
        data = [dict(r) for r in retry];data[3][key]+=8
        save('gap_'+key,data,**dict(retry_exp,status='INCOMPLETE',gap=key,
             diagnostic=dict(sample=data[3]['sample'],signal=key,expected=retry[3][key],observed=data[3][key])))
    save('busy_prefix',retry[3:],unknown=True)
    # Unknown history is not permission for impossible local status combinations.
    for field,value,signal,expected in [('error',3,'error','one of 0, 1, 2'),
                                      ('fired_attempt',3,'fired_attempt',2),
                                      ('retried',1,'detected',1)]:
        data = [dict(r) for r in retry[3:]]
        data[0][field]=value
        save('invalid_unknown_'+field,data,unknown=True,diagnostic=dict(
            sample=data[0]['sample'],signal=signal,expected=expected,observed=data[0][signal]))
    # A leading terminal has no known transaction, but done still requires valid or an error.
    data = [dict(r) for r in clean[4:]]
    data[0]['result_valid']=0
    save('invalid_leading_terminal',data,idle=True,diagnostic=dict(
        sample=data[0]['sample'],signal='result_valid',expected=1,observed=0))
    save('missing_launch_history',clean[2:],**dict(clean_exp,status='INCOMPLETE'))
    # Back-to-back sequence numbers do not allow different captures to be joined.
    save('split_begin',retry[:4],**dict(retry_exp,status='INCOMPLETE'))
    save('split_end',retry[4:],unknown=True)
    save('idle_only',rows[1:3],idle=True)
    i=next(i for i,r in enumerate(rows) if r['start_pulse'] and r['clear'] and not r['busy'] and not r['rst'])
    blocked=[dict(r) for r in rows[i-2:i+3]]
    blocked_exp=dict(sample=rows[i]['sample'],action='hybrid_ignored_start',status='BLOCKED',latency=1,acc=0)
    save('blocked_idle_clear',blocked,**blocked_exp)
    mutate('queued_blocked_start',blocked,blocked_exp,3,'busy',1)
    save('blocked_cutoff',blocked[:3],**dict(blocked_exp,status='INCOMPLETE'))
    # Parser controls are archived as analysis_error, never silently dropped.
    malformed = {
        'missing_probe': lambda t: [r[:-1] for r in t],
        'duplicate_probe': lambda t: [[*r,r[3]] for r in t],
        'short_row': lambda t: t[:3]+[t[3][:-1]]+t[4:],
        'unknown_value': lambda t: t[:3]+[t[3][:3]+['x']+t[3][4:]]+t[4:],
        'bad_radix': lambda t: [t[0],t[1][:3]+['FLOAT']+t[1][4:],*t[2:]],
        'out_of_range': lambda t: t[:3]+[t[3][:3]+['2']+t[3][4:]]+t[4:],
        'empty_capture': lambda t: t[:2],
        'no_radix': lambda t: [t[0],*t[2:]],
        'negative_index': lambda t: t[:3]+[['-1',*t[3][1:]]]+t[4:],
    }
    parser_errors = {
        'missing_probe': 'Expected one named probe for commit_eligible; found 0',
        'duplicate_probe': 'Expected one named probe for rst; found 2',
        'short_row': 'Malformed hybrid CSV row',
        'unknown_value': "invalid literal for int() with base 16: 'x'",
        'bad_radix': "Unsupported radix 'FLOAT' for rst",
        'out_of_range': 'Out-of-range rst in row 4',
        'empty_capture': 'Expected Vivado sample index columns',
        'no_radix': 'Expected a Vivado CSV header, radix row, and samples',
        'negative_index': 'Negative capture sample index',
    }
    for name,fn in malformed.items():
        path=fixtures/(name+'.csv')
        with (fixtures/'clean.csv').open() as f: t=list(csv.reader(f))
        with path.open('w',newline='') as f: csv.writer(f).writerows(fn(t))
        inputs.append(path); expectations[name]=dict(analysis_error=parser_errors[name])
    path = fixtures/'unterminated_quote.csv'
    path.write_text((fixtures/'clean.csv').read_text()+'"unterminated')
    inputs.append(path); expectations[path.stem]=dict(analysis_error='unexpected end of data')
    path = fixtures/'corrupt.ila'
    path.write_bytes(b'not a ZIP')
    inputs.append(path); expectations[path.stem]=dict(analysis_error_contains='Expected Vivado sample index columns',
                                                    warning_contains='cannot extract ILA: File is not a zip file')
    path = fixtures/'no_waveform.ila'
    with ZipFile(path,'x') as z: z.writestr('probes.ltx','SYNTHETIC missing waveform control')
    inputs.append(path); expectations[path.stem]=dict(analysis_error_contains='waveform.csv')
    # The ILA extraction path must retain negative diagnostics too, not just clean data.
    ila = fixtures/'missing_ack_zip.ila'
    with ZipFile(ila,'x') as z:
        z.write(fixtures/'wrong_retry_inject_fired.csv','waveform.csv')
    inputs.append(ila); expectations[ila.stem]=expectations['wrong_retry_inject_fired']
    (out/'expectations.json').write_text(json.dumps(expectations,indent=2)+'\n')
    before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (out/'fixture_sha256.json').write_text(json.dumps(before,indent=2)+'\n')
    project = out/'synthetic_project';project.mkdir()
    (project/'synthetic.xpr').write_text('<Project/>\n')
    # M3's explicit reports/LTX are at the project root, outside impl_1.
    # These labelled text files test byte preservation, never physical results.
    project_artifacts = {}
    for name in ('timing_summary.rpt','utilization.rpt','drc.rpt','hybrid.ltx','build_identity.txt'):
        data = f'SYNTHETIC preservation fixture: {name}; no physical evidence.\n'.encode()
        (project/name).write_bytes(data)
        project_artifacts[name] = data
    # methodology.rpt deliberately missing: omission must remain an archive warning.
    archive = out/'runs/synthetic'
    argv=[sys.executable,str(ROOT/'scripts/archive_fpga_run.py'),'--variant','hybrid',
          '--evidence-kind','synthetic','--project',str(project),'--output',str(archive),
          '--build-store',str(out/'builds')]
    for path in inputs: argv += ['--capture',str(path)]
    def git_metadata():
        return {str(p.relative_to(ROOT)):dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                            mode=p.stat().st_mode)
                for p in sorted((ROOT/'.git').rglob('*')) if p.is_file()}

    git_before = git_metadata()
    (out/'git_metadata_before.json').write_text(json.dumps(git_before,indent=2)+'\n')
    # Prove the helper is safe independently of the supervisor's environment guard.
    archive_env = dict(os.environ)
    archive_env.pop('GIT_OPTIONAL_LOCKS',None)
    run('archive',argv,env=archive_env)
    git_after = git_metadata()
    (out/'git_metadata_after.json').write_text(json.dumps(git_after,indent=2)+'\n')
    assert git_before == git_after, 'Archive provenance changed Git metadata'
    verify_run(archive)
    manifest=json.loads((archive/'manifest.json').read_text())
    assert manifest['evidence_kind']=='synthetic' and manifest['board_reported_by_user'] is None
    assert 'Missing M3 project artifact: methodology.rpt' in manifest['warnings']
    assert 'No bitstream found in selected implementation run' in manifest['warnings']
    storage = json.loads((archive/'storage.json').read_text())
    for name,data in project_artifacts.items():
        member = ('build/' if name.endswith('.ltx') else 'reports/')+'m3_'+name
        assert manifest['file_sha256'][member] == hashlib.sha256(data).hexdigest()
        with ZipFile(archive/storage['packed_files'][member]) as z:
            assert z.read(member) == data
        assert (project/name).read_bytes() == data
    def read(name):
        with (archive/name).open() as f: return list(csv.DictReader(f))
    events,failures,summaries=read('tests.csv'),read('mismatches.csv'),read('capture_summary.csv')
    assert len(summaries)==len(inputs)
    results=[]
    expected_fired = {
        'clean': [], 'retry': [['candidate',0]],
        'two_retries': [['candidate',0],['candidate',1]],
        'exhausted': [['candidate',0],['candidate',1],['candidate',2]],
        'storage_repair': [['storage',0],['candidate',0]],
        'uncorrectable': [['storage',0]], 'unreached': [], 'zero_masks': [],
        'checker': [['checker',0]], 'modulo_escape': [['candidate',0]],
        'correlated_escape': [['candidate',0],['checker',0]], 'commit_escape': [['commit',0]],
    }
    for n,path in enumerate(inputs,1):
        label=f'{n:03d}_{path.stem}'; expect=expectations[path.stem]
        summary=next(s for s in summaries if s['capture']==label)
        found=[e for e in events if e['capture']==label]
        errors=[e for e in failures if e['capture']==label]
        preserved=archive/'captures'/label/path.name
        assert hashlib.sha256(preserved.read_bytes()).hexdigest()==before[path.name]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before[path.name]
        if expect.get('analysis_error_contains'):
            assert expect['analysis_error_contains'] in summary['analysis_error'] and not found,(label,summary)
            if expect.get('warning_contains'):
                assert any(expect['warning_contains'] in w for w in manifest['warnings'])
        elif expect.get('analysis_error'):
            assert summary['analysis_error']==expect['analysis_error'] and not found, (label,summary,found)
        elif expect.get('full'):
            assert not errors, errors[:3]
            assert int(summary['checked_transitions'])==8013 and int(summary['unchecked_transitions'])==0
            assert int(summary['complete_mac_transactions'])==1498
            assert sum(e['status']=='ESCAPE' for e in found)==3
            assert sum(e['action']=='hybrid_uncorrectable' for e in found)==435
            assert sum(e['action']=='hybrid_retried' for e in found)==60
            assert sum(e['action'] in ('hybrid_reset_aborted','hybrid_abort_aborted') for e in found)==6
            macros=[e for e in found if e['action'].startswith('hybrid_') and e['action']!='hybrid_ignored_start']
            assert len(macros)==1505
            fired=[pair for e in macros for pair in json.loads(e['notes'])['fired']]
            assert [sum(pair[0]==site for pair in fired) for site in ('storage','candidate','checker','commit')]==[465,76,2,1]
            assert found[-1]['status']=='INCOMPLETE'  # Real trace stops at last terminal sample.
            observed={int(e['observed_acc']) for e in found if e['observed_acc']}
            assert {-8388608,8388607,8372224} <= observed
        elif expect.get('unknown'):
            assert int(summary['complete_mac_transactions'])==0
            assert any(e['action']=='hybrid_unknown_pending' and e['status']=='INCOMPLETE' for e in found)
        elif expect.get('idle'):
            assert int(summary['complete_mac_transactions'])==0
        else:
            e=next(e for e in found if int(e['sample'])==expect['sample'] and e['action'].startswith('hybrid_'))
            assert e['status']==expect['status'],(label,expect,e,errors[:4])
            if expect['status']!='INCOMPLETE':
                assert e['action']==expect['action'],(label,e)
                meta=json.loads(e['notes'])
                assert meta['terminal_sample']-expect['sample']==expect['latency'],(label,meta)
                if expect['status']!='FAIL':
                    assert not errors,(label,errors[:3])
                    if expect.get('acc') is not None: assert int(e['observed_acc'])==expect['acc'],(label,e)
                    if expect.get('initial') is not None: assert int(e['initial_acc'])==expect['initial']
                if path.stem in expected_fired:
                    assert meta['fired']==expected_fired[path.stem],(label,meta)
                if expect['action']=='hybrid_silent_escape':
                    assert int(e['observed_acc'])!=meta['clean_acc']
                if 'initial_tainted' in expect:
                    assert meta['initial_tainted']==expect['initial_tainted'],(label,meta)
                    assert meta['terminal_tainted']==expect['terminal_tainted'],(label,meta)
                    assert meta['clean_acc_usable']==(meta['initial_source_usable'] and not expect['initial_tainted'])
                    assert meta['fired']==expect['fired'] and not meta['unfired'],(label,meta)
                if 'source_usable' in expect:
                    assert meta['initial_source_usable']==expect['source_usable']
                    assert meta['clean_acc_usable']==expect['source_usable']
                    assert meta['clean_acc']==expect['clean_acc']
                    assert meta['fired']==[['storage',0]]
                    assert not meta['unfired']
                    assert meta['warnings']==(['Nonzero arithmetic mask with attempt_select=0; no arithmetic injection requested']
                                              if expect['disabled_mask'] else [])
                if expect['status']!='FAIL':
                    assert meta['attempts']==(expect['latency']-2 if 'aborted' in expect['action']
                                              else expect['latency']-1 if expect['action']!='hybrid_ignored_start' else 0),(label,meta)
                    if expect['action']!='hybrid_ignored_start':
                        assert meta['retry_count']==(0 if 'aborted' in expect['action'] else expect['latency']-2),(label,meta)
                if expect['status']=='UNFIRED': assert meta['unfired']
            if expect['status']=='INCOMPLETE':
                meta=json.loads(e['notes'])
                assert not meta['unfired']  # Missing samples cannot prove a request did not fire.
                if path.stem=='split_begin': assert meta['unresolved']==[['candidate',0]]
            if expect.get('gap'): assert any(e['signal']==expect['gap'] for e in errors)
        if 'diagnostic' in expect:
            diagnostic={k:str(v) for k,v in expect['diagnostic'].items()}
            assert any(all(err[k]==v for k,v in diagnostic.items()) for err in errors),(label,diagnostic,errors)
        results.append(dict(capture=label,expected=expect,result='matched expectation'))
    (out/'checks.json').write_text(json.dumps(results,indent=2)+'\n')
    # New-output refusal must not mutate the completed archive or original inputs.
    original_manifest=(archive/'manifest.json').read_bytes()
    refusal=run('refuse_overwrite',argv,expect=2)
    assert 'Output already exists' in refusal
    assert (archive/'manifest.json').read_bytes()==original_manifest
    verify_run(archive)
    run('verify_archive',[sys.executable,str(ROOT/'scripts/compact_fpga_results.py'),
                          '--root',str(out),'--verify-only'])
    # Run the old defective guard through the real CLI/archive path. The literal
    # R4 expectation must reject its false PASS for exactly the reviewed reason.
    mutant = out/'old_guard_source'
    shutil.copytree(root,mutant)
    for name in ('README.md','.gitignore'):
        shutil.copyfile(ROOT/name,mutant/name)
    target = mutant/'scripts/hybrid_capture.py'
    text = target.read_text()
    old = "if not m['initial_source_usable']:"
    assert text.count(old)==1
    target.write_text(text.replace(old, "if False:  # negative control: reviewed old guard").replace(
        "elif e['expected_acc'] != m['clean_acc']:",
        "elif m['initial_source_usable'] and e['expected_acc'] != m['clean_acc']:").replace(
        'elif tainted:', 'elif False:  # negative control: no trust guard'))
    mutant_archive = out/'runs/old_guard_negative_control'
    run('old_guard_archive',[sys.executable,str(mutant/'scripts/archive_fpga_run.py'),
        '--variant','hybrid','--evidence-kind','synthetic','--project',str(project),
        '--capture',str(fixtures/'source_case_1.csv'),'--output',str(mutant_archive),
        '--build-store',str(out/'builds')])
    verify_run(mutant_archive)
    with (mutant_archive/'tests.csv').open() as f:
        bad = next(e for e in csv.DictReader(f) if e['sample']==str(extra_rows[second]['sample']))
    assert bad['action']=='hybrid_clean' and bad['status']=='PASS' and bad['observed_acc']=='13',bad
    try:
        assert bad['status']=='ESCAPE', 'unusable-source valid result must be ESCAPE, observed PASS'
    except AssertionError as exc:
        (out/'negative_control.json').write_text(json.dumps(dict(
            status='rejected as intended',diagnostic=str(exc),observed=bad,
            mutant_sha256=hashlib.sha256(target.read_bytes()).hexdigest()),indent=2)+'\n')
    else:
        raise AssertionError('Old guard negative control was not rejected')
    # Independent mutation controls: rejection checking and carried trust must
    # each be necessary. Preserve actual false-PASS archives, not just messages.
    rejection_controls = []
    for name,n,old,new,action,acc in [
        ('no_rejection_check',7,"elif outcome in ('uncorrectable', 'exhausted'):",
         'elif False:','hybrid_exhausted','1'),
        ('no_carried_trust',12,'elif tainted:',
         'elif False:','hybrid_clean','13'),
    ]:
        mutant=out/(name+'_source')
        shutil.copytree(root,mutant)
        for filename in ('README.md','.gitignore'):
            shutil.copyfile(ROOT/filename,mutant/filename)
        target=mutant/'scripts/hybrid_capture.py'
        text=target.read_text()
        assert old in text
        target.write_text(text.replace(old,new))
        dest=out/'runs'/name
        run(name,[sys.executable,str(mutant/'scripts/archive_fpga_run.py'),
            '--variant','hybrid','--evidence-kind','synthetic','--project',str(project),
            '--capture',str(fixtures/f'rejection_case_{n}.csv'),'--output',str(dest),
            '--build-store',str(out/'builds')])
        verify_run(dest)
        with (dest/'tests.csv').open() as f:
            bad=next(e for e in csv.DictReader(f) if e['sample']==str(extra_rows[starts[n]]['sample']))
        assert (bad['action'],bad['status'],bad['observed_acc'])==(action,'PASS',acc),bad
        try:
            assert bad['status']=='ESCAPE', f'{name}: expected ESCAPE, observed PASS/acc{acc}'
        except AssertionError as exc:
            rejection_controls.append(dict(name=name,status='rejected as intended',
                diagnostic=str(exc),observed=bad,
                mutant_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        else:
            raise AssertionError('Rejection/trust negative control was not rejected')
    (out/'rejection_negative_controls.json').write_text(json.dumps(rejection_controls,indent=2)+'\n')
    # Historical inputs are READ ONLY. Reanalyze into new directories with the
    # legacy modes and demand unchanged historical fields and values. These are
    # compatibility checks of old evidence, not additional hardware experiments.
    compatibility = []
    for variant,run_id in LEGACY_RUNS:
        historical = legacy_fixtures['runs'][run_id]
        original = json.loads((historical/'manifest.json').read_text())
        capture_paths = [historical/x['archived'] for x in original['copied_files']
                         if x['archived'].endswith('.ila')]
        assert len(capture_paths)==(1 if variant=='unprotected' else 7)
        capture_hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in capture_paths}
        dest = out/'runs'/('legacy_'+variant)
        argv = [sys.executable,str(ROOT/'scripts/archive_fpga_run.py'),
                '--variant',variant,'--project',str(project),'--output',str(dest),
                '--build-store',str(out/'builds')]
        for path in capture_paths: argv += ['--capture',str(path)]
        run('legacy_'+variant,argv)
        verify_run(dest)
        outputs = {}
        for name in ('tests.csv','mismatches.csv','capture_summary.csv','test_plan.csv'):
            historical_bytes = (historical/name).read_bytes()
            expected = ((root/'tests/fixtures/m7_secded_test_plan.csv').read_bytes()
                        if variant=='secded' and name=='test_plan.csv' else historical_bytes)
            # The oldest baseline archive predates the accepted SECDED columns.
            # Preserve every old field/value; its later additive columns must be
            # empty. SECDED measured outputs are byte-exact. Its old test plan
            # predates five additions already in accepted M7: compare the frozen
            # M7 reference for that unperformed plan, never rewrite old evidence.
            if variant=='secded':
                assert (dest/name).read_bytes()==expected, (variant,name,'legacy semantics changed')
            else:
                with (historical/name).open() as f:
                    reader=csv.DictReader(f); fields=reader.fieldnames; old_rows=list(reader)
                with (dest/name).open() as f:
                    reader=csv.DictReader(f); new_fields=reader.fieldnames; new_rows=list(reader)
                assert set(fields)<=set(new_fields), (variant,name,'lost historical column')
                assert [{k:r[k] for k in fields} for r in new_rows]==old_rows, (variant,name,'legacy semantics changed')
                assert all(not r[k] for r in new_rows for k in set(new_fields)-set(fields)), (variant,name,'nonempty added column')
            outputs[name]=dict(historical_sha256=hashlib.sha256(historical_bytes).hexdigest(),
                               expected_sha256=hashlib.sha256(expected).hexdigest(),
                               reanalysis_sha256=hashlib.sha256((dest/name).read_bytes()).hexdigest())
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
                   for p,h in capture_hashes.items())
        compatibility.append(dict(variant=variant,historical_run=run_id,
            status='historical measurements unchanged; accepted M7 plan matched',capture_sha256=capture_hashes,
            output_sha256=outputs,evidence_kind='historical reanalysis with synthetic project; no new hardware'))
    (out/'legacy_compatibility.json').write_text(json.dumps(compatibility,indent=2)+'\n')
    parser_controls = sum('analysis_error' in e or 'analysis_error_contains' in e for e in expectations.values())
    print(f'PASS R4: {len(inputs)} CSV/ILA fixtures archived and verified; {parser_controls} parser/extraction controls; synthetic only',flush=True)


if __name__=='__main__':
    main()
