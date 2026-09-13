# Manifest format, version 1

A UTF-8 TOML document with three top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `format_version` | Integer | Must be `1`. This versions the format, not the skills. |
| `sources` | Table of strings | Source names mapped to local skill directories. |
| `profiles` | Table of tables | Named selections and installation destinations. |

Source and profile names use lowercase letters, digits, and single hyphens between words.
Paths are absolute, relative to the manifest, or start with `~/`.
Other shell or environment-variable expansion is unsupported.
Sources are existing directories; Git URLs, revision pins, and cloning are outside this format.

## Profile fields

| Field | Required | Meaning |
| --- | --- | --- |
| `target` | Yes | Directory receiving the installed links. |
| `include` | Yes | List of `source/skill` identifiers or `source/*` selections. May be empty. |
| `exclude` | No | Exact included identifiers to remove. Defaults to `[]`. |
| `variants` | No | Selected identifiers mapped to variant names. Defaults to `{}`. |

`source/*` selects immediate child directories containing `SKILL.md`, including future additions.
There is no recursive discovery or general glob syntax.
Repeated selections of an identifier collapse into one entry; exclusions apply afterward.
An exclusion must match an included identifier.
Only sources referenced by the selected profile need to exist for installation.

The installed directory name is the skill's directory name, without the source prefix.
The frontmatter `name` must match that directory name.
Selecting the same installed name from two sources is an error; exclude one explicitly.
Skill names are lowercase letters, digits, and single hyphens between words, at most 64 characters.
A skill needs YAML frontmatter with a nonempty `description`, followed by a nonempty instruction body.

Unknown fields, missing selected sources or skill files, invalid selections, and name collisions are errors before installation changes any links.
Profile names do not select a model.
Profiles do not inherit from one another.

## Variants

```toml
[profiles.local.variants]
"team/check-refs" = "detailed"
```

This selects `variants/detailed.md` within the skill directory.
Variant names use the same character pattern as profile names and cannot contain paths.
An override must reference a selected skill and an existing variant file; there is no fallback.

A variant is a complete skill file with the canonical skill's `name`.
Its description and instructions can differ.
Resource links resolve from the installed skill root, such as `references/example.md`.
The installer links the variant as `SKILL.md` and shares the source's other entries, excluding the `variants` directory.
