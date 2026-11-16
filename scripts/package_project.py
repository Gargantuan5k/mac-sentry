#!/usr/bin/env python3
"""Export a verified source distribution without Git operations or local caches."""
from pathlib import Path, PurePosixPath
import argparse
import fnmatch
import hashlib
import io
import json
import tarfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = 'PACKAGE_MANIFEST.json'


def relative_path(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.as_posix() != name:
        raise ValueError('Unsafe package path: ' + name)
    if any(x in p.parts for x in ('.git', '.aws', '.codex', '.agents', 'overnight', '.context')):
        raise ValueError('Private path in source package: ' + name)
    return p


def source_files(root):
    root = Path(root).resolve(strict=True)
    cfg = json.loads((root / 'project_manifest.json').read_text())
    if cfg.get('schema') != 1:
        raise ValueError('Unsupported package manifest')
    excluded = cfg['exclude']
    files = {}
    def visit(path):
        rel = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatchcase(rel, rule) or fnmatch.fnmatchcase(path.name, rule)
               for rule in excluded):
            return
        relative_path(rel)
        if not path.resolve().is_relative_to(root):
            raise ValueError('Source path escapes package root: ' + rel)
        for parent in path.parents:
            if parent == root:break
            if parent.is_symlink():
                raise ValueError('Symlinks are not allowed in source parents: ' + rel)
        if path.is_symlink():
            raise ValueError('Symlinks are not allowed in source packages: ' + rel)
        if path.is_dir():
            for child in sorted(path.iterdir()):
                visit(child)
        elif path.is_file():
            files[rel] = path
        else:
            raise FileNotFoundError('Required package input missing: ' + rel)
    for name in cfg['root_files'] + cfg['directories'] + cfg['additional_paths']:
        relative_path(name)
        visit(root / name)
    if not files:
        raise ValueError('Empty source package')
    return dict(sorted(files.items()))


def export(root, output, max_file_mib=25):
    root, output = Path(root), Path(output)
    files = source_files(root)
    if output.resolve() in {p.resolve() for p in files.values()}:
        raise ValueError('Output would overwrite an input')
    if output.exists():
        raise FileExistsError('Refusing to overwrite a source distribution')
    manifest = {'schema': 1, 'scope': 'portable source and selected historical evidence; no tools, raw local builds or agents', 'files': {}}
    for rel, p in files.items():
        if p.stat().st_size > max_file_mib * 1024**2:
            raise ValueError('Unexpected large source file: ' + rel)
        manifest['files'][rel] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                  'size': p.stat().st_size, 'mode': p.stat().st_mode & 0o777}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as tar:
        for rel, p in files.items():
            before = manifest['files'][rel]
            data = p.read_bytes()
            if hashlib.sha256(data).hexdigest() != before['sha256']:
                raise ValueError('Source changed during export: ' + rel)
            info = tarfile.TarInfo('mac_sentry/' + rel)
            info.size = len(data); info.mode = before['mode']; info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
        data = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
        info = tarfile.TarInfo('mac_sentry/' + STAMP); info.size = len(data); info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
    verify(output)
    return manifest


def verify(archive):
    observed = {}; manifest = None
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            prefix = 'mac_sentry/'
            if not member.name.startswith(prefix) or not member.isfile():
                raise ValueError('Unexpected package member')
            rel = member.name[len(prefix):]; relative_path(rel)
            if rel in observed:
                raise ValueError('Duplicate package member')
            if member.size > 25 * 1024**2:
                raise ValueError('Oversized package member')
            data = tar.extractfile(member).read()
            observed[rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': member.mode}
            if rel == STAMP:
                manifest = json.loads(data)
    observed.pop(STAMP, None)
    if not manifest or manifest.get('schema') != 1 or observed != manifest.get('files') or not observed:
        raise ValueError('Package inventory or member hash mismatch')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify', type=Path)
    args = p.parse_args()
    result = verify(args.verify) if args.verify else export(ROOT, args.output)
    print(json.dumps({'status': 'PASS', 'files': len(result['files']), 'uncompressed_bytes': sum(x['size'] for x in result['files'].values())}))


if __name__ == '__main__':
    main()
