#!/usr/bin/env python3
"""Run M1 checks, retaining every run (including failures) with source identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RTL = ['rtl/secded_encoder.sv', 'rtl/secded_decoder.sv', 'rtl/signed_residue7.sv',
       'rtl/mac_residue7_check.sv', 'rtl/mac_hybrid.sv', 'asic/rtl/tt_um_mac_sentry.sv']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=2, choices=[1, 2])
    parser.add_argument('--verilator', default='verilator')
    parser.add_argument('--yosys', default='yosys')
    args = parser.parse_args()
    os.chdir(ROOT)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    base = ROOT / 'build/asic_interface'
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run_', dir=base))
    print(f'Interface evidence: {out.relative_to(ROOT)}', flush=True)
    sources = RTL + ['rtl/secded_functions.vh', 'rtl/mac_hybrid_datapath.vh',
                     'tests/asic_interface_tb.sv', 'scripts/test_asic_interface.py', 'Makefile']
    hashes = {}
    for name in sources:
        data = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        dest = out / 'sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    (out / 'source_sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    commands = []

    def run(name, argv, failure_marker=None):
        start = datetime.now(timezone.utc).isoformat()
        with (out / f'{name}.log').open('w') as log:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, text=True)
        output = (out / f'{name}.log').read_text()
        commands.append(dict(name=name, argv=argv, started_utc=start, returncode=result.returncode,
                             expected_failure_marker=failure_marker))
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        if failure_marker is None:
            if result.returncode != 0:
                raise RuntimeError(f'{name} failed ({result.returncode}):\n{output[-12000:]}')
        elif result.returncode == 0 or failure_marker not in output:
            raise RuntimeError(f'{name} did not fail for {failure_marker!r}:\n{output}')
        return output

    try:
        run('verilator_version', [args.verilator, '--version'])
        run('yosys_version', [args.yosys, '-V'])
        run('lint', [args.verilator, '--lint-only', '--Wall', '-Irtl',
                     '--top-module', 'tt_um_mac_sentry', *RTL])
        run('compile', [args.verilator, '--binary', '--timing', '-j', str(args.jobs),
                        '--Wall', '-Wno-TIMESCALEMOD', '-Irtl', '--top-module',
                        'asic_interface_tb', '--Mdir', str(out / 'obj'), *RTL,
                        'tests/asic_interface_tb.sv'])
        runner = str(out / 'obj/Vasic_interface_tb')
        output = run('simulation', [runner])
        if 'PASS interface transactions=' not in output:
            raise RuntimeError('Simulation lacks terminal success marker')
        print(output, end='', flush=True)
        run('negative_bad_expected', [runner, '+bad_expected'],
            'result bytes expected 00000d got fffff4')
        run('negative_missing_fault', [runner, '+skip_fault'],
            'candidate XOR acknowledgement')
        # Isolated defective wrapper copies prove the protocol assertions can
        # reject realistic regressions. Never edit the production source.
        wrapper = (ROOT / RTL[-1]).read_text()
        mutations = [
            ('unmasked_output', "assign uo_out = reset ? 8'b0 : response;",
             'assign uo_out = response;', 'nonzero response masked by ena between edges'),
            ('illegal_launch', 'request && legal && command == 3',
             'request && command == 3', 'malformed loaded START must not launch core'),
            ('aliased_launch', 'request && legal && command == 3',
             "request && uio_in[7:5] == 0 && command[2:0] == 3",
             'malformed loaded START must not launch core'),
            ('busy_read_rejected', 'command >= 1 && command <= 4 && pending',
             'command >= 1 && command <= 8 && pending',
             'clean capture-edge read retains prior snapshot'),
            ('start_clears_protocol_error', 'pending <= 1;',
             'pending <= 1; protocol_error <= 0;', 'fault status expected 86 got 06'),
            ('early_result_read', '5: response <= result_snapshot[7:0];',
             '5: response <= core_done ? core_accumulator[7:0] : result_snapshot[7:0];',
             'clean capture-edge read retains prior snapshot'),
            ('early_retry_detail', 'saw_retried, retries};',
             'saw_retried, (retries | core_retries)};',
             'retry pin read op=8 N+2 expected=00 got=01'),
            ('pending_only_correction', 'saw_corrected <= saw_corrected | core_corrected;',
             'if (pending) saw_corrected <= saw_corrected | core_corrected;',
             'idle scrub STATUS expected=26'),
        ]
        # Restrict omissions to CLEAR; START independently resets these fields
        # and previously hid stale history. Each field gets its own counterexample.
        clear_branch = wrapper.split('                        4: begin\n', 1)[1].split(
            '                        5: response', 1)[0]
        for field, diagnostic in [
            ('last_error', 'fault recovery CLEAR STATUS kind=0 expected=00 got=10'),
            ('retries', 'fault recovery CLEAR DETAIL kind=0 expected=00 got=02'),
            ('saw_corrected', 'fault recovery CLEAR STATUS kind=2 expected=00 got=20'),
            ('saw_detected', 'fault recovery CLEAR STATUS kind=0 expected=00 got=40'),
            ('saw_retried', 'fault recovery CLEAR DETAIL kind=0 expected=00 got=04'),
        ]:
            assignment = f'                            {field} <= 0;\n'
            if clear_branch.count(assignment) != 1:
                raise RuntimeError(f'Missing unique CLEAR assignment for {field}')
            mutations.append((f'clear_keeps_{field}', clear_branch,
                              clear_branch.replace(assignment, ''), diagnostic))
        for name, old, new, diagnostic in mutations:
            if wrapper.count(old) != 1:
                raise RuntimeError(f'Mutation {name} must match exactly one source site')
            mutant_dir = out / 'mutants' / name
            mutant_dir.mkdir(parents=True)
            mutant = mutant_dir / 'tt_um_mac_sentry.sv'
            mutant.write_text(wrapper.replace(old, new))
            (mutant_dir / 'mutation.json').write_text(json.dumps(dict(
                original_sha256=hashes[RTL[-1]],
                mutant_sha256=hashlib.sha256(mutant.read_bytes()).hexdigest(),
                old=old, new=new, expected_diagnostic=diagnostic), indent=2)+'\n')
            run(f'mutant_{name}_compile', [args.verilator, '--binary', '--timing',
                '-j', str(args.jobs), '--Wall', '-Wno-TIMESCALEMOD', '-Irtl',
                '--top-module', 'asic_interface_tb', '--Mdir', str(mutant_dir / 'obj'),
                *RTL[:-1], str(mutant), 'tests/asic_interface_tb.sv'])
            run(f'mutant_{name}_simulation', [str(mutant_dir / 'obj/Vasic_interface_tb')], diagnostic)
        # Production sources only: no injectable module, testbench, force or debug IP.
        synth = (f'read_verilog -sv -Irtl {" ".join(RTL)}; '
                 'synth -top tt_um_mac_sentry; check -assert; '
                 f'write_json {out}/netlist.json; stat')
        run('synth', [args.yosys, '-Q', '-T', '-p', synth])
        netlist = json.loads((out / 'netlist.json').read_text())
        ports = netlist['modules']['tt_um_mac_sentry']['ports']
        expected = {'ui_in': ('input', 8), 'uo_out': ('output', 8),
                    'uio_in': ('input', 8), 'uio_out': ('output', 8),
                    'uio_oe': ('output', 8), 'ena': ('input', 1),
                    'clk': ('input', 1), 'rst_n': ('input', 1)}
        actual = {k: (v['direction'], len(v['bits'])) for k,v in ports.items()}
        if actual != expected:
            raise RuntimeError(f'Production top port mismatch: {actual}')
        for name in ('uio_out', 'uio_oe'):
            if ports[name]['bits'] != ['0'] * 8:
                raise RuntimeError(f'{name} is not tied to zero in synthesis')
        core_cells = netlist['modules']['tt_um_mac_sentry']['cells']
        if not any('mac_hybrid' in cell['type'] for cell in core_cells.values()):
            raise RuntimeError('Missing production protected hybrid in synthesized hierarchy')
        (out / 'result.json').write_text(json.dumps({'status': 'PASS',
            'scope': f'M1 RTL interface, strict lint, two harness controls, {len(mutations)} wrapper mutants, generic synthesis only'}, indent=2)+'\n')
        print('PASS M1 RTL interface, negative controls, lint and generic synthesis', flush=True)
    except Exception as exc:
        (out / 'result.json').write_text(json.dumps({'status': 'FAIL', 'reason': str(exc)}, indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
