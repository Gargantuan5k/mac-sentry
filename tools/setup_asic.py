#!/usr/bin/env python3
"""Explicit, fresh-cache ASIC setup. Without --execute this only prints its plan."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.process_runtime import stop_group
LOCK = ROOT / 'requirements/asic-lock.json'

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):h.update(block)
    return h.hexdigest()

def write(path, value):Path(path).write_text(json.dumps(value, indent=2) + '\n')

def extract_vendor(archive, destination):
    """Strip one archive root; reject links, traversal and nonregular members."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError(destination)
    with tarfile.open(archive, 'r:gz') as tar:
        members = []
        prefix = None
        seen = set()
        for m in tar.getmembers():
            p = PurePosixPath(m.name)
            if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe vendor archive path')
            if prefix is None:prefix = p.parts[0]
            if p.parts[0] != prefix or not (m.isfile() or m.isdir()):raise ValueError('Unsafe vendor archive member')
            if len(p.parts) == 1:
                if not m.isdir():raise ValueError('Archive root must be directory')
                continue
            rel = Path(*p.parts[1:])
            if rel.as_posix() in seen:raise ValueError('Duplicate vendor archive member')
            seen.add(rel.as_posix());members.append((m, rel))
        if not members:raise ValueError('Empty vendor archive')
        destination.mkdir(parents=True)
        for m, rel in members:
            path = destination / rel
            if m.isdir():path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, path.open('xb') as dst:shutil.copyfileobj(src, dst)
                path.chmod(0o755 if m.mode & 0o111 else 0o644)

def fetch_vendor(tools, pins, opener=urllib.request.urlopen):
    vendor = tools / 'vendor'
    vendor.mkdir()
    for name, item in pins.items():
        if not re.fullmatch(r'[a-z0-9-]+', name) or not re.fullmatch(r'[0-9a-f]{40}', item['commit']):raise ValueError('Invalid vendor pin')
        expected_url = f'https://codeload.github.com/TinyTapeout/{name}/tar.gz/{item["commit"]}'
        if item['url'] != expected_url:raise ValueError('Vendor URL drift')
        archive = tools / (name + '.tar.gz')
        with opener(expected_url, timeout=60) as response, archive.open('xb') as dst:shutil.copyfileobj(response, dst)
        if digest(archive) != item['tar_sha256']:raise ValueError('Vendor archive hash mismatch: ' + name)
        extract_vendor(archive, vendor / name)
    write(vendor / 'sources.json', {name:{k:v for k,v in item.items() if k != 'url'} for name,item in pins.items()})

def image_id(text):
    value = text.strip().removeprefix('sha256:')
    if not re.fullmatch('[0-9a-f]{64}', value):raise ValueError('Invalid immutable image ID')
    return value

def validate_pdks(root, pins):
    for key in ('hardening_pdk', 'precheck_pdk'):
        rev = pins[key]
        if (root / 'sky130/versions' / rev / 'sky130A/SOURCES').read_text().strip() != 'open_pdks ' + rev:raise ValueError('PDK identity mismatch: ' + key)

@contextmanager
def termination_signals():
    previous={}
    def interrupted(signum,frame):
        for signum in previous:signal.signal(signum,signal.SIG_IGN)
        raise KeyboardInterrupt('ASIC setup interrupted')
    try:
        for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):previous[signum]=signal.signal(signum,interrupted)
        yield
    finally:
        for signum,handler in previous.items():signal.signal(signum,handler)


def run_process(command, log, env, timeout):
    """Bound and reap the command group, including pip/build descendants."""
    with Path(log).open('w') as stream:
        proc=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:return proc.wait(timeout=timeout)
        finally:
            cleanup=stop_group(proc)
            if not cleanup['quiescent']:raise RuntimeError('Setup command group did not become quiescent: ' + repr(cleanup))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, default=ROOT / 'build/asic-tools')
    parser.add_argument('--python', default='python3.11', help='Python 3.11 executable for isolated host environments')
    parser.add_argument('--pdk-root', type=Path, help='Existing Ciel root, e.g. /external/pdks/ciel; read-only unless --fetch-pdks')
    parser.add_argument('--fetch-pdks', action='store_true', help='Explicitly download both pinned revisions into --pdk-root')
    parser.add_argument('--execute', action='store_true', help='Authorize downloads, fresh venvs, image pull/build and optional PDK fetch')
    args = parser.parse_args(argv)
    pins = json.loads(LOCK.read_text());tools = args.tools.expanduser().resolve()
    pdk_root = (args.pdk_root.expanduser().resolve() if args.pdk_root else tools / 'pdk/ciel')
    print(json.dumps({'tools':str(tools), 'pdk_root':str(pdk_root), 'python':args.python, 'vendor':pins['vendor'], 'fetch_pdks':args.fetch_pdks, 'execute':args.execute, 'note':'Setup is not physical validation. Existing cache directories are never overwritten.'}, indent=2))
    if not args.execute:return 0
    if tools.exists() or tools.is_symlink():raise FileExistsError('Choose a fresh --tools path; refusing existing cache: ' + str(tools))
    if not args.fetch_pdks:validate_pdks(pdk_root, pins)
    tools.mkdir(parents=True);records=[]
    env=os.environ.copy();label='setup-' + str(os.getpid()) + '-' + str(datetime.now(timezone.utc).timestamp()).replace('.','-')
    env.update(MAC_SENTRY_RUN_ID=label, MAC_SENTRY_CONTAINER_MARKER=str(tools/'containers-used'))
    def run(command, timeout=1800):
        record={'argv':[str(a) for a in command], 'returncode':None};records.append(record);write(tools/'setup-commands.json',records)
        log=tools/f'setup-{len(records):02d}.log'
        try:
            code=run_process(command,log,env,timeout)
            record.update(returncode=code,log=log.name)
            if code:raise RuntimeError('Setup command failed; see ' + str(log))
            return log.read_text()
        except BaseException as exc:
            record.update(log=log.name,error=str(exc));raise
        finally:write(tools/'setup-commands.json',records)
    status={'schema':2,'status':'RUNNING','created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Tool setup only; no physical acceptance','pdk_root':str(pdk_root),'lock_sha256':digest(LOCK), 'setup_source_sha256':{name:digest(ROOT/name) for name in ('tools/setup_asic.py','tools/container_runtime.py','tools/process_runtime.py','tools/precheck.Containerfile','requirements/asic-python.txt','requirements/asic-metadata.txt')}}
    write(tools/'setup-manifest.json',status)
    try:
        version=run([args.python,'-c','import sys; print("%d.%d" % sys.version_info[:2])'])
        if version.strip() != '3.11':raise ValueError('ASIC setup requires Python 3.11')
        fetch_vendor(tools,pins['vendor'])
        for name,req in [('venv','asic-python.txt'),('tt-venv','asic-metadata.txt')]:
            run([args.python,'-m','venv',str(tools/name)])
            run([str(tools/name/'bin/python'),'-m','pip','install','-r',str(ROOT/'requirements'/req)])
        if args.fetch_pdks:
            for key in ('hardening_pdk','precheck_pdk'):
                run([str(tools/'venv/bin/ciel'),'fetch','--pdk-family','sky130','--pdk-root',str(pdk_root),pins[key]],timeout=7200)
        validate_pdks(pdk_root,pins)
        run(['podman','pull',pins['librelane_image']])
        ll=image_id(run(['podman','image','inspect',pins['librelane_image'],'--format','{{.Id}}']))
        helper=ROOT/'tools/container_runtime.py'
        v=run([sys.executable,str(helper),'run','--network=none','--pull=never','sha256:'+ll,'python3','-m','librelane','--version'])
        if '3.0.14' not in v:raise ValueError('Wrong LibreLane image version')
        tag='localhost/mac-sentry-precheck:local-' + str(os.getpid())
        run(['podman','build','--pull=never','--jobs=2','--build-arg','BASE_IMAGE=sha256:'+ll,'-t',tag,'-f',str(ROOT/'tools/precheck.Containerfile'),str(tools/'vendor/tt-support-tools')],timeout=7200)
        pre=image_id(run(['podman','image','inspect',tag,'--format','{{.Id}}']))
        run([sys.executable,str(helper),'run','--network=none','--pull=never','sha256:'+pre,'python --version; klayout -v; magic --version'])
        status.update(images={'librelane':ll,'precheck':pre},vendor_manifest_sha256=digest(tools/'vendor/sources.json'),containerfile_sha256=digest(ROOT/'tools/precheck.Containerfile'))
    except BaseException as exc:
        status.update(status='FAILED',reason=str(exc));write(tools/'setup-manifest.json',status);raise
    finally:
        if (tools/'containers-used').exists():
            try:run([sys.executable,str(ROOT/'tools/container_runtime.py'),'cleanup','--label',label],timeout=40)
            except BaseException as exc:
                status.update(status='FAILED',reason='Owned-container cleanup: ' + str(exc));write(tools/'setup-manifest.json',status);raise
    status.update(status='PREPARED');write(tools/'setup-manifest.json',status)
    print('ASIC_TOOLS_PREPARED: run the full ASIC target for physical validation')
    return 0

if __name__=='__main__':
    with termination_signals():sys.exit(main())
