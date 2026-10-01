#!/usr/bin/env python3
"""Compare dotenv configuration contracts without reporting their values."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "0.1.0"
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
REFERENCE = re.compile(r"(?<!\\)\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-|:\?|\?)([^}]*))?\}")
PLACEHOLDERS = {"changeme", "change-me", "replace-me", "replace_me", "your-value-here", "todo"}


@dataclass
class Document:
    values: dict[str, str] = field(default_factory=dict)
    expandable: dict[str, bool] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)


def issue(code: str, key: str | None = None, line: int | None = None, **extra) -> dict:
    result = {"code": code, **extra}
    if key is not None:
        result["key"] = key
    if line is not None:
        result["line"] = line
    return result


def parse(text: str) -> Document:
    """Parse a conservative dotenv subset; no evaluation or environment reads."""
    doc = Document()
    lines = text.lstrip("\ufeff").splitlines()
    index = 0
    while index < len(lines):
        start = index + 1
        raw = lines[index].strip()
        index += 1
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[7:].lstrip()
        if "=" not in raw:
            doc.issues.append(issue("invalid-assignment", line=start))
            continue
        key, value = raw.split("=", 1)
        key, value = key.strip(), value.lstrip()
        if not KEY.fullmatch(key):
            doc.issues.append(issue("invalid-key", line=start))
            continue
        expandable = True
        if value.startswith(("'", '"')):
            quote = value[0]
            expandable = quote == '"'
            chunks = []
            rest = value[1:]
            closed = False
            while True:
                position = None
                for offset, char in enumerate(rest):
                    if char != quote:
                        continue
                    backslashes = 0
                    for previous in reversed(rest[:offset]):
                        if previous != "\\":
                            break
                        backslashes += 1
                    if quote == "'" or backslashes % 2 == 0:
                        position = offset
                        break
                if position is not None:
                    chunks.append(rest[:position])
                    trailing = rest[position + 1:].strip()
                    if trailing and not trailing.startswith("#"):
                        doc.issues.append(issue("trailing-content", key, start))
                    closed = True
                    break
                chunks.append(rest)
                if index >= len(lines):
                    break
                rest = lines[index]
                index += 1
            if not closed:
                doc.issues.append(issue("unclosed-quote", key, start))
                continue
            value = "\n".join(chunks)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if key in doc.values:
            doc.issues.append(issue("duplicate-key", key, start))
        doc.values[key] = value
        doc.expandable[key] = expandable
    return doc


def references(doc: Document, key: str) -> list[tuple[str, str | None, str | None]]:
    if not doc.expandable.get(key, False):
        return []
    return [(m[1], m[2], m[3]) for m in REFERENCE.finditer(doc.values[key])]


def inspect(doc: Document, required: set[str] | None = None) -> list[dict]:
    result = list(doc.issues)
    keys = set(doc.values)
    for key in sorted(required or ()):
        if key not in keys:
            result.append(issue("missing-key", key))
    graph = {}
    for key in sorted(keys):
        value = doc.values[key]
        if not value.strip():
            result.append(issue("empty-value", key))
        elif value.lower().strip() in PLACEHOLDERS or re.fullmatch(r"<[^<>]+>", value.strip()):
            result.append(issue("placeholder-value", key))
        graph[key] = []
        for ref, operator, default in references(doc, key):
            usable = ref in keys and (bool(doc.values[ref]) or operator not in (":-", ":?"))
            if operator in ("-", ":-") and not usable:
                continue
            if ref not in keys:
                result.append(issue("unresolved-reference", key, reference=ref))
            elif operator == ":?" and not doc.values[ref]:
                result.append(issue("unresolved-reference", key, reference=ref))
            else:
                graph[key].append(ref)
    # Iterative graph traversal handles long configuration chains without recursion.
    visited, active, cycles = set(), set(), set()
    for root in sorted(keys):
        stack = [(root, False)]
        while stack:
            key, leaving = stack.pop()
            if leaving:
                active.discard(key)
                visited.add(key)
                continue
            if key in active:
                cycles.add(key)
                continue
            if key in visited:
                continue
            active.add(key)
            stack.append((key, True))
            stack.extend((child, False) for child in reversed(graph[key]))
    result.extend(issue("cyclic-reference", key) for key in sorted(cycles))
    return result


def compare(reference: Document, target: Document, allow_extra: bool = False) -> list[dict]:
    result = inspect(target, set(reference.values))
    result.extend({**item, "source": "reference"} for item in reference.issues)
    for key in sorted(set(target.values) - set(reference.values)):
        if not allow_extra:
            result.append(issue("extra-key", key))
    return result


def read(path: str) -> Document:
    return parse(Path(path).read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check syntax, duplicates, placeholders and references")
    check.add_argument("file")
    check.add_argument("--required", help="Reference dotenv file defining required keys")
    diff = commands.add_parser("diff", help="Compare a reference contract with a target dotenv file")
    diff.add_argument("reference")
    diff.add_argument("target")
    diff.add_argument("--allow-extra", action="store_true")
    template = commands.add_parser("template", help="Export keys only, with empty values")
    template.add_argument("file")
    for sub in (check, diff):
        sub.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            doc = read(args.file)
            if doc.issues:
                print("Cannot generate a template from invalid or duplicate assignments.", file=sys.stderr)
                return 2
            print("\n".join(key + "=" for key in sorted(doc.values)))
            return 0
        if args.command == "diff":
            findings = compare(read(args.reference), read(args.target), args.allow_extra)
        else:
            doc = read(args.file)
            reference = read(args.required) if args.required else None
            findings = inspect(doc, set(reference.values) if reference else None)
            if reference:
                findings.extend({**item, "source": "reference"} for item in reference.issues)
        report = {"version": __version__, "ok": not findings, "count": len(findings), "issues": findings}
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=True, indent=2))
        elif not findings:
            print("OK: configuration contract satisfied.")
        else:
            for item in findings:
                # All printable content comes from validated keys, fixed codes or integers.
                detail = " ".join(f"{k}={v}" for k, v in item.items() if k != "code")
                print(f"{item['code']}: {detail}")
            print(f"{len(findings)} issue(s). Configuration values are never included.")
        return 0 if not findings else 1
    except (OSError, UnicodeError):
        print("Cannot read input as UTF-8. Check the path and permissions.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
