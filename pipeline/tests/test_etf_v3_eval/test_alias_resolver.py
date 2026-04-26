"""Tests for Phase 2 alias resolver — 4 Phase 1 alias gaps from §17 caveat (c)."""
from pipeline.autoresearch.etf_v3_eval.phase_2.alias_resolver import (
    resolve_alias,
    KNOWN_ALIASES,
)


def test_known_aliases_present():
    """The 4 Phase 1 fail tickers are in the alias registry with explicit
    resolve-to symbol or None for documented exclusion."""
    assert "L&TFH" in KNOWN_ALIASES
    assert "LTIM" in KNOWN_ALIASES
    assert "MCDOWELL-N" in KNOWN_ALIASES
    assert "ZOMATO" in KNOWN_ALIASES


def test_resolve_alias_returns_modern_symbol_or_none():
    """Each value is either a modern symbol (str) or None (documented exclusion)."""
    for old, new in KNOWN_ALIASES.items():
        assert new is None or isinstance(new, str), f"{old}: bad mapping value {new!r}"


def test_resolve_alias_passthrough_for_unknown():
    """Unknown tickers return themselves unchanged."""
    assert resolve_alias("RELIANCE") == "RELIANCE"
