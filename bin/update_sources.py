#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Fetch and review, or fast-forward, each clean Git checkout named in a manifest."""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

from manifest_path import manifest_path


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def update(
    manifest: Path,
    dry_run: bool = False,
    apply: bool = False,
    show_diff: bool = False,
) -> int:
    data = tomllib.loads(manifest.read_text())
    if (
        type(data.get("format_version")) is not int
        or data["format_version"] != 1
        or not isinstance(data.get("sources"), dict)
    ):
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
            action = "WOULD UPDATE" if apply else "WOULD FETCH"
            cmd = "pull --ff-only" if apply else "fetch"
            print(f"{action} {label}: git -C {root} {cmd}")
            continue
        if apply:
            result = git(root, "pull", "--ff-only")
            print(f"{'UPDATED' if result.returncode == 0 else 'FAILED'} {label}: {root}")
            output = (result.stdout + result.stderr).strip()
            if output:
                print(output)
            failed |= result.returncode != 0
            continue
        fetched = git(root, "fetch")
        if fetched.returncode != 0:
            print(f"FAILED {label}: {root}")
            output = (fetched.stdout + fetched.stderr).strip()
            if output:
                print(output)
            failed = True
            continue
        counts = git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        if counts.returncode != 0:
            print(f"FAILED {label}: {root}")
            failed = True
            continue
        ahead, behind = (int(part) for part in counts.stdout.strip().split())
        if ahead and behind:
            print(f"DIVERGED {label}: {root} (ahead {ahead}, behind {behind})")
            failed = True
            continue
        if behind == 0:
            note = f" (ahead {ahead})" if ahead else ""
            print(f"UP TO DATE {label}: {root}{note}")
            continue
        noun = "commit" if behind == 1 else "commits"
        print(
            f"PENDING {label}: {root} ({behind} incoming {noun}; "
            "rerun with --apply to fast-forward)"
        )
        summary = git(root, "log", "--oneline", "--stat", "HEAD..@{upstream}")
        if summary.stdout.strip():
            print(summary.stdout.strip())
        if show_diff:
            diff = git(root, "diff", "HEAD..@{upstream}")
            if diff.stdout.strip():
                print(diff.stdout.strip())
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="manifest path (default: user Skillink configuration)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview without network requests or working-tree changes",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="fast-forward clean checkouts with git pull --ff-only",
    )
    mode.add_argument(
        "--diff",
        action="store_true",
        help="fetch and print full diffs of incoming upstream changes",
    )
    args = parser.parse_args()
    if args.dry_run and args.diff:
        parser.error("--dry-run and --diff cannot be combined")
    try:
        return update(
            manifest_path(args.manifest),
            dry_run=args.dry_run,
            apply=args.apply,
            show_diff=args.diff,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
