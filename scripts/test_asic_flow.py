#!/usr/bin/env python3
"""CR2 local, offline physical flow. Preparation is explicitly not acceptance."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.process_runtime import stop_group
TOOLS = Path(os.environ.get('MAC_SENTRY_ASIC_TOOLS', ROOT / 'build/asic-tools')).expanduser().resolve()
LOCK_PATH = ROOT / 'requirements/asic-lock.json'
VENDOR_PINS = json.loads(LOCK_PATH.read_text())['vendor']
TOP = 'tt_um_mac_sentry'
HARDEN_PDK = '8afc8346a57fe1ab7934ba5a6056ea8b43078e71'
PRECHECK_PDK = '0536d02d875c8f67dd7cca3902ac457e62f20005'
COMMITS = {'ttsky-verilog-template': 'a42e6662fab316e93b4e26399e21d41664a460b7',
           'tt-support-tools': '9d13ff3e3e6202090740110438c6a10c1d62ca0f',
           'tt-gds-action': '395eedb3eeec3c2f4961c3b04ff2cf87f5525636'}
RTL = ['rtl/secded_encoder.sv', 'rtl/secded_decoder.sv', 'rtl/signed_residue7.sv',
       'rtl/mac_residue7_check.sv', 'rtl/mac_hybrid.sv', 'asic/rtl/tt_um_mac_sentry.sv']
HEADERS = ['rtl/secded_functions.vh', 'rtl/mac_hybrid_datapath.vh']
CORNERS = [f'{rc}_{pvt}' for rc in ('min', 'nom', 'max')
           for pvt in ('tt_025C_1v80', 'ss_100C_1v60', 'ff_n40C_1v95')]
ZERO_METRICS = ['design__instance_unmapped__count', 'synthesis__check_error__count',
    'design__inferred_latch__count', 'design__lint_error__count',
    'route__drc_errors', 'magic__drc_error__count', 'klayout__drc_error__count',
    'magic__illegal_overlap__count', 'design__lvs_error__count',
    'design__xor_difference__count', 'design__critical_disconnected_pin__count',
    'design__power_grid_violation__count', 'route__antenna_violation__count']
CORNER_ZERO = ['timing__setup_vio__count', 'timing__hold_vio__count',
    'design__max_slew_violation__count', 'design__max_cap_violation__count',
    'design__max_fanout_violation__count', 'timing__unannotated_net_filtered__count']
PRECHECKS = {'Magic DRC', 'KLayout FEOL', 'KLayout BEOL', 'KLayout offgrid',
    'KLayout pin label overlapping drawing', 'KLayout zero area', 'KLayout Checks',
    'Pin check', 'Boundary check', 'Power pin check', 'Layer check', 'Cell name check',
    'urpm/nwell check', 'Analog pin check', 'Verilog syntax check'}
PHYSICAL_REPORTS = {
    '*-magic-drc': 'reports/drc.magic.rpt',
    '*-klayout-drc': 'reports/drc.klayout.json',
    '*-netgen-lvs': 'reports/lvs.netgen.rpt',
}

# Pass this code inline: a probe stored inside an inaccessible bind mount would
# itself fail to load and hide which required input could not be opened. Use
# read_bytes, not exists/is_file (which can misreport EACCES as absence).
ACCESS_PROBE = '''import hashlib, json, os, sys
from pathlib import Path
print(json.dumps({"cwd": os.getcwd(), "uid": os.getuid(), "gid": os.getgid()}), flush=True)
for filename, expected in zip(sys.argv[2::2], sys.argv[3::2]):
    print("M2_INPUT_OPEN " + filename, flush=True)
    actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError("M2_INPUT_HASH_MISMATCH " + filename)
    print("M2_INPUT_READ_OK " + filename + " " + actual, flush=True)
with Path(sys.argv[1]).open("x") as stream:
    stream.write("Input hashes and new output write verified; not a physical PASS.\\n")
print("M2_CONTAINER_ACCESS_OK", flush=True)
'''


def access_probe(marker, inputs):
    """Build a read/hash/write probe; never adjust host access permissions."""
    if not inputs:
        raise ValueError('Container access probe requires inputs')
    return ['python3', '-c', ACCESS_PROBE, marker,
            *[item for container_path, host_path in inputs
              for item in (container_path, digest(require_file(host_path)))]]


def container_command(out, pdk, image, workdir, command, jobs):
    """Rootless default UID mapping retains the image's prepared Nix cache.

    Only this run's private output tree is relabelled; the shared PDK is read-only.
    """
    return [sys.executable, str(ROOT / 'tools/container_runtime.py'), 'run',
            '--network=none', '--pull=never',
            '-v', f'{out}:/work:rw,Z', '-v', f'{pdk}:/pdk:ro',
            '-w', workdir, '-e', 'PDK_ROOT=/pdk', '-e', 'PDK=sky130A',
            '-e', 'PYTHONDONTWRITEBYTECODE=1',
            '-e', f'OMP_NUM_THREADS={jobs}', image, *command]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def require_file(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f'Missing/empty required artifact: {path}')
    return path


def number(metrics, key):
    v = metrics.get(key)
    if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
        raise ValueError(f'Missing/nonfinite numeric metric {key}: {v!r}')
    return v


class EvidenceErrors(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('; '.join(errors))


def collect(errors, operation):
    """Keep independent failures; missing artifacts never become skipped passes."""
    try:
        return operation()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.extend(exc.errors if isinstance(exc, EvidenceErrors) else [str(exc)])
        return None


def validate_metrics(metrics):
    errors = []
    def zero(key):
        if number(metrics, key) != 0:
            raise ValueError(f'Physical violation: {key}={metrics[key]}')
    def slack(key):
        if number(metrics, key) < 0:
            raise ValueError(f'Negative timing slack: {key}={metrics[key]}')
    for key in ZERO_METRICS:
        collect(errors, lambda key=key: zero(key))
    for corner in CORNERS:
        for base in CORNER_ZERO:
            collect(errors, lambda key=f'{base}__corner:{corner}': zero(key))
        for kind in ('setup', 'hold'):
            collect(errors, lambda key=f'timing__{kind}__ws__corner:{corner}': slack(key))
    def fit():
        if number(metrics, 'design__instance__count__stdcell') <= 0:
            raise ValueError('No standard cells')
        area = number(metrics, 'design__instance__area__stdcell')
        core = number(metrics, 'design__core__area')
        if not 0 < area <= core:
            raise ValueError(f'Cell area {area} does not fit core {core}')
    collect(errors, fit)
    if str(metrics.get('design__die__bbox')).split() not in (
            ['0', '0', '334.88', '225.76'], ['0.0', '0.0', '334.88', '225.76']):
        errors.append('Measured die does not match pinned 2x2 budget')
    if errors:
        raise EvidenceErrors(errors)


def cell_instances(netlist):
    # OpenROAD's flattened, named-port standard-cell netlist. Escaped instance
    # identifiers terminate at whitespace; connection values remain unmodified.
    cells = {}
    pattern = r'(sky130_fd_sc_hd__\w+)\s+(\\[^\s]+|[\w$]+)\s*\((.*?)\);'
    for match in re.finditer(pattern, netlist, re.S):
        kind, name, body = match.groups()
        name = name.removeprefix('\\')
        if name in cells:
            raise ValueError(f'Duplicate netlist instance: {name}')
        ports = dict(re.findall(r'\.(\w+)\s*\(([^()]*)\)', body))
        residue = re.sub(r'\.\w+\s*\([^()]*\)', '', body)
        if residue.replace(',', '').strip():
            raise ValueError(f'Cannot parse netlist instance: {name}')
        cells[name] = (kind, {k: v.strip() for k, v in ports.items()})
    if not cells:
        raise ValueError('No parsed SKY130 cells')
    return cells


def validate_unannotated(checks, metrics, corner, cells):
    marker = 'report_parasitic_annotation -report_unannotated'
    if checks.count(marker) != 1:
        raise ValueError(f'Missing/duplicate annotation report: {corner}')
    section = checks.split(marker)[1]
    match = re.search(r'Found (\d+) unannotated drivers\.\n(.*?)Found (\d+) partially unannotated drivers\.', section, re.S)
    if not match:
        raise ValueError(f'Cannot parse annotation report: {corner}')
    count, entries, partial = match.groups()
    pins = [line.strip() for line in entries.splitlines() if line.strip()]
    if int(partial) or int(count) != len(pins) or len(set(pins)) != len(pins):
        raise ValueError(f'Incomplete/partial annotation list: {corner}')
    # No hidden drivers after the partial-count line (which must be zero).
    tail = section[match.end():].split('===', 1)[0]
    if tail.strip():
        raise ValueError(f'Unexpected annotation tail: {corner}')
    if number(metrics, f'timing__unannotated_net__count__corner:{corner}') != len(pins):
        raise ValueError(f'Raw annotation metric/list mismatch: {corner}')
    if number(metrics, f'timing__unannotated_net_filtered__count__corner:{corner}') != 0:
        raise ValueError(f'Filtered annotation violation: {corner}')
    for pin in pins:
        instance, port = pin.rsplit('/', 1)
        if instance not in cells:
            raise ValueError(f'Unannotated instance absent from netlist: {pin}')
        kind, ports = cells[instance]
        allowed = ((kind == 'sky130_fd_sc_hd__conb_1' and port == 'HI') or
                   (re.fullmatch(r'clkload\d+', instance) and
                    kind.startswith('sky130_fd_sc_hd__clkbuf_') and port == 'X'))
        if not allowed or ports.get(port, '').strip():
            raise ValueError(f'Unannotated connected/unapproved driver: {pin}')
    return pins


def clock_tree(netlist):
    """Diagnostic fanout/depth from actual named connections, including diodes."""
    cells = cell_instances(netlist)
    buffers = {n: p for n, (k, p) in cells.items()
               if k.startswith('sky130_fd_sc_hd__clkbuf_') and p.get('X')}
    loads = {}
    for n, (kind, ports) in cells.items():
        for port, net in ports.items():
            if net and port not in ('X', 'Q', 'Q_N', 'Y', 'HI', 'LO', 'VPWR', 'VGND', 'VPB', 'VNB'):
                loads.setdefault(net, []).append((n, port))
    roots = [n for n, ports in buffers.items() if ports.get('A') == 'clk']
    if len(roots) != 1:
        raise ValueError(f'Expected one clock root: {roots}')
    fanouts, depths = {}, []
    def walk(name, depth, ancestors):
        if name in ancestors:
            raise ValueError('Clock tree cycle')
        sinks = loads.get(buffers[name]['X'], [])
        fanouts[name] = len(sinks)
        for child, port in sinks:
            if child in buffers and port == 'A':
                walk(child, depth + 1, ancestors | {name})
            elif port == 'CLK':
                depths.append(depth)
    walk(roots[0], 1, set())
    if not depths:
        raise ValueError('No clocked endpoints')
    return dict(root=roots[0], root_fanout=fanouts[roots[0]], fanouts=fanouts,
                max_fanout=max(fanouts.values()), min_depth=min(depths),
                max_depth=max(depths), balanced_depth=min(depths) == max(depths),
                sequential_sinks=len(depths))


def validate_precheck(path):
    root = ET.parse(require_file(path)).getroot()
    cases = root.findall('.//testcase')
    names = [case.get('name') for case in cases]
    if len(names) != len(PRECHECKS) or set(names) != PRECHECKS:
        raise ValueError(f'Missing/duplicate/unexpected SKY130 prechecks: {names}')
    for case in cases:
        if any(case.find(tag) is not None for tag in ('error', 'failure', 'skipped')):
            raise ValueError(f'Precheck failed/skipped: {case.get("name")}')


def validate_physical(run, diagnostics_path=None, enforce_repair=True):
    errors, diagnostics = [], {'corners': {}}
    final = run / 'final'
    def read_json(path):
        return json.loads(require_file(path).read_text())
    metrics = collect(errors, lambda: read_json(final / 'metrics.json')) or {}
    collect(errors, lambda: validate_metrics(metrics))
    config = collect(errors, lambda: read_json(run / 'resolved.json')) or {}
    def config_check():
        if config.get('meta', {}).get('librelane_version') != '3.0.14':
            errors.append('Unexpected resolved LibreLane version')
        if set(config.get('STA_CORNERS', [])) != set(CORNERS):
            errors.append('Unexpected/missing signoff corners')
        for key, value in {'CLOCK_PERIOD': 50, 'CLOCK_PORT': 'clk',
                           'MAX_FANOUT_CONSTRAINT': 10, 'MAX_TRANSITION_CONSTRAINT': 0.75,
                           'MAX_CAPACITANCE_CONSTRAINT': 0.2, 'TIME_DERATING_CONSTRAINT': 5,
                           'CTS_ROOT_BUFFER': 'sky130_fd_sc_hd__clkbuf_16',
                           'CTS_CLK_BUFFERS': ['sky130_fd_sc_hd__clkbuf_8',
                                               'sky130_fd_sc_hd__clkbuf_4',
                                               'sky130_fd_sc_hd__clkbuf_2']}.items():
            if config.get(key) != value:
                errors.append(f'Constraint changed: {key}={config.get(key)}')
        if Path(config.get('SIGNOFF_SDC_FILE', '')).name != 'constraints.sdc':
            errors.append('Signoff SDC contract changed')
        for key in ('RUN_DRT', 'RUN_CTS', 'RUN_MCSTA', 'RUN_SPEF_EXTRACTION',
                    'RUN_MAGIC_DRC', 'RUN_KLAYOUT_DRC', 'RUN_KLAYOUT_XOR', 'RUN_LVS'):
            if config.get(key) is not True:
                errors.append(f'Required flow check disabled: {key}')
        for key in ('TIMING_VIOLATION_CORNERS', 'SETUP_VIOLATION_CORNERS',
                    'HOLD_VIOLATION_CORNERS', 'MAX_SLEW_VIOLATION_CORNERS', 'MAX_CAP_VIOLATION_CORNERS'):
            if config.get(key) != ['*']:
                errors.append(f'Corner check changed: {key}')
        if enforce_repair:
            overrides = json.loads((ROOT / 'asic/flow/overrides.json').read_text())
            for key in ('EXTRA_EXCLUDED_CELLS', 'DESIGN_REPAIR_MAX_SLEW_PCT',
                        'GRT_DESIGN_REPAIR_MAX_SLEW_PCT', 'RUN_POST_GRT_DESIGN_REPAIR',
                        'CTS_DISTANCE_BETWEEN_BUFFERS'):
                if config.get(key) != overrides[key]:
                    errors.append(f'Repair configuration drift: {key}')
            if Path(config.get('PNR_SDC_FILE', '')).name != 'constraints_pnr.sdc':
                errors.append('Missing implementation fanout headroom')
    collect(errors, config_check)
    for fmt, suffix in [('gds', 'gds'), ('lef', 'lef'), ('nl', 'nl.v'),
                        ('pnl', 'pnl.v'), ('def', 'def'), ('sdc', 'sdc')]:
        collect(errors, lambda fmt=fmt, suffix=suffix: require_file(final / fmt / f'{TOP}.{suffix}'))
    netlist = collect(errors, lambda: require_file(final / 'nl' / f'{TOP}.nl.v').read_text())
    cells = collect(errors, lambda: cell_instances(netlist)) if netlist is not None else None
    if cells:
        diagnostics['clock_tree'] = collect(errors, lambda: clock_tree(netlist))
        # Check actual cells against every pinned exclusion, including weak
        # non-delay buffers. Passing metrics cannot excuse config drift or a
        # forbidden cell that survived synthesis/resizing.
        patterns = json.loads((ROOT / 'asic/flow/overrides.json').read_text())['EXTRA_EXCLUDED_CELLS']
        excluded = {n: k for n, (k, _) in cells.items()
                    if any(fnmatchcase(k, pattern) for pattern in patterns)}
        diagnostics['excluded_cell_instances'] = excluded
        diagnostics['excluded_delay_instances'] = [n for n, k in excluded.items()
                    if re.match(r'sky130_fd_sc_hd__(clkdlybuf4s|dlygate4sd|dlymetal6s)', k)]
        if enforce_repair and excluded:
            errors.append(f'Excluded cells remain: {excluded}')
    for pattern, report in PHYSICAL_REPORTS.items():
        folders = list(run.glob(pattern))
        if len(folders) != 1:
            errors.append(f'Missing/ambiguous physical step: {pattern}')
        else:
            for name in (report, 'state_out.json'):
                collect(errors, lambda name=name: require_file(folders[0] / name))
    routing = list(run.glob('*-openroad-detailedrouting'))
    antennas = list(run.glob('*-openroad-checkantennas*'))
    ordinal = lambda path: int(path.name.split('-')[0])
    if len(routing) != 1 or not antennas:
        errors.append('Missing detailed routing/final antenna step')
    else:
        antenna = max(antennas, key=ordinal)
        if ordinal(antenna) <= ordinal(routing[0]):
            errors.append('Antenna evidence predates detailed routing')
        for name in ('reports/antenna.rpt', 'reports/antenna_summary.rpt', 'state_out.json'):
            collect(errors, lambda name=name: require_file(antenna / name))
    steps = list(run.glob('*-openroad-stapostpnr'))
    if len(steps) != 1:
        errors.append('Missing/ambiguous post-route STA step')
    else:
        for corner in CORNERS:
            folder = steps[0] / corner
            entry = diagnostics['corners'][corner] = {'metrics': {
                k: v for k, v in metrics.items() if k.endswith('__corner:' + corner)}}
            checks = collect(errors, lambda: require_file(folder / 'checks.rpt').read_text())
            if checks is not None:
                entry['violating_pins'] = [line.strip() for line in checks.splitlines() if '(VIOLATED)' in line]
                entry['unannotated_disconnected'] = collect(errors, lambda: validate_unannotated(checks, metrics, corner, cells or {}))
                if ('check_setup -verbose -unconstrained_endpoints' not in checks or
                        re.search(r'(?im)^\s*Warning|\(unconstrained\)', checks)):
                    errors.append(f'STA checks incomplete or contain warnings: {corner}')
            for name in ('max.rpt', 'min.rpt', 'sta.log', 'filter_unannotated.log'):
                collect(errors, lambda name=name: require_file(folder / name))
    diagnostics['errors'] = errors
    diagnostics['scope'] = 'candidate' if enforce_repair else 'historical diagnostic only; never acceptance'
    if diagnostics_path:
        write_json(diagnostics_path, diagnostics)
    if errors:
        raise EvidenceErrors(errors)
    return metrics


def resolve_vendor():
    """The standalone project only reads its explicitly prepared vendor cache."""
    return TOOLS / 'vendor'


def base_sdc():
    candidates = list((TOOLS / 'venv/lib').glob('python*/site-packages/librelane/scripts/base.sdc'))
    if len(candidates) != 1:
        raise ValueError('Expected one installed LibreLane base.sdc in the prepared venv')
    return require_file(candidates[0])


@contextmanager
def termination_signals():
    previous = {}
    def interrupted(signum, frame):
        for signum in previous:signal.signal(signum, signal.SIG_IGN)
        raise KeyboardInterrupt('ASIC run interrupted')
    try:
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[signum] = signal.signal(signum, interrupted)
        yield
    finally:
        for signum, handler in previous.items():signal.signal(signum, handler)


def run_command(argv, cwd, log, env, timeout):
    """Bound foreground children and reap their process group on any interruption."""
    with Path(log).open('w') as stream:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        try:
            return proc.wait(timeout=timeout)
        finally:
            cleanup = stop_group(proc)
            if not cleanup['quiescent']:
                raise RuntimeError('ASIC command group did not become quiescent: ' + repr(cleanup))



def cleanup_containers(out, env):
    marker = Path(env['MAC_SENTRY_CONTAINER_MARKER'])
    if not marker.exists():return {'status':'NOT_USED'}
    command = [sys.executable, str(ROOT / 'tools/container_runtime.py'), 'cleanup',
               '--label', env['MAC_SENTRY_RUN_ID']]
    rc = run_command(command, ROOT, out / 'container_cleanup.log', env, 40)
    result = {'status':'PASS' if rc == 0 else 'FAIL', 'returncode':rc,
              'label':env['MAC_SENTRY_RUN_ID'], 'marker':marker.name, 'command':command}
    write_json(out / 'container_cleanup.json', result)
    if rc != 0:raise RuntimeError('Owned container cleanup failed')
    return result


def prepare(out, jobs):
    vendor = resolve_vendor()
    pins = json.loads(require_file(vendor / 'sources.json').read_text())
    require_file(vendor / 'tt-support-tools/precheck/precheck.py')
    if any(pins[name]['commit'] != commit for name, commit in COMMITS.items()):
        raise ValueError('Vendor commit drift')
    if any(pins[name].get('tar_sha256') != item['tar_sha256'] for name, item in VENDOR_PINS.items()):
        raise ValueError('Vendor archive identity drift')
    sources = RTL + HEADERS + ['asic/info.yaml', 'asic/flow/overrides.json',
        'asic/flow/constraints.sdc', 'asic/flow/constraints_pnr.sdc', 'scripts/test_asic_flow.py',
        'scripts/copy_evidence.py', 'tests/test_evidence_copy.py',
        'tests/asic_gl_tb.sv', 'tests/test_asic_flow.py', 'Makefile',
        'tools/container_runtime.py', 'tools/process_runtime.py', 'tools/precheck.Containerfile', 'requirements/asic-lock.json']
    hashes = {}
    for name in sources:
        source = require_file(ROOT / name)
        dest = out / 'sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        hashes[name] = digest(dest)
    project = out / 'project'
    src = project / 'src'
    src.mkdir(parents=True)
    for name in RTL + HEADERS:
        shutil.copyfile(out / 'sources' / name, src / Path(name).name)
    shutil.copyfile(out / 'sources/asic/info.yaml', project / 'info.yaml')
    for name in ('constraints.sdc', 'constraints_pnr.sdc'):
        shutil.copyfile(out / 'sources/asic/flow' / name, src / name)
    shutil.copyfile(base_sdc(), src / 'base.sdc')
    # Copy unmodified reference scripts; never execute upstream Git/download paths.
    shutil.copytree(vendor / 'tt-support-tools/precheck', out / 'tt/precheck',
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(vendor / 'tt-support-tools/tech', out / 'tt/tech',
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(vendor / 'tt-support-tools/project_info.py', out / 'tt/project_info.py')
    shutil.copyfile(vendor / 'sources.json', out / 'vendor-sources.json')
    template = vendor / 'ttsky-verilog-template/src/config.json'
    shutil.copyfile(template, out / 'template-config.json')
    config = json.loads(template.read_text())
    config.pop('//', None)
    config.update(json.loads((out / 'sources/asic/flow/overrides.json').read_text()))
    config.update(DESIGN_NAME=TOP, VERILOG_FILES=['dir::' + Path(n).name for n in RTL],
        VERILOG_INCLUDE_DIRS=['dir::.'], DIE_AREA=[0, 0, 334.88, 225.76],
        FP_DEF_TEMPLATE='dir::../../tt/tech/sky130A/def/tt_block_2x2_pg.def',
        VDD_PIN='VPWR', GND_PIN='VGND', RT_MAX_LAYER='met4',
        PNR_SDC_FILE='dir::constraints_pnr.sdc', SIGNOFF_SDC_FILE='dir::constraints.sdc',
        STA_CORNERS=CORNERS)
    write_json(src / 'config.json', config)
    info = json.loads((project / 'info.yaml').read_text())
    if (info['project']['clock_hz'] != 1e9 / config['CLOCK_PERIOD'] or
            info['project']['tiles'] != '2x2' or info['project']['top_module'] != TOP or
            info['project']['source_files'] != [Path(n).name for n in RTL]):
        raise ValueError('Project metadata/config mismatch')
    setup = json.loads((TOOLS / 'setup-manifest.json').read_text())
    schema = setup.get('schema', 1)
    expected_status = {1: 'PASS', 2: 'PREPARED'}.get(schema)
    if expected_status is None or setup.get('status') != expected_status:
        raise ValueError('Tools cache is not prepared')
    if setup.get('schema') == 2 and setup.get('lock_sha256') != digest(LOCK_PATH):
        raise ValueError('Prepared tools lock identity drift')
    images = {}
    pdks = {}
    for key, env, rev in [('librelane', 'MAC_SENTRY_LIBRELANE_IMAGE', HARDEN_PDK),
                          ('precheck', 'MAC_SENTRY_PRECHECK_IMAGE', PRECHECK_PDK)]:
        image = os.environ.get(env, setup['images'][key]).removeprefix('sha256:')
        if image != setup['images'][key] or not re.fullmatch('[0-9a-f]{64}', image):
            raise ValueError(f'Image drift: {env}')
        images[key] = 'sha256:' + image
        pdk_root = Path(setup.get('pdk_root', TOOLS / 'pdk/ciel')).expanduser().resolve()
        pdk = (pdk_root / f'sky130/versions/{rev}').resolve()
        if (pdk / 'sky130A/SOURCES').read_text().strip() != 'open_pdks ' + rev:
            raise ValueError(f'PDK identity mismatch: {pdk}')
        pdks[key] = pdk
    write_json(out / 'provenance.json', dict(created_utc=datetime.now(timezone.utc).isoformat(),
        source_sha256=hashes, vendor=pins, images=images,
        hardening_pdk=HARDEN_PDK, precheck_pdk=PRECHECK_PDK,
        base_sdc_sha256=digest(src / 'base.sdc'), jobs=jobs,
        clock_ns=50, tile='2x2', sdf_annotated=False, scope='Protected standalone ASIC flow; no full signoff'))
    return images, pdks


def execute_gls(out, physical, pdks, run, stage):
    models_dir = pdks['librelane'] / 'sky130A/libs.ref/sky130_fd_sc_hd/verilog'
    models = [models_dir / 'primitives.v', models_dir / 'sky130_fd_sc_hd.v']
    netlist = physical / f'final/nl/{TOP}.nl.v'
    tb = out / 'sources/tests/asic_gl_tb.sv'
    for path in models + [netlist, tb]:
        require_file(path)
    write_json(out / 'gls_inputs.json', {str(p): digest(p) for p in [*models, netlist, tb]})
    ref = out / 'reference.sv'
    wrapper = (out / 'sources/asic/rtl/tt_um_mac_sentry.sv').read_text()
    if wrapper.count('module tt_um_mac_sentry (') != 1:
        raise ValueError('Unexpected reference wrapper declaration')
    ref.write_text(wrapper.replace('module tt_um_mac_sentry (', 'module tt_um_mac_sentry_reference ('))
    compiler_version = run('iverilog_version', ['iverilog', '-V'])
    runtime_version = run('vvp_version', ['vvp', '-V'])
    if not re.match(r'Icarus Verilog version 12\.0 \(stable\)', compiler_version):
        raise ValueError('GLS requires the prepared Icarus Verilog 12.0 stable compiler')
    if not re.match(r'Icarus Verilog runtime version 12\.0 \(stable\)', runtime_version):
        raise ValueError('GLS requires the prepared Icarus Verilog 12.0 stable runtime')
    exe = out / 'gls.vvp'
    run('gls_compile', ['iverilog', '-g2012', '-DFUNCTIONAL', '-DUNIT_DELAY=#0',
        '-I' + str(out / 'sources/rtl'), '-s', 'asic_gl_tb', '-o', str(exe),
        *map(str, models), str(netlist), str(ref),
        *[str(out / 'sources' / name) for name in RTL[:-1]], str(tb)])
    def positive_check():
        positive = run('gls_positive', ['vvp', str(exe), '+TRACE=' + str(out / 'gls_positive.vcd')])
        if 'M2_GLS_PASS transactions=777 aborts=2 samples=15642' not in positive:
            raise ValueError('Missing GLS completion marker')
        require_file(out / 'gls_positive.vcd')
    stage('gls_positive', positive_check)
    stage('gls_negative_observation', lambda: run('gls_negative_observation', ['vvp', str(exe), '+NEGATIVE_OBSERVATION'], 'M2_GLS_COMPARE sample=100'))
    stage('gls_negative_arithmetic', lambda: run('gls_negative_arithmetic', ['vvp', str(exe), '+NEGATIVE_ARITHMETIC'], 'M2_GLS_ORACLE'))
    write_json(out / 'gls_inputs.json', {str(p): digest(p) for p in [*models, netlist, ref, tb]})


REQUIRED_STAGES = {'harden', 'physical', 'precheck', 'precheck_xml', 'gls',
                   'gls_positive', 'gls_negative_observation', 'gls_negative_arithmetic'}


def final_result(stages):
    missing = sorted(REQUIRED_STAGES - stages.keys())
    errors = [f'{name}: {entry.get("error", "not passed")}' for name, entry in stages.items()
              if entry['status'] != 'PASS'] + [f'Missing stage: {name}' for name in missing]
    return dict(status='FAIL' if errors else 'PASS', errors=errors, stages=stages,
                scope='CR2_1794085081502364837 local physical checks and zero-delay functional GLS',
                sdf_annotated=False, signoff=False, required_precheck_count=len(PRECHECKS))


def cts_probes(out, physical, container, run, jobs):
    """Failure-only experiments; none can satisfy required acceptance stages."""
    report = {'scope': 'failure-only diagnostics, never acceptance', 'probes': []}
    write_json(out / 'cts_probe.json', report)
    help_text = run('cts_probe_help', container('librelane', '/work', 'python3', '-m', 'librelane', '--help'))
    for flag in ('--to', '--run-tag', '--override-config'):
        if flag not in help_text:
            raise ValueError(f'Pinned CLI lacks {flag}')
    configs = [dict(CTS_DISTANCE_BETWEEN_BUFFERS=value) for value in (15, 25, 40, 60)]
    configs.append(dict(CTS_DISTANCE_BETWEEN_BUFFERS=25, CTS_MAX_SLEW=0.375, CTS_MAX_CAP=0.1))
    for index, config in enumerate(configs):
        tag = f'R2_CTS_DIAGNOSTIC_{index}'
        entry = {'tag': tag, 'overrides': config}
        report['probes'].append(entry)
        try:
            argv = ['python3', '-m', 'librelane', '--pdk-root', '/pdk', '--pdk', 'sky130A',
                    '--scl', 'sky130_fd_sc_hd', '--manual-pdk', '--flow', 'classic',
                    '--jobs', str(jobs), '--run-tag', tag, '--to', 'OpenROAD.CTS', '--hide-progress-bar']
            for key, value in config.items():
                argv += ['--override-config', f'{key}={json.dumps(value)}']
            run(tag, container('librelane', '/work/project', *argv, '/work/project/src/config.json'))
            folder, = (physical.parent / tag).glob('*-openroad-cts')
            entry['tree'] = clock_tree(require_file(folder / f'{TOP}.nl.v').read_text())
            metrics = json.loads(require_file(folder / 'state_out.json').read_text())['metrics']
            entry['skew_metrics'] = {k: v for k, v in metrics.items() if 'skew' in k}
            entry['status'] = 'DIAGNOSTIC_COMPLETE'
        except Exception as exc:
            entry.update(status='DIAGNOSTIC_FAILED', error=str(exc))
        write_json(out / 'cts_probe.json', report)
    report['balanced_fanout_candidates'] = [p['tag'] for p in report['probes']
        if p.get('tree', {}).get('balanced_depth') and p['tree']['max_fanout'] <= 10]
    report['stop_rule'] = ('No candidate: defer clock repair; no clock exemption allowed' if not
        report['balanced_fanout_candidates'] else 'Candidate diagnostics require a new full routed run and review')
    write_json(out / 'cts_probe.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    parser.add_argument('--command-timeout', type=int, default=1800, help='Per-command seconds (positive)')
    parser.add_argument('--prepare-only', action='store_true', help='No physical PASS; sandbox preparation only')
    args = parser.parse_args()
    if args.command_timeout <= 0:parser.error('--command-timeout must be positive')
    os.chdir(ROOT)
    base = ROOT / 'build/asic_flow'
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run_', dir=base))
    print(f'CR2 evidence: {out.relative_to(ROOT)}', flush=True)
    write_json(out / 'result.json', {'status': 'RUNNING'})
    env = dict(os.environ, MAC_SENTRY_RUN_ID='asic-' + out.name,
               MAC_SENTRY_CONTAINER_MARKER=str(out / 'containers-used'))
    commands = []
    stages = {}
    cleanup_done = False

    def stage(name, operation):
        try:
            result = operation()
            stages[name] = {'status': 'PASS'}
            return result
        except Exception as exc:
            stages[name] = {'status': 'FAIL', 'error': str(exc)}
            return None
        finally:
            write_json(out / 'stages.json', stages)

    def run(name, argv, expected_failure=None):
        record = dict(name=name, argv=[str(a) for a in argv],
                      started_utc=datetime.now(timezone.utc).isoformat(), returncode=None)
        commands.append(record)
        write_json(out / 'commands.json', commands)
        print(f'CR2 stage: {name}', flush=True)
        rc = run_command(argv, ROOT, out / f'{name}.log', env, args.command_timeout)
        record['returncode'] = rc
        record['expected_failure'] = expected_failure
        write_json(out / 'commands.json', commands)
        output = (out / f'{name}.log').read_text(errors='replace')
        if expected_failure:
            if rc == 0 or expected_failure not in output:
                raise RuntimeError(f'{name}: negative control failed to detect {expected_failure!r}')
        elif rc != 0:
            raise RuntimeError(f'{name} exited {rc}: see {out / (name + ".log")}\n{output[-4000:]}')
        return output

    try:
        images, pdks = prepare(out, args.jobs)
        run('tt_environment', [str(TOOLS / 'tt-venv/bin/python'), '-B', '-c',
            'import sys,json,importlib.metadata as m; '
            'print(json.dumps({"python":sys.version,"packages":'
            'sorted((d.metadata["Name"],d.version) for d in m.distributions())},indent=2))'])
        run('tt_metadata', [str(TOOLS / 'tt-venv/bin/python'), '-B', '-c',
            'import sys,yaml; from pathlib import Path; '
            'p=Path(sys.argv[1]); sys.path.insert(0,str(p/"tt")); '
            'from project_info import ProjectInfo; '
            'i=ProjectInfo(yaml.safe_load((p/"project/info.yaml").read_text()), '
            'yaml.safe_load((p/"tt/tech/sky130A/tile_sizes.yaml").read_text()),require_pinout=True); '
            'print("TT_METADATA_VALID",i.top_module,i.tiles)', str(out)])
        if args.prepare_only:
            write_json(out / 'result.json', {'status': 'PREPARED_ONLY', 'physical_checks': 'NOT RUN'})
            print('CR2 PREPARED ONLY; no physical checks executed', flush=True)
            return
        # One foreground container/process at a time; only this new evidence dir
        # is writable. Prepared PDK mounts are read-only, no network or pulling.
        def container(key, workdir, *command):
            return container_command(out, pdks[key], images[key], workdir, command, args.jobs)
        version = run('librelane_version', container('librelane', '/work',
            'python3', '-m', 'librelane', '--version'))
        if '3.0.14' not in version:
            raise ValueError('Wrong LibreLane runtime version')
        run('hardening_input_access', container('librelane', '/work', *access_probe(
            '/work/hardening_input_access.txt', [
                ('/work/project/src/config.json', out / 'project/src/config.json'),
                ('/pdk/sky130A/SOURCES', pdks['librelane'] / 'sky130A/SOURCES')])))
        stage('harden', lambda: run('harden', container('librelane', '/work/project', 'python3', '-m', 'librelane',
            '--pdk-root', '/pdk', '--pdk', 'sky130A', '--scl', 'sky130_fd_sc_hd',
            '--manual-pdk', '--flow', 'classic', '--jobs', str(args.jobs), '--run-tag', 'R2',
            '--hide-progress-bar', '/work/project/src/config.json')))
        physical = out / 'project/src/runs/R2'
        metrics = stage('physical', lambda: validate_physical(physical, out / 'physical_diagnostics.json'))
        if metrics is not None:
            write_json(out / 'physical_summary.json', metrics)
        # These stages are deliberately independent: an electrical/DRC failure
        # cannot hide a GLS/precheck harness defect, but still forbids PASS.
        def precheck():
            package = out / 'project/checks'
            package.mkdir()
            for fmt, suffix, dest in [('gds', 'gds', 'gds'), ('lef', 'lef', 'lef'), ('pnl', 'pnl.v', 'v')]:
                shutil.copyfile(require_file(physical / f'final/{fmt}/{TOP}.{suffix}'), package / f'{TOP}.{dest}')
            run('precheck_input_access', container('precheck', '/work', shlex.join(access_probe(
                '/work/precheck_input_access.txt', [
                    ('/work/tt/precheck/precheck.py', out / 'tt/precheck/precheck.py'),
                    (f'/work/project/checks/{TOP}.gds', package / f'{TOP}.gds'),
                    ('/pdk/sky130A/SOURCES', pdks['precheck'] / 'sky130A/SOURCES')]))))
            run('precheck', container('precheck', '/work/tt/precheck',
                f'python precheck.py --gds /work/project/checks/{TOP}.gds --tech sky130A'))
        stage('precheck', precheck)
        stage('precheck_xml', lambda: validate_precheck(out / 'tt/precheck/reports/results.xml'))
        stage('gls', lambda: execute_gls(out, physical, pdks, run, stage))
        diag = json.loads((out / 'physical_diagnostics.json').read_text())
        if diag.get('clock_tree') and diag['clock_tree']['root_fanout'] > 10:
            stage('cts_diagnostics', lambda: cts_probes(out, physical, container, run, args.jobs))
        cleanup_containers(out, env)
        cleanup_done = True
        result = final_result(stages)
        write_json(out / 'result.json', result)
        print(f'CR2_CHECKS_{result["status"]}: {out.relative_to(ROOT)} (not full signoff)', flush=True)
        return 0 if result['status'] == 'PASS' else 1
    except BaseException as exc:
        write_json(out / 'result.json', {'status': 'FAIL', 'reason': str(exc), 'stages': stages})
        raise
    finally:
        try:
            if not cleanup_done:cleanup_containers(out, env)
        except BaseException as exc:
            write_json(out / 'result.json', {'status':'FAIL', 'reason':'Container cleanup: ' + str(exc), 'stages':stages})
            raise
        finally:
            # Hash logs after cleanup too, including failed/interrupted runs.
            write_json(out / 'artifact_sha256.json', {str(p.relative_to(out)): digest(p)
                for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifact_sha256.json'})



if __name__ == '__main__':
    with termination_signals():
        sys.exit(main())
