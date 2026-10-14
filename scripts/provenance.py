#!/usr/bin/env python3
"""Record tool versions and source hashes even without Git metadata."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = [ROOT / "Makefile", ROOT / "README.md"]
    for folder in ("rtl", "model", "tests", "scripts", "spec"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    artifacts = [args.output.parent / name for name in
                 ("vectors.txt", "vectors.json", "simulation.log", "harness_checks.log",
                  "compile.log", "stat.json", "netlist.v", "netlist.json", "synth.log")]
    record = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "git_revision": command("git", "rev-parse", "HEAD"),
              "git_status": command("git", "status", "--porcelain"),
              "tools": {"python": platform.python_version(), "verilator": command("verilator", "--version"),
                        "yosys": command("yosys", "-V"), "compiler": command("g++", "--version")},
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
              "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts if p.is_file()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
