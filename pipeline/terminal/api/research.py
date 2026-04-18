"""GET /api/research — article index and content."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_ARTICLES_INDEX = _HERE.parent.parent / "data" / "articles_index.json"
_ARTICLES_DIR = _HERE.parent.parent / "articles"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/research")
def research():
    raw = _read_json(_ARTICLES_INDEX, default=[])
    articles = raw if isinstance(raw, list) else raw.get("articles", [])
    return {"articles": articles, "total": len(articles)}


@router.get("/research/{filename}")
def research_article(filename: str):
    article_path = _ARTICLES_DIR / filename
    if not article_path.exists():
        raise HTTPException(status_code=404, detail=f"Article not found: {filename}")
    return {"filename": filename, "content": article_path.read_text(encoding="utf-8")}
