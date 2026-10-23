#!/usr/bin/env python3
"""Reject unresolved placeholders in rendered deployment files.

Only file names, line numbers, and marker categories are reported. File
contents and resolved values are never printed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MARKER_PATTERNS = {
    "REPLACE_WITH": re.compile(r"(?<![A-Z0-9])REPLACE_WITH_[A-Z0-9_]+(?![A-Z0-9])"),
    "CHANGE_ME": re.compile(r"(?<![A-Z0-9])CHANGE_ME(?:_[A-Z0-9_]+)?(?![A-Z0-9])"),
    "YOUR": re.compile(r"(?<![A-Z0-9])YOUR_[A-Z0-9_]+(?![A-Z0-9])"),
}

KNOWN_TEMPLATE_LITERALS = {
    "your-product-image-bucket",
    "your-user-pool-id",
    "your-spa-app-client-id",
}

COMMENT_PREFIXES = ("#", "--")


def marker_categories(text: str) -> set[str]:
    categories = {
        category
        for category, pattern in MARKER_PATTERNS.items()
        if pattern.search(text)
    }
    if any(literal in text for literal in KNOWN_TEMPLATE_LITERALS):
        categories.add("KNOWN_TEMPLATE_VALUE")
    return categories


def scan_text(path: Path, text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(COMMENT_PREFIXES):
            continue
        findings.extend(
            (line_number, category) for category in sorted(marker_categories(line))
        )
    return findings


def validate_json(path: Path, text: str) -> str | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        return f"invalid JSON at line {error.lineno}, column {error.colno}"
    return None


def validate_file(path: Path) -> tuple[list[tuple[int, str]], str | None]:
    if not path.is_file():
        return [], "file does not exist or is not a regular file"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [], "file cannot be read as UTF-8 text"

    format_error = validate_json(path, text)
    if format_error:
        return [], format_error
    return scan_text(path, text), None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate rendered deployment files before installation"
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="rendered files that will actually be installed or applied",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failed = False

    for path in args.files:
        findings, error = validate_file(path)
        if error:
            print(f"ERROR {path}: {error}", file=sys.stderr)
            failed = True
            continue
        for line_number, category in findings:
            print(
                f"ERROR {path}:{line_number}: unresolved placeholder ({category})",
                file=sys.stderr,
            )
            failed = True

    if failed:
        print("Deployment preflight failed", file=sys.stderr)
        return 1

    print(f"Deployment preflight passed for {len(args.files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
