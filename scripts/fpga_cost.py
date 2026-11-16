#!/usr/bin/env python3
"""Matched, serial Vivado core OOC experiment with retained failures and reports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
VARIANTS=('unprotected','secded','hybrid','tmr')
REPORTS=('synth_utilization.rpt','synth_timing.rpt','routed_utilization.rpt',
         'routed_timing.rpt','route_status.rpt','drc.rpt','check_timing.rpt',
         'constraints.xdc','synth.dcp','routed.dcp','routed.v')

def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def timing_status(setup,hold,pulse):
    return 'closed' if min(setup,hold,pulse)>=0 else 'failure_to_close'

def inspect_clean_netlist(path):
    # Strip comments only: a tied-off port/net is still instrumentation at a
    # preserved hierarchy boundary. Also catch the TMR parent mask spelling.
    text=re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
    if re.search(r'fault_mask|candidate_mask',text,re.I):
        raise ValueError('PRODUCTION_INJECTION_LOGIC')

def group_members(pgid):
    """Linux host: retain state for all descendants in our private process group."""
    members=[]
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            # comm may contain spaces or parentheses. Fields after it start at 3.
            fields=path.read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid:
                members.append(dict(pid=int(path.parent.name),state=fields[0]))
        except (FileNotFoundError, ProcessLookupError):pass  # process exited during enumeration
    return members

def stop_group(proc):
    """Reap wrapper and verify no executable descendants before returning."""
    evidence=dict(pgid=proc.pid,before=group_members(proc.pid),signals=[])
    proc.poll()
    if proc.returncode is not None and not evidence['before']:
        evidence.update(after=[],quiescent=True,returncode=proc.returncode)
        return evidence
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try:
            os.killpg(proc.pid,sig)
            evidence['signals'].append(sig.name)
        except ProcessLookupError:pass
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            proc.poll()  # reap our direct child; init owns any orphan zombies
            members=group_members(proc.pid)
            if proc.returncode is not None and not any(m['state'] not in ('Z','X') for m in members):
                evidence.update(after=members,quiescent=True,returncode=proc.returncode)
                return evidence
            time.sleep(0.05)
    evidence.update(after=group_members(proc.pid),quiescent=False,returncode=proc.poll())
    return evidence

def execute_tool(cmd,folder,timeout=600):
    """Foreground, serial process-group supervision, including wrapper children."""
    save(folder/'command.json',cmd)
    proc=None
    result={}
    try:
        with (folder/'console.log').open('w') as f:
            proc=subprocess.Popen(cmd,cwd=folder,stdout=f,stderr=subprocess.STDOUT,
                                  start_new_session=True)
            try:
                result['returncode']=proc.wait(timeout=timeout)
                result['status']='completed' if proc.returncode==0 else 'tool_or_flow_failure'
            except subprocess.TimeoutExpired:
                result.update(status='infrastructure_timeout',reason=f'{timeout} second per-variant limit; logs retained')
            finally:
                cleanup=stop_group(proc)
                save(folder/'process_cleanup.json',cleanup)
                result['returncode']=proc.returncode
                if not cleanup['quiescent']:
                    result.update(status='infrastructure_failure',reason='PROCESS_GROUP_NOT_QUIESCENT',stop=True)
    except OSError as e:
        result.update(status='infrastructure_failure',reason=str(e),stop=proc is not None)
    return result

def process_controls(out):
    """Real process controls, not fabricated Vivado reports or physical results."""
    controls=[]
    root=out/'process_controls';root.mkdir()
    wrapper=root/'fake_vivado.py'
    wrapper.write_text('''import signal, subprocess, sys, time
from pathlib import Path
child=subprocess.Popen([sys.executable, '-c', "import time; time.sleep(60)"])
def stop(sig, frame):
    # Only reap: the supervisor must signal the child as part of the group.
    child.wait(timeout=3)
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
Path('child.pid').write_text(str(child.pid))
# Do not wait() here: a handler re-entering Popen.wait holds its internal lock.
time.sleep(60)
''')
    for name,cmd,expected,limit in (
        ('missing_tool',[str(root/'absent_vivado')],'infrastructure_failure',5),
        ('nonzero_exit',[sys.executable,'-c','raise SystemExit(17)'],'tool_or_flow_failure',5),
        ('child_timeout',[sys.executable,str(wrapper)],'infrastructure_timeout',2)):
        folder=root/name;folder.mkdir()
        result=execute_tool(cmd,folder,limit)
        save(folder/'result.json',result)
        controls.append(dict(name=name,expected=expected,observed=result['status']))
        if result.get('stop'):raise RuntimeError('PROCESS_GROUP_NOT_QUIESCENT')
    # This subsequent foreground tool checks the exact child's PID, proving the
    # timeout returns only after cleanup and cannot overlap the next variant.
    pid=int((root/'child_timeout/child.pid').read_text())
    folder=root/'next_variant';folder.mkdir()
    result=execute_tool([sys.executable,'-c',
        'import os,sys\ntry: os.kill(int(sys.argv[1]),0)\nexcept ProcessLookupError: sys.exit(0)\nsys.exit(19)',str(pid)],folder,5)
    save(folder/'result.json',result)
    controls.append(dict(name='no_descendant_overlap',child_pid=pid,expected='completed',observed=result['status']))
    if result.get('stop'):raise RuntimeError('PROCESS_GROUP_NOT_QUIESCENT')
    return controls

def inspect(folder):
    metrics=dict(line.split('\t',1) for line in (folder/'metrics.tsv').read_text().splitlines())
    if metrics.get('complete')!='1':raise ValueError('INCOMPLETE_REPORTS')
    if not {'tool_version','part','period_ns','dsp_policy','scope','lut','ff','dsp',
            'setup_slack_ns','hold_slack_ns'}<=metrics.keys():
        raise ValueError('MISSING_METRIC_FIELDS')
    if metrics.get('tool_version')!='2025.2.1':raise ValueError('UNPREPARED_TOOL_VERSION')
    for name in REPORTS:
        if not (folder/name).is_file() or not (folder/name).stat().st_size:raise ValueError('MISSING_REPORT '+name)
    inspect_clean_netlist(folder/'routed.v')
    if (metrics['part'],metrics['period_ns'],metrics['dsp_policy'],metrics['scope'])!=('xc7z020clg484-1','10.000','max_dsp_0','production_core_only_OOC'):
        raise ValueError('UNMATCHED_CONSTRAINTS')
    for key in ('lut','ff','dsp'):metrics[key]=int(metrics[key])
    if metrics['lut']<=0 or metrics['ff']<=0 or metrics['dsp']!=0:raise ValueError('RESOURCE_POLICY')
    # get_cells counts LUT primitives, not packed FPGA LUT resources. Cross-
    # hierarchy combining means these can differ substantially after route.
    top_rows=[line.strip().strip('|').split('|') for line in (folder/'routed_utilization.rpt').read_text().splitlines()
              if re.search(r'^\|\s*mac_(unprotected|secded|hybrid|tmr)\s*\|\s*\(top\)\s*\|',line)]
    if len(top_rows)!=1 or len(top_rows[0])!=10:raise ValueError('MISSING_UTILIZATION_TOP')
    row=[c.strip() for c in top_rows[0]]
    packed_luts,report_ffs,report_dsps=(int(row[i]) for i in (2,6,9))
    if not 0<packed_luts<=metrics['lut'] or report_ffs!=metrics['ff'] or report_dsps!=metrics['dsp']:
        raise ValueError('RESOURCE_REPORT_MISMATCH')
    metrics['lut_primitives']=metrics['lut']
    metrics['lut']=packed_luts
    for key in ('setup_slack_ns','hold_slack_ns'):
        metrics[key]=float(metrics[key])
        if not math.isfinite(metrics[key]):raise ValueError('INVALID_SLACK')
    timing=(folder/'routed_timing.rpt').read_text()
    table=re.search(r'^\s*WNS\(ns\)[^\n]*\n[^\n]*\n([^\n]+)',timing,re.M)
    if not table or len(table[1].split())!=12:raise ValueError('MISSING_TIMING_SUMMARY')
    values=table[1].split()
    setup,hold,pulse=(float(values[i]) for i in (0,4,8))
    if not all(math.isfinite(x) for x in (setup,hold,pulse)):raise ValueError('INVALID_SLACK')
    if abs(setup-metrics['setup_slack_ns'])>0.0005 or abs(hold-metrics['hold_slack_ns'])>0.0005:raise ValueError('TIMING_REPORT_MISMATCH')
    if min(int(values[i]) for i in (3,7,11))<=0:raise ValueError('MISSING_TIMING_ENDPOINTS')
    metrics['pulse_width_slack_ns']=pulse
    # Vivado's route summary is independent of a Tcl completion marker.
    route=(folder/'route_status.rpt').read_text()
    route_counts={}
    for label in ('routable nets','fully routed nets','nets with routing errors'):
        matches=re.findall(r'# of '+label+r'[.\s]*:\s*(\d+)',route,re.I)
        if len(matches)!=1:raise ValueError('ROUTE_REPORT_MISSING '+label)
        route_counts[label]=int(matches[0])
    if (route_counts['routable nets']<=0 or route_counts['routable nets']!=route_counts['fully routed nets']
            or route_counts['nets with routing errors']):raise ValueError('ROUTE_INCOMPLETE')
    metrics['route_counts']=route_counts
    check=(folder/'check_timing.rpt').read_text()
    # Require every section emitted by the prepared Vivado release.
    counts=re.findall(r'checking\s+(\w+)\s*\((\d+)\)',check,re.I)
    required={'no_clock','constant_clock','pulse_width_clock','unconstrained_internal_endpoints',
              'no_input_delay','no_output_delay','multiple_clock','generated_clocks','loops',
              'partial_input_delay','partial_output_delay','latch_loops'}
    if set(name for name,_ in counts)!=required:raise ValueError('MISSING_TIMING_CHECKS')
    metrics['timing_checks']={name:int(n) for name,n in counts}
    if any(metrics['timing_checks'].values()):raise ValueError('CONSTRAINT_OR_TIMING_CHECK_FAILURE')
    drc=(folder/'drc.rpt').read_text()
    if re.search(r'\|\s*(?:Error|Critical Warning)\s*\|',drc,re.I):raise ValueError('DRC_FAILURE')
    metrics['drc_warnings']=re.findall(r'^\|\s*(\S+)\s*\|\s*Warning\s*\|',drc,re.M)
    metrics['status']=timing_status(setup,hold,pulse)
    # OOC reports are not full-board DRC or bitstream acceptance. Keep every warning.
    metrics['drc_report']='drc.rpt (unmodified; OOC boundary, no bitstream sign-off)'
    return metrics

def inspect_lanes(folder):
    evidence={}
    for stage in ('synth','routed'):
        rows=[r.split('\t') for r in (folder/f'{stage}_lanes.tsv').read_text().splitlines()[1:]]
        if len(rows)!=12:raise ValueError('TMR_LANE_REPORT')
        seen=set();sites=set();physical_flops=0
        for lane,reg,count,names in rows:
            key=(lane,reg)
            if key in sites or lane not in ('lane0','lane1','lane2'):raise ValueError('TMR_LANE_ALIAS')
            sites.add(key)
            cells=names.split()
            if int(count)!=len(cells) or len(set(cells))!=len(cells) or seen.intersection(cells) or any(not c.startswith(lane+'/') for c in cells):raise ValueError('TMR_LANE_ALIAS')
            seen.update(cells)
            if reg=='arithmetic_luts':
                if not cells:raise ValueError('TMR_MISSING_ARITHMETIC')
            else:
                width={'acc_state':24,'saved_a':8,'saved_b':8}.get(reg)
                if width is None:raise ValueError('TMR_UNKNOWN_REGISTER')
                canonical={f'{lane}/{reg}_reg[{bit}]' for bit in range(width)}
                if not canonical<=set(cells):raise ValueError('TMR_MERGED_REGISTERS')
                for cell in cells:
                    match=re.fullmatch(re.escape(lane+'/'+reg)+r'_reg\[(\d+)\](?:__\d+|_replica(?:_\d+)?)?',cell)
                    if not match or int(match[1])>=width:raise ValueError('TMR_UNKNOWN_REGISTER')
                physical_flops+=len(cells)
        evidence[stage]=dict(distinct_cells=len(seen),logical_lane_register_bits=120,physical_lane_flops=physical_flops)
    return evidence

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--jobs',type=int,default=2)
    ap.add_argument('--vivado',default=os.environ.get('VIVADO', 'vivado'))
    ap.add_argument('--analyze-run',type=Path,help='Revalidate retained reports in a NEW evidence directory; does not rerun Vivado')
    ap.add_argument('--controls-only',action='store_true',help='Process/netlist controls only; no cost or implementation claim')
    ap.add_argument('--variants',nargs='+',choices=VARIANTS,default=list(VARIANTS),help='Diagnostic subset only; default acceptance target always runs all four')
    args=ap.parse_args()
    if not 1<=args.jobs<=2:ap.error('jobs must be 1 or 2')
    if len(set(args.variants))!=len(args.variants):ap.error('duplicate variants')
    parent=ROOT/'build/fpga_cost';parent.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='analysis_' if args.analyze_run else 'run_',dir=parent));print(out,flush=True)
    sources=[*ROOT.glob('rtl/*'),ROOT/'scripts/fpga_cost.py',ROOT/'scripts/fpga_cost.tcl',ROOT/'Makefile']
    hashes={}
    for src in sources:
        if src.is_file():
            rel=src.relative_to(ROOT);dst=out/'sources'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
            hashes[str(rel)]=hashlib.sha256(src.read_bytes()).hexdigest()
    save(out/'manifest.json',dict(created=datetime.now(timezone.utc).isoformat(),source_sha256=hashes,
        variants=args.variants,complete_comparison=not args.controls_only and set(args.variants)==set(VARIANTS),part='xc7z020clg484-1',period_ns=10.0,uncertainty_ns=0.2,
        input_output_delay_ns=dict(min=0.2,max=2.0),max_dsp=0,ow=8,aw=24,max_retries=2,
        scope='production core only; no debug IP or fault harness; no board pin placement',
        timing_policy='Measured negative slack is failure_to_close, not infrastructure failure. Target requires completed, validated reports, not timing sign-off.',
        workers=args.jobs,serial=True))
    controls=process_controls(out)
    # Available even when Vivado is absent. The real-report control below also
    # exercises inspect(), not merely this leaf validator.
    for name,netlist,expected in (
        ('clean_netlist','module core(input clk); endmodule\n','clean'),
        ('fault_port','module core(input candidate_fault_mask); endmodule\n','PRODUCTION_INJECTION_LOGIC'),
        ('fault_net','module core; wire commit_fault_mask; endmodule\n','PRODUCTION_INJECTION_LOGIC'),
        ('tmr_parent_mask','module core; wire candidate_mask0; endmodule\n','PRODUCTION_INJECTION_LOGIC')):
        path=out/(name+'.v');path.write_text(netlist)
        try:inspect_clean_netlist(path);observed='clean'
        except ValueError as e:observed=str(e)
        controls.append(dict(name=name,expected=expected,observed=observed))
    if args.controls_only:
        failures=[c['name'] for c in controls if c['observed']!=c['expected']]
        save(out/'controls.json',controls)
        save(out/'summary.json',dict(results=[],failures=failures,accepted=False,complete_comparison=False,kind='controls only'))
        save(out/'artifact_sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()})
        print(json.dumps(dict(evidence=str(out),failures=failures,kind='controls only')))
        return int(bool(failures))
    if args.analyze_run:
        original=args.analyze_run.resolve()
        original_manifest=json.loads((original/'manifest.json').read_text())
        original_hashes=json.loads((original/'artifact_sha256.json').read_text())
        # A parser repair may reuse actual tool results, never a changed design/flow.
        for name,digest in hashes.items():
            if name.startswith('rtl/') or name=='scripts/fpga_cost.tcl':
                if original_manifest['source_sha256'].get(name)!=digest:raise ValueError('REANALYSIS_SOURCE_MISMATCH '+name)
        save(out/'reanalysis.json',dict(input_run=str(original),kind='report reanalysis, no new implementation',
            input_manifest_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest()))
    results=[];stopped=False
    for variant in args.variants:
        folder=out/variant;folder.mkdir()
        cmd=[args.vivado,'-mode','batch','-nojournal','-log',str(folder/'vivado.log'),
             '-source',str(out/'sources/scripts/fpga_cost.tcl'),'-tclargs',str(out/'sources'),str(folder),variant,str(args.jobs)]
        save(folder/'command.json',cmd)
        r=dict(variant=variant)
        try:
            if stopped:
                r.update(status='infrastructure_failure',reason='NOT_LAUNCHED: preceding process group not quiescent')
            elif args.analyze_run:
                # All inputs are verified against the original immutable run inventory.
                for name in (*REPORTS,'metrics.tsv','result.json',*(['synth_lanes.tsv','routed_lanes.tsv'] if variant=='tmr' else [])):
                    src=original/variant/name
                    if hashlib.sha256(src.read_bytes()).hexdigest()!=original_hashes.get(variant+'/'+name):raise ValueError('INPUT_HASH_MISMATCH '+name)
                    if name!='result.json':shutil.copy2(src,folder/name)
                r['returncode']=json.loads((original/variant/'result.json').read_text())['returncode']
                save(folder/'command.json',dict(executed=False,reanalysis_of=str(original/variant)))
            else:
                r.update(execute_tool(cmd,folder))
                stopped=r.get('stop',False)
            if r.get('status') in ('infrastructure_failure','infrastructure_timeout'):
                pass
            elif r['returncode']:
                # No fabricated timing outcome when route reports do not exist.
                r['status']='tool_or_flow_failure'
                r['reason']=(folder/'failure.txt').read_text() if (folder/'failure.txt').exists() else 'Vivado did not complete; inspect console.log'
            else:
                r.update(inspect(folder))
                if variant=='tmr':r['redundancy']=inspect_lanes(folder)
        except OSError as e:r.update(status='infrastructure_failure',reason=str(e))
        except (ValueError,KeyError,TypeError,IndexError) as e:
            r.update(status='evidence_failure',reason=str(e))
        results.append(r);save(folder/'result.json',r);save(out/'results.json',results)
    versions={r.get('tool_version') for r in results if r.get('complete')=='1'}
    failures=[r['variant'] for r in results if r['status'] not in ('closed','failure_to_close')]
    failures.extend(c['name'] for c in controls if c['observed']!=c['expected'])
    if len(versions)!=1:failures.append('unmatched_or_missing_tool_versions')
    # Negative parser controls use actual reports when available, never fixture PPA.
    complete=next((r for r in results if r['status'] in ('closed','failure_to_close')),None)
    if complete:
        source=out/complete['variant']
        for name,old,new,expected in [('fabricated_slack','setup_slack_ns\t'+str(complete['setup_slack_ns']),None,'TIMING_REPORT_MISMATCH'),
                                      ('fabricated_ffs','ff\t'+str(complete['ff']),'ff\t'+str(complete['ff']+1),'RESOURCE_REPORT_MISMATCH'),
                                      ('dsp_policy','dsp_policy\tmax_dsp_0','dsp_policy\tmax_dsp_1','UNMATCHED_CONSTRAINTS'),
                                      ('missing_metric','part\txc7z020clg484-1\n','','MISSING_METRIC_FIELDS'),
                                      ('incomplete','complete\t1','complete\t0','INCOMPLETE_REPORTS')]:
            dst=out/name;dst.mkdir()
            for f in REPORTS: shutil.copyfile(source/f,dst/f)
            text=(source/'metrics.tsv').read_text()
            if name=='fabricated_slack':text=re.sub(r'setup_slack_ns\t[^\n]+','setup_slack_ns\t1000.125',text)
            else:text=text.replace(old,new)
            (dst/'metrics.tsv').write_text(text)
            try:observed=inspect(dst)['status']
            except ValueError as e:observed=str(e)
            controls.append(dict(name=name,expected=expected,observed=observed))
            if observed!=expected:failures.append(name)
        for name,filename,expected in (
            ('production_fault_net','routed.v','PRODUCTION_INJECTION_LOGIC'),
            ('route_incomplete','route_status.rpt','ROUTE_INCOMPLETE')):
            dst=out/name;dst.mkdir()
            for f in (*REPORTS,'metrics.tsv'):
                if f!=filename:shutil.copyfile(source/f,dst/f)
            text=(source/filename).read_text()
            if name=='production_fault_net':
                text+='\nmodule negative_control; wire candidate_fault_mask; endmodule\n'
            else:
                text,n=re.subn(r'(# of fully routed nets[.\s]*:\s*)\d+',r'\g<1>0',text,flags=re.I)
                if n!=1:raise ValueError('ROUTE_CONTROL_NOT_APPLIED')
            (dst/filename).write_text(text)
            try:observed=inspect(dst)['status']
            except ValueError as e:observed=str(e)
            controls.append(dict(name=name,expected=expected,observed=observed))
            if observed!=expected:failures.append(name)
        for name,slacks,expected in [('negative_setup',(-1,1,1),'failure_to_close'),
                                    ('negative_hold',(1,-1,1),'failure_to_close'),
                                    ('negative_pulse',(1,1,-1),'failure_to_close'),
                                    ('all_positive',(1,1,1),'closed')]:
            observed=timing_status(*slacks)
            controls.append(dict(name=name,kind='synthetic classification control, not PPA',slacks=slacks,expected=expected,observed=observed))
            if observed!=expected:failures.append(name)
    if any(r['variant']=='tmr' and r['status'] in ('closed','failure_to_close') for r in results):
        for name,expected in [('missing_canonical_bit','TMR_MERGED_REGISTERS'),('aliased_lane','TMR_LANE_ALIAS')]:
            dst=out/('negative_'+name);dst.mkdir()
            for stage in ('synth','routed'):shutil.copy2(out/'tmr'/f'{stage}_lanes.tsv',dst/f'{stage}_lanes.tsv')
            rows=(dst/'synth_lanes.tsv').read_text().splitlines()
            if name=='missing_canonical_bit':
                parts=rows[1].split('\t');cells=parts[3].split();cells.remove('lane0/acc_state_reg[0]')
                parts[2]=str(len(cells));parts[3]=' '.join(cells);rows[1]='\t'.join(parts)
            else:rows[5]=rows[5].replace('lane1/','lane0/')
            (dst/'synth_lanes.tsv').write_text('\n'.join(rows)+'\n')
            try:inspect_lanes(dst);observed='NOT_REJECTED'
            except ValueError as e:observed=str(e)
            controls.append(dict(name=name,expected=expected,observed=observed))
            if observed!=expected:failures.append(name)
    save(out/'controls.json',controls)
    save(out/'summary.json',dict(results=results,failures=failures,accepted=False,
        process_groups_quiescent=not stopped,complete_comparison=set(args.variants)==set(VARIANTS)))
    if stopped:
        # A process that resisted cleanup could still change reports later. Do
        # not advertise a stable inventory or start any more physical work.
        save(out/'artifact_hashes_withheld.json',dict(reason='PROCESS_GROUP_NOT_QUIESCENT; raw evidence may still change'))
    else:
        save(out/'artifact_sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(evidence=str(out),results=results,failures=failures)))
    return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
