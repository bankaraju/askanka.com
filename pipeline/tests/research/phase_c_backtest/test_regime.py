import json
import pandas as pd
from pipeline.research.phase_c_backtest import regime


SAMPLE_WEIGHTS = {
    "optimal_weights": {"SPY": 0.5, "QQQ": 0.3, "GLD": -0.2},
    "thresholds": {
        "EUPHORIA":  0.015,
        "RISK-ON":   0.005,
        "NEUTRAL":   -0.005,
        "CAUTION":   -0.015,
        "RISK-OFF":  -1.0,
    },
}


def _bars(prices: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-04-19", periods=len(prices))
    return pd.DataFrame({"date": dates, "close": prices})


def test_compute_regime_for_date_strong_up(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    etf_bars = {
        "SPY": _bars([100, 102]),  # +2%
        "QQQ": _bars([100, 103]),  # +3%
        "GLD": _bars([100, 100]),  # flat
    }
    z = regime.compute_regime_for_date("2026-04-19", weights_file, etf_bars)
    assert z == "EUPHORIA"


def test_compute_regime_for_date_strong_down(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    etf_bars = {
        "SPY": _bars([100, 98]),
        "QQQ": _bars([100, 97]),
        "GLD": _bars([100, 100]),
    }
    z = regime.compute_regime_for_date("2026-04-19", weights_file, etf_bars)
    assert z == "RISK-OFF"


def test_backfill_regime_writes_json(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text(json.dumps(SAMPLE_WEIGHTS))
    out_file = tmp_path / "backfill.json"
    etf_bars = {
        "SPY": _bars([100, 101, 102, 100, 99, 101]),
        "QQQ": _bars([100, 102, 103, 99, 97, 102]),
        "GLD": _bars([100, 100, 100, 100, 100, 100]),
    }
    dates = etf_bars["SPY"]["date"].dt.strftime("%Y-%m-%d").tolist()[1:]  # skip first (no return)
    regime.backfill_regime(dates, weights_file, etf_bars, out_file)
    data = json.loads(out_file.read_text())
    assert set(data.keys()) == set(dates)
    for v in data.values():
        assert v in {"EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"}
