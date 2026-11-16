#!/usr/bin/env python3
"""Lifecycle helper for trusted host acceptance targets; not a security boundary."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

LABEL = "io.mac-sentry.run"


def validate_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value or ""):
        raise ValueError("Run ID must be 1–128 ASCII letters/digits/dot/underscore/hyphen, starting with letter/digit")
    return value


def run_container(arguments, environ=None):
    environ = os.environ if environ is None else environ
    run_id = validate_id(environ.get("MAC_SENTRY_RUN_ID"))
    marker_value = environ.get("MAC_SENTRY_CONTAINER_MARKER")
    if not marker_value:
        raise ValueError("MAC_SENTRY_CONTAINER_MARKER is required")
    if not arguments:
        raise ValueError("Provide a container image and any podman run arguments")
    # Conservative across the complete argument vector: ambiguous image-command
    # flags are rejected too. This avoids incorrectly parsing podman's options.
    for arg in arguments:
        short_detach = re.fullmatch(r"-[A-Za-z]+", arg) and "d" in arg[1:]
        if arg == "--detach" or arg.startswith("--detach=") or short_detach:
            raise ValueError("Detached container mode is forbidden")
        if arg == "--rm" or arg.startswith("--rm="):
            raise ValueError("Container removal is managed by this helper")
        if LABEL in arg or arg.startswith("--label-file"):
            raise ValueError("The ownership label is managed by this helper")
    marker = Path(marker_value)
    if not marker.is_absolute():
        raise ValueError("MAC_SENTRY_CONTAINER_MARKER must be an absolute path")
    marker.parent.mkdir(parents=True, exist_ok=True)
    # Append before launch so interruption cannot leave an unmarked container.
    with marker.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"run_id": run_id, "pid": os.getpid(),
                                 "label": f"{LABEL}={run_id}"}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    command = ["podman", "run", "--rm", "--label", f"{LABEL}={run_id}", *arguments]
    return subprocess.run(command, check=False).returncode


def _containers(run_id, all_states=False, timeout=10):
    command = ["podman", "ps"]
    if all_states:
        command.append("-a")
    command.extend(["--filter", f"label={LABEL}={run_id}", "--format", "{{.ID}}"])
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"Cannot list owned containers: {result.stderr.strip()}")
    ids = result.stdout.split()
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", item) for item in ids):
        raise RuntimeError("Unexpected podman container ID output")
    return ids


def cleanup(label):
    run_id = validate_id(label)
    deadline = time.monotonic() + 25

    def timeout():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Owned-container cleanup exceeded its 25-second budget")
        return min(10, remaining)

    ids = _containers(run_id, timeout=timeout())
    failures = []
    if ids:
        result = subprocess.run(["podman", "kill", *ids], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout(), check=False)
        if result.returncode:
            failures.append(result.stderr.strip() or f"podman kill exited {result.returncode}")
    # A crash before container start or after exit can leave an owned container
    # which kill cannot remove. Re-list all states before removing exact IDs.
    remaining = _containers(run_id, all_states=True, timeout=timeout())
    if remaining:
        result = subprocess.run(["podman", "rm", "--force", *remaining], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout(), check=False)
        if result.returncode:
            failures.append(result.stderr.strip() or f"podman rm exited {result.returncode}")
    # Never kill/remove unlabelled containers. Verify rather than trusting rm's
    # status; concurrent --rm cleanup may already have removed an exact owned ID.
    for _ in range(11):
        remaining = _containers(run_id, all_states=True, timeout=timeout())
        if not remaining:
            # A container exiting between listing and kill is a benign race.
            print(f"CONTAINER_CLEANUP_PASS: {run_id}")
            return 0
        time.sleep(0.2)
    detail = "; cleanup errors: " + "; ".join(failures) if failures else ""
    print(f"CONTAINER_CLEANUP_FAIL: {run_id}: containers remain {remaining}{detail}", file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run_parser = sub.add_parser("run", help="Run an attached, labelled, auto-removed container")
    run_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    clean_parser = sub.add_parser("cleanup", help="Kill/remove only containers with the exact run label")
    clean_parser.add_argument("--label", required=True)
    # REMAINDER does not consume leading option-like arguments without --;
    # preserve podman's complete argument vector directly for the run subcommand.
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "run":
        return run_container(values[1:])
    args = parser.parse_args(values)
    return cleanup(args.label)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"CONTAINER_RUNTIME_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
