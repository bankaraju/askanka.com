"""FastAPI endpoints for Feature Coincidence Scorer output."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pipeline.feature_scorer import storage

router = APIRouter()


@router.get("/attractiveness")
def all_attractiveness() -> dict:
    return storage.read_scores()


@router.get("/attractiveness/{ticker}")
def one_attractiveness(ticker: str) -> dict:
    data = storage.read_scores()
    scores = data.get("scores", {})
    key = ticker.upper()
    if key not in scores:
        raise HTTPException(status_code=404, detail=f"no attractiveness score for {ticker}")
    return scores[key]
