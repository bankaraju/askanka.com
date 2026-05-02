#!/usr/bin/env python3
"""Validate every source path in docs/faq/INDEX.md resolves to an existing file.

Exit 0 if all OK; exit 1 if any path is broken (with list).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INDEX = REPO_ROOT / "docs" / "faq" / "INDEX.md"

# Match lines like:  "  - docs/foo/bar.md  §X"  or  "  - memory/foo.md"
SOURCE_RE = re.compile(r'^\s*-\s+([\w./_-]+\.(?:md|txt|jsonl|json|py))(?:\s+§[\w.]+)?\s*$')

def main() -> int:
    if not INDEX.exists():
        print(f"FAIL: {INDEX} not found", file=sys.stderr)
        return 1

    broken: list[tuple[int, str]] = []
    in_sources_block = False

    for lineno, line in enumerate(INDEX.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("- Sources:"):
            in_sources_block = True
            continue
        if line.strip().startswith("###") or line.strip().startswith("##"):
            in_sources_block = False
            continue
        if not in_sources_block:
            continue

        m = SOURCE_RE.match(line)
        if not m:
            continue
        path = REPO_ROOT / m.group(1)
        if not path.exists():
            broken.append((lineno, m.group(1)))

    if broken:
        print(f"FAIL: {len(broken)} broken source path(s) in INDEX.md:")
        for lineno, path in broken:
            print(f"  L{lineno}: {path}")
        return 1
    print(f"PASS: all source paths in {INDEX} resolve")
    return 0

if __name__ == "__main__":
    sys.exit(main())
