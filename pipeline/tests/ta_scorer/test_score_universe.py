import json
import pandas as pd
import numpy as np
from pathlib import Path

from pipeline.ta_scorer import score_universe, fit_universe


def _seed_csv(path: Path, n=750, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close - 0.3, "High": close + 0.8, "Low": close - 0.8,
        "Close": close, "Volume": 1_000_000,
    })
    df.to_csv(path, index=False)


def test_score_universe_writes_reliance_score(tmp_path, monkeypatch):
    hist = tmp_path / "fno_historical"
    idx = tmp_path / "india_historical" / "indices"
    hist.mkdir(parents=True)
    idx.mkdir(parents=True)
    _seed_csv(hist / "RELIANCE.csv", 750, 1)
    _seed_csv(idx / "NIFTYENERGY_daily.csv", 750, 2)
    _seed_csv(idx / "NIFTY_daily.csv", 750, 3)

    models_path = tmp_path / "ta_feature_models.json"
    scores_path = tmp_path / "ta_attractiveness_scores.json"

    monkeypatch.setattr(fit_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(fit_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(fit_universe, "_MODELS_OUT", models_path)
    monkeypatch.setattr(score_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(score_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(score_universe, "_MODELS_IN", models_path)
    monkeypatch.setattr(score_universe, "_SCORES_OUT", scores_path)

    assert fit_universe.main() == 0
    assert score_universe.main() == 0

    data = json.loads(scores_path.read_text(encoding="utf-8"))
    assert "RELIANCE" in data["scores"]
    rec = data["scores"]["RELIANCE"]
    assert rec["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
    assert isinstance(rec["top_features"], list)
    # When model health is GREEN/AMBER, the scorer produces a 0-100 score.
    # For synthetic random-walk data the fit typically lands on RED/UNAVAILABLE,
    # in which case the scorer short-circuits with score=None and band=UNAVAILABLE.
    if rec["score"] is not None:
        assert 0 <= rec["score"] <= 100
        assert rec["band"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
    else:
        assert rec["band"] == "UNAVAILABLE"
