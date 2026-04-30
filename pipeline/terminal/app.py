"""Anka Terminal — FastAPI application."""
from pathlib import Path
import sys

# Make sibling-imports (e.g. `from config import ...`, `from eodhd_client import ...`)
# resolvable regardless of how uvicorn was launched. Many pipeline/ files use the
# bare-name import style that only works when `pipeline/` is on sys.path; without
# this bootstrap, a fresh uvicorn restart silently breaks LTP/PnL the moment any
# such module is imported lazily inside a request handler.
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pipeline.terminal.api.health import router as health_router
from pipeline.terminal.api.regime import router as regime_router
from pipeline.terminal.api.signals import router as signals_router
from pipeline.terminal.api.risk_gates import router as risk_gates_router
from pipeline.terminal.api.spreads import router as spreads_router
from pipeline.terminal.api.charts import router as charts_router
from pipeline.terminal.api.ta import router as ta_router
from pipeline.terminal.api.news import router as news_router
from pipeline.terminal.api.trust_scores import router as trust_scores_router
from pipeline.terminal.api.research import router as research_router
from pipeline.terminal.api.tickers import router as tickers_router
from pipeline.terminal.api.track_record import router as track_record_router
from pipeline.terminal.api.scanner import router as scanner_router
from pipeline.terminal.api.oi import router as oi_router
from pipeline.terminal.api.candidates import router as candidates_router
from pipeline.terminal.api.risk import router as risk_router
from pipeline.terminal.api import live as live_api
from pipeline.terminal.api.live_monitor import router as live_monitor_router
from pipeline.terminal.api.attractiveness import router as attractiveness_router
from pipeline.terminal.api.ta_attractiveness import router as ta_attractiveness_router
from pipeline.terminal.api.scanner_pattern import router as scanner_pattern_router
from pipeline.terminal.api.sidebar_status import router as sidebar_status_router
from pipeline.terminal.api.ticker_narrative import router as ticker_narrative_router

app = FastAPI(title="Anka Terminal", version="0.1.0")

app.include_router(health_router, prefix="/api")
app.include_router(regime_router, prefix="/api")
app.include_router(signals_router, prefix="/api")
app.include_router(risk_gates_router, prefix="/api")
app.include_router(spreads_router, prefix="/api")
app.include_router(charts_router, prefix="/api")
app.include_router(ta_router, prefix="/api")
app.include_router(news_router, prefix="/api")
app.include_router(trust_scores_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(tickers_router, prefix="/api")
app.include_router(track_record_router, prefix="/api")
app.include_router(scanner_router, prefix="/api")
app.include_router(oi_router, prefix="/api")
app.include_router(candidates_router, prefix="/api")
app.include_router(risk_router, prefix="/api")
app.include_router(live_api.router, prefix="/api")
app.include_router(live_monitor_router, prefix="/api")
app.include_router(attractiveness_router, prefix="/api")
app.include_router(ta_attractiveness_router, prefix="/api")
app.include_router(scanner_pattern_router)  # route already includes /api/ — no prefix
app.include_router(sidebar_status_router, prefix="/api")
app.include_router(ticker_narrative_router, prefix="/api")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
