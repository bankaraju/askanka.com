"""Tests for trade_postmortem (#30).

Renders markdown per closed trade, captures peak/final/lesson, writes to
articles/postmortem-<date>-<slug>.md, appends to articles_index.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.trade_postmortem import (
    extract_lesson,
    render_postmortem,
    slugify,
    write_postmortem_for_trade,
)


# ---------------------------------------------------------------------------
# render_postmortem — plain dict input (the plan's shape)
# ---------------------------------------------------------------------------

def test_postmortem_captures_peak_to_final_gap_plan_shape():
    # Exact shape from plan lines 628-637.
    trade = {
        "spread_name": "Fossil Arbitrage",
        "peak_pnl": 7.07,
        "final_pnl": -4.04,
        "daily_stop_pct": -1.19,
        "exit_reason": "Daily stop",
    }
    md = render_postmortem(trade)
    assert "peak" in md.lower() and "7.07" in md
    assert "final" in md.lower() and "-4.04" in md
    assert "surrendered" in md.lower() or "gave back" in md.lower()
    assert "trail" in md.lower()


# ---------------------------------------------------------------------------
# render_postmortem — closed_signals.json native shape
# ---------------------------------------------------------------------------

def test_postmortem_native_closed_signal_shape():
    trade = {
        "signal_id": "SIG-2026-03-31-020-Coal_vs_OMCs",
        "spread_name": "Coal vs OMCs",
        "status": "STOPPED_OUT",
        "tier": "SIGNAL",
        "peak_spread_pnl_pct": 7.07,
        "days_open": 6,
        "close_timestamp": "2026-04-08T04:14:51.598949",
        "_data_levels": {"daily_stop": -1.19, "cumulative": -4.04},
        "final_pnl": {"spread_pnl_pct": -4.04},
    }
    md = render_postmortem(trade)
    assert "Coal vs OMCs" in md
    assert "7.07" in md
    assert "-4.04" in md
    # Daily stop value should appear in the rendered output.
    assert "-1.19" in md
    # Should name the lesson — peak >= 5% but final negative → trail-didn't-arm.
    assert "trail" in md.lower()


def test_postmortem_target_hit_winner_names_clean_target():
    trade = {
        "spread_name": "Tech Long",
        "status": "TARGET_HIT",
        "peak_spread_pnl_pct": 5.0,
        "final_pnl": {"spread_pnl_pct": 4.6},
        "_data_levels": {"daily_stop": -1.5},
        "days_open": 2,
    }
    md = render_postmortem(trade)
    assert "4.6" in md
    assert "target" in md.lower()


def test_postmortem_modest_winner_no_trail_lesson():
    # Peak just above final, final positive — no trail-arm lesson.
    trade = {
        "spread_name": "Modest Win",
        "status": "TARGET_HIT",
        "peak_spread_pnl_pct": 1.8,
        "final_pnl": {"spread_pnl_pct": 1.5},
        "_data_levels": {"daily_stop": -1.0},
        "days_open": 1,
    }
    md = render_postmortem(trade)
    assert "1.5" in md
    # Trail-arm threshold is 2.0; peak 1.8 should NOT trigger trail lesson.
    assert "did not arm" not in md.lower()


def test_postmortem_no_peak_data_falls_back_gracefully():
    trade = {
        "spread_name": "Sparse",
        "status": "STOPPED_OUT",
        "final_pnl": {"spread_pnl_pct": -2.5},
    }
    md = render_postmortem(trade)
    # Must include final and the spread name, must not crash on missing peak.
    assert "Sparse" in md
    assert "-2.5" in md


# ---------------------------------------------------------------------------
# extract_lesson — rule-based lesson string
# ---------------------------------------------------------------------------

def test_lesson_trail_did_not_arm():
    # Peak >= TRAIL_ARM_PCT (2.0), final negative.
    lesson = extract_lesson(peak=7.07, final=-4.04, daily_stop=-1.19, status="STOPPED_OUT")
    assert "trail" in lesson.lower()
    assert "did not arm" in lesson.lower() or "not armed" in lesson.lower()


def test_lesson_clean_target_hit():
    lesson = extract_lesson(peak=4.8, final=4.5, daily_stop=-1.5, status="TARGET_HIT")
    assert "target" in lesson.lower()
    assert "clean" in lesson.lower() or "hit" in lesson.lower()


def test_lesson_daily_stop_on_winner():
    # Final positive but status is STOPPED_OUT — daily stop killed a winner.
    lesson = extract_lesson(peak=2.5, final=0.5, daily_stop=-1.5, status="STOPPED_OUT")
    assert "stop" in lesson.lower() and "winner" in lesson.lower()


def test_lesson_default_when_no_rule_fires():
    lesson = extract_lesson(peak=0.5, final=0.4, daily_stop=-1.5, status="TARGET_HIT")
    assert lesson  # non-empty


# ---------------------------------------------------------------------------
# slugify — markdown filename helper
# ---------------------------------------------------------------------------

def test_slugify_lowercases_and_dashes():
    assert slugify("Coal vs OMCs") == "coal-vs-omcs"
    assert slugify("Defence vs IT") == "defence-vs-it"
    assert slugify("Long-Short Basket #4") == "long-short-basket-4"


# ---------------------------------------------------------------------------
# write_postmortem_for_trade — articles/ + articles_index integration
# ---------------------------------------------------------------------------

def test_write_postmortem_creates_file_and_appends_index(tmp_path: Path):
    trade = {
        "spread_name": "Coal vs OMCs",
        "status": "STOPPED_OUT",
        "peak_spread_pnl_pct": 7.07,
        "final_pnl": {"spread_pnl_pct": -4.04},
        "_data_levels": {"daily_stop": -1.19},
        "close_timestamp": "2026-04-08T04:14:51",
    }
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    index_path = tmp_path / "data" / "articles_index.json"
    index_path.parent.mkdir()
    index_path.write_text(json.dumps({"articles": []}))

    md_path = write_postmortem_for_trade(
        trade, articles_dir=articles_dir, index_path=index_path
    )

    assert md_path.exists()
    assert md_path.name.startswith("postmortem-2026-04-08-")
    body = md_path.read_text()
    assert "Coal vs OMCs" in body
    assert "7.07" in body

    idx = json.loads(index_path.read_text())
    assert len(idx["articles"]) == 1
    entry = idx["articles"][0]
    assert entry["segment"] == "postmortem"
    assert entry["date"] == "2026-04-08"
    assert entry["filename"] == md_path.name
    assert "Coal vs OMCs" in entry["headline"]


def test_write_postmortem_idempotent_no_duplicate_index(tmp_path: Path):
    trade = {
        "spread_name": "Sparse",
        "status": "STOPPED_OUT",
        "peak_spread_pnl_pct": 3.0,
        "final_pnl": {"spread_pnl_pct": -1.0},
        "_data_levels": {"daily_stop": -1.0},
        "close_timestamp": "2026-04-10T15:00:00",
    }
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    index_path = tmp_path / "data" / "articles_index.json"
    index_path.parent.mkdir()
    index_path.write_text(json.dumps({"articles": []}))

    p1 = write_postmortem_for_trade(trade, articles_dir=articles_dir, index_path=index_path)
    p2 = write_postmortem_for_trade(trade, articles_dir=articles_dir, index_path=index_path)
    assert p1 == p2
    idx = json.loads(index_path.read_text())
    # Calling twice on the same trade should not create a duplicate entry.
    matching = [a for a in idx["articles"] if a["filename"] == p1.name]
    assert len(matching) == 1
