"""
Tests for apply_news_modifier — Task B7: news verdicts modify candidate conviction.
"""
import pytest
from pipeline.signal_enrichment import apply_news_modifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _verdict(symbol, category, recommendation, impact, title="Event"):
    return {
        "symbol": symbol,
        "category": category,
        "recommendation": recommendation,
        "impact": impact,
        "event_title": title,
    }


# ---------------------------------------------------------------------------
# Single-ticker tests
# ---------------------------------------------------------------------------

def test_high_impact_add_lifts_long():
    signal = {
        "ticker": "SUZLON",
        "category": "results_announcement",
        "direction": "LONG",
        "entry_score": 50,
    }
    verdicts = [
        _verdict("SUZLON", "results_announcement", "ADD", "HIGH_IMPACT", "Q4 beat"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 10
    assert out["entry_score"] == 60
    ctx = out.get("news_context", "")
    assert "SUZLON" in ctx or "Q4" in ctx


def test_moderate_add_lifts_long_by_5():
    signal = {
        "ticker": "RELIANCE",
        "category": "results_announcement",
        "direction": "LONG",
        "entry_score": 55,
    }
    verdicts = [
        _verdict("RELIANCE", "results_announcement", "ADD", "MODERATE"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 5
    assert out["entry_score"] == 60


def test_high_impact_cut_fades_long():
    signal = {
        "ticker": "X",
        "category": "mgmt_change",
        "direction": "LONG",
        "entry_score": 60,
    }
    verdicts = [
        _verdict("X", "mgmt_change", "CUT", "HIGH_IMPACT"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == -10
    assert out["entry_score"] == 50


def test_moderate_cut_fades_long_by_5():
    signal = {
        "ticker": "Y",
        "category": "mgmt_change",
        "direction": "LONG",
        "entry_score": 65,
    }
    verdicts = [
        _verdict("Y", "mgmt_change", "CUT", "MODERATE"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == -5
    assert out["entry_score"] == 60


def test_no_match_returns_zero_modifier():
    signal = {
        "ticker": "X",
        "category": "results",
        "direction": "LONG",
        "entry_score": 50,
    }
    verdicts = [
        _verdict("Y", "results", "ADD", "HIGH_IMPACT"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 0
    assert out["entry_score"] == 50


def test_ambiguous_combination_yields_zero():
    signal = {
        "ticker": "X",
        "category": "c",
        "direction": "LONG",
        "entry_score": 50,
    }
    verdicts = [
        _verdict("X", "c", "NO_ACTION", "HIGH_IMPACT"),
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 0
    assert out["entry_score"] == 50


def test_low_impact_add_yields_zero():
    """LOW_IMPACT and NO_IMPACT never yield a modifier."""
    signal = {
        "ticker": "A",
        "category": "cat",
        "direction": "LONG",
        "entry_score": 50,
    }
    for impact in ("LOW", "NO_IMPACT"):
        verdicts = [_verdict("A", "cat", "ADD", impact)]
        out = apply_news_modifier(signal, verdicts)
        assert out["news_modifier"] == 0, f"Expected 0 for impact={impact}"
        assert out["entry_score"] == 50


def test_cut_aligned_with_short():
    """CUT + SHORT direction = aligned → +10."""
    signal = {
        "ticker": "Z",
        "category": "results",
        "direction": "SHORT",
        "entry_score": 50,
    }
    verdicts = [_verdict("Z", "results", "CUT", "HIGH_IMPACT")]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 10
    assert out["entry_score"] == 60


def test_add_opposite_to_short():
    """ADD contradicts SHORT direction → -10."""
    signal = {
        "ticker": "Z",
        "category": "results",
        "direction": "SHORT",
        "entry_score": 60,
    }
    verdicts = [_verdict("Z", "results", "ADD", "HIGH_IMPACT")]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == -10
    assert out["entry_score"] == 50


def test_does_not_mutate_input():
    signal = {
        "ticker": "SUZLON",
        "category": "results_announcement",
        "direction": "LONG",
        "entry_score": 50,
    }
    verdicts = [_verdict("SUZLON", "results_announcement", "ADD", "HIGH_IMPACT")]
    original_score = signal["entry_score"]
    apply_news_modifier(signal, verdicts)
    assert signal["entry_score"] == original_score  # input unchanged


def test_empty_verdicts():
    signal = {
        "ticker": "X",
        "category": "cat",
        "direction": "LONG",
        "entry_score": 50,
    }
    out = apply_news_modifier(signal, [])
    assert out["news_modifier"] == 0
    assert out["entry_score"] == 50


# ---------------------------------------------------------------------------
# Spread signal tests
# ---------------------------------------------------------------------------

def test_spread_signal_aggregates_leg_deltas_capped_at_15():
    signal = {
        "spread_name": "Test",
        "long_legs": [
            {"ticker": "A", "category": "results_announcement"},
            {"ticker": "B", "category": "results_announcement"},
        ],
        "short_legs": [
            {"ticker": "C", "category": "results_announcement"},
        ],
        "entry_score": 50,
    }
    verdicts = [
        _verdict("A", "results_announcement", "ADD", "HIGH_IMPACT"),
        _verdict("B", "results_announcement", "ADD", "HIGH_IMPACT"),
        _verdict("C", "results_announcement", "CUT", "HIGH_IMPACT"),
    ]
    # A +10 (LONG+ADD+HIGH), B +10 (LONG+ADD+HIGH), C +10 (SHORT+CUT+HIGH) = 30 → capped at 15
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 15
    assert out["entry_score"] == 65


def test_spread_signal_negative_cap():
    """Negative leg deltas capped at -15."""
    signal = {
        "spread_name": "NegTest",
        "long_legs": [
            {"ticker": "A", "category": "cat"},
            {"ticker": "B", "category": "cat"},
        ],
        "short_legs": [
            {"ticker": "C", "category": "cat"},
        ],
        "entry_score": 50,
    }
    verdicts = [
        # All legs adverse
        _verdict("A", "cat", "CUT", "HIGH_IMPACT"),   # LONG+CUT = -10
        _verdict("B", "cat", "CUT", "HIGH_IMPACT"),   # LONG+CUT = -10
        _verdict("C", "cat", "ADD", "HIGH_IMPACT"),   # SHORT+ADD = -10
    ]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == -15
    assert out["entry_score"] == 35


def test_spread_contributing_legs_stored():
    """Spread: contributing legs list is non-empty when there are matching verdicts."""
    signal = {
        "spread_name": "S",
        "long_legs": [{"ticker": "A", "category": "cat"}],
        "short_legs": [],
        "entry_score": 50,
    }
    verdicts = [_verdict("A", "cat", "ADD", "HIGH_IMPACT", "Good news")]
    out = apply_news_modifier(signal, verdicts)
    legs = out.get("news_contributing_legs", [])
    assert len(legs) >= 1
    assert any(l.get("ticker") == "A" for l in legs)


def test_spread_no_match_zero_modifier():
    signal = {
        "spread_name": "S",
        "long_legs": [{"ticker": "A", "category": "cat"}],
        "short_legs": [{"ticker": "B", "category": "cat"}],
        "entry_score": 50,
    }
    verdicts = [_verdict("Z", "cat", "ADD", "HIGH_IMPACT")]
    out = apply_news_modifier(signal, verdicts)
    assert out["news_modifier"] == 0
    assert out["entry_score"] == 50
