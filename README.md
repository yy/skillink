# Skillink

A TOML manifest and a few zero-dependency Python scripts for managing AI agent skills with symlinks.
Keep skills in their own repositories, choose which ones each agent receives, and inspect the resulting links.

An early prototype, extracted from a working dotfiles setup.
Requires Python 3.11+ (stdlib only, no third-party packages; runs with `python3` or [uv](https://docs.astral.sh/uv/)) and Git.
There is no background service, package registry, or npm dependency tree.
Released under the [MIT license](LICENSE).

## Try it

From this repository:

```bash
python3 bin/list_skills.py --manifest examples/skills.toml
python3 bin/install_skills.py demo --manifest examples/skills.toml --dry-run
python3 bin/install_skills.py demo --manifest examples/skills.toml
python3 bin/install_skills.py demo --manifest examples/skills.toml --check
python3 bin/install_skills.py demo --manifest examples/skills.toml --audit
python3 bin/list_skills.py --manifest examples/skills.toml --open
```

The example installs one greeting skill into `.demo/skills/` inside this checkout.
It does not change your agent settings.

## Your manifest

Keep your manifest in your configuration repository, for example `~/git/dotfiles/skillink/skills.toml`:

```toml
format_version = 1

[sources]
personal = "../skills"
team = "../../team-skills/skills"
public = "../../public-skills/skills"

[profiles.claude]
target = "~/.claude/skills"
include = ["personal/*", "team/*", "public/check-refs"]

[profiles.pi]
target = "~/.pi/agent/skills"
include = ["personal/review", "public/check-refs"]

# Optional, once the file exists:
# [profiles.pi.variants]
# "public/check-refs" = "detailed"
```

Paths resolve relative to the manifest; `~/` expands to your home directory.
Link it into your user configuration once:

```bash
mkdir -p ~/.config/skillink
ln -s ~/git/dotfiles/skillink/skills.toml ~/.config/skillink/skills.toml
```

All three scripts use the same lookup order: `--manifest`, then `SKILLINK_MANIFEST`, then `$XDG_CONFIG_HOME/skillink/skills.toml` (default `~/.config/skillink/skills.toml`).
They do not search the working directory or the tool checkout.
Relative source and target paths resolve from the real manifest file, even when accessed through a symlink.
See [SPEC.md](SPEC.md) for the complete format.

## Three helpers

| Script | Purpose |
| --- | --- |
| `bin/install_skills.py PROFILE` | Validate a profile and reconcile its symlinks. Supports `--dry-run`, `--check`, `--audit`, `--safe`, `--migrate`, `--import-state`, and `--target`. |
| `bin/list_skills.py` | List names, descriptions, and profiles. Use a search term, `--profile`, `--html [PATH]`, or `--open`. |
| `bin/update_sources.py` | Fetch clean source checkouts and summarize incoming commits without changing live files. Use `--diff` to inspect diffs, `--apply` to fast-forward with `git pull --ff-only`, or `--dry-run` to preview without network requests. |

By default, `bin/update_sources.py` only fetches and reports incoming commits (`PENDING`) so live symlinked skills do not change before you inspect upstream commits.
Use `--diff` to inspect the full incoming diff, then run `--apply` to fast-forward once you are satisfied.
The updater skips dirty checkouts and branches without an upstream (including detached/pinned commits), continues through failures, and exits nonzero if any source could not be fetched, diverged, or failed to update.
It never clones, commits, rebases, or resets repositories.

The catalog is a self-contained HTML file with search, filters, and expandable instructions.
It contains full local skill instructions and file paths; keep private catalogs local.
Generated files are readable only by their owner (`0600`) and ignored by this repository.
The tools do not upload catalogs or skill content; only the source updater contacts the configured Git remotes.

## Safety and installation behavior

Each destination records owned links in `.skillink.json` and belongs to one manifest/profile pair.
The installer checks the selected sources, symlink boundaries, and destination conflicts before modifying links.
It rejects any symlink inside a source skill that escapes its configured source root (and rejects `SKILL.md` or variant symlinks that escape their skill directory).
It preserves unrelated files and refuses to replace managed entries that someone has changed.

When a profile already has a `.skillink.json`, `--dry-run` and normal installs annotate newly discovered wildcard skills (`(new via source/*)`).
Use `--audit` to inspect a profile without modifying links: it flags wildcard inclusions (`source/*`), newly appeared wildcard skills, executable files, script files, hidden dotfiles, and internal symlinks inside selected skills (exiting `1` when findings are reported).
For third-party or public repositories, prefer explicit `source/skill` entries over `source/*`.

`--safe` only adds missing entries; it leaves existing and obsolete entries alone.
`--migrate` can adopt legacy links into manifest source roots and replace a whole-directory source symlink with individual skill links.
It does not overwrite arbitrary directories.

### Import an existing ownership record

For installations using the predecessor's version-1 JSON ownership format, import the record before reconciling skills:

```bash
python3 bin/install_skills.py claude --import-state ~/.claude/skills/.dotfiles-skills.json --dry-run
python3 bin/install_skills.py claude --import-state ~/.claude/skills/.dotfiles-skills.json
python3 bin/install_skills.py claude --check
```

The import file must be in the target directory and contain `version`, `manifest`, `profile`, and `skills` fields in Skillink's state format.
Import verifies the manifest/profile identity and all existing owned links, preserves ownership of obsolete entries, writes `.skillink.json`, and archives the original as `<filename>.migrated`.
It leaves skill links and unrelated files unchanged and refuses conflicting records or an existing archive.
`--dry-run` previews the transfer; `--check` reports a pending import without writing.
Use a normal installation afterward to reconcile any changes to the manifest.

The default skill is `SKILL.md`.
A selected `variants/detailed.md` replaces the instruction file while retaining shared scripts, references, and assets.
Variants are complete skill files with the same frontmatter name as the canonical skill.

A profile manages its target directory, not every location the agent scans.
Configure additional discovery paths and duplicate plugin loading in the agent itself.

## Development

```bash
python3 -m unittest discover -s tests -v
uvx ruff check bin tests
```
