"""Training loop with class-balanced sampling, AdamW, and early-stop."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.model import EtfStockTailMlp


def panel_to_tensors(
    panel: pd.DataFrame,
    feature_cols: Sequence[str],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    etf_cols = [c for c in feature_cols if c.startswith("etf_")]
    ctx_cols = [c for c in feature_cols if c.startswith("stock_")]
    etf_x = torch.tensor(panel[etf_cols].values, dtype=torch.float32)
    ctx_x = torch.tensor(panel[ctx_cols].values, dtype=torch.float32)
    ticker_ids = torch.tensor(panel["ticker_id"].values, dtype=torch.long)
    labels = torch.tensor(panel["label"].values, dtype=torch.long)
    return etf_x, ctx_x, ticker_ids, labels


def _class_balanced_sampler(labels: torch.Tensor) -> WeightedRandomSampler:
    counts = torch.bincount(labels, minlength=C.N_CLASSES).float()
    weights_per_class = 1.0 / counts.clamp(min=1.0)
    sample_weights = weights_per_class[labels]
    return WeightedRandomSampler(sample_weights.tolist(), num_samples=len(labels), replacement=True)


def fit_model(
    train_panel: pd.DataFrame,
    val_panel: pd.DataFrame,
    n_tickers: int,
    n_etf_features: int,
    n_context: int,
    feature_cols: Sequence[str],
    max_epochs: int = C.MAX_EPOCHS,
    seed: int = C.RANDOM_SEED,
) -> tuple[EtfStockTailMlp, dict]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    etf_t, ctx_t, tid_t, lab_t = panel_to_tensors(train_panel, feature_cols)
    etf_v, ctx_v, tid_v, lab_v = panel_to_tensors(val_panel, feature_cols)

    train_ds = TensorDataset(etf_t, ctx_t, tid_t, lab_t)
    sampler = _class_balanced_sampler(lab_t)
    train_loader = DataLoader(train_ds, batch_size=C.BATCH_SIZE, sampler=sampler)

    model = EtfStockTailMlp(n_etf_features=n_etf_features, n_context=n_context, n_tickers=n_tickers)
    optimizer = torch.optim.AdamW(model.param_groups(), lr=C.LR)
    loss_fn = nn.CrossEntropyLoss()

    best_val = math.inf
    best_state = None
    epochs_no_improve = 0
    history: list[dict] = []

    for epoch in range(max_epochs):
        model.train()
        for etf_b, ctx_b, tid_b, lab_b in train_loader:
            optimizer.zero_grad()
            logits = model(etf_b, ctx_b, tid_b)
            loss = loss_fn(logits, lab_b)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(etf_v, ctx_v, tid_v)
            val_loss = float(loss_fn(val_logits, lab_v).item())
        history.append({"epoch": epoch, "val_loss": val_loss})

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= C.EARLY_STOP_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, {"best_val_loss": best_val, "history": history, "epochs_run": len(history)}


def predict_proba(
    model: EtfStockTailMlp,
    panel: pd.DataFrame,
    feature_cols: Sequence[str],
) -> np.ndarray:
    etf_x, ctx_x, tid_x, _ = panel_to_tensors(panel, feature_cols)
    model.eval()
    with torch.no_grad():
        logits = model(etf_x, ctx_x, tid_x)
        probs = torch.softmax(logits, dim=-1).numpy()
    return probs
