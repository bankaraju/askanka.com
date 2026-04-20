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
