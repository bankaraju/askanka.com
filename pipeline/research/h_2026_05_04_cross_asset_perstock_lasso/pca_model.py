"""PCA on the 30-CURATED-ETF 1d-return block. Frozen per fold."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA


@dataclass
class FrozenPCA:
    K_ETF: int
    mean_: np.ndarray
    std_: np.ndarray
    components_: np.ndarray  # (K_ETF, n_features)
    explained_variance_ratio_: np.ndarray  # full ratio (n_features,)
    cum_var_at_K: float
    feature_names_: list[str]


def fit_pca(X: pd.DataFrame, *, variance_target: float = 0.85, max_K: int = 12) -> FrozenPCA:
    """Fit PCA on training data only. Aborts if K_ETF > max_K (spec section 16 Check 2 cap)."""
    feat_names = list(X.columns)
    arr = X.values.astype(float)
    mu = arr.mean(axis=0)
    sd = arr.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (arr - mu) / sd

    n_comp = min(Z.shape[0], Z.shape[1])
    pca = PCA(n_components=n_comp).fit(Z)
    cum = np.cumsum(pca.explained_variance_ratio_)
    K = int(np.searchsorted(cum, variance_target)) + 1
    if K > max_K:
        raise ValueError(
            f"K_ETF={K} at variance_target={variance_target} exceeds cap max_K={max_K}. "
            "Feature library design failed; abort registration per spec section 16 Check 2."
        )

    return FrozenPCA(
        K_ETF=K,
        mean_=mu,
        std_=sd,
        components_=pca.components_[:K],
        explained_variance_ratio_=pca.explained_variance_ratio_,
        cum_var_at_K=float(cum[K - 1]),
        feature_names_=feat_names,
    )


def apply_pca(X: pd.DataFrame, model: FrozenPCA) -> pd.DataFrame:
    """Project X onto the frozen PCs using TRAINING-ONLY mean/std."""
    if list(X.columns) != model.feature_names_:
        raise ValueError(
            f"feature mismatch: expected {model.feature_names_[:3]}..., got {list(X.columns)[:3]}..."
        )
    arr = X.values.astype(float)
    Z = (arr - model.mean_) / model.std_
    proj = Z @ model.components_.T  # (n_rows, K_ETF)
    return pd.DataFrame(proj, index=X.index, columns=[f"PC{i + 1}" for i in range(model.K_ETF)])


def save_pca(model: FrozenPCA, path: Path) -> None:
    np.savez(
        path,
        K_ETF=model.K_ETF,
        mean_=model.mean_,
        std_=model.std_,
        components_=model.components_,
        explained_variance_ratio_=model.explained_variance_ratio_,
        cum_var_at_K=model.cum_var_at_K,
        feature_names_=np.array(model.feature_names_),
    )


def load_pca(path: Path) -> FrozenPCA:
    data = np.load(path, allow_pickle=False)
    return FrozenPCA(
        K_ETF=int(data["K_ETF"]),
        mean_=data["mean_"],
        std_=data["std_"],
        components_=data["components_"],
        explained_variance_ratio_=data["explained_variance_ratio_"],
        cum_var_at_K=float(data["cum_var_at_K"]),
        feature_names_=list(data["feature_names_"]),
    )
