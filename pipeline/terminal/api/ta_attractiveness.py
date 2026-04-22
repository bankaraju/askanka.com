"""FastAPI endpoints for TA Coincidence Scorer output."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pipeline.ta_scorer import storage

router = APIRouter()


@router.get("/ta_attractiveness")
def all_ta() -> dict:
    return storage.read_scores()


@router.get("/ta_attractiveness/{ticker}")
def one_ta(ticker: str) -> dict:
    data = storage.read_scores()
    scores = data.get("scores", {})
    key = ticker.upper()
    if key not in scores:
        raise HTTPException(status_code=404, detail=f"no TA score for {ticker}")
    return scores[key]
