#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Install one skills.toml profile using owned symlinks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

import yaml
from manifest_path import manifest_path

STATE = ".skillink.json"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class InstallError(ValueError):
    """Invalid manifest or a destination that must be preserved."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InstallError(message)


def keys(value: object, allowed: set[str], required: set[str], label: str) -> None:
    require(isinstance(value, dict), f"{label}: expected a table")
    require(required <= value.keys(), f"{label}: missing {required - value.keys()}")
    require(
        not value.keys() - allowed, f"{label}: unknown fields {value.keys() - allowed}"
    )


def path_value(value: object, base: Path) -> Path:
    require(isinstance(value, str) and bool(value), "paths must be nonempty strings")
    require(not value.startswith("~") or value.startswith("~/"), f"invalid path: {value}")
    path = Path(value).expanduser()
    # Do not resolve the final symlink: target may be the old whole-directory link.
    return Path(os.path.abspath(base / path))


def string_list(value: object, label: str) -> list[str]:
    require(isinstance(value, list), f"{label}: expected a list")
    require(all(isinstance(item, str) for item in value), f"{label}: expected strings")
    return value


def skill_file(path: Path, name: str) -> None:
    require(path.is_file(), f"missing skill file: {path}")
    lines = path.read_text().splitlines()
    require(bool(lines) and lines[0] == "---", f"{path}: missing frontmatter")
    require("---" in lines[1:], f"{path}: unclosed frontmatter")
    end = lines.index("---", 1)
    data = yaml.safe_load("\n".join(lines[1:end]))
    require(isinstance(data, dict), f"{path}: frontmatter must be a mapping")
    require(data.get("name") == name, f"{path}: frontmatter name must be {name!r}")
    description = data.get("description")
    require(
        isinstance(description, str) and bool(description.strip()),
        f"{path}: missing description",
    )
    require(bool("\n".join(lines[end + 1 :]).strip()), f"{path}: empty instructions")


def selection(manifest: Path, profile: str, target: str | None = None) -> tuple:
    data = tomllib.loads(manifest.read_text())
    keys(
        data,
        {"format_version", "sources", "profiles"},
        {"format_version", "sources", "profiles"},
        "manifest",
    )
    require(
        type(data["format_version"]) is int and data["format_version"] == 1,
        "unsupported format_version",
    )
    require(isinstance(data["sources"], dict), "sources must be a table")
    sources = {}
    for name, value in data["sources"].items():
        require(bool(NAME.fullmatch(name)), f"invalid source name: {name}")
        sources[name] = path_value(value, manifest.parent).resolve()
    require(isinstance(data["profiles"], dict), "profiles must be a table")
    for name, config in data["profiles"].items():
        require(bool(NAME.fullmatch(name)), f"invalid profile name: {name}")
        keys(
            config,
            {"target", "include", "exclude", "variants"},
            {"target", "include"},
            f"profile {name}",
        )
        path_value(config["target"], manifest.parent)
        string_list(config["include"], "include")
        string_list(config.get("exclude", []), "exclude")
        require(isinstance(config.get("variants", {}), dict), "variants must be a table")
    require(profile in data["profiles"], f"unknown profile: {profile}")
    config = data["profiles"][profile]
    destination = path_value(target or config["target"], manifest.parent)
    selected = {}
    for identifier in config["include"]:
        parts = identifier.split("/")
        require(len(parts) == 2, f"invalid selection: {identifier}")
        source, name = parts
        require(source in sources, f"unmanifest source: {source}")
        require(name == "*" or bool(NAME.fullmatch(name)), f"invalid skill: {identifier}")
        root = sources[source]
        require(root.is_dir(), f"missing source: {root}; clone it or edit the manifest")
        paths = (
            sorted(root.glob("*/SKILL.md")) if name == "*" else [root / name / "SKILL.md"]
        )
        require(bool(paths), f"selection matches no skills: {identifier}")
        for path in paths:
            selected[f"{source}/{path.parent.name}"] = path.parent
    for identifier in config.get("exclude", []):
        require(identifier in selected, f"exclusion is not included: {identifier}")
        del selected[identifier]
    variants = config.get("variants", {})
    for identifier, variant in variants.items():
        require(identifier in selected, f"variant is not included: {identifier}")
        require(
            isinstance(variant, str) and bool(NAME.fullmatch(variant)),
            f"invalid variant name: {variant!r}",
        )
    desired = {}
    for identifier, root in selected.items():
        name = root.name
        require(
            bool(NAME.fullmatch(name)) and len(name) <= 64, f"invalid skill name: {name}"
        )
        require(name not in desired, f"name collision: {name}; exclude one source")
        skill_file(root / "SKILL.md", name)
        resolved = root.resolve()
        require(
            not destination.resolve().is_relative_to(resolved),
            f"target is inside selected source skill: {root}",
        )
        if identifier in variants:
            variant = root / "variants" / f"{variants[identifier]}.md"
            skill_file(variant, name)
            desired[name] = {
                entry.name: str(entry.resolve())
                for entry in root.iterdir()
                if entry.name not in {"SKILL.md", "variants"}
            }
            desired[name]["SKILL.md"] = str(variant.resolve())
        else:
            desired[name] = str(resolved)
    return destination, desired, sources


def link_target(path: Path) -> str:
    return str(path.resolve(strict=False))


def matches(path: Path, spec: str | dict) -> bool:
    if isinstance(spec, str):
        return path.is_symlink() and link_target(path) == spec
    return (
        not path.is_symlink()
        and path.is_dir()
        and {p.name for p in path.iterdir()} == spec.keys()
        and all(matches(path / name, value) for name, value in spec.items())
    )


def read_state(target: Path) -> dict:
    path = target / STATE
    if not path.exists() and not path.is_symlink():
        return {}
    require(not path.is_symlink(), f"state file must not be a symlink: {path}")
    data = json.loads(path.read_text())
    keys(
        data,
        {"version", "manifest", "profile", "skills"},
        {"version", "manifest", "profile", "skills"},
        "installation state",
    )
    require(data["version"] == 1, "unsupported installation state version")
    require(isinstance(data["skills"], dict), "invalid installation state")
    for name, spec in data["skills"].items():
        require(bool(NAME.fullmatch(name)), f"invalid owned name: {name}")
        if isinstance(spec, dict):
            require("SKILL.md" in spec, f"invalid variant state: {name}")
            for child in spec:
                require(
                    child not in {".", ".."} and Path(child).name == child,
                    f"invalid owned child: {child}",
                )
            values = spec.values()
        else:
            values = [spec]
        require(
            all(isinstance(v, str) and Path(v).is_absolute() for v in values),
            f"invalid link targets in state: {name}",
        )
    return data


def plan(
    manifest: Path, profile: str, target: str | None = None, migrate: bool = False
) -> tuple:
    destination, desired, sources = selection(manifest, profile, target)
    whole_link = destination.is_symlink()
    # Migration recognizes only the source roots explicitly named in the manifest.
    legacy_roots = set(sources.values())
    if whole_link:
        require(
            migrate and destination.resolve() in sources.values(),
            f"{destination}: directory symlink; use --migrate for a manifest source",
        )
    else:
        require(
            not destination.exists() or destination.is_dir(),
            f"{destination}: target is not a directory",
        )
    state = {} if whole_link else read_state(destination)
    if state:
        require(
            state["manifest"] == str(manifest),
            f"{destination}: owned by another manifest: {state['manifest']}",
        )
    if state:
        require(
            state["profile"] == profile,
            f"{destination}: owned by another profile: {state['profile']}",
        )
    owned = state.get("skills", {}).copy()
    if migrate and not whole_link and destination.is_dir():
        for path in destination.iterdir():
            if (
                path.name in owned
                or not NAME.fullmatch(path.name)
                or not path.is_symlink()
            ):
                continue
            resolved = path.resolve(strict=False)
            if resolved.parent in legacy_roots and resolved.name == path.name:
                owned[path.name] = str(resolved)
    changes = []
    for name in sorted(owned.keys() | desired.keys()):
        path = destination / name
        exists = not whole_link and (path.exists() or path.is_symlink())
        old, new = owned.get(name), desired.get(name)
        if exists:
            if old is not None:
                require(
                    matches(path, old), f"{path}: managed entry was modified; preserved"
                )
            else:
                require(
                    new is not None and matches(path, new),
                    f"{path}: conflicts with an unmanaged entry; preserved",
                )
        if new is None:
            if exists:
                changes.append(("remove", name, old, None))
        elif not exists:
            changes.append(("link", name, None, new))
        elif old != new and not matches(path, new):
            changes.append(("replace", name, old, new))
        elif name not in state.get("skills", {}):
            changes.append(("adopt", name, None, new))
    return destination, desired, changes, whole_link


def remove_entry(path: Path, spec: str | dict) -> None:
    if isinstance(spec, str):
        path.unlink()
    else:
        for name in spec:
            (path / name).unlink()
        path.rmdir()


def install(
    manifest: Path,
    profile: str,
    target: str | None = None,
    dry_run: bool = False,
    check: bool = False,
    migrate: bool = False,
) -> int:
    destination, desired, changes, whole_link = plan(manifest, profile, target, migrate)
    state = {
        "version": 1,
        "manifest": str(manifest),
        "profile": profile,
        "skills": desired,
    }
    state_ok = not whole_link and read_state(destination) == state
    if whole_link:
        print(f"migrate directory link {destination}")
    for action, name, _, new in changes:
        print(f"{action:7} {destination / name}" + (f" -> {new}" if new else ""))
    if not state_ok:
        print(f"record  {destination / STATE}")
    print(f"{profile}: {len(desired)} skills, {len(changes)} changes")
    if check:
        return int(whole_link or bool(changes) or not state_ok)
    if dry_run:
        return 0
    if whole_link:
        destination.unlink()
    destination.mkdir(parents=True, exist_ok=True)
    for action, name, old, new in changes:
        path = destination / name
        if action in {"remove", "replace"}:
            remove_entry(path, old)
        if action in {"link", "replace"}:
            if isinstance(new, str):
                path.symlink_to(new, target_is_directory=True)
            else:
                path.mkdir()
                for child, source in sorted(new.items()):
                    (path / child).symlink_to(source)
    if not state_ok:
        with tempfile.NamedTemporaryFile(mode="w", dir=destination, delete=False) as out:
            json.dump(state, out, indent=2, sort_keys=True)
            out.write("\n")
        os.replace(out.name, destination / STATE)
    return 0


def install_safe(manifest: Path, profile: str, target: str | None = None) -> int:
    destination, desired, _ = selection(manifest, profile, target)
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        print(f"skip {destination}: existing target")
        return 0
    state = read_state(destination)
    if state:
        require(
            state["manifest"] == str(manifest),
            f"{destination}: owned by another manifest",
        )
    if state:
        require(
            state["profile"] == profile,
            f"{destination}: owned by another profile: {state['profile']}",
        )
    owned = state.get("skills", {}).copy()
    additions = {}
    for name, spec in desired.items():
        path = destination / name
        if path.exists() or path.is_symlink():
            print(f"skip {path}: already exists")
        else:
            additions[name] = spec
    if not additions:
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    for name, spec in additions.items():
        path = destination / name
        if isinstance(spec, str):
            path.symlink_to(spec, target_is_directory=True)
        else:
            path.mkdir()
            for child, source in sorted(spec.items()):
                (path / child).symlink_to(source)
        owned[name] = spec
        print(f"link {path}")
    state = {"version": 1, "manifest": str(manifest), "profile": profile, "skills": owned}
    with tempfile.NamedTemporaryFile(mode="w", dir=destination, delete=False) as out:
        json.dump(state, out, indent=2, sort_keys=True)
        out.write("\n")
    os.replace(out.name, destination / STATE)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="manifest path (default: user Skillink configuration)",
    )
    parser.add_argument("--target", help="override the profile's installation directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="show changes without writing"
    )
    mode.add_argument(
        "--check", action="store_true", help="exit 1 if installation differs"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="adopt legacy source links and split a source directory link",
    )
    mode.add_argument(
        "--safe",
        action="store_true",
        help="add missing skills only; preserve all existing entries",
    )
    args = parser.parse_args()
    if args.safe and args.migrate:
        parser.error("--safe and --migrate cannot be combined")
    try:
        if args.safe:
            return install_safe(manifest_path(args.manifest), args.profile, args.target)
        return install(
            manifest_path(args.manifest),
            args.profile,
            args.target,
            args.dry_run,
            args.check,
            args.migrate,
        )
    except (InstallError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
