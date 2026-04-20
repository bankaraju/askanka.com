import json
import pandas as pd
import pytest
from pipeline.research.phase_c_backtest import regime


# Just optimal_weights — no thresholds (live engine doesn't use them)
SAMPLE_WEIGHTS = {"optimal_weights": {"SPY": 0.5, "QQQ": 0.3, "GLD": -0.2}}


def _bars(prices: list[float]) -> pd.DataFrame:
    """Use Friday end so 2026-04-19 (Sunday) tests can fall back to it."""
    dates = pd.bdate_range(end="2026-04-17", periods=len(prices))  # Friday
    return pd.DataFrame({"date": dates, "close": prices})


def test_compute_regime_for_date_strong_up_is_euphoria(tmp_path):
    """Need signal in percent-space >= 7.89 to be EUPHORIA.
    Weighted return: 0.5*X + 0.3*Y + (-0.2)*Z, multiplied by 100."""
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    # SPY +20%, QQQ +20%, GLD -10% → signal = 0.5*20 + 0.3*20 + (-0.2)*(-10) = 18.0 percent
    etf_bars = {
        "SPY": _bars([100, 120]),
        "QQQ": _bars([100, 120]),
        "GLD": _bars([100, 90]),
    }
    z = regime.compute_regime_for_date("2026-04-17", weights_file, etf_bars)
    assert z == "EUPHORIA"


def test_compute_regime_for_date_strong_down_is_risk_off(tmp_path):
    """Need signal <= -7.70 to be RISK-OFF."""
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    # SPY -15%, QQQ -15%, GLD +5% → signal = 0.5*(-15) + 0.3*(-15) + (-0.2)*5 = -13.0 percent
    etf_bars = {
        "SPY": _bars([100, 85]),
        "QQQ": _bars([100, 85]),
        "GLD": _bars([100, 105]),
    }
    z = regime.compute_regime_for_date("2026-04-17", weights_file, etf_bars)
    assert z == "RISK-OFF"


def test_compute_regime_for_date_neutral_when_signal_small(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    # Tiny moves → signal very small → NEUTRAL
    etf_bars = {
        "SPY": _bars([100, 100.1]),
        "QQQ": _bars([100, 100.1]),
        "GLD": _bars([100, 100.1]),
    }
    z = regime.compute_regime_for_date("2026-04-17", weights_file, etf_bars)
    assert z == "NEUTRAL"


def test_backfill_regime_writes_sorted_json(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    out_file = tmp_path / "backfill.json"
    etf_bars = {
        "SPY": _bars([100, 120, 100, 130]),
        "QQQ": _bars([100, 120, 100, 130]),
        "GLD": _bars([100, 80, 110, 90]),
    }
    dates = etf_bars["SPY"]["date"].dt.strftime("%Y-%m-%d").tolist()[1:]
    regime.backfill_regime(dates, weights_file, etf_bars, out_file)
    raw = out_file.read_text()
    data = json.loads(raw)
    assert set(data.keys()) == set(dates)
    for v in data.values():
        assert v in regime.VALID_ZONES
    # Sort-key assertion: keys appear in sorted order in raw text
    keys_in_order = list(data.keys())
    assert keys_in_order == sorted(keys_in_order)


def test_daily_return_at_handles_weekend_target(tmp_path):
    """When target is a Sunday, fall back to most recent trading day."""
    bars = _bars([100, 110])  # ends Friday
    ret = regime._daily_return_at(bars, "2026-04-19")  # Sunday
    assert ret is not None
    assert ret == pytest.approx(0.10, abs=0.001)


def test_daily_return_at_returns_none_for_nan_close():
    bars = pd.DataFrame({
        "date": pd.bdate_range(end="2026-04-17", periods=2),
        "close": [100.0, float("nan")],
    })
    ret = regime._daily_return_at(bars, "2026-04-17")
    assert ret is None


def test_daily_return_at_returns_none_when_only_one_bar():
    bars = pd.DataFrame({"date": [pd.Timestamp("2026-04-17")], "close": [100.0]})
    ret = regime._daily_return_at(bars, "2026-04-17")
    assert ret is None


def test_compute_regime_raises_when_weights_empty(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps({"optimal_weights": {}}))
    with pytest.raises(ValueError, match="optimal_weights"):
        regime.compute_regime_for_date("2026-04-17", weights_file, {})
