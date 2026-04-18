"""Anka Terminal — FastAPI application."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pipeline.terminal.api.health import router as health_router

app = FastAPI(title="Anka Terminal", version="0.1.0")

app.include_router(health_router, prefix="/api")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
