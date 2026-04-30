from fastapi.testclient import TestClient

from pipeline.terminal.app import app
import pipeline.terminal.api.live as live_module


def test_returns_dict_per_ticker(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {t: 100.0 + i for i, t in enumerate(tickers)})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,BEL,TCS")
    assert r.status_code == 200
    assert r.json() == {"HAL": 100.0, "BEL": 101.0, "TCS": 102.0}


def test_uppercases_tickers(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {t: 200.0 for t in tickers})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=hal,bel")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"HAL", "BEL"}


def test_rejects_empty_tickers_param(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=")
    assert r.status_code == 400


def test_rejects_whitespace_only_tickers(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=%20,,%20")
    assert r.status_code == 400


def test_caps_request_size(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=" + ",".join([f"T{i}" for i in range(100)]))
    assert r.status_code == 400


def test_returns_null_for_missing_tickers(monkeypatch):
    """Unknown tickers must not render ₹0.00 in the UI. Return null so
    the frontend falls back to the live_status.json snapshot."""
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {"HAL": 4200.0})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,UNKNOWN")
    assert r.status_code == 200
    assert r.json() == {"HAL": 4200.0, "UNKNOWN": None}


def test_returns_null_for_explicit_none(monkeypatch):
    """If Kite returns a ticker with value None, pass the None through."""
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {"HAL": None, "BEL": 450.0})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,BEL")
    assert r.status_code == 200
    assert r.json() == {"HAL": None, "BEL": 450.0}


# ---------------------------------------------------------------------------
# Options live LTP — Phase B for the Phase C paired-shadow ledger.
# ---------------------------------------------------------------------------

def test_options_live_ltp_returns_quote_per_tradingsymbol(monkeypatch):
    """Each NFO tradingsymbol resolves to a {ltp, bid, ask} dict."""
    monkeypatch.setattr(
        live_module, "fetch_option_quotes",
        lambda ts_list: {
            ts: {"ltp": 12.5 + i, "bid": 12.0 + i, "ask": 13.0 + i}
            for i, ts in enumerate(ts_list)
        },
    )
    client = TestClient(app)
    r = client.get("/api/options/live_ltp?tradingsymbols=HAL26APR4300CE,RELIANCE26APR2400PE")
    assert r.status_code == 200
    body = r.json()
    assert body["HAL26APR4300CE"] == {"ltp": 12.5, "bid": 12.0, "ask": 13.0}
    assert body["RELIANCE26APR2400PE"] == {"ltp": 13.5, "bid": 13.0, "ask": 14.0}


def test_options_live_ltp_returns_null_for_missing(monkeypatch):
    """Missing tradingsymbols (delisted, illiquid) come back null so the UI
    keeps the snapshot value visible instead of painting fake zeros."""
    monkeypatch.setattr(
        live_module, "fetch_option_quotes",
        lambda ts_list: {"HAL26APR4300CE": {"ltp": 12.5, "bid": 12.0, "ask": 13.0}},
    )
    client = TestClient(app)
    r = client.get("/api/options/live_ltp?tradingsymbols=HAL26APR4300CE,GHOST26MAY100PE")
    assert r.status_code == 200
    body = r.json()
    assert body["HAL26APR4300CE"]["ltp"] == 12.5
    assert body["GHOST26MAY100PE"] is None


def test_options_live_ltp_rejects_empty(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_option_quotes", lambda ts_list: {})
    client = TestClient(app)
    r = client.get("/api/options/live_ltp?tradingsymbols=")
    assert r.status_code == 400


def test_options_live_ltp_caps_request_size(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_option_quotes", lambda ts_list: {})
    client = TestClient(app)
    payload = ",".join([f"T{i}26APR100CE" for i in range(60)])
    r = client.get(f"/api/options/live_ltp?tradingsymbols={payload}")
    assert r.status_code == 400


def test_options_live_ltp_uppercases(monkeypatch):
    """NFO tradingsymbols are case-sensitive on Kite's side; normalize to
    upper so the route is forgiving of frontend casing."""
    monkeypatch.setattr(
        live_module, "fetch_option_quotes",
        lambda ts_list: {ts: {"ltp": 1.0, "bid": 0.9, "ask": 1.1} for ts in ts_list},
    )
    client = TestClient(app)
    r = client.get("/api/options/live_ltp?tradingsymbols=hal26apr4300ce")
    assert r.status_code == 200
    assert "HAL26APR4300CE" in r.json()


def test_options_live_ltp_kite_failure_returns_nulls(monkeypatch):
    """Kite session/network failure → fetch_option_quotes returns {}, route
    surfaces nulls. The UI keeps showing the snapshot value."""
    monkeypatch.setattr(live_module, "fetch_option_quotes", lambda ts_list: {})
    client = TestClient(app)
    r = client.get("/api/options/live_ltp?tradingsymbols=HAL26APR4300CE,RELIANCE26APR2400PE")
    assert r.status_code == 200
    assert r.json() == {"HAL26APR4300CE": None, "RELIANCE26APR2400PE": None}
