"""Anka Research — article lifecycle.

Daily prune: move articles older than ARTICLE_RETENTION_DAYS to _archive/ and
trim them from data/articles_index.json. Idempotent.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("anka.article_lifecycle")

IST = timezone(timedelta(hours=5, minutes=30))
ARTICLE_RETENTION_DAYS = 7

GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")
DEFAULT_ARTICLES_DIR = GIT_REPO / "articles"
DEFAULT_INDEX_PATH = GIT_REPO / "data" / "articles_index.json"

_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.html$")
_PROTECTED_DIRS = {"_archive", "_template", "_failed"}


def prune_old_articles(
    articles_dir: Path = DEFAULT_ARTICLES_DIR,
    index_path: Path = DEFAULT_INDEX_PATH,
    today: date | None = None,
) -> dict:
    """Move articles older than retention to _archive/, update the index.

    Returns {"archived": [filenames], "kept": int}.
    """
    if today is None:
        today = datetime.now(IST).date()
    cutoff = today - timedelta(days=ARTICLE_RETENTION_DAYS)
    archive_dir = articles_dir / "_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    for f in articles_dir.iterdir():
        if f.is_dir():
            continue
        m = _FILENAME_RE.match(f.name)
        if not m:
            continue
        try:
            article_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if article_date < cutoff:
            target = archive_dir / f.name
            shutil.move(str(f), str(target))
            archived.append(f.name)
            log.info(f"Archived {f.name} (date={article_date}, cutoff={cutoff})")

    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        arts = idx.get("articles", [])
        kept = [a for a in arts if a.get("filename") not in archived]
        kept = [a for a in kept if _is_kept(a, cutoff)]
        idx["articles"] = kept
        index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        kept = []

    return {"archived": archived, "kept": len(kept)}


def _is_kept(article_entry: dict, cutoff: date) -> bool:
    try:
        d = datetime.strptime(article_entry.get("date", ""), "%Y-%m-%d").date()
        return d >= cutoff
    except (ValueError, TypeError):
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = prune_old_articles()
    print(f"Archived: {len(result['archived'])} files")
    for name in result["archived"]:
        print(f"  {name}")
    print(f"Index now has {result['kept']} articles")
