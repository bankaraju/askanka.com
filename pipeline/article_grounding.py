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
from datetime import datetime, timedelta
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
    # NOTE: epstein is a political/investigative topic, not a market topic.
    # It synthesizes YouTube watch history about the Trump impeachment angle
    # and intentionally does not cite market numbers. It is deliberately
    # excluded from TOPIC_SCHEMAS so generate_article() skips market grounding.
}


class MarketDataMissing(Exception):
    """Raised when the day's pipeline data dump cannot be loaded."""


@dataclass
class Violation:
    number: float
    text_excerpt: str
    pattern_kind: str
    closest_panel_value: tuple[str, float] | None


@dataclass
class Extraction:
    value: float
    text_excerpt: str
    pattern_kind: str  # "dollar" | "rupee" | "pct_bps" | "index"


_PATTERN_DOLLAR = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
_PATTERN_RUPEE  = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)")
_PATTERN_PCTBPS = re.compile(r"([\d,]+(?:\.\d+)?)\s?(?:%|bps)")
_PATTERN_INDEX  = re.compile(
    r"(?i)(?:Nifty|Sensex|Dow|S&P|BSE)[\s\w]{0,15}?\s+(?:at|@|of|to)\s+([\d,]+(?:\.\d+)?)"
)


def _excerpt(text: str, start: int, end: int, window: int = 60) -> str:
    a = max(0, start - window)
    b = min(len(text), end + window)
    return text[a:b].replace("\n", " ").strip()


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _extract_numbers(text: str) -> list[Extraction]:
    """Scan text, return all numeric mentions with kind labels."""
    out = []
    for kind, pat in (
        ("dollar",  _PATTERN_DOLLAR),
        ("rupee",   _PATTERN_RUPEE),
        ("pct_bps", _PATTERN_PCTBPS),
        ("index",   _PATTERN_INDEX),
    ):
        for m in pat.finditer(text):
            try:
                val = _to_float(m.group(1))
            except (ValueError, IndexError):
                continue
            out.append(Extraction(
                value=val,
                text_excerpt=_excerpt(text, m.start(), m.end()),
                pattern_kind=kind,
            ))
    return out


# Each entry: (compiled_regex, set_of_kinds_it_applies_to | None-means-all)
_WHITELIST_RULES: list[tuple[re.Pattern, set[str] | None]] = [
    (re.compile(r"\d+(?:\.\d+)?%\s+of\s+\w+", re.I),                               {"pct_bps"}),
    (re.compile(r"₹\s?[\d.]+(?:-[\d.]+)?\s+per\s+(liter|kg|share|barrel)", re.I), {"rupee"}),
    (re.compile(r"\d+(?:-\d+)?\s+(year|month|day|week)s?", re.I),                   {"pct_bps"}),
    (re.compile(r"\d+(?:,\d{3})*\s+jobs", re.I),                                    {"pct_bps"}),
    (re.compile(r"\d+%\s+(?:increase|decrease|growth|decline)\s+in\s+\w+", re.I),   {"pct_bps"}),
    # Percentage-change/move language — only fires for pct_bps extractions
    (re.compile(r"(?:another|up|down|fell?|rose?|gained?|lost?|dropped?|surged?|slipped?|climbed?|slid?|jumped?|eased?)\s+[\d.]+\s*%", re.I), {"pct_bps"}),
    (re.compile(r"[\d.]+\s*%\s+(?:higher|lower|above|below|more|less)", re.I),      {"pct_bps"}),
    # Regime-context phrasing: period-over-period returns/moves (the ETF engine
    # feeds these verbatim into the prompt, e.g. "5-day return of -12.65%",
    # "30-day return of 2.41%", "5d move of 0.54%"). These are regime telemetry,
    # not price claims, so they must not be flagged as violations.
    (re.compile(r"\d+[- ]?(?:day|d|month|mo|week|wk|year|yr)s?\s+(?:[\w ]{0,40}?\s+)?(?:return|move|change|performance|decline|drop|fall|gain|rise|rally|slide|loss|surge|jump|advance)\s+of\s+-?[\d.]+\s*%", re.I), {"pct_bps"}),
    (re.compile(r"-?[\d.]+\s*%\s+(?:over|in)\s+(?:the\s+)?(?:last\s+|past\s+|previous\s+)?\d+[- ]?(?:day|d|month|mo|week|wk|year|yr)s?", re.I), {"pct_bps"}),
]

# Keep the old name so existing unit tests (_is_whitelisted) still work unchanged
_WHITELIST_PATTERNS = [pat for pat, _ in _WHITELIST_RULES]


def _is_whitelisted(text_excerpt: str, value: float, pattern_kind: str) -> bool:
    """Return True if the text around the number matches a known-safe pattern."""
    for pat, kinds in _WHITELIST_RULES:
        if kinds is not None and pattern_kind not in kinds:
            continue
        if pat.search(text_excerpt):
            return True
    return False


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


def load_prior_context(date_str: str, max_lookback: int = 5) -> dict | None:
    """Walk back from date_str - 1 day up to max_lookback days, return first
    existing daily dump (parsed). Returns None if nothing found in window.

    Missing priors are normal (weekends, holidays, early history) — callers
    should treat None as "no delta available".
    """
    try:
        anchor = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    for n in range(1, max_lookback + 1):
        prior_date = anchor - timedelta(days=n)
        p = DAILY_DUMP_DIR / f"{prior_date.isoformat()}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


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


def build_topic_panel(topic: str, context: dict, prior_context: dict | None = None) -> dict:
    """Resolve the topic schema against context.

    Returns {label: formatted_string} ordered as the schema, plus hidden
    "_raw" ({label: float_or_None}) and "_deltas" ({label: pct_or_None})
    keys. When prior_context is supplied AND both current and prior values
    are numeric, the formatted string embeds a day-over-day Δ%:
        "$95.07 (-7.5%)"   for dollar-kind
        "23,842.65 (-0.8%)" for index-kind
    When prior is missing or unavailable for that field, the bare value is
    shown and _deltas[label] = None.
    """
    if topic not in TOPIC_SCHEMAS:
        raise KeyError(f"unknown topic {topic!r}")
    panel = {}
    raw = {}
    deltas: dict[str, float | None] = {}
    for label, dotted in TOPIC_SCHEMAS[topic]:
        val = _resolve_path(context, dotted)
        raw[label] = val if isinstance(val, (int, float)) else None

        # Resolve prior value for delta (if prior_context given)
        prior_val = None
        if prior_context is not None:
            pv = _resolve_path(prior_context, dotted)
            if isinstance(pv, (int, float)):
                prior_val = pv

        delta_pct: float | None = None
        if (
            isinstance(val, (int, float))
            and isinstance(prior_val, (int, float))
            and prior_val != 0
        ):
            delta_pct = (val - prior_val) / prior_val * 100.0
        deltas[label] = delta_pct

        # Base formatted value
        if val is not None and label in ("Brent", "WTI", "Gold", "Bitcoin", "DXY"):
            base = f"${_format_value(val)}"
        else:
            base = _format_value(val)

        # Append delta suffix when available
        if delta_pct is not None and base != "—":
            sign = "+" if delta_pct >= 0 else ""
            panel[label] = f"{base} ({sign}{delta_pct:.1f}%)"
        else:
            panel[label] = base
    # Promote delta magnitudes into _raw so the verifier accepts narrative
    # citations of them (extractor emits unsigned, so use abs()). Round to
    # one decimal to match the displayed panel precision.
    for lbl, dp in deltas.items():
        if isinstance(dp, (int, float)):
            raw[f"delta_{lbl}"] = round(abs(dp), 1)
    panel["_raw"] = raw
    panel["_deltas"] = deltas
    return panel


def verify_narrative(narrative_html: str, panel: dict) -> list[Violation]:
    """Scan the narrative, return Violations for numbers outside tolerance.

    Strips HTML tags first so attribute values aren't matched.
    Rules:
      - For each number found, if a whitelist pattern matches the surrounding
        text, skip it.
      - Otherwise compare against every panel value of a comparable kind:
        dollar/index check against numeric panel values; rupee always
        considered against panel values too. pct_bps without whitelist is
        an unsourced market percent — also a violation if no panel match.
      - "Within tolerance" = abs(num - panel_val) / panel_val <= TOLERANCE_PCT
      - The first panel value within tolerance wins (no violation).
      - If no panel value is within tolerance, record a Violation whose
        closest_panel_value is the (label, value) with smallest relative
        distance.
    """
    text = re.sub(r"<[^>]+>", " ", narrative_html)
    raw = panel.get("_raw", {})
    panel_pairs = [(label, val) for label, val in raw.items() if isinstance(val, (int, float))]

    violations = []
    for ext in _extract_numbers(text):
        # Zero is semantically null — can't match any specific level and can't
        # contradict direction on its own. "Nifty was flat 0.0%" is safe.
        if ext.value == 0:
            continue
        if _is_whitelisted(ext.text_excerpt, ext.value, ext.pattern_kind):
            continue

        # Find closest panel value (by relative distance)
        best = None
        for label, pval in panel_pairs:
            if pval == 0:
                continue
            rel = abs(ext.value - pval) / pval
            if best is None or rel < best[0]:
                best = (rel, label, pval)

        if best is not None and best[0] <= TOLERANCE_PCT:
            continue  # within tolerance, OK

        violations.append(Violation(
            number=ext.value,
            text_excerpt=ext.text_excerpt,
            pattern_kind=ext.pattern_kind,
            closest_panel_value=(best[1], best[2]) if best else None,
        ))
    return violations


def render_panel_html(panel: dict, date_str: str) -> str:
    cells = []
    for label, value in panel.items():
        if label in ("_raw", "_deltas"):
            continue
        cells.append(
            f'<div><span class="lbl">{label}</span>'
            f'<span class="val">{value}</span></div>'
        )
    return (
        '<section class="market-anchor">'
        f'<div class="anchor-title">Today\'s Numbers '
        f'<span class="anchor-date">{date_str}</span></div>'
        f'<div class="anchor-grid">{"".join(cells)}</div>'
        '<div class="anchor-source">Source: NSE / yfinance, last close. '
        'Numbers in this article must match this panel.</div>'
        '</section>'
    )
