"""Make a new lossless copy of a moved run with hash-bound historical links.

Original archives are never edited. An absolute link may refer only to a file
under the explicitly named original run root. Its relocated referent must be
inside the supplied source and match that link's original artifact SHA256.
This does not validate experiment outcomes or change archive safety policy.
"""
from pathlib import Path
import argparse
import json
import os
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.copy_evidence import digest


def restore(source, destination, manifest, original_root):
    source = Path(source).resolve(strict=True)
    destination, manifest = Path(destination), Path(manifest)
    original_root = Path(original_root)
    if not original_root.is_absolute():
        raise ValueError('Original run root must be absolute')
    if destination.resolve().is_relative_to(source) or manifest.resolve().is_relative_to(source):
        raise ValueError('Destination must be outside original evidence')
    if any(p.exists() or p.is_symlink() for p in (destination, manifest)):
        raise FileExistsError('Refusing to overwrite evidence')
    hashes = json.loads((source / 'artifact_sha256.json').read_text())
    entries = {}
    inputs = {}
    for path in sorted(source.rglob('*')):
        name = str(path.relative_to(source))
        item = {}
        if path.is_symlink():
            target = Path(os.readlink(path))
            if not target.is_absolute() or not target.is_relative_to(original_root):
                raise ValueError('Link outside explicit original run root: ' + name)
            referent = (source / target.relative_to(original_root)).resolve(strict=True)
            if not referent.is_relative_to(source) or not referent.is_file():
                raise ValueError('Relocated referent outside source or not a file: ' + name)
            if name not in hashes or digest(referent) != hashes[name]:
                raise ValueError('Historical link hash mismatch: ' + name)
            item.update(original_link=str(target), relocated_target=str(referent))
        elif path.is_dir():
            continue
        elif path.is_file():
            referent = path
        else:
            raise ValueError('Non-regular evidence: ' + name)
        sha = digest(referent)
        if name in hashes and sha != hashes[name]:
            raise ValueError('Historical artifact hash mismatch: ' + name)
        item.update(sha256=sha, size=referent.stat().st_size)
        entries[name] = item
        inputs[name] = referent
    if set(hashes) - entries.keys():
        raise ValueError('Missing original manifest members')
    destination.mkdir(parents=True)
    for name, referent in inputs.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with referent.open('rb') as src, target.open('xb') as dst:
            for block in iter(lambda: src.read(1024 * 1024), b''):
                dst.write(block)
        if digest(target) != entries[name]['sha256'] or digest(referent) != entries[name]['sha256']:
            raise ValueError('Evidence changed during copy: ' + name)
        if 'original_link' in entries[name] and os.readlink(source / name) != entries[name]['original_link']:
            raise ValueError('Original link changed during copy: ' + name)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open('x') as stream:
        json.dump(dict(schema=1, source=str(source), original_root=str(original_root),
                       destination=str(destination), entries=entries,
                       scope='lossless packaging; original outcomes unchanged'), stream, indent=2)
        stream.write('\n')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--original-root', type=Path, required=True)
    args = parser.parse_args()
    restore(args.source, args.destination, args.manifest, args.original_root)
