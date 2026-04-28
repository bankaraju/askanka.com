"""Locks Daily-alongside-Total rendering on the Telegram EOD dashboard.

Mirrors the rule already enforced for the terminal positions header in
`pipeline/tests/terminal/test_positions_table_js.py`:

    Anywhere a basket Total P&L is rendered, render Daily next to it.
    If any position is missing `todays_move`, render Daily as "-" rather
    than a partial sum (memory: feedback_daily_pnl_alongside_total.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from telegram_bot import format_eod_dashboard  # noqa: E402


def _open_positions(today_a: float | None, today_b: float | None) -> list[dict]:
    return [
        {
            "tier": "SIGNAL",
            "spread_pnl_pct": 8.0,
            "todays_move": today_a,
            "days_open": 6,
            "spread_name": "Defensive Rotation",
        },
        {
            "tier": "EXPLORING",
            "spread_pnl_pct": 1.9,
            "todays_move": today_b,
            "days_open": 1,
            "spread_name": "Commodity-Credit Divergence",
        },
    ]


def _kwargs(open_positions, daily_pnl_pct):
    return dict(
        regime="RISK_OFF",
        open_positions=open_positions,
        portfolio_pnl=4.95,
        daily_pnl_pct=daily_pnl_pct,
        cumulative_pnl=12.3,
        days_active=14,
        signal_stats={"wins": 3, "losses": 1, "avg_pnl": 2.1},
        exploring_stats={"wins": 1, "losses": 2, "avg_pnl": -0.4},
    )


def test_header_shows_daily_alongside_total():
    text = format_eod_dashboard(**_kwargs(_open_positions(-0.05, 1.68), 1.63))
    # Both labels must appear on the basket-level header.
    assert "TODAY" in text and "TOTAL" in text
    # The summed daily figure renders, not just the cumulative.
    assert "+1.63%" in text
    # The cumulative-since-entry total still renders.
    assert "+4.95%" in text


def test_header_shows_dash_when_any_position_lacks_todays_move():
    text = format_eod_dashboard(**_kwargs(_open_positions(None, 1.68), None))
    # Daily falls back to em-dash when any position is missing today's move,
    # to avoid a partial-sum that under-represents the day.
    assert "TODAY" in text
    assert "TODAY: —" in text or "TODAY: -" in text
    # Total still renders normally.
    assert "+4.95%" in text


def test_per_position_line_shows_today_alongside_total():
    text = format_eod_dashboard(**_kwargs(_open_positions(-0.05, 1.68), 1.63))
    # Per-position line must include today's contribution next to cumulative.
    # +8.00% is cumulative since entry; -0.05% is today's move.
    assert "+8.00%" in text
    assert "today -0.05%" in text or "today: -0.05%" in text
