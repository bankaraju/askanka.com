"""Cross-surface reconciliation: one fixture, matching badges across Python
surfaces (Telegram card + future terminal renders). The marketing website no
longer inlines badge thresholds — that surface was dropped when index.html
was cryptified (commit 7f465e2)."""
from pipeline.signal_badges import trust_badge, rank_badge, conviction_badge


FIXTURE = {
    "signal_id": "SIG-RECON",
    "event": {"category": "test", "confidence": 0.85, "headline": "Reconciliation"},
    "spreads": [{
        "spread_name": "HAL vs TCS",
        "tier": "SIGNAL",
        "hit_rate": 0.7,
        "n_precedents": 20,
        "expected_1d_spread": 1.2,
        "long_leg": [{"ticker": "HAL", "price": 4000}],
        "short_leg": [{"ticker": "TCS", "price": 2500}],
    }],
    "trust_scores": {
        "HAL": {"trust_grade": "A", "trust_score": 80},
        "TCS": {"trust_grade": "C", "trust_score": 35},
    },
    "regime_rank": {"HAL": {"hit_rate": 0.62}, "TCS": {"hit_rate": 0.48}},
    "conviction_score": 68.0,
}


def test_python_badges_correct():
    assert trust_badge("A")["tone"] == "strong"
    assert trust_badge("A")["label"] == "A"
    assert trust_badge("C")["tone"] == "weak"
    assert trust_badge("C")["label"] == "C"
    assert rank_badge(0.62)["tone"] == "strong"
    assert rank_badge(0.62)["label"] == "62%"
    assert conviction_badge(68.0)["tone"] == "strong"
    assert conviction_badge(68.0)["label"] == "68"


def test_telegram_card_carries_badges():
    from pipeline.telegram_bot import format_multi_spread_card
    card = format_multi_spread_card(FIXTURE, regime="NEUTRAL")
    assert "CONV 68" in card
    assert "L HAL A" in card
    assert "S TCS C" in card


