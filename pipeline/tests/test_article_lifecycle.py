"""Tests for pipeline/article_lifecycle.py — article pruning."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from article_lifecycle import prune_old_articles, ARTICLE_RETENTION_DAYS

IST = timezone(timedelta(hours=5, minutes=30))


def _setup(tmp_path):
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "_archive").mkdir()
    idx = tmp_path / "articles_index.json"
    return articles, idx


def _write_article(articles_dir, date_str, topic="war", body="<html>x</html>"):
    p = articles_dir / f"{date_str}-{topic}.html"
    p.write_text(body, encoding="utf-8")
    return p


def test_prune_keeps_recent(tmp_path):
    articles, idx = _setup(tmp_path)
    today = datetime.now(IST).date()
    fresh = _write_article(articles, (today - timedelta(days=2)).strftime("%Y-%m-%d"))
    idx.write_text(json.dumps({"articles": [
        {"date": (today - timedelta(days=2)).strftime("%Y-%m-%d"), "segment": "war", "filename": fresh.name}
    ]}), encoding="utf-8")
    prune_old_articles(articles_dir=articles, index_path=idx, today=today)
    assert fresh.exists()
    assert json.loads(idx.read_text())["articles"]


def test_prune_archives_old(tmp_path):
    articles, idx = _setup(tmp_path)
    today = datetime.now(IST).date()
    old_date = (today - timedelta(days=ARTICLE_RETENTION_DAYS + 3)).strftime("%Y-%m-%d")
    old = _write_article(articles, old_date)
    idx.write_text(json.dumps({"articles": [
        {"date": old_date, "segment": "war", "filename": old.name}
    ]}), encoding="utf-8")
    prune_old_articles(articles_dir=articles, index_path=idx, today=today)
    assert not old.exists()
    assert (articles / "_archive" / old.name).exists()
    assert json.loads(idx.read_text())["articles"] == []


def test_prune_idempotent(tmp_path):
    articles, idx = _setup(tmp_path)
    today = datetime.now(IST).date()
    old_date = (today - timedelta(days=ARTICLE_RETENTION_DAYS + 1)).strftime("%Y-%m-%d")
    old = _write_article(articles, old_date)
    idx.write_text(json.dumps({"articles": [
        {"date": old_date, "segment": "war", "filename": old.name}
    ]}), encoding="utf-8")
    prune_old_articles(articles_dir=articles, index_path=idx, today=today)
    prune_old_articles(articles_dir=articles, index_path=idx, today=today)
    assert (articles / "_archive" / old.name).exists()


def test_prune_skips_template_and_archive_dirs(tmp_path):
    articles, idx = _setup(tmp_path)
    today = datetime.now(IST).date()
    (articles / "_template").mkdir()
    (articles / "_template" / "regime-engine-defining.html").write_text("x", encoding="utf-8")
    idx.write_text(json.dumps({"articles": []}), encoding="utf-8")
    prune_old_articles(articles_dir=articles, index_path=idx, today=today)
    assert (articles / "_template" / "regime-engine-defining.html").exists()
    assert (articles / "_archive").exists()
