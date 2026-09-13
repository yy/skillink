#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Fast-forward each clean Git checkout named in a skill manifest, once."""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def update(manifest: Path, dry_run: bool = False) -> int:
    data = tomllib.loads(manifest.read_text())
    if data.get("format_version") != 1 or not isinstance(data.get("sources"), dict):
        raise ValueError("expected a version 1 manifest with a sources table")
    repos = {}
    failed = False
    for name, value in data["sources"].items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"source {name}: expected a local directory path")
        source = (manifest.parent / Path(value).expanduser()).resolve()
        result = git(source, "rev-parse", "--show-toplevel")
        if result.returncode:
            print(f"SKIP {name}: {result.stderr.strip()}", file=sys.stderr)
            failed = True
            continue
        repos.setdefault(Path(result.stdout.strip()), []).append(name)
    for root, names in repos.items():
        label = ", ".join(names)
        status = git(root, "status", "--porcelain", "--untracked-files=normal")
        if status.returncode or status.stdout.strip():
            print(f"SKIP {label}: {root} has local changes or cannot be inspected")
            failed = True
            continue
        upstream = git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        if upstream.returncode:
            print(f"SKIP {label}: {root} has no tracking branch")
            failed = True
            continue
        if dry_run:
            print(f"WOULD UPDATE {label}: git -C {root} pull --ff-only")
            continue
        result = git(root, "pull", "--ff-only")
        print(f"{'UPDATED' if result.returncode == 0 else 'FAILED'} {label}: {root}")
        print((result.stdout + result.stderr).strip())
        failed |= result.returncode != 0
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path.cwd() / "skills.toml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return update(args.manifest.expanduser().resolve(), args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
