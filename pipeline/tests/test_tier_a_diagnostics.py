"""Tests for pipeline.autoresearch.mechanical_replay.tier_a_diagnostics.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import tier_a_diagnostics as ta


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict]) -> Path:
    fields = [
        "signal_id", "ticker", "date", "regime", "classification",
        "sector", "side", "exit_reason", "pnl_pct", "abs_z", "z_bucket",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            full = {k: r.get(k, "") for k in fields}
            writer.writerow(full)
    return path


def _row(
    *,
    ticker: str,
    date: str,
    side: str,
    pnl_pct: float,
    abs_z: float = 2.5,
    classification: str = "POSSIBLE_OPPORTUNITY",
    sector: str = "Banks",
    regime: str = "RISK-OFF",
) -> dict:
    return {
        "signal_id": f"BRK-{date}-{ticker}",
        "ticker": ticker,
        "date": date,
        "regime": regime,
        "classification": classification,
        "sector": sector,
        "side": side,
        "exit_reason": "TIME_STOP",
        "pnl_pct": pnl_pct,
        "abs_z": abs_z,
        "z_bucket": "[2.0,3.0)" if abs_z < 3.0 else "[3.0,4.0)",
    }


# ---------------------------------------------------------------------------
# Test 1 — Trend-follow opposite inverts pnl
# ---------------------------------------------------------------------------

def test_trend_follow_opposite_inverts_pnl(tmp_path: Path) -> None:
    """Synthetic 4-row CSV; flipped-side pnl must equal -original pnl."""
    rows = [
        _row(ticker="AAA", date="2026-03-10", side="LONG",  pnl_pct=+1.50),
        _row(ticker="BBB", date="2026-03-11", side="LONG",  pnl_pct=-0.80),
        _row(ticker="CCC", date="2026-03-12", side="SHORT", pnl_pct=+2.00),
        _row(ticker="DDD", date="2026-03-13", side="SHORT", pnl_pct=-0.40),
    ]
    csv_path = _write_csv(tmp_path / "trades.csv", rows)
    df = ta.load_trades(csv_path)
    sigma = ta.filter_sigma_slice(df, 2.0)
    assert len(sigma) == 4

    out = ta.trend_follow_opposite(sigma)

    obs_sum = out["observed"]["sum_pnl_pct"]
    flipped_sum = out["flipped"]["sum_pnl_pct"]
    obs_mean = out["observed"]["mean_pnl_pct"]
    flipped_mean = out["flipped"]["mean_pnl_pct"]

    # flipped pnl = -original pnl, both per-trade and in aggregate
    assert flipped_sum == pytest.approx(-obs_sum, abs=1e-9)
    assert flipped_mean == pytest.approx(-obs_mean, abs=1e-9)

    # observed: 2 winners (1.50, 2.00) of 4 -> 50%
    assert out["observed"]["hits"] == 2
    assert out["observed"]["hit_rate_pct"] == pytest.approx(50.0, abs=1e-6)
    # flipped: complement -> 2 winners (0.80, 0.40) of 4 -> 50%
    assert out["flipped"]["hits"] == 2

    # observed mean = (1.5 - 0.8 + 2.0 - 0.4)/4 = 0.575
    assert obs_mean == pytest.approx(0.575, abs=1e-6)
    assert flipped_mean == pytest.approx(-0.575, abs=1e-6)


# ---------------------------------------------------------------------------
# Test 2 — Random-direction p-value is high when observed is at random
# ---------------------------------------------------------------------------

def test_random_direction_p_value_high_when_observed_at_random(tmp_path: Path) -> None:
    """Synthetic where realised hit rate is ~50%; p-value must be > 0.4."""
    # 20 trades, all with abs_z=2.5; alternating signs so observed hit
    # rate is exactly 50%. With Bernoulli(0.5) per trade the realised
    # hit count under random direction is also 50% in expectation, so
    # P(random >= observed) should be ~ 0.5.
    rows = []
    for i in range(20):
        sign = +1.0 if i % 2 == 0 else -1.0
        rows.append(_row(
            ticker=f"T{i:02d}",
            date=f"2026-03-{10 + (i % 18):02d}",
            side="LONG",
            pnl_pct=sign * 1.0,
            abs_z=2.5,
        ))
    csv_path = _write_csv(tmp_path / "trades.csv", rows)
    df = ta.load_trades(csv_path)
    sigma = ta.filter_sigma_slice(df, 2.0)
    assert len(sigma) == 20

    rng = np.random.default_rng(20260426)
    out = ta.random_direction_perm(sigma, n_perms=10_000, rng=rng)

    # observed is exactly 50%
    assert out["observed_hit_rate_pct"] == pytest.approx(50.0, abs=1e-6)
    # P(random >= 50%) for Bernoulli should be > 0.4 (and < 0.6)
    p = out["p_value_random_beats_observed"]
    assert 0.4 < p < 0.6, f"p-value {p} not in (0.4, 0.6) for at-random case"
    # And the diagnostic should not declare direction-alpha pass
    assert out["direction_alpha_pass"] is False


# ---------------------------------------------------------------------------
# Test 3 — Per-week stratification groups correctly
# ---------------------------------------------------------------------------

def test_per_week_stratification_groups_correctly(tmp_path: Path) -> None:
    """Verify the ISO-week bucketing groups dates correctly and computes
    per-week stats.

    Within ISO week 2026-W11 (Mon 2026-03-09 to Sun 2026-03-15) the
    inputs are 2026-03-10, 2026-03-12. Within 2026-W12 (Mon 2026-03-16
    to Sun 2026-03-22): 2026-03-17. Within 2026-W13: 2026-03-23,
    2026-03-25, 2026-03-27.
    """
    rows = [
        _row(ticker="AAA", date="2026-03-10", side="LONG",  pnl_pct=+1.0),
        _row(ticker="BBB", date="2026-03-12", side="LONG",  pnl_pct=+2.0),
        _row(ticker="CCC", date="2026-03-17", side="LONG",  pnl_pct=-0.5),
        _row(ticker="DDD", date="2026-03-23", side="SHORT", pnl_pct=+1.0),
        _row(ticker="EEE", date="2026-03-25", side="LONG",  pnl_pct=+2.0),
        _row(ticker="FFF", date="2026-03-27", side="LONG",  pnl_pct=-1.0),
    ]
    csv_path = _write_csv(tmp_path / "trades.csv", rows)
    df = ta.load_trades(csv_path)
    sigma = ta.filter_sigma_slice(df, 2.0)
    assert len(sigma) == 6

    out = ta.per_week_stationarity(sigma)

    weeks = {r["week_label"]: r for r in out["per_week"]}
    assert set(weeks.keys()) == {"2026-W11", "2026-W12", "2026-W13"}, weeks

    w11 = weeks["2026-W11"]
    assert w11["n_trades"] == 2
    assert w11["sum_pnl_pct"] == pytest.approx(3.0, abs=1e-6)
    assert w11["mean_pnl_pct"] == pytest.approx(1.5, abs=1e-6)
    assert w11["hits"] == 2
    assert w11["week_start"] == "2026-03-09"

    w12 = weeks["2026-W12"]
    assert w12["n_trades"] == 1
    assert w12["sum_pnl_pct"] == pytest.approx(-0.5, abs=1e-6)
    assert w12["mean_pnl_pct"] == pytest.approx(-0.5, abs=1e-6)
    assert w12["hits"] == 0

    w13 = weeks["2026-W13"]
    assert w13["n_trades"] == 3
    assert w13["sum_pnl_pct"] == pytest.approx(2.0, abs=1e-6)
    assert w13["hits"] == 2

    # ordering by week_start
    labels = [r["week_label"] for r in out["per_week"]]
    assert labels == ["2026-W11", "2026-W12", "2026-W13"]

    # totals consistency
    total = sum(r["sum_pnl_pct"] for r in out["per_week"])
    assert out["total_pnl_pct"] == pytest.approx(total, abs=1e-6)
    assert out["n_weeks"] == 3
    # 2 of 3 weeks positive (W11 +, W13 +), W12 negative
    assert out["n_positive_weeks"] == 2


# ---------------------------------------------------------------------------
# Bonus: end-to-end smoke (ensures CLI orchestrator + JSON round-trip)
# ---------------------------------------------------------------------------

def test_run_tier_a_end_to_end(tmp_path: Path) -> None:
    """Smoke: run the full orchestrator on a small synthetic CSV."""
    rows = []
    # 10 winners as LONG, 10 winners as SHORT, with mostly positive pnl,
    # spread across 4 ISO weeks.
    dates_w1 = ["2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13"]
    dates_w2 = ["2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20"]
    dates_w3 = ["2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27"]
    dates_w4 = ["2026-03-31", "2026-04-01", "2026-04-02", "2026-04-03"]
    all_dates = dates_w1 + dates_w2 + dates_w3 + dates_w4
    for i, d in enumerate(all_dates):
        side = "LONG" if i % 2 == 0 else "SHORT"
        # mostly positive
        pnl = +1.5 if i % 5 != 0 else -0.5
        rows.append(_row(
            ticker=f"T{i:02d}", date=d, side=side, pnl_pct=pnl, abs_z=2.5,
        ))
    csv_path = _write_csv(tmp_path / "trades.csv", rows)

    summary = ta.run_tier_a(
        in_sample_csv=csv_path,
        sigma_threshold=2.0,
        n_perms_random_dir=2_000,
        seed=20260426,
    )
    assert summary["n_observed_trades"] == 16
    assert summary["sigma_threshold"] == 2.0
    assert "tier_a1_trend_follow_opposite" in summary
    assert "tier_a2_random_direction" in summary
    assert "tier_a3_per_week_stationarity" in summary
    assert isinstance(summary["overall_tier_a_pass"], bool)

    # JSON round-trip
    blob = json.dumps(summary)
    parsed = json.loads(blob)
    assert parsed["hypothesis_id"] == "H-2026-04-26-001"

    # Markdown render must include all three section headers
    md = ta.render_report(summary)
    assert "Tier A.1" in md
    assert "Tier A.2" in md
    assert "Tier A.3" in md
    assert "Bottom-line verdict" in md
