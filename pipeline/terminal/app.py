"""Anka Terminal — FastAPI application."""
from pathlib import Path

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

app = FastAPI(title="Anka Terminal", version="0.1.0")

app.include_router(health_router, prefix="/api")
app.include_router(regime_router, prefix="/api")
app.include_router(signals_router, prefix="/api")
app.include_router(risk_gates_router, prefix="/api")
app.include_router(spreads_router, prefix="/api")
app.include_router(charts_router, prefix="/api")
app.include_router(ta_router, prefix="/api")
app.include_router(news_router, prefix="/api")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
