import json
import pandas as pd
import pytest


def _synthetic_ticker_history(n_days=300):
    """Minimal synthetic history for testing."""
    import numpy as np
    rng = np.random.default_rng(7)
    dates = pd.date_range("2023-01-01", periods=n_days, freq="B")
    df = pd.DataFrame({
        "date": dates,
        "close": 100 + np.cumsum(rng.normal(0, 0.5, n_days)),
    })
    return df


@pytest.fixture
def toy_fitter_env(tmp_path, monkeypatch):
    """Set up a minimal fitter environment with 3 tickers."""
    from pipeline.feature_scorer import fit_universe, storage

    def fake_load_prices(ticker):
        return _synthetic_ticker_history(300)

    def fake_load_sector_bars(cohort):
        df = _synthetic_ticker_history(300)
        df = df.rename(columns={"y": "y_unused"})
        return df

    def fake_load_regime_history():
        return {}  # empty → fitter fills NEUTRAL

    def fake_ticker_universe():
        return ["KAYNES", "TCS", "HDFCBANK"]

    def fake_fit_one(ticker, sector_df, regime_map, as_of):
        """Stub out _fit_one to speed up test."""
        return {
            "health": "GREEN",
            "source": "own",
            "mean_auc": 0.58,
            "folds": [],
            "coefficients": {},
        }

    monkeypatch.setattr(fit_universe, "_load_ticker_prices", fake_load_prices, raising=False)
    monkeypatch.setattr(fit_universe, "_load_sector_bars", fake_load_sector_bars, raising=False)
    monkeypatch.setattr(fit_universe, "_load_regime_history", fake_load_regime_history, raising=False)
    monkeypatch.setattr(fit_universe, "_ticker_universe", fake_ticker_universe, raising=False)
    monkeypatch.setattr(fit_universe, "_fit_one", fake_fit_one, raising=False)
    monkeypatch.setattr(storage, "_MODELS_FILE", tmp_path / "models.json", raising=False)
    return tmp_path


def test_fit_universe_writes_models_json(toy_fitter_env):
    from pipeline.feature_scorer.fit_universe import main
    result = main()
    assert result == 0
    models_file = toy_fitter_env / "models.json"
    assert models_file.exists()
    data = json.loads(models_file.read_text(encoding="utf-8"))
    assert "models" in data
    assert set(data["models"].keys()) == {"KAYNES", "TCS", "HDFCBANK"}


def test_fit_universe_models_carry_health_and_source(toy_fitter_env):
    from pipeline.feature_scorer.fit_universe import main
    main()
    models_file = toy_fitter_env / "models.json"
    data = json.loads(models_file.read_text(encoding="utf-8"))
    for ticker, m in data["models"].items():
        assert m["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
        assert m["source"] in ("own", "sector_cohort")


def test_fit_universe_with_real_fit_one(tmp_path, monkeypatch):
    """Test _fit_one logic directly with synthetic data (no full walk-forward)."""
    from pipeline.feature_scorer import fit_universe, storage
    import numpy as np

    def fake_load_prices(ticker):
        return _synthetic_ticker_history(300)

    def fake_load_sector_bars(cohort):
        df = _synthetic_ticker_history(300)
        df = df.rename(columns={"y": "y_unused"})
        return df

    def fake_load_regime_history():
        return {}

    monkeypatch.setattr(fit_universe, "_load_ticker_prices", fake_load_prices, raising=False)
    monkeypatch.setattr(fit_universe, "_load_sector_bars", fake_load_sector_bars, raising=False)
    monkeypatch.setattr(fit_universe, "_load_regime_history", fake_load_regime_history, raising=False)
    monkeypatch.setattr(storage, "_MODELS_FILE", tmp_path / "models.json", raising=False)

    # Call _fit_one directly
    prices = fake_load_prices("TEST")
    sector_df = fake_load_sector_bars("NIFTYIT")
    regime_map = {}
    result = fit_universe._fit_one("TEST", sector_df, regime_map, "2024-01-01")

    # Verify result structure
    assert "health" in result
    assert result["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
    assert "source" in result
    assert result["source"] in ("own", "sector_cohort")
