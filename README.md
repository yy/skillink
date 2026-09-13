# Skillink

A TOML manifest and a few scripts for managing AI agent skills with symlinks.
Keep skills in their own repositories, choose which ones each agent receives, and inspect the resulting links.

Local prototype, extracted from a working dotfiles setup.
Requires [uv](https://docs.astral.sh/uv/) and Git.
There is no background service or registry.

## Try it

From this repository:

```bash
uv run bin/list_skills.py --manifest examples/skills.toml
uv run bin/install_skills.py demo --manifest examples/skills.toml --dry-run
uv run bin/install_skills.py demo --manifest examples/skills.toml
uv run bin/install_skills.py demo --manifest examples/skills.toml --check
uv run bin/list_skills.py --manifest examples/skills.toml --open
```

The example installs one greeting skill into `.demo/skills/` inside this checkout.
It does not change your agent settings.

## Your manifest

Put `skills.toml` in your dotfiles repository or another directory you maintain:

```toml
format_version = 1

[sources]
personal = "skills"
team = "../team-skills/skills"

[profiles.claude]
target = "~/.claude/skills"
include = ["personal/*", "team/*"]

[profiles.pi]
target = "~/.pi/agent/skills"
include = ["personal/review", "team/check-refs"]

# Optional, once the file exists:
# [profiles.pi.variants]
# "team/check-refs" = "detailed"
```

Paths resolve relative to the manifest; `~/` expands to your home directory.
The scripts look for `skills.toml` in the current working directory by default.
Pass `--manifest /path/to/skills.toml` to use another location.
See [SPEC.md](SPEC.md) for the complete format.

## Three helpers

| Script | Purpose |
| --- | --- |
| `bin/install_skills.py PROFILE` | Validate a profile and reconcile its symlinks. Supports `--dry-run`, `--check`, `--safe`, `--migrate`, and `--target`. |
| `bin/list_skills.py` | List names, descriptions, and profiles. Use a search term, `--profile`, `--html [PATH]`, or `--open`. |
| `bin/update_sources.py` | Find the source checkouts and update each once with `git pull --ff-only`. Use `--dry-run` to preview without network requests. |

The updater skips dirty checkouts and branches without an upstream, continues through failures, and exits nonzero if any source could not be updated.
It never clones, commits, rebases, or resets repositories.
Update sources and install profiles as separate steps so you can review incoming changes first.

The catalog is a self-contained HTML file with search, filters, and expandable instructions.
It contains local skill content; keep private catalogs local.

## Installation behavior

Each destination records owned links in `.skillink.json`.
The installer checks the selected sources and destination conflicts before modifying links.
It preserves unrelated files and refuses to replace managed entries that someone has changed.

`--safe` only adds missing entries; it leaves existing and obsolete entries alone.
`--migrate` can adopt legacy links into manifest source roots and replace a whole-directory source symlink with individual skill links.
It does not overwrite arbitrary directories.

The default skill is `SKILL.md`.
A selected `variants/detailed.md` replaces the instruction file while retaining shared scripts, references, and assets.
Variants are complete skill files with the same frontmatter name as the canonical skill.

A profile manages its target directory, not every location the agent scans.
Configure additional discovery paths and duplicate plugin loading in the agent itself.

## Development

```bash
uv run --python 3.11 --with pyyaml python -m unittest discover -s tests -v
uvx ruff check bin tests
```
