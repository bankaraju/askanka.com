"""Risk tab API endpoints.

/api/risk/regime-flip — replaces the hardcoded -2%/position placeholder
with a real percentile drawdown from historical regime flips.

Note: the route is declared here without the /api prefix because
`pipeline/terminal/app.py` mounts this router with `prefix="/api"`
(matching the convention of every other terminal router).
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from pipeline.autoresearch.regime_flip_analyzer import compute_flip_drawdown_ci


router = APIRouter()


@router.get("/risk/regime-flip")
def regime_flip(
    to_zone: str = Query("RISK-OFF"),
    percentile: int = Query(95, ge=1, le=99),
):
    return compute_flip_drawdown_ci(to_zone=to_zone, percentile=percentile)
