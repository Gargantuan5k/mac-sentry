#!/usr/bin/env python3
"""M3 local simulation + portable synthesis; preserve each run and its controls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ['rtl/secded_encoder.sv', 'rtl/secded_decoder.sv', 'rtl/signed_residue7.sv',
        'rtl/mac_residue7_check.sv', 'fpga/zedboard/mac_hybrid_board_core.sv',
        'fpga/zedboard/hybrid_fault_sequencer.sv']
SIM = CORE + ['fpga/zedboard/zedboard_hybrid_top.sv', 'tests/hybrid_debug_models.sv',
              'tests/zedboard_hybrid_tb.sv']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    p.add_argument('--verilator', default='verilator')
    p.add_argument('--yosys', default='yosys')
    args = p.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    base = ROOT / 'build/hybrid_board'
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run_', dir=base))
    print(f'M3 evidence: {out.relative_to(ROOT)}', flush=True)
    sources = SIM + ['rtl/mac_hybrid_datapath.vh', 'rtl/secded_functions.vh',
                     'scripts/test_hybrid_board.py', 'scripts/create_hybrid_project.tcl',
                     'tests/hybrid_project_check.tcl',
                     'fpga/zedboard/zedboard_100mhz.xdc', 'Makefile']
    hashes = {}
    for name in sources:
        content = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(content).hexdigest()
        dest = out / 'sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    (out / 'source_sha256.json').write_text(json.dumps(hashes, indent=2)+'\n')
    commands = []

    def run(name, argv, marker=None):
        with (out / f'{name}.log').open('w') as log:
            result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        text = (out / f'{name}.log').read_text()
        commands.append(dict(name=name, argv=argv, returncode=result.returncode,
                             ended_utc=datetime.now(timezone.utc).isoformat(), expected_failure=marker))
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        if marker is None and result.returncode != 0:
            raise RuntimeError(f'{name}:\n{text[-16000:]}')
        first_line = text.splitlines()[0] if text else ''
        diagnostic = first_line.partition('Assertion failed in zedboard_hybrid_tb.oracle: ')[2]
        if marker is not None and (result.returncode == 0 or diagnostic != marker):
            raise RuntimeError(f'{name} did not fail for {marker}:\n{text[-16000:]}')
        return text

    def compile_run(name, root, marker=None):
        run(name+'_compile', [args.verilator, '--binary', '--timing', '--Wall',
            '-Wno-TIMESCALEMOD', '-Wno-DECLFILENAME', '-CFLAGS', '-O0', '-j', str(args.jobs),
            '-I'+str(root/'rtl'), '--top-module', 'zedboard_hybrid_tb',
            '--Mdir', str(out/name), *[str(root/s) for s in SIM]])
        result = run(name+'_simulation', [str(out/name/'Vzedboard_hybrid_tb'),
                    '+trace='+str(out/(name+'_trace.csv'))], marker)
        if marker is None and 'PASS hybrid board H1-H15' not in result:
            raise RuntimeError('Missing success marker')
        return result

    run('verilator_version', [args.verilator, '--version'])
    run('yosys_version', [args.yosys, '-V'])
    print(run('tcl_contract', ['tclsh', str(out/'sources/tests/hybrid_project_check.tcl'),
        str(ROOT/'scripts/create_hybrid_project.tcl'), str(out)]), end='', flush=True)
    print(compile_run('normal', out/'sources'), end='', flush=True)
    run('synth', [args.yosys, '-Q', '-T', '-p',
        'read_verilog -sv -Irtl '+ ' '.join(CORE) +
        '; synth -top hybrid_fault_sequencer; check -assert; stat; write_json '+str(out/'netlist.json')])
    # Defective isolated copies; exact first failure must identify the boundary.
    mutations = [
        ('missing_storage', 'rtl/mac_hybrid_datapath.vh',
         'acc_codeword <= acc_codeword ^ storage_mask;', 'acc_codeword <= acc_codeword;',
         'raw storage XOR/commit cycle 223 expected 20000006 got 20000007'),
        ('missing_candidate', 'rtl/mac_hybrid_datapath.vh',
         'exact_sum ^ candidate_fault_mask', 'exact_sum ^ (candidate_fault_mask & 0)',
         'candidate actual XOR cycle 14'),
        ('shifted_attempt', 'fpga/zedboard/hybrid_fault_sequencer.sv',
         'latched_attempts[retry_count]', "latched_attempts[retry_count + 2'd1]",
         'selected attempt masks cycle 14'),
        ('live_mask', 'fpga/zedboard/hybrid_fault_sequencer.sv',
         "selected ? latched_candidate : 25'b0", "selected ? candidate_mask : 25'b0",
         'selected attempt masks cycle 5882'),
        ('false_commit_ack', 'fpga/zedboard/hybrid_fault_sequencer.sv',
         'commit_eligible && (|applied_commit)', 'source_usable && (|applied_commit)',
         'sampled injection acknowledgement cycle 22'),
        ('swapped_vio_operands', 'fpga/zedboard/zedboard_hybrid_top.sv',
         '.probe_out3(operand_a),\n        .probe_out4(operand_b)',
         '.probe_out3(operand_b),\n        .probe_out4(operand_a)',
         'VIO probe_out3 wiring'),
        ('swapped_vio_reset_abort', 'fpga/zedboard/zedboard_hybrid_top.sv',
         '.probe_out0(rst)', '.probe_out0(abort_request)',
         'VIO probe_out0 wiring'),
        # Simulation-only hierarchy deliberately distinguishes abort from reset
        # at the shared reset input; all other reset assignments remain intact.
        ('abort_retains_storage', 'rtl/mac_hybrid_datapath.vh',
         'if (rst) begin\n            acc_codeword <= 0;',
         'if (rst) begin\n            if (!zedboard_hybrid_tb.dut.abort_request) acc_codeword <= 0;',
         'reset/abort raw storage clear'),
        ('busy_reset_retains_storage', 'rtl/mac_hybrid_datapath.vh',
         'if (rst) begin\n            acc_codeword <= 0;',
         'if (rst) begin\n            if (!busy) acc_codeword <= 0;',
         'reset/abort raw storage clear'),
    ]
    import shutil
    for name, path, before, after, marker in mutations:
        root = out/(name+'_sources')
        shutil.copytree(out/'sources', root)
        target = root/path
        text = target.read_text()
        if text.count(before) != 1:
            raise RuntimeError(f'Ambiguous mutation {name}')
        target.write_text(text.replace(before, after))
        if name == 'swapped_vio_reset_abort':
            # Complete the isolated swap, avoiding multiply driven nets.
            text = target.read_text()
            before = '.probe_out10(abort_request)'
            if text.count(before) != 1:
                raise RuntimeError(f'Ambiguous second half of {name}')
            target.write_text(text.replace(before, '.probe_out10(rst)'))
        compile_run(name, root, marker)
        print(f'PASS negative control {name}: {marker}', flush=True)
    print('PASS M3 local checks; hardware/Vivado implementation NOT RUN', flush=True)


if __name__ == '__main__':
    main()
