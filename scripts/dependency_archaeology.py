"""Dependency archaeology for the strategy pack extraction.

Walks the AST of strategy-pack-candidate files, follows first-party imports
recursively, and reports:
  1. The minimal third-party package set required.
  2. The full first-party module call tree per strategy.
  3. Modules imported by candidates but not yet identified as candidates
     (these are the hidden dependencies that need promotion or refactor).

Usage:
    python scripts/dependency_archaeology.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent

# Seed candidates -- the production-grade alpha components.
SEEDS = [
    "pipeline/break_signal_generator.py",
    "pipeline/h_2026_04_26_001_paper.py",
    "pipeline/research/vwap_filter.py",
    "pipeline/research/neutral_cohort_tracker.py",
    "pipeline/autoresearch/etf_v3_curated_signal.py",
    "pipeline/etf_signal.py",
    "pipeline/signal_tracker.py",
    "pipeline/run_signals.py",
]


def find_imports(py_file: Path) -> tuple[set[str], set[str]]:
    """Return (third_party_top_level, first_party_modules) imported by py_file."""
    third = set()
    first = set()
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return third, first

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if _is_first_party(alias.name):
                    first.add(_resolve_first_party(alias.name))
                elif top and not _is_stdlib(top):
                    third.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            if _is_first_party(node.module):
                first.add(_resolve_first_party(node.module))
            elif top and not _is_stdlib(top):
                third.add(top)
    return third, first


_PIPELINE_TOP_MODULES = {
    p.stem for p in (REPO / "pipeline").glob("*.py")
} | {p.name for p in (REPO / "pipeline").iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def _is_first_party(modname: str) -> bool:
    top = modname.split(".")[0]
    if top in {"pipeline", "opus", "config"}:
        return True
    return top in _PIPELINE_TOP_MODULES


def _resolve_first_party(modname: str) -> str:
    """Convert sibling import `break_signal_generator` -> `pipeline.break_signal_generator`."""
    top = modname.split(".")[0]
    if top in _PIPELINE_TOP_MODULES and top not in {"pipeline", "opus", "config"}:
        return f"pipeline.{modname}"
    return modname


def _is_stdlib(top: str) -> bool:
    # Python 3.10+ stdlib_module_names; fall back to a hand-list for 3.9
    if hasattr(sys, "stdlib_module_names"):
        return top in sys.stdlib_module_names
    return top in {
        "os", "sys", "json", "re", "time", "datetime", "pathlib",
        "logging", "typing", "collections", "itertools", "functools",
        "dataclasses", "ast", "subprocess", "tempfile", "shutil", "io",
        "math", "random", "csv", "argparse", "warnings", "traceback",
        "threading", "asyncio", "uuid", "hashlib", "base64", "urllib",
        "http", "xml", "html", "email", "smtplib", "ssl", "socket",
        "struct", "enum", "abc", "copy", "pickle", "operator", "string",
        "textwrap", "calendar", "zoneinfo", "decimal", "statistics",
    }


def _path_for_module(modname: str) -> Path | None:
    """Convert pipeline.foo.bar -> /repo/pipeline/foo/bar.py if it exists."""
    p = REPO / Path(*modname.split("."))
    if p.with_suffix(".py").exists():
        return p.with_suffix(".py")
    if (p / "__init__.py").exists():
        return p / "__init__.py"
    return None


def walk(seeds: Iterable[str]) -> tuple[set[str], set[str], set[str]]:
    visited: set[str] = set()
    queue: list[Path] = []
    for s in seeds:
        p = REPO / s
        if p.exists():
            queue.append(p)

    third_total: set[str] = set()
    first_total: set[str] = set()
    while queue:
        f = queue.pop()
        rel = str(f.relative_to(REPO))
        if rel in visited:
            continue
        visited.add(rel)

        third, first = find_imports(f)
        third_total |= third
        first_total |= first

        for fp_mod in first:
            target = _path_for_module(fp_mod)
            if target is not None and str(target.relative_to(REPO)) not in visited:
                queue.append(target)

    return third_total, first_total, visited


def main() -> None:
    third, first, visited = walk(SEEDS)

    print("# Strategy Pack — Dependency Archaeology Report")
    print()
    print(f"**Seeds analyzed:** {len(SEEDS)}")
    print(f"**First-party files reached (transitively):** {len(visited)}")
    print(f"**Third-party top-level packages required:** {len(third)}")
    print()

    print("## Third-party packages (lean requirements_pack.txt set)")
    print()
    for pkg in sorted(third):
        print(f"- {pkg}")
    print()

    print("## First-party modules pulled in (the actual code surface)")
    print()
    for mod in sorted(first):
        print(f"- {mod}")
    print()

    print("## Files visited (transitive)")
    print()
    for f in sorted(visited):
        print(f"- {f}")


if __name__ == "__main__":
    main()
