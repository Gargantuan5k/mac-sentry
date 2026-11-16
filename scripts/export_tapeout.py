#!/usr/bin/env python3
"""Export a standalone Tiny Tapeout candidate; never initialize or modify Git."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RTL = ['rtl/secded_encoder.sv', 'rtl/secded_decoder.sv', 'rtl/signed_residue7.sv',
       'rtl/mac_residue7_check.sv', 'rtl/mac_hybrid.sv', 'asic/rtl/tt_um_mac_sentry.sv',
       'rtl/secded_functions.vh', 'rtl/mac_hybrid_datapath.vh']
CORNERS = [f'{rc}_{pvt}' for rc in ('min', 'nom', 'max')
           for pvt in ('tt_025C_1v80', 'ss_100C_1v60', 'ff_n40C_1v95')]


def export(root, output):
    root, output = Path(root).resolve(), Path(output)
    if output.resolve().is_relative_to(root) and not output.resolve().is_relative_to(root / 'build'):
        raise ValueError('Exports inside the research checkout must be under build/')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite an existing export')
    # Validate every input before creating output; no private state or symlinks.
    inputs = {}
    for path in sorted((root / 'asic/submission').rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('Symlink in submission scaffold')
        if path.is_file():
            inputs[path.relative_to(root / 'asic/submission').as_posix()] = path
    for rel in RTL:
        inputs['src/' + Path(rel).name] = root / rel
    for name in ('constraints.sdc', 'constraints_pnr.sdc'):
        inputs['src/' + name] = root / 'asic/flow' / name
    inputs['requirements/asic-lock.json'] = root / 'requirements/asic-lock.json'
    for source in inputs.values():
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError('Missing or unsafe source: ' + str(source))
        if any(p.is_symlink() for p in source.parents if p != root and root in p.parents):
            raise ValueError('Symlink source parent')
    # Read all small inputs once: exported bytes and provenance bind one snapshot.
    payload = {name: p.read_bytes() for name, p in inputs.items()}
    info = json.loads((root / 'asic/info.yaml').read_text())
    info['project']['author'] = 'Siddharth Vivek, Tejas Singh Kohli, Arohi Mehta'
    payload['info.yaml'] = (json.dumps(info, indent=2) + '\n').encode()
    config = json.loads((root / 'results/published/data/asic/template-config.json').read_text())
    config.pop('//', None)
    overrides = json.loads((root / 'asic/flow/overrides.json').read_text())
    config.update(overrides)
    config.update(VERILOG_INCLUDE_DIRS=['dir::.'], STA_CORNERS=CORNERS,
                  PNR_SDC_FILE='dir::constraints_pnr.sdc', SIGNOFF_SDC_FILE='dir::constraints.sdc')
    payload['src/config.json'] = (json.dumps(config, indent=2) + '\n').encode()
    # Preserve the independent contract for CI/config drift checks.
    payload['flow_contract.json'] = (json.dumps({**overrides, 'STA_CORNERS': CORNERS,
        'DIE_AREA': [0, 0, 334.88, 225.76], 'DESIGN_NAME': 'tt_um_mac_sentry',
        'PNR_SDC_FILE': 'constraints_pnr.sdc', 'SIGNOFF_SDC_FILE': 'constraints.sdc'}, indent=2) + '\n').encode()
    manifest = {'schema': 1, 'purpose': 'submission candidate, not sign-off or portal acceptance',
        'files': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(payload.items())},
        'source_files': {n: {'origin': str(inputs[n].relative_to(root)),
                           'sha256': hashlib.sha256(b).hexdigest()}
                         for n, b in sorted(payload.items()) if n in inputs},
        'pending': ['SDF simulation', 'full sign-off and team review',
                    'original-code licensing decision', 'hosted workflows', 'portal submission']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive directory creation; no overwrite or Git operation.
    for name, data in payload.items():
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    (output / 'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'build/distribution/mac-sentry-tinytapeout')
    args = p.parse_args()
    result = export(ROOT, args.output)
    print(json.dumps({'status': 'EXPORTED', 'path': str(args.output.resolve()),
                      'files': len(result['files']), 'signoff': False}))


if __name__ == '__main__':
    main()
