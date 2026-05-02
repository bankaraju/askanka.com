"""Extract citations and verbatim-quote blocks from a SKILL-compliant answer.

A SKILL-compliant quote looks like:
    > "the quoted text"
    — docs/path/to/source.md

A SKILL-compliant Sources section looks like:
    Sources:
    - docs/path/one.md
    - docs/path/two.md
"""
from __future__ import annotations
import re

QUOTE_RE = re.compile(
    r'^\s*>\s*"(?P<text>.+?)"\s*\n\s*[—-]\s*(?P<source>[\w./_-]+\.(?:md|txt|jsonl|json|py))',
    re.MULTILINE,
)
SOURCE_LINE_RE = re.compile(
    r'^\s*-\s+([\w./_-]+\.(?:md|txt|jsonl|json|py))(?:\s+§[\w.]+)?\s*$',
    re.MULTILINE,
)


def extract_quotes(answer: str) -> list[dict]:
    """Return list of {text, source} for every SKILL-compliant quote block."""
    return [
        {"text": m.group("text"), "source": m.group("source")}
        for m in QUOTE_RE.finditer(answer)
    ]


def extract_citations(answer: str) -> list[str]:
    """Return de-duped, order-preserving list of all cited source paths.

    Includes paths from blockquote `— path` lines AND from the Sources: bullet list.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in QUOTE_RE.finditer(answer):
        path = m.group("source")
        if path not in seen:
            seen.add(path)
            out.append(path)
    in_sources = False
    for line in answer.splitlines():
        if line.strip().lower().startswith("sources:"):
            in_sources = True
            continue
        if in_sources:
            sm = SOURCE_LINE_RE.match(line)
            if sm:
                p = sm.group(1)
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            elif line.strip() == "":
                continue
            else:
                in_sources = False
    return out
