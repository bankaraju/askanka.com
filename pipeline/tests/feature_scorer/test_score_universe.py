import json


def _build_models_fixture(tmp_path):
    """Minimal models.json with GREEN ticker + RED ticker."""
    data = {
        "fitted_at": "2026-04-22T01:00:00+05:30",
        "models": {
            "KAYNES": {
                "health": "GREEN", "source": "own",
                "mean_auc": 0.58, "min_fold_auc": 0.53,
                "coefficients": {
                    "sector_5d_return": 1.5, "sector_20d_return": 0.2,
                    "ticker_rs_10d": 0.8, "ticker_3d_momentum": 0.5,
                    "nifty_breadth_5d": 0.3, "pcr_z_score": 0.1,
                    "trust_grade_ordinal": 0.05, "realized_vol_60d": -0.1,
                    "regime_RISK-OFF": -0.2, "regime_NEUTRAL": 0.3,
                    "regime_RISK-ON": 0.1, "regime_EUPHORIA": 0.0, "regime_CRISIS": 0.0,
                    "dte_0_5": 0.1, "dte_6_15": 0.0, "dte_16_plus": -0.1,
                    "regime_NEUTRAL__x__trust_grade_ordinal": 0.2,
                    "regime_NEUTRAL__x__pcr_z_score": 0.15,
                    "sector_5d_return__x__ticker_rs_10d": 0.1,
                },
            },
            "THINCO": {"health": "RED", "source": "own", "reason": "thin history"},
        },
    }
    p = tmp_path / "models.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_score_universe_emits_scores_for_green_tickers_only(tmp_path, monkeypatch):
    from pipeline.feature_scorer import score_universe, storage
    models_path = _build_models_fixture(tmp_path)
    scores_path = tmp_path / "scores.json"
    snapshots_path = tmp_path / "snap.jsonl"

    monkeypatch.setattr(storage, "_MODELS_FILE", models_path, raising=False)
    monkeypatch.setattr(storage, "_SCORES_FILE", scores_path, raising=False)
    monkeypatch.setattr(storage, "_SNAPSHOTS_FILE", snapshots_path, raising=False)

    def fake_live_features(ticker):
        return {
            "sector_5d_return": 0.02, "sector_20d_return": 0.04,
            "ticker_rs_10d": 0.01, "ticker_3d_momentum": 0.01,
            "nifty_breadth_5d": 0.6, "pcr_z_score": 0.5,
            "trust_grade_ordinal": 3, "realized_vol_60d": 0.22,
            "regime_RISK-OFF": 0, "regime_NEUTRAL": 1, "regime_RISK-ON": 0,
            "regime_EUPHORIA": 0, "regime_CRISIS": 0,
            "dte_0_5": 1, "dte_6_15": 0, "dte_16_plus": 0,
        }
    monkeypatch.setattr(score_universe, "_build_live_features", fake_live_features, raising=False)

    exit_code = score_universe.main()
    assert exit_code == 0

    data = json.loads(scores_path.read_text(encoding="utf-8"))
    assert "KAYNES" in data["scores"]
    assert "THINCO" not in data["scores"]  # RED → skipped
    s = data["scores"]["KAYNES"]
    assert 0 <= s["score"] <= 100
    assert s["band"] == "GREEN"
    assert "top_features" in s and len(s["top_features"]) >= 3


def test_score_universe_appends_snapshots(tmp_path, monkeypatch):
    from pipeline.feature_scorer import score_universe, storage
    models_path = _build_models_fixture(tmp_path)
    snapshots_path = tmp_path / "snap.jsonl"
    monkeypatch.setattr(storage, "_MODELS_FILE", models_path, raising=False)
    monkeypatch.setattr(storage, "_SCORES_FILE", tmp_path / "scores.json", raising=False)
    monkeypatch.setattr(storage, "_SNAPSHOTS_FILE", snapshots_path, raising=False)
    monkeypatch.setattr(score_universe, "_build_live_features",
                         lambda t: {k: 0.01 for k in ["sector_5d_return", "sector_20d_return",
                                                        "ticker_rs_10d", "ticker_3d_momentum",
                                                        "nifty_breadth_5d", "pcr_z_score",
                                                        "trust_grade_ordinal", "realized_vol_60d",
                                                        "regime_RISK-OFF", "regime_NEUTRAL",
                                                        "regime_RISK-ON", "regime_EUPHORIA",
                                                        "regime_CRISIS", "dte_0_5", "dte_6_15",
                                                        "dte_16_plus"]}, raising=False)
    score_universe.main()
    lines = snapshots_path.read_text(encoding="utf-8").strip().split("\n")
    assert any('"ticker": "KAYNES"' in l for l in lines)


def test_live_feature_builder_returns_all_keys(monkeypatch, tmp_path):
    """_build_live_features on a known ticker returns all 16 expected feature keys."""
    import pandas as pd
    from pipeline.feature_scorer import score_universe

    monkeypatch.setattr(score_universe, "_load_today_regime",
                         lambda: {"zone": "NEUTRAL"}, raising=False)
    monkeypatch.setattr(score_universe, "_load_positioning",
                         lambda: {"KAYNES": {"pcr": 0.9, "days_to_expiry": 6}}, raising=False)
    monkeypatch.setattr(score_universe, "_load_trust_scores",
                         lambda: {"KAYNES": "B"}, raising=False)
    monkeypatch.setattr(score_universe, "_load_ticker_bars",
                         lambda t: pd.DataFrame({"date": pd.date_range("2026-01-01", periods=80, freq="B"),
                                                  "close": [100 + i * 0.1 for i in range(80)]}), raising=False)
    monkeypatch.setattr(score_universe, "_load_sector_bars",
                         lambda c: pd.DataFrame({"date": pd.date_range("2026-01-01", periods=80, freq="B"),
                                                  "close": [1000 + i * 0.5 for i in range(80)]}), raising=False)
    monkeypatch.setattr(score_universe, "_nifty_breadth_5d", lambda: 0.55, raising=False)

    v = score_universe._build_live_features("KAYNES")
    assert v is not None
    expected = {"sector_5d_return", "sector_20d_return", "ticker_rs_10d",
                "ticker_3d_momentum", "nifty_breadth_5d", "pcr_z_score",
                "trust_grade_ordinal", "realized_vol_60d",
                "regime_RISK-OFF", "regime_NEUTRAL", "regime_RISK-ON",
                "regime_EUPHORIA", "regime_CRISIS",
                "dte_0_5", "dte_6_15", "dte_16_plus"}
    assert set(v.keys()) == expected
