#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""List manifest skills and descriptions, or build a searchable offline HTML catalog."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import textwrap
import tomllib
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path

import yaml
from install_skills import path_value, require, selection, skill_file

DEFAULT_HTML = Path.home() / ".local/share/skillink/skills.html"


def describe(path: Path, name: str) -> dict:
    skill_file(path, name)
    lines = path.read_text().splitlines()
    end = lines.index("---", 1)
    metadata = yaml.safe_load("\n".join(lines[1:end]))
    return {
        "description": " ".join(metadata["description"].split()),
        "instructions": "\n".join(lines[end + 1 :]).strip(),
        "path": str(path),
    }


def catalog(manifest: Path, profile: str | None = None) -> list[dict]:
    data = tomllib.loads(manifest.read_text())
    # Reuse the installer's selection rules, including exclusions and variants.
    profiles = [profile] if profile else list(data.get("profiles", {}))
    require(bool(profiles), "manifest has no profiles")
    selected = {}
    for name in profiles:
        _, desired, sources = selection(manifest, name)
        config = data["profiles"][name]
        for source, root in sources.items():
            for skill_name, spec in desired.items():
                identifier = f"{source}/{skill_name}"
                if identifier in config.get("exclude", []):
                    continue
                if (
                    identifier not in config["include"]
                    and f"{source}/*" not in config["include"]
                ):
                    continue
                variant = config.get("variants", {}).get(identifier, "canonical")
                path = (
                    Path(spec) / "SKILL.md"
                    if isinstance(spec, str)
                    else Path(spec["SKILL.md"])
                )
                expected = (
                    root
                    / skill_name
                    / ("SKILL.md" if variant == "canonical" else f"variants/{variant}.md")
                )
                if expected.resolve() != path.resolve():
                    continue
                key = (identifier, variant)
                if key not in selected:
                    selected[key] = {
                        "id": identifier,
                        "name": skill_name,
                        "source": source,
                        "variant": variant,
                        "profiles": [],
                        **describe(path, skill_name),
                    }
                selected[key]["profiles"].append(name)
    # The all-sources view also shows canonical skills not selected by any profile.
    if profile is None:
        for source, value in data["sources"].items():
            root = path_value(value, manifest.parent)
            require(root.is_dir(), f"missing source: {root}")
            for path in sorted(root.glob("*/SKILL.md")):
                name = path.parent.name
                identifier = f"{source}/{name}"
                selected.setdefault(
                    (identifier, "canonical"),
                    {
                        "id": identifier,
                        "name": name,
                        "source": source,
                        "variant": "canonical",
                        "profiles": [],
                        **describe(path, name),
                    },
                )
    return [selected[key] for key in sorted(selected)]


def html_catalog(rows: list[dict], manifest: Path) -> str:
    def options(values):
        return "".join(
            f'<option value="{escape(v)}">{escape(v)}</option>' for v in values
        )

    entries = []
    for row in rows:
        variant = (
            f'<span class="variant">{escape(row["variant"])}</span>'
            if row["variant"] != "canonical"
            else ""
        )
        profiles = "".join(
            f'<span class="tag">{escape(p)}</span>' for p in row["profiles"]
        )
        entries.append(
            f'<tr data-source="{escape(row["source"])}" '
            f'data-profiles="{escape(" ".join(row["profiles"]))}">'
            f'<th scope="row"><span class="name">{escape(row["name"])}</span>'
            f'<span class="source">{escape(row["source"])}</span>{variant}</th>'
            f"<td><p>{escape(row['description'])}</p><details><summary>Instructions</summary>"
            f"<pre>{escape(row['instructions'])}</pre>"
            f'<a class="path" href="{escape(Path(row["path"]).as_uri())}">'
            f"{escape(row['path'])}</a></details></td>"
            f'<td class="profiles">{profiles or "<span class=muted>Not selected</span>"}'
            "</td></tr>"
        )
    template = Path(__file__).resolve().parent / "templates/skills.html"
    values = {
        "rows": "\n".join(entries),
        "sources": options(sorted({r["source"] for r in rows})),
        "profiles": options(sorted({p for r in rows for p in r["profiles"]})),
        "count": str(len(rows)),
        "manifest": escape(str(manifest)),
        "updated": datetime.now().astimezone().strftime("%b %d, %Y · %H:%M %Z"),
    }
    # Substitute only tokens in the template; never interpret skill content as a template.
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]], template.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "query", nargs="?", default="", help="search names and descriptions"
    )
    parser.add_argument("--profile", help="show the skills selected for one profile")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path.cwd() / "skills.toml",
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const=str(DEFAULT_HTML),
        metavar="PATH",
        help=f"write an offline HTML page (default: {DEFAULT_HTML})",
    )
    parser.add_argument("--open", action="store_true", help="generate HTML and open it")
    args = parser.parse_args()
    try:
        manifest = args.manifest.expanduser().resolve()
        rows = catalog(manifest, args.profile)
        words = args.query.casefold().split()
        rows = [
            row
            for row in rows
            if all(
                word in f"{row['id']} {row['description']}".casefold() for word in words
            )
        ]
        if args.html or args.open:
            output = Path(args.html or DEFAULT_HTML).expanduser().absolute()
            # Do not let an output path overwrite a source file or the manifest.
            protected = {manifest, *(Path(row["path"]).resolve() for row in rows)}
            require(output.suffix.lower() == ".html", "HTML output must end in .html")
            require(
                not output.is_symlink() and output.resolve() not in protected,
                f"refusing to overwrite a source file or symlink: {output}",
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(html_catalog(rows, manifest))
            print(f"{len(rows)} entries → {output}")
            if args.open:
                webbrowser.open(output.as_uri())
        else:
            width = max(40, min(shutil.get_terminal_size().columns, 100))
            for row in rows:
                variant = f" ({row['variant']})" if row["variant"] != "canonical" else ""
                profiles = ", ".join(row["profiles"]) or "not selected"
                print(f"{row['id']}{variant} [{profiles}]")
                print(
                    textwrap.fill(
                        row["description"],
                        width,
                        initial_indent="  ",
                        subsequent_indent="  ",
                    )
                )
                print()
            print(f"{len(rows)} entries")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
