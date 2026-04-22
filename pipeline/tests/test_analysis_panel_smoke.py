"""End-to-end smoke: bring up the FastAPI app, hit all four engine endpoints,
verify shapes. Skips TA-specific assertions when local artifacts
(ta_feature_models.json) don't exist yet — which is the correct pre-fit state
on fresh checkouts."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.terminal.app import app


def test_all_four_endpoints_return_200_or_404():
    with TestClient(app) as c:
        paths = [
            "/api/attractiveness",
            "/api/ta_attractiveness",
            "/api/research/digest",
            "/api/correlation_breaks",
        ]
        for p in paths:
            r = c.get(p)
            assert r.status_code in (200, 404), f"{p} -> {r.status_code}"


def test_ta_endpoint_returns_reliance_when_fit():
    if not Path("pipeline/data/ta_feature_models.json").exists():
        pytest.skip("ta_feature_models.json not yet built - run fit_universe first")
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    scores = body.get("scores", body)
    assert isinstance(scores, dict)
