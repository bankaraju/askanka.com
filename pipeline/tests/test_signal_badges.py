import pytest
from pipeline.signal_badges import (
    trust_badge,
    break_badge,
    rank_badge,
    conviction_badge,
)


class TestTrustBadge:
    def test_trust_badge_grades(self):
        assert trust_badge("A+") == {"emoji": "🟢", "label": "A+", "tone": "strong"}
        assert trust_badge("A") == {"emoji": "🟢", "label": "A", "tone": "strong"}
        assert trust_badge("B+") == {"emoji": "🟡", "label": "B+", "tone": "ok"}
        assert trust_badge("B") == {"emoji": "🟡", "label": "B", "tone": "ok"}
        assert trust_badge("C") == {"emoji": "🔴", "label": "C", "tone": "weak"}
        assert trust_badge("F") == {"emoji": "🔴", "label": "F", "tone": "weak"}
        assert trust_badge(None) == {"emoji": "⚪", "label": "—", "tone": "none"}


class TestBreakBadge:
    def test_break_badge(self):
        assert break_badge("MOMENTUM_CONFIRM") == {
            "emoji": "🟢",
            "label": "CONFIRM",
            "tone": "strong",
        }
        assert break_badge("POSSIBLE_OPPORTUNITY") == {
            "emoji": "🟡",
            "label": "OPPO",
            "tone": "ok",
        }
        assert break_badge("DIVERGENCE_WARNING") == {
            "emoji": "🔴",
            "label": "DIVERGE",
            "tone": "weak",
        }
        assert break_badge(None) == {"emoji": "⚪", "label": "—", "tone": "none"}
        assert break_badge("UNKNOWN_TYPE")["emoji"] == "⚪"


class TestRankBadge:
    def test_rank_badge_from_hit_rate(self):
        assert rank_badge(0.75) == {"emoji": "🟢", "label": "75%", "tone": "strong"}
        assert rank_badge(0.55) == {"emoji": "🟡", "label": "55%", "tone": "ok"}
        assert rank_badge(0.40) == {"emoji": "🔴", "label": "40%", "tone": "weak"}
        assert rank_badge(None) == {"emoji": "⚪", "label": "—", "tone": "none"}
        assert rank_badge(0.60) == {"emoji": "🟢", "label": "60%", "tone": "strong"}
        assert rank_badge(0.50) == {"emoji": "🟡", "label": "50%", "tone": "ok"}


class TestConvictionBadge:
    def test_conviction_badge_thresholds(self):
        assert conviction_badge(80) == {"emoji": "🟢", "label": "80", "tone": "strong"}
        assert conviction_badge(55) == {"emoji": "🟡", "label": "55", "tone": "ok"}
        assert conviction_badge(30) == {"emoji": "🔴", "label": "30", "tone": "weak"}
        assert conviction_badge(None) == {"emoji": "⚪", "label": "—", "tone": "none"}
        assert conviction_badge(65) == {"emoji": "🟢", "label": "65", "tone": "strong"}
        assert conviction_badge(40) == {"emoji": "🟡", "label": "40", "tone": "ok"}
