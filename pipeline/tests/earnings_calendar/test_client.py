from unittest.mock import MagicMock, patch

import pytest

from pipeline.earnings_calendar import client


def _mock_resp(status_code=200, payload=None):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = payload or {}
    m.raise_for_status = MagicMock()
    if status_code >= 400:
        m.raise_for_status.side_effect = RuntimeError(f"HTTP {status_code}")
    return m


def test_fetch_corporate_actions_uses_x_api_key_header(monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "test-key-123")
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return _mock_resp(200, {"board_meetings": {"data": []}})

    with patch("pipeline.earnings_calendar.client.requests.get", fake_get):
        client.fetch_corporate_actions("RELIANCE")

    assert captured["url"] == "https://stock.indianapi.in/corporate_actions"
    assert captured["headers"] == {"X-Api-Key": "test-key-123"}
    assert captured["params"] == {"stock_name": "RELIANCE"}
    assert captured["timeout"] == client.DEFAULT_TIMEOUT


def test_fetch_returns_payload_on_200(monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "k")
    payload = {"board_meetings": {"data": [["24-04-2026", "Quarterly Results"]]}}
    with patch(
        "pipeline.earnings_calendar.client.requests.get",
        lambda *a, **kw: _mock_resp(200, payload),
    ):
        out = client.fetch_corporate_actions("RELIANCE")
    assert out == payload


def test_fetch_raises_on_401(monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "k")
    with patch(
        "pipeline.earnings_calendar.client.requests.get",
        lambda *a, **kw: _mock_resp(401),
    ):
        with pytest.raises(RuntimeError):
            client.fetch_corporate_actions("RELIANCE")


def test_fetch_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("INDIANAPI_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INDIANAPI_KEY"):
        client.fetch_corporate_actions("RELIANCE")
