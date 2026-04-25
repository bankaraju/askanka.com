import numpy as np
import pandas as pd
import torch

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.train import (
    fit_model,
    panel_to_tensors,
    predict_proba,
)


def _toy_panel(n_train: int = 600, n_val: int = 200, n_tickers: int = 5, seed: int = 0):
    rng = np.random.default_rng(seed)
    rows = []
    feature_cols = [f"etf_x{i}" for i in range(8)] + [f"stock_x{i}" for i in range(4)]
    for split, n, label_bias in [("train", n_train, 0.0), ("val", n_val, 0.0)]:
        for i in range(n):
            row = {c: rng.normal() for c in feature_cols}
            row["ticker_id"] = int(rng.integers(0, n_tickers))
            # Force class signal: x0 > 0 → up, < 0 → down, else neutral
            row["label"] = (1 if abs(row["etf_x0"]) < 0.3
                            else (2 if row["etf_x0"] > 0 else 0))
            row["date"] = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
            row["split"] = split
            rows.append(row)
    df = pd.DataFrame(rows)
    return df, feature_cols


def test_fit_model_produces_lower_val_loss_than_random():
    df, feature_cols = _toy_panel()
    train = df[df["split"] == "train"].copy()
    val = df[df["split"] == "val"].copy()
    n_etf = sum(1 for c in feature_cols if c.startswith("etf_"))
    n_ctx = sum(1 for c in feature_cols if c.startswith("stock_"))
    model, history = fit_model(
        train_panel=train, val_panel=val, n_tickers=5,
        n_etf_features=n_etf, n_context=n_ctx,
        feature_cols=feature_cols, max_epochs=20,
    )
    # Random log-loss on 3-class is log(3) ≈ 1.0986
    assert history["best_val_loss"] < 1.0986


def test_predict_proba_returns_probabilities():
    df, feature_cols = _toy_panel(n_train=200, n_val=50)
    train, val = df[df["split"] == "train"], df[df["split"] == "val"]
    n_etf = sum(1 for c in feature_cols if c.startswith("etf_"))
    n_ctx = sum(1 for c in feature_cols if c.startswith("stock_"))
    model, _ = fit_model(train_panel=train, val_panel=val, n_tickers=5,
                        n_etf_features=n_etf, n_context=n_ctx,
                        feature_cols=feature_cols, max_epochs=5)
    probs = predict_proba(model, val, feature_cols)
    assert probs.shape == (len(val), 3)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)
