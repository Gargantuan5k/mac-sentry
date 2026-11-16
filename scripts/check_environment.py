#!/usr/bin/env python3
"""Report required host tools without installing packages or launching builds."""
import argparse
import json
import shutil
import subprocess
import sys


def inspect(profile):
    commands = {'make': ['make', '--version'], 'verilator': ['verilator', '--version'],
                'compiler': ['g++', '--version'], 'yosys': ['yosys', '-V']}
    if profile == 'python': commands = {}
    if profile == 'asic': commands.update(podman=['podman', '--version'], iverilog=['iverilog', '-V'])
    if profile == 'fpga': commands.update(vivado=['vivado', '-version'])
    result = {'python': {'version': sys.version.split()[0], 'ok': sys.version_info >= (3, 10)}}
    for name, argv in commands.items():
        path = shutil.which(argv[0])
        if path is None:
            result[name] = {'ok': False, 'reason': 'not on PATH'}; continue
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
            lines = (p.stdout + p.stderr).strip().splitlines()
            result[name] = {'ok': p.returncode == 0, 'path': path,
                            'version': lines[0] if lines else '(no version output)'}
        except (OSError, subprocess.TimeoutExpired) as e:
            result[name] = {'ok': False, 'reason': str(e)}
    return {'profile': profile, 'status': 'PASS' if all(x['ok'] for x in result.values()) else 'FAIL', 'tools': result}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', choices=['python', 'rtl', 'asic', 'fpga'], default='rtl')
    result = inspect(p.parse_args().profile); print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
