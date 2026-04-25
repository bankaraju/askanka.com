"""EtfStockTailMlp — small multi-task MLP with per-ticker embedding and 3-class head."""
from __future__ import annotations

import torch
import torch.nn as nn

from pipeline.autoresearch.etf_stock_tail import constants as C


class EtfStockTailMlp(nn.Module):
    def __init__(self, n_etf_features: int, n_context: int, n_tickers: int,
                 embed_dim: int = C.EMBEDDING_DIM):
        super().__init__()
        self.embedding = nn.Embedding(n_tickers, embed_dim)
        in_dim = n_etf_features + n_context + embed_dim
        self.trunk = nn.Sequential(
            nn.Linear(in_dim, C.TRUNK_HIDDEN_1), nn.ReLU(), nn.Dropout(C.DROPOUT),
            nn.Linear(C.TRUNK_HIDDEN_1, C.TRUNK_HIDDEN_2), nn.ReLU(), nn.Dropout(C.DROPOUT),
            nn.Linear(C.TRUNK_HIDDEN_2, C.N_CLASSES),
        )

    def forward(self, etf_x: torch.Tensor, ctx_x: torch.Tensor, ticker_ids: torch.Tensor) -> torch.Tensor:
        e = self.embedding(ticker_ids)
        x = torch.cat([etf_x, ctx_x, e], dim=-1)
        return self.trunk(x)

    def param_groups(self) -> list[dict]:
        """Return AdamW-ready parameter groups with separate weight decays."""
        embed_params = list(self.embedding.parameters())
        trunk_params = [p for p in self.trunk.parameters()]
        return [
            {"params": trunk_params, "weight_decay": C.WEIGHT_DECAY_TRUNK},
            {"params": embed_params, "weight_decay": C.WEIGHT_DECAY_EMBEDDING},
        ]
