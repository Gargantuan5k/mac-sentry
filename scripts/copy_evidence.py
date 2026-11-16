"""Create a new lossless evidence tree; never modify or overwrite the source.

Symlink targets must be within explicitly supplied read boundaries. The copy has
only regular files/directories; original link text, resolved target and content
identity are recorded in a separate manifest. This is packaging, not validation
of the experiment. A failed copy is retained for diagnosis.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import stat


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(source, allowed_roots=()):
    source = Path(source).resolve(strict=True)
    roots = [source, *[Path(p).resolve(strict=True) for p in allowed_roots]]
    result = {}

    def walk(path, relative, ancestors):
        resolved = path.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in roots):
            raise ValueError(f'Target outside explicit evidence boundaries: {path}')
        mode = resolved.stat().st_mode
        entry = {'kind': 'directory' if stat.S_ISDIR(mode) else 'file'}
        if path.is_symlink():
            entry.update(original_link=os.readlink(path), original_target=str(resolved))
        if stat.S_ISREG(mode):
            entry.update(sha256=digest(path), size=resolved.stat().st_size)
        elif not stat.S_ISDIR(mode):
            raise ValueError(f'Non-regular evidence: {path}')
        if relative:
            result[relative] = entry
        if stat.S_ISDIR(mode):
            if resolved in ancestors:
                raise ValueError(f'Evidence directory cycle: {path}')
            for child in sorted(path.iterdir()):
                walk(child, str(Path(relative) / child.name), ancestors | {resolved})
    walk(source, '', set())
    return result


def copy_evidence(source, destination, manifest, allowed_roots=()):
    source = Path(source).resolve(strict=True)
    destination, manifest = Path(destination), Path(manifest)
    if destination.resolve().is_relative_to(source) or manifest.resolve().is_relative_to(source):
        raise ValueError('Evidence destination must be outside source')
    if destination.exists() or destination.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise FileExistsError('Refusing to overwrite evidence or manifest')
    entries = inventory(source, allowed_roots)
    destination.mkdir(parents=True)
    for name, item in entries.items():
        target = destination / name
        if item['kind'] == 'directory':
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with (source / name).open('rb') as src, target.open('xb') as dst:
                for block in iter(lambda: src.read(1024 * 1024), b''):
                    dst.write(block)
            if digest(target) != item['sha256']:
                raise ValueError(f'Evidence changed during copy: {name}')
    if inventory(source, allowed_roots) != entries:
        raise ValueError('Source changed during evidence copy')
    if any(p.is_symlink() for p in destination.rglob('*')):
        raise ValueError('Copy unexpectedly contains symlinks')
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open('x') as stream:
        json.dump(dict(schema=1, source=str(source), destination=str(destination),
                       scope='lossless packaging only; original verdicts unchanged',
                       entries=entries), stream, indent=2)
        stream.write('\n')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--allowed-root', type=Path, action='append', default=[])
    args = parser.parse_args()
    copy_evidence(args.source, args.destination, args.manifest, args.allowed_root)
