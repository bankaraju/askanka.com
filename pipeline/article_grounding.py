"""Anka Research — article grounding.

Anchors daily articles to the authoritative pipeline data dump so
hallucinated market numbers cannot reach publish. Three responsibilities:

  load_market_context(date_str)  — read the data sources into one dict
  build_topic_panel(topic, ctx)  — pick the topic's labeled fields
  verify_narrative(text, panel)  — scan article body for contradictions
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DAILY_DUMP_DIR = DATA_DIR / "daily"

TOLERANCE_PCT = 0.02  # ±2% per spec

TOPIC_SCHEMAS = {
    "war": [
        ("Brent",         "commodities.Brent Crude.close"),
        ("WTI",           "commodities.WTI Crude.close"),
        ("Gold",          "commodities.Gold.close"),
        ("Nifty Defence", "indices.NIFTY DEFENCE.close"),
        ("Nifty 50",      "indices.Nifty 50.close"),
        ("USD/INR",       "fx.USD/INR.close"),
        ("India VIX",     "indices.INDIA VIX.close"),
        ("FII flow Cr",   "flows.fii_equity_net"),
    ],
    "epstein": [
        ("Dow",           "indices.DJI.close"),
        ("S&P 500",       "indices.S&P 500.close"),
        ("VIX (US)",      "volatility.VIX.close"),
        ("Gold",          "commodities.Gold.close"),
        ("DXY",           "fx.DXY.close"),
        ("US 10Y",        "bonds.US10Y.close"),
        ("Bitcoin",       "crypto.BTC.close"),
    ],
}


class MarketDataMissing(Exception):
    """Raised when the day's pipeline data dump cannot be loaded."""


@dataclass
class Violation:
    number: float
    text_excerpt: str
    pattern_kind: str
    closest_panel_value: tuple[str, float] | None


def load_market_context(date_str: str) -> dict:
    """Load merged authoritative market data for a YYYY-MM-DD date.

    Reads <DAILY_DUMP_DIR>/<date>.json. Raises MarketDataMissing if absent.
    Future: merge today_regime.json + fii_flows.json into the same dict
    under top-level keys 'regime' and 'flows'. For now those are optional.
    """
    dump_path = DAILY_DUMP_DIR / f"{date_str}.json"
    if not dump_path.exists():
        raise MarketDataMissing(f"daily dump not found: {dump_path}")
    return json.loads(dump_path.read_text(encoding="utf-8"))


def _resolve_path(ctx: dict, dotted: str):
    """Walk a dotted path through nested dicts. Return None if any step missing."""
    cur = ctx
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _format_value(val) -> str:
    """Format a numeric value for panel display. Currency-agnostic."""
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        if abs(val) >= 1000:
            return f"{val:,.2f}".rstrip("0").rstrip(".")
        return f"{val:.2f}".rstrip("0").rstrip(".")
    return str(val)


def build_topic_panel(topic: str, context: dict) -> dict:
    """Resolve the topic schema against context.

    Returns {label: formatted_string} ordered as the schema, plus a hidden
    "_raw" key whose value is {label: float_or_None} for the verifier.
    """
    if topic not in TOPIC_SCHEMAS:
        raise KeyError(f"unknown topic {topic!r}")
    panel = {}
    raw = {}
    for label, dotted in TOPIC_SCHEMAS[topic]:
        val = _resolve_path(context, dotted)
        raw[label] = val if isinstance(val, (int, float)) else None
        # For dollar-denominated commodities prefix with $; for indices/fx leave plain.
        if val is not None and label in ("Brent", "WTI", "Gold", "Bitcoin", "DXY"):
            panel[label] = f"${_format_value(val)}"
        else:
            panel[label] = _format_value(val)
    panel["_raw"] = raw
    return panel


def verify_narrative(narrative_html: str, panel: dict) -> list[Violation]:
    """Scan narrative, return list of Violations (empty if clean)."""
    raise NotImplementedError
