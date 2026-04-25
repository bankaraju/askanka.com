import pytest
import torch

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.model import EtfStockTailMlp


def test_forward_shape():
    n_etf, n_ctx, n_tickers = 90, 6, 211
    model = EtfStockTailMlp(n_etf_features=n_etf, n_context=n_ctx, n_tickers=n_tickers)
    batch = 4
    etf_x = torch.randn(batch, n_etf)
    ctx_x = torch.randn(batch, n_ctx)
    ticker_ids = torch.randint(0, n_tickers, (batch,))
    out = model(etf_x, ctx_x, ticker_ids)
    assert out.shape == (batch, C.N_CLASSES)


def test_param_groups_have_right_weight_decay():
    model = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    groups = model.param_groups()
    by_decay = {g["weight_decay"]: g for g in groups}
    assert C.WEIGHT_DECAY_TRUNK in by_decay
    assert C.WEIGHT_DECAY_EMBEDDING in by_decay
    # embedding params live ONLY in the embedding group
    embed_params = list(model.embedding.parameters())
    assert any(p is embed_params[0] for p in by_decay[C.WEIGHT_DECAY_EMBEDDING]["params"])
    assert not any(p is embed_params[0] for p in by_decay[C.WEIGHT_DECAY_TRUNK]["params"])


def test_seed_locked_reproducibility():
    torch.manual_seed(C.RANDOM_SEED)
    m1 = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    torch.manual_seed(C.RANDOM_SEED)
    m2 = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    for p1, p2 in zip(m1.parameters(), m2.parameters()):
        assert torch.equal(p1, p2)
