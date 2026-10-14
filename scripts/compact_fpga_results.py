#!/usr/bin/env python3
"""Losslessly pack FPGA evidence, sharing identical builds across run archives."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_run(run):
    manifest = json.loads((run / 'manifest.json').read_text())
    storage_path = run / 'storage.json'
    storage = json.loads(storage_path.read_text()) if storage_path.exists() else {}
    for name, expected in manifest['file_sha256'].items():
        if name in storage.get('packed_files', {}):
            archive = run / storage['packed_files'][name]
            with ZipFile(archive) as handle:
                data = handle.read(name)
        else:
            data = (run / name).read_bytes()
        if digest(data) != expected:
            raise ValueError(f'Hash mismatch: {run.name}/{name}')
    for archive, expected in storage.get('archive_sha256', {}).items():
        if digest((run / archive).read_bytes()) != expected:
            raise ValueError(f'Archive hash mismatch: {archive}')
    return len(manifest['file_sha256'])


def pack_verified(archive, run, names):
    """Publish a ZIP only after checking each member against its original bytes."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix('.zip.tmp')
        with temporary.open('xb') as stream:
            with ZipFile(stream, 'w', compression=ZIP_DEFLATED, compresslevel=9) as handle:
                for name in names:
                    handle.write(run / name, name)
        with ZipFile(temporary) as handle:
            for name in names:
                if handle.read(name) != (run / name).read_bytes():
                    raise ValueError(f'ZIP verification failed: {name}')
        temporary.rename(archive)
    with ZipFile(archive) as handle:
        if set(handle.namelist()) != set(names):
            raise ValueError(f'Unexpected member list: {archive}')
        for name in names:
            if handle.read(name) != (run / name).read_bytes():
                raise ValueError(f'Existing ZIP differs: {name}')


def compact_run(run, build_store):
    """Keep original manifests unchanged; storage.json maps paths into ZIPs."""
    import os
    run, build_store = run.resolve(), build_store.resolve()
    verify_run(run)
    if (run / 'storage.json').exists():
        return
    manifest = json.loads((run / 'manifest.json').read_text())
    groups = {
        'build': sorted(name for name in manifest['file_sha256']
                        if name.startswith(('build/', 'reports/'))),
        'sources': sorted(name for name in manifest['file_sha256'] if name.startswith('sources/')),
    }
    # Never remove unlisted files or assume different source snapshots are equal.
    for folder in ('build', 'reports', 'sources'):
        actual = {str(p.relative_to(run)) for p in (run / folder).rglob('*') if p.is_file()}
        expected = {name for name in manifest['file_sha256'] if name.startswith(folder + '/')}
        if actual != expected:
            raise ValueError(f'Unrecorded or missing files under {run / folder}')
    identity = digest(json.dumps({name: manifest['file_sha256'][name]
                                 for name in groups['build']}, sort_keys=True).encode())
    archives = {'build': build_store / f'{identity}.zip', 'sources': run / 'sources.zip'}
    packed = {}
    archive_hashes = {}
    for group, names in groups.items():
        if not names:
            continue
        archive = archives[group]
        pack_verified(archive, run, names)
        relative = os.path.relpath(archive, run)
        packed.update({name: relative for name in names})
        archive_hashes[relative] = digest(archive.read_bytes())
    storage = {'schema': 1, 'build_content_id': identity,
               'note': 'Original manifest paths are ZIP member names. Build identity includes reports; it does not prove which bitstream was programmed.',
               'packed_files': packed, 'archive_sha256': archive_hashes}
    # Verify the packed representation before deleting any original file.
    (run / 'storage.json').write_text(json.dumps(storage, indent=2) + '\n')
    verify_run(run)
    for name in packed:
        (run / name).unlink()
    for folder in ('build', 'reports', 'sources'):
        base = run / folder
        for directory in sorted((p for p in base.rglob('*') if p.is_dir()), reverse=True):
            directory.rmdir()
        if base.exists():
            base.rmdir()
    verify_run(run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'results')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    runs = sorted(p.parent for folder in ('fpga', 'runs')
                  for p in (root / folder).glob('*/manifest.json'))
    # Preflight every archive before making changes.
    for run in runs:
        verify_run(run)
        destination = root / 'runs' / run.name
        if run != destination and destination.exists():
            raise ValueError(f'Destination exists: {destination}')
    if args.verify_only:
        print(f'Verified {len(runs)} run archives against original SHA-256 manifests')
        return
    for run in runs:
        destination = root / 'runs' / run.name
        if run != destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            run.rename(destination)
        compact_run(destination, root / 'builds')
    # Remove staging exports only when an identical file is already in a run.
    archived_hashes = {digest(p.read_bytes()) for p in (root / 'runs').glob('*/captures/**/*') if p.is_file()}
    for source in (root / 'captures').glob('*'):
        if source.is_file() and digest(source.read_bytes()) in archived_hashes:
            source.unlink()
    # Remove empty scaffolding only; never delete nonempty unrecognized folders.
    for directory in sorted((p for p in root.rglob('*') if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    (root / 'README.md').write_text(
        '# FPGA results\n\n'
        '- `runs/`: one directory per measurement run. Start with `tests.csv`, '
        '`capture_summary.csv`, and `manifest.json`.\n'
        '- `builds/`: compressed build artifacts and reports, shared only when their '
        'paths and SHA-256 hashes are identical.\n'
        '- `captures/`: temporary incoming exports, when present.\n\n'
        'Each run keeps raw captures and CSVs directly accessible. `sources.zip` '
        'preserves its exact source snapshot. `storage.json` maps original manifest '
        'paths to ZIP files; historical run READMEs describe those original paths. '
        'Original manifests and recorded outcomes have not been edited.\n\n'
        'Back up this entire results directory, including builds. A run copied alone '
        'does not contain its shared build ZIP. Archives are ignored by Git.\n\n'
        'Verify integrity from the repository root:\n\n'
        '```sh\npython3 scripts/compact_fpga_results.py --verify-only\n```\n\n'
        '## Runs\n\n' + ''.join(f'- [{p.name}](runs/{p.name}/tests.csv)\n'
                                 for p in sorted((root / 'runs').iterdir()) if p.is_dir()))
    print(f'Compacted {len(runs)} runs; original file hashes verified before and after packing')


if __name__ == '__main__':
    main()
