"""Minimal stdlib YAML frontmatter parser for SKILL.md files."""

from __future__ import annotations

import json
import re
from pathlib import Path

KEY_LINE = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*)|\s*)$")


def strip_inline_comment(value: str) -> str:
    """Remove an unquoted inline YAML comment preceded by whitespace."""
    for index, char in enumerate(value):
        if char == "#" and index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
    return value.rstrip()


def parse_block_header(text: str) -> tuple[str, str, int | None] | None:
    cleaned = strip_inline_comment(text)
    if not cleaned or cleaned[0] not in "|>":
        return None
    style = cleaned[0]
    rest = cleaned[1:]
    chomp = ""
    indent: int | None = None
    for char in rest:
        if char in "+-" and not chomp:
            chomp = char
        elif char.isdigit() and char != "0" and indent is None:
            indent = int(char)
        else:
            return None
    return style, chomp, indent


def parse_block_scalar(
    lines: list[str], start: int, style: str, chomp: str, explicit_indent: int | None
) -> tuple[str, int]:
    raw: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if line == "" or line[0] == " ":
            raw.append(line)
            index += 1
        else:
            break
    indent = explicit_indent
    if indent is None:
        for line in raw:
            if line.strip():
                indent = len(line) - len(line.lstrip(" "))
                break
    if indent is None:
        return ("\n" * len(raw) if chomp == "+" else ""), index
    stripped = [line[indent:] if len(line) >= indent else "" for line in raw]
    trailing_blanks = 0
    while stripped and stripped[-1] == "":
        stripped.pop()
        trailing_blanks += 1
    if not stripped:
        return ("\n" * trailing_blanks if chomp == "+" else ""), index
    if style == "|":
        text = "\n".join(stripped)
    else:
        parts: list[str] = []
        for idx, line in enumerate(stripped):
            if idx == 0:
                parts.append(line)
                continue
            prev = stripped[idx - 1]
            if line == "":
                parts.append("\n")
            elif prev == "":
                parts.append(line)
            elif line[0].isspace() or prev[0].isspace():
                parts.append("\n" + line)
            else:
                parts.append(" " + line)
        text = "".join(parts)
    if chomp == "-":
        return text, index
    if chomp == "+":
        return text + "\n" * (trailing_blanks + 1), index
    return text + "\n", index


def parse_quoted(lines: list[str], start: int, raw: str, quote: str) -> tuple[str, int]:
    collected = raw
    index = start
    while True:
        if quote == '"':
            escaped = False
            end = -1
            for pos in range(1, len(collected)):
                ch = collected[pos]
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    end = pos
                    break
            if end != -1:
                after = strip_inline_comment(collected[end + 1 :])
                if after:
                    raise ValueError(f"unexpected content after quoted string: {after}")
                try:
                    encoded = collected[: end + 1].replace("\n", "\\n")
                    return json.loads(encoded), index + 1
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid double-quoted string: {exc}") from exc
        else:
            pos = 1
            end = -1
            while pos < len(collected):
                if collected[pos] == "'":
                    if pos + 1 < len(collected) and collected[pos + 1] == "'":
                        pos += 2
                        continue
                    end = pos
                    break
                pos += 1
            if end != -1:
                after = strip_inline_comment(collected[end + 1 :])
                if after:
                    raise ValueError(f"unexpected content after quoted string: {after}")
                return collected[1:end].replace("''", "'"), index + 1
        index += 1
        if index >= len(lines):
            raise ValueError("unclosed quoted string in frontmatter")
        continuation = lines[index].strip()
        collected += (" " + continuation) if continuation else "\n"


def parse_plain_value(
    lines: list[str], start: int, first: str
) -> tuple[object, int]:
    parts = [strip_inline_comment(first)]
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line == "":
            parts.append("")
            index += 1
        elif line[0] == " ":
            parts.append(strip_inline_comment(line.strip()))
            index += 1
        else:
            break
    while parts and parts[-1] == "":
        parts.pop()
    if len(parts) == 1:
        scalar = parts[0]
        lowered = scalar.lower()
        if lowered in {"true", "false"}:
            return lowered == "true", index
        if lowered in {"null", "~"}:
            return None, index
        return scalar, index
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx == 0:
            out.append(part)
        elif part == "":
            out.append("\n")
        elif parts[idx - 1] == "":
            out.append(part)
        else:
            out.append(" " + part)
    return "".join(out), index


def parse_frontmatter(text: str, label: Path | str = "frontmatter") -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a Markdown file without external libraries."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{label}: missing frontmatter")
    end = None
    for idx in range(1, len(lines)):
        if lines[idx] in {"---", "..."}:
            end = idx
            break
    if end is None:
        raise ValueError(f"{label}: unclosed frontmatter")
    header = lines[1:end]
    body = "\n".join(lines[end + 1 :])
    data: dict[str, object] = {}
    index = 0
    while index < len(header):
        line = header[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[0].isspace():
            raise ValueError(f"{label}: unexpected indentation in frontmatter")
        match = KEY_LINE.match(line)
        if not match:
            raise ValueError(f"{label}: frontmatter must be a mapping")
        key, rest = match.group(1), match.group(2)
        if key in data:
            raise ValueError(f"{label}: duplicate frontmatter key: {key}")
        if rest is None or not strip_inline_comment(rest):
            # Nested block (mapping or sequence) or empty value.
            nested: list[str] = []
            index += 1
            while index < len(header):
                sub = header[index]
                if not sub.strip() or sub[0] == " ":
                    nested.append(sub)
                    index += 1
                else:
                    break
            has_content = any(
                item.strip() and not item.lstrip().startswith("#") for item in nested
            )
            data[key] = nested if has_content else None
            continue
        block = parse_block_header(rest)
        if block is not None:
            style, chomp, explicit_indent = block
            value, index = parse_block_scalar(
                header, index + 1, style, chomp, explicit_indent
            )
            data[key] = value
        elif rest[0] in {'"', "'"}:
            value, index = parse_quoted(header, index, rest, rest[0])
            data[key] = value
        else:
            value, index = parse_plain_value(header, index, rest)
            data[key] = value
    return data, body
