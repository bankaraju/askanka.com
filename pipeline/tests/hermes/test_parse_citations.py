from pipeline.scripts.hermes.parse_citations import (
    extract_citations,
    extract_quotes,
    extract_quotes_loose,
)


def test_extracts_inline_citations():
    answer = """BH-FDR is a multiple-testing correction.

> "0 of 448 cells passed BH-FDR"
— docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md

Sources:
- docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
- docs/superpowers/specs/backtesting-specs.txt
"""
    cites = extract_citations(answer)
    assert "docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md" in cites
    assert "docs/superpowers/specs/backtesting-specs.txt" in cites
    assert len(cites) == 2


def test_extracts_quotes():
    answer = '''
> "Per-stock Lasso L1 logistic regression on ~60 daily TA features"
— docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md

> "0 of 448 cells passed BH-FDR"
— docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
'''
    quotes = extract_quotes(answer)
    assert len(quotes) == 2
    assert quotes[0]["text"].startswith("Per-stock Lasso L1")
    assert quotes[0]["source"].endswith("ta-karpathy-v1-design.md")


def test_no_citations_returns_empty():
    cites = extract_citations("just a plain answer with no sources")
    assert cites == []


def test_quote_without_dash_source_is_skipped():
    answer = '> "hello world"\n\nno source line'
    quotes = extract_quotes(answer)
    assert quotes == []


def test_extract_quotes_loose_counts_bare_quotes():
    """Loose counter accepts `> "..."` blocks with or without trailing path."""
    answer = '''Some prose.

> "first quote without path"

More prose.

> "second quote with path"
— docs/x.md

End.
'''
    loose = extract_quotes_loose(answer)
    assert len(loose) == 2
    assert loose[0] == "first quote without path"
    assert loose[1] == "second quote with path"
