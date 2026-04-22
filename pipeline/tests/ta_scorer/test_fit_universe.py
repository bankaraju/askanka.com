import json
import pandas as pd
import numpy as np
from pathlib import Path
import pytest

from pipeline.ta_scorer import fit_universe


def _seed_csv(path: Path, n=600, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close - 0.3, "High": close + 0.8, "Low": close - 0.8,
        "Close": close, "Volume": 1_000_000,
    })
    df.to_csv(path, index=False)


def test_fit_universe_writes_reliance_model(tmp_path, monkeypatch):
    hist = tmp_path / "fno_historical"
    idx = tmp_path / "india_historical" / "indices"
    hist.mkdir(parents=True)
    idx.mkdir(parents=True)
    _seed_csv(hist / "RELIANCE.csv", n=750, seed=1)
    _seed_csv(idx / "NIFTYENERGY_daily.csv", n=750, seed=2)
    _seed_csv(idx / "NIFTY_daily.csv", n=750, seed=3)

    out_models = tmp_path / "ta_feature_models.json"

    monkeypatch.setattr(fit_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(fit_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(fit_universe, "_MODELS_OUT", out_models)

    exit_code = fit_universe.main()
    assert exit_code == 0
    assert out_models.exists()
    data = json.loads(out_models.read_text(encoding="utf-8"))
    assert "RELIANCE" in data["models"]
    assert data["models"]["RELIANCE"]["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
