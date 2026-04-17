import pytest
from pipeline.telegram_bot import format_multi_spread_card


def test_spread_card_shows_enrichment_when_present():
    signal = {
        "signal_id": "SIG-TEST-010",
        "event": {"category": "test", "confidence": 0.8, "headline": "Test headline"},
        "spreads": [{
            "spread_name": "X vs Y",
            "tier": "SIGNAL",
            "hit_rate": 0.7,
            "n_precedents": 10,
            "expected_1d_spread": 1.0,
            "long_leg": [{"ticker": "HAL", "price": 100}],
            "short_leg": [{"ticker": "TCS", "price": 200}],
        }],
        "trust_scores": {
            "HAL": {"trust_grade": "A", "trust_score": 80},
            "TCS": {"trust_grade": "B+", "trust_score": 70},
        },
        "regime_rank": {"HAL": {"hit_rate": 0.62}, "TCS": {"hit_rate": 0.48}},
        "conviction_score": 72.5,
    }
    card = format_multi_spread_card(signal, regime="NEUTRAL")
    assert card  # not empty
    assert "CONV" in card
    assert "72" in card  # conviction rounded (72.5 → 72 via Python banker's rounding)
    assert "L HAL" in card
    assert "S TCS" in card


def test_spread_card_works_without_enrichment():
    signal = {
        "signal_id": "SIG-OLD",
        "event": {"category": "test", "confidence": 0.8, "headline": "No enrichment"},
        "spreads": [{
            "spread_name": "A vs B",
            "tier": "SIGNAL",
            "hit_rate": 0.7,
            "n_precedents": 10,
            "expected_1d_spread": 1.0,
            "long_leg": [{"ticker": "ABC", "price": 100}],
            "short_leg": [{"ticker": "DEF", "price": 200}],
        }],
    }
    card = format_multi_spread_card(signal, regime="NEUTRAL")
    assert card  # still produces a card
    assert "CONV" not in card  # no enrichment line
