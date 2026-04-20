from __future__ import annotations

import json
import pandas as pd
from pipeline.research.phase_c_backtest import profile


def _two_year_bars(symbol: str, drift: float, regimes: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Synthetic 500-day price series with constant daily drift; regimes is {date: zone}."""
    dates = pd.bdate_range(end="2026-03-31", periods=500)
    rng = __import__("numpy").random.default_rng(42)
    rets = rng.normal(loc=drift, scale=0.01, size=500)
    closes = 100 * (1 + rets).cumprod()
    df = pd.DataFrame({"date": dates, "close": closes, "open": closes, "high": closes, "low": closes, "volume": 100000})
    regime_dict = {d.strftime("%Y-%m-%d"): regimes.get(d.strftime("%Y-%m-%d"), "NEUTRAL") for d in dates}
    return df, regime_dict


def test_train_profile_no_lookahead(tmp_path):
    bars, _ = _two_year_bars("X", drift=0.001, regimes={})
    regime = {d: "NEUTRAL" for d in bars["date"].dt.strftime("%Y-%m-%d")}
    cutoff = "2025-01-01"
    prof = profile.train_profile(
        symbol_bars={"X": bars},
        regime_by_date=regime,
        cutoff_date=cutoff,
        lookback_years=2,
    )
    assert "X" in prof
    assert "NEUTRAL" in prof["X"]
    assert prof["X"]["NEUTRAL"]["n"] > 100


def test_train_profile_excludes_post_cutoff_data(tmp_path, monkeypatch):
    """Strict no-lookahead boundary test.

    Pre-cutoff bars are flat at 100. Post-cutoff bars explode +10%/day.
    If the cutoff-day close (or anything later) leaks into next_ret, the
    profile's expected_return blows up. Legitimate pre-cutoff returns are 0.
    """
    monkeypatch.setattr(profile, "_PROFILES_DIR", tmp_path)
    dates = pd.bdate_range(end="2026-03-31", periods=500)
    pre_n = 250
    pre_closes = [100.0] * pre_n
    post_closes = [100.0 * (1.10 ** (i + 1)) for i in range(len(dates) - pre_n)]
    closes = pre_closes + post_closes
    bars = pd.DataFrame({
        "date": dates, "close": closes, "open": closes,
        "high": closes, "low": closes, "volume": 1,
    })
    cutoff = dates[pre_n].strftime("%Y-%m-%d")
    regime = {d.strftime("%Y-%m-%d"): "NEUTRAL" for d in dates}
    prof = profile.train_profile({"X": bars}, regime, cutoff, lookback_years=5)
    # If post-cutoff leaked, expected_return would be enormous (~0.10).
    # Pre-cutoff is flat so legitimate expected_return ≈ 0.
    assert "X" in prof
    if "NEUTRAL" in prof["X"]:
        assert abs(prof["X"]["NEUTRAL"]["expected_return"]) < 1e-6


def test_train_profile_separates_regimes(tmp_path):
    bars, _ = _two_year_bars("X", drift=0.0, regimes={})
    dates = bars["date"].dt.strftime("%Y-%m-%d").tolist()
    regime = {d: ("RISK-ON" if i % 2 == 0 else "RISK-OFF") for i, d in enumerate(dates)}
    prof = profile.train_profile(
        symbol_bars={"X": bars},
        regime_by_date=regime,
        cutoff_date="2026-01-01",
        lookback_years=2,
    )
    assert "RISK-ON" in prof["X"]
    assert "RISK-OFF" in prof["X"]


def test_train_profile_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_PROFILES_DIR", tmp_path)
    bars, _ = _two_year_bars("X", drift=0.001, regimes={})
    regime = {d: "NEUTRAL" for d in bars["date"].dt.strftime("%Y-%m-%d")}
    profile.train_and_cache(
        symbol_bars={"X": bars},
        regime_by_date=regime,
        cutoff_date="2025-01-01",
        lookback_years=2,
    )
    cache = tmp_path / "profile_2025-01-01.json"
    assert cache.is_file()
    data = json.loads(cache.read_text())
    assert "X" in data


def test_train_profile_uses_cache_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_PROFILES_DIR", tmp_path)
    bars, _ = _two_year_bars("X", drift=0.001, regimes={})
    regime = {d: "NEUTRAL" for d in bars["date"].dt.strftime("%Y-%m-%d")}
    p1 = profile.train_and_cache({"X": bars}, regime, "2025-01-01", lookback_years=2)
    p2 = profile.train_and_cache({"X": bars}, regime, "2025-01-01", lookback_years=2)
    assert p1 == p2


def test_train_and_cache_recovers_from_corrupt_cache(tmp_path, monkeypatch):
    """A malformed cache file should be unlinked and re-trained, not raise."""
    monkeypatch.setattr(profile, "_PROFILES_DIR", tmp_path)
    cutoff = "2026-01-01"
    cache = tmp_path / f"profile_{cutoff}.json"
    cache.write_text("{ this is not valid json", encoding="utf-8")
    bars = pd.DataFrame({
        "date": pd.bdate_range(end="2025-12-31", periods=300),
        "close": [100.0 + i * 0.1 for i in range(300)],
        "open":  [100.0 + i * 0.1 for i in range(300)],
        "high":  [100.0 + i * 0.1 for i in range(300)],
        "low":   [100.0 + i * 0.1 for i in range(300)],
        "volume": 1,
    })
    regime = {d.strftime("%Y-%m-%d"): "NEUTRAL" for d in bars["date"]}
    prof = profile.train_and_cache({"X": bars}, regime, cutoff, lookback_years=2)
    assert "X" in prof
    assert json.loads(cache.read_text(encoding="utf-8")) == prof


def test_train_profile_skips_small_samples(tmp_path, monkeypatch):
    """Regimes with fewer than 5 next-day observations must be dropped."""
    monkeypatch.setattr(profile, "_PROFILES_DIR", tmp_path)
    bars = pd.DataFrame({
        "date": pd.bdate_range(end="2025-12-31", periods=300),
        "close": [100.0 + i * 0.1 for i in range(300)],
        "open":  [100.0 + i * 0.1 for i in range(300)],
        "high":  [100.0 + i * 0.1 for i in range(300)],
        "low":   [100.0 + i * 0.1 for i in range(300)],
        "volume": 1,
    })
    # Only 3 days labelled RARE, the rest COMMON.
    regime = {}
    for i, d in enumerate(bars["date"]):
        regime[d.strftime("%Y-%m-%d")] = "RARE" if i < 3 else "COMMON"
    prof = profile.train_profile({"X": bars}, regime, "2026-06-01", lookback_years=2)
    assert "RARE" not in prof.get("X", {})
    assert "COMMON" in prof.get("X", {})


def test_cutoff_dates_quarterly_cadence():
    out = profile.cutoff_dates_for_walk_forward("2024-01-01", "2025-01-01", refit_months=3)
    assert out == ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01"]


def test_cutoff_dates_snaps_to_month_start():
    out = profile.cutoff_dates_for_walk_forward("2024-01-15", "2024-12-31", refit_months=3)
    assert out == ["2024-02-01", "2024-05-01", "2024-08-01", "2024-11-01"]
