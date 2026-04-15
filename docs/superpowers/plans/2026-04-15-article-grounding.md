# Article Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate hallucinated market numbers from daily articles by adding a visible "Today's Numbers" panel anchored to authoritative pipeline data and rejecting any article whose narrative contradicts the panel by >2%; plus library auto-prune at 7 days, plus template-driven generation hook.

**Architecture:** Three new files — `pipeline/article_grounding.py` (load context, build panel, verify narrative), `pipeline/article_lifecycle.py` (prune old articles), `pipeline/scripts/prune_articles.bat` (schedule). One modified file — `pipeline/daily_articles.py` (wire grounding, prepend panel, gate publish, load defining-article template). Reject-on-violation; rejected drafts go to `articles/_failed/` and trigger a telegram alert.

**Tech Stack:** Python 3.13, pytest, vanilla HTML, Windows Task Scheduler. No new external deps.

**Spec:** `docs/superpowers/specs/2026-04-15-article-grounding-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `pipeline/article_grounding.py` | Create | `load_market_context()`, `build_topic_panel()`, `verify_narrative()`, `Violation` dataclass, `MarketDataMissing` exception, `TOPIC_SCHEMAS` constant |
| `pipeline/article_lifecycle.py` | Create | `prune_old_articles()` — moves files >7d to `articles/_archive/`, trims `data/articles_index.json` |
| `pipeline/daily_articles.py` | Modify | Wire grounding, prepend panel HTML, gate publish, load defining-article template |
| `pipeline/tests/test_article_grounding.py` | Create | Unit tests for context loader, panel builder, verifier (regex + whitelist + tolerance) |
| `pipeline/tests/test_article_lifecycle.py` | Create | Unit tests for prune behavior |
| `pipeline/tests/fixtures/daily_dump_fixture.json` | Create | Sample daily dump with Brent/WTI/Gold/indices |
| `pipeline/scripts/prune_articles.bat` | Create | Schedule wrapper that runs `python article_lifecycle.py` |
| `articles/_failed/` | Created at runtime | Holds rejected article drafts |
| `articles/_archive/` | Created at runtime | Holds pruned old articles |
| `articles/_template/regime-engine-defining.html` | Created in Phase B (out of scope of this plan) | Few-shot reference for daily LLM prompts; loader is graceful when missing |
| `pipeline/logs/article_violations.log` | Created at runtime | Append-only log of rejected drafts |

---

## Task 1: Create test fixture for the daily dump

**Files:**
- Create: `pipeline/tests/fixtures/daily_dump_fixture.json`

- [ ] **Step 1: Write the fixture**

```json
{
  "date": "2026-04-15",
  "generated_at": "2026-04-15T04:31:00+05:30",
  "indices": {
    "S&P 500": {"date": "2026-04-14", "close": 5612.4, "source": "yfinance"},
    "Nifty 50": {"date": "2026-04-14", "close": 25432.1, "source": "yfinance"},
    "Nikkei 225": {"date": "2026-04-14", "close": 58162.84, "source": "yfinance"}
  },
  "commodities": {
    "Brent Crude": {"date": "2026-04-14", "open": 95.52, "high": 95.52, "low": 94.84, "close": 95.07, "source": "yfinance"},
    "WTI Crude": {"date": "2026-04-14", "open": 92.02, "high": 92.5, "low": 91.0, "close": 92.02, "source": "yfinance"},
    "Gold": {"date": "2026-04-14", "close": 2478.4, "source": "yfinance"}
  },
  "fx": {
    "USD/INR": {"date": "2026-04-14", "close": 83.12, "source": "yfinance"},
    "USD/JPY": {"date": "2026-04-14", "close": 152.4, "source": "yfinance"},
    "USD/CNY": {"date": "2026-04-14", "close": 7.18, "source": "yfinance"}
  },
  "volatility": {
    "VIX": {"date": "2026-04-14", "close": 18.36, "source": "eodhd"}
  },
  "sector_etfs": {
    "XLE": {"date": "2026-04-14", "close": 55.95, "name": "Energy Select SPDR"},
    "ITA": {"date": "2026-04-14", "close": 235.43, "name": "iShares US Aerospace & Defense"}
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/tests/fixtures/daily_dump_fixture.json
git commit -m "test: fixture for article grounding (daily dump sample)"
```

---

## Task 2: Create `pipeline/article_grounding.py` skeleton

**Files:**
- Create: `pipeline/article_grounding.py`

- [ ] **Step 1: Write the skeleton**

```python
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
    """Load merged authoritative market data for a YYYY-MM-DD date."""
    raise NotImplementedError


def build_topic_panel(topic: str, context: dict) -> dict:
    """Resolve the topic schema against context. Returns {label: value_str}."""
    raise NotImplementedError


def verify_narrative(narrative_html: str, panel: dict) -> list[Violation]:
    """Scan narrative, return list of Violations (empty if clean)."""
    raise NotImplementedError
```

- [ ] **Step 2: Verify it imports**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 -c "from pipeline.article_grounding import TOPIC_SCHEMAS, Violation, MarketDataMissing; print('OK', len(TOPIC_SCHEMAS))"`
Expected: `OK 2`

- [ ] **Step 3: Commit**

```bash
git add pipeline/article_grounding.py
git commit -m "feat(grounding): module skeleton with schemas + dataclass + exception"
```

---

## Task 3: TDD `load_market_context()` — happy path

**Files:**
- Create: `pipeline/tests/test_article_grounding.py`
- Modify: `pipeline/article_grounding.py`

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/test_article_grounding.py` with:

```python
"""Tests for pipeline/article_grounding.py."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from article_grounding import (
    load_market_context, build_topic_panel, verify_narrative,
    MarketDataMissing, Violation, TOPIC_SCHEMAS, TOLERANCE_PCT,
)

FIXTURE = Path(__file__).parent / "fixtures" / "daily_dump_fixture.json"


def _stage_fixture(tmp_path, monkeypatch, name="2026-04-15.json"):
    """Copy fixture into a tmp daily dir and point the loader at it."""
    daily = tmp_path / "daily"
    daily.mkdir()
    shutil.copy(FIXTURE, daily / name)
    monkeypatch.setattr("article_grounding.DAILY_DUMP_DIR", daily)
    return daily


def test_load_market_context_reads_brent(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    assert ctx["commodities"]["Brent Crude"]["close"] == 95.07


def test_load_market_context_reads_indices(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    assert ctx["indices"]["Nifty 50"]["close"] == 25432.1


def test_load_market_context_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("article_grounding.DAILY_DUMP_DIR", tmp_path / "daily")
    with pytest.raises(MarketDataMissing):
        load_market_context("2099-01-01")
```

- [ ] **Step 2: Run tests; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -v`
Expected: 3 FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `load_market_context()` in `pipeline/article_grounding.py`**

Replace the `raise NotImplementedError` body with:

```python
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
```

- [ ] **Step 4: Run tests; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tests/test_article_grounding.py pipeline/article_grounding.py
git commit -m "feat(grounding): load_market_context reads daily dump"
```

---

## Task 4: TDD `build_topic_panel()` — full population + missing→"—"

**Files:**
- Modify: `pipeline/tests/test_article_grounding.py`
- Modify: `pipeline/article_grounding.py`

- [ ] **Step 1: Append failing tests**

```python
def test_build_panel_war_brent_present(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    assert panel["Brent"] == "$95.07"


def test_build_panel_war_missing_field_renders_dash(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    # Fixture has no INDIA VIX or FII flow → both render as "—"
    assert panel["India VIX"] == "—"
    assert panel["FII flow Cr"] == "—"


def test_build_panel_unknown_topic_raises():
    with pytest.raises(KeyError):
        build_topic_panel("nonexistent", {})


def test_build_panel_returns_raw_alongside(tmp_path, monkeypatch):
    """Panel must include a hidden _raw map for the verifier to use."""
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    assert "_raw" in panel
    assert panel["_raw"]["Brent"] == 95.07
    assert panel["_raw"]["India VIX"] is None  # missing
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k panel -v`
Expected: 4 FAIL.

- [ ] **Step 3: Implement `build_topic_panel()` in `pipeline/article_grounding.py`**

Replace the function body with:

```python
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
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k panel -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tests/test_article_grounding.py pipeline/article_grounding.py
git commit -m "feat(grounding): build_topic_panel resolves schema, formats values, exposes _raw"
```

---

## Task 5: TDD number extraction (regex helpers)

**Files:**
- Modify: `pipeline/tests/test_article_grounding.py`
- Modify: `pipeline/article_grounding.py`

- [ ] **Step 1: Append failing tests**

```python
def test_extract_dollar_numbers():
    from article_grounding import _extract_numbers
    text = "Brent rose to $103 a barrel and gold hit $2,478."
    found = _extract_numbers(text)
    kinds_and_vals = [(f.pattern_kind, f.value) for f in found]
    assert ("dollar", 103.0) in kinds_and_vals
    assert ("dollar", 2478.0) in kinds_and_vals


def test_extract_percent_and_bps():
    from article_grounding import _extract_numbers
    text = "CPI is 5.7% and the RBI raised by 25 bps."
    found = _extract_numbers(text)
    pcts = [f.value for f in found if f.pattern_kind == "pct_bps"]
    assert 5.7 in pcts
    assert 25.0 in pcts


def test_extract_index_levels():
    from article_grounding import _extract_numbers
    text = "Nifty 50 closed at 25,432 today."
    found = _extract_numbers(text)
    idx = [f.value for f in found if f.pattern_kind == "index"]
    assert 25432.0 in idx


def test_extract_includes_text_excerpt():
    from article_grounding import _extract_numbers
    text = "Indian refiners face $103 oil pressure today."
    found = _extract_numbers(text)
    dol = [f for f in found if f.pattern_kind == "dollar"][0]
    assert "$103" in dol.text_excerpt
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k extract -v`
Expected: 4 FAIL (`_extract_numbers` does not exist).

- [ ] **Step 3: Add `_extract_numbers()` in `pipeline/article_grounding.py`**

Add this dataclass and function below the existing `Violation` class:

```python
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
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k extract -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/article_grounding.py pipeline/tests/test_article_grounding.py
git commit -m "feat(grounding): regex extractor for $/₹/%/index numeric mentions"
```

---

## Task 6: TDD whitelist matcher

**Files:**
- Modify: `pipeline/tests/test_article_grounding.py`
- Modify: `pipeline/article_grounding.py`

- [ ] **Step 1: Append failing tests**

```python
def test_whitelist_pct_of_imports():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("85% of crude imports come from", 85.0, "pct_bps")


def test_whitelist_per_liter():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("retail prices up by ₹5-7 per liter", 7.0, "rupee")


def test_whitelist_year_window():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("over the next 2-3 years", 3.0, "pct_bps")


def test_whitelist_jobs():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("creating 3,000 jobs in defence", 3000.0, "pct_bps")


def test_whitelist_does_not_match_market_price():
    from article_grounding import _is_whitelisted
    assert not _is_whitelisted("Brent rose to $103 a barrel", 103.0, "dollar")
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k whitelist -v`
Expected: 5 FAIL.

- [ ] **Step 3: Implement `_is_whitelisted()` in `pipeline/article_grounding.py`**

Add below `_extract_numbers`:

```python
_WHITELIST_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?%\s+of\s+\w+", re.I),
    re.compile(r"₹\s?[\d.]+(?:-[\d.]+)?\s+per\s+(liter|kg|share|barrel)", re.I),
    re.compile(r"\d+(?:-\d+)?\s+(year|month|day|week)s?", re.I),
    re.compile(r"\d+(?:,\d{3})*\s+jobs", re.I),
    re.compile(r"\d+%\s+(?:increase|decrease|growth|decline)\s+in\s+\w+", re.I),
]


def _is_whitelisted(text_excerpt: str, value: float, pattern_kind: str) -> bool:
    """Return True if the text around the number matches a known-safe pattern."""
    for pat in _WHITELIST_PATTERNS:
        if pat.search(text_excerpt):
            return True
    return False
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k whitelist -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/article_grounding.py pipeline/tests/test_article_grounding.py
git commit -m "feat(grounding): whitelist patterns for non-market numbers"
```

---

## Task 7: TDD `verify_narrative()` — panel comparison + tolerance + Violation

**Files:**
- Modify: `pipeline/tests/test_article_grounding.py`
- Modify: `pipeline/article_grounding.py`

- [ ] **Step 1: Append failing tests**

```python
def _war_panel(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    return build_topic_panel("war", load_market_context("2026-04-15"))


def test_verify_clean_narrative_returns_no_violations(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Brent closed at $95 a barrel today, with WTI at $92.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_catches_today_bug_103_oil(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Crude spiked another 3% today to $103 a barrel.</p>"
    issues = verify_narrative(text, panel)
    assert len(issues) == 1
    v = issues[0]
    assert v.number == 103.0
    assert v.pattern_kind == "dollar"
    assert v.closest_panel_value == ("Brent", 95.07)


def test_verify_within_tolerance_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    # 95.07 * 1.018 = 96.78 — within 2% tolerance
    text = "<p>Brent at $96.78 today.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_whitelisted_85pct_of_imports_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>India imports 85% of crude oil from OPEC.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_whitelisted_per_liter_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Petrol prices could rise ₹5-7 per liter at the pump.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_index_violation(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    # Panel Nifty 50 = 25432.1; "26500" is way outside ±2% (~510)
    text = "<p>Nifty 50 closed at 26,500 today.</p>"
    issues = verify_narrative(text, panel)
    assert len(issues) == 1
    assert issues[0].pattern_kind == "index"
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k verify -v`
Expected: 6 FAIL (`verify_narrative` still raises NotImplementedError).

- [ ] **Step 3: Implement `verify_narrative()` in `pipeline/article_grounding.py`**

Replace the `raise NotImplementedError` body with:

```python
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
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k verify -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -v`
Expected: all PASS (3 load + 4 panel + 4 extract + 5 whitelist + 6 verify = 22 tests).

- [ ] **Step 6: Commit**

```bash
git add pipeline/article_grounding.py pipeline/tests/test_article_grounding.py
git commit -m "feat(grounding): verify_narrative compares to panel within ±2% tolerance"
```

---

## Task 8: Add panel HTML renderer + helper for daily_articles

**Files:**
- Modify: `pipeline/article_grounding.py`
- Modify: `pipeline/tests/test_article_grounding.py`

- [ ] **Step 1: Append failing test**

```python
def test_render_panel_html_contains_labels_and_values(tmp_path, monkeypatch):
    from article_grounding import render_panel_html
    panel = _war_panel(tmp_path, monkeypatch)
    html = render_panel_html(panel, date_str="2026-04-15")
    assert 'class="market-anchor"' in html
    assert "Brent" in html
    assert "$95.07" in html
    assert "Today's Numbers" in html
    assert "2026-04-15" in html
    assert "_raw" not in html  # internal key must not leak


def test_render_panel_html_renders_dash_for_missing(tmp_path, monkeypatch):
    from article_grounding import render_panel_html
    panel = _war_panel(tmp_path, monkeypatch)
    html = render_panel_html(panel, date_str="2026-04-15")
    assert "—" in html  # India VIX, FII flow are missing in fixture
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k render_panel -v`
Expected: 2 FAIL.

- [ ] **Step 3: Implement `render_panel_html()`**

Add at the end of `pipeline/article_grounding.py`:

```python
def render_panel_html(panel: dict, date_str: str) -> str:
    """Render the panel as a self-contained HTML section.

    Caller is responsible for ensuring the article CSS includes
    .market-anchor, .anchor-title, .anchor-grid, .anchor-source rules.
    """
    cells = []
    for label, value in panel.items():
        if label == "_raw":
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
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_grounding.py -k render_panel -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/article_grounding.py pipeline/tests/test_article_grounding.py
git commit -m "feat(grounding): render_panel_html for embedding in articles"
```

---

## Task 9: Wire grounding into `daily_articles.py` — context + panel injection into prompt

**Files:**
- Modify: `pipeline/daily_articles.py`

- [ ] **Step 1: Read the existing `generate_article(segment, sources, date)` function**

Run: `grep -n "def generate_article" pipeline/daily_articles.py`
Open the function. Identify the LLM prompt construction (search for "messages" or "prompt" or "system").

- [ ] **Step 2: Add the import + context load at the top of `generate_article`**

At the top of `pipeline/daily_articles.py` (with the other imports), add:

```python
from article_grounding import (
    load_market_context, build_topic_panel, verify_narrative,
    render_panel_html, MarketDataMissing,
)
```

Inside `generate_article(segment, sources, date)`, after `if not ANTHROPIC_API_KEY: return ""`, add:

```python
    try:
        ctx = load_market_context(date)
    except MarketDataMissing as e:
        log.error(f"Cannot generate {segment} article — market data missing: {e}")
        return ""
    panel = build_topic_panel(segment, ctx)
    panel_lines = "\n".join(f"  - {k}: {v}" for k, v in panel.items() if k != "_raw")
```

- [ ] **Step 3: Inject the grounding instructions into the LLM system/user prompt**

Find where the prompt content is built (look for the long instructional string with "Write 500-700 words" — around line 139). Insert this block at the END of the system instruction (or prepend to the user prompt — wherever the current behavioral rules live):

```python
    grounding_block = f"""
# GROUNDING — DO NOT VIOLATE
The following panel will be displayed to the reader at the top of the article:
{panel_lines}

Rules:
1. Every market number you cite (oil, gold, indices, currencies, yields) must match
   the panel within ±2%.
2. If a number you want to cite is NOT in the panel, OMIT it. Do not invent.
3. Non-market figures (population %, retail prices ₹/liter, forecasts) are allowed
   but should not contradict the panel direction.
4. Articles whose numbers contradict the panel are REJECTED and not published.
"""
```

Then concatenate `grounding_block` into the prompt text wherever the existing rules go.

- [ ] **Step 4: Run a quick sanity import check**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 -c "import sys; sys.path.insert(0,'pipeline'); import daily_articles; print('OK')"`
Expected: `OK` with no traceback.

- [ ] **Step 5: Commit**

```bash
git add pipeline/daily_articles.py
git commit -m "feat(articles): inject grounding panel into LLM prompt with strict rules"
```

---

## Task 10: Wire publish gate — verify, route to `_failed/` on violation, prepend panel on pass

**Files:**
- Modify: `pipeline/daily_articles.py`

- [ ] **Step 1: Find the publish flow**

Open `pipeline/daily_articles.py`. Locate the function that takes the LLM output and writes the article HTML to `articles/`. (Search for `articles_dir`, `write_text`, or `.html`.) Identify the line where the LLM-returned narrative is composed into the final HTML.

- [ ] **Step 2: Insert verification + branching**

After the line that captures the LLM-returned `narrative` (or `body`) string, BEFORE it is wrapped into the final HTML, insert:

```python
    violations = verify_narrative(narrative, panel)
    if violations:
        failed_dir = GIT_REPO / "articles" / "_failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        failed_path = failed_dir / f"{date}-{segment}.html"
        failed_path.write_text(narrative, encoding="utf-8")
        log.error(f"REJECTED {segment} article — {len(violations)} violations:")
        for v in violations:
            log.error(f"  {v.pattern_kind}={v.number} (closest panel: {v.closest_panel_value}) — '{v.text_excerpt[:80]}'")
        # Append to violations log
        viol_log = PIPELINE_DIR / "logs" / "article_violations.log"
        viol_log.parent.mkdir(parents=True, exist_ok=True)
        with viol_log.open("a", encoding="utf-8") as f:
            f.write(f"\n=== {date} {segment} — {len(violations)} violations ===\n")
            for v in violations:
                f.write(f"  {v.pattern_kind}={v.number} closest={v.closest_panel_value} text='{v.text_excerpt[:120]}'\n")
        # Best-effort telegram alert
        try:
            from telegram_bot import send_message
            send_message(f"⚠️ {segment} article rejected ({len(violations)} violations). Drafted to articles/_failed/")
        except Exception:
            pass
        return ""  # or whatever sentinel signals "do not publish"
```

After the verification gate (when there are 0 violations), before the existing line that writes the article HTML, prepend the panel:

```python
    panel_html = render_panel_html(panel, date_str=date)
    # Insert panel_html into the article body — typically right after the hero
    # block. Replace the existing body wrap to include it:
    body_with_panel = panel_html + "\n" + body  # or wherever body is built
```

- [ ] **Step 3: Add CSS for `.market-anchor` to the article HTML template**

Find the inline `<style>` block in the article HTML template inside `daily_articles.py`. Append before `</style>`:

```css
.market-anchor { background:#161616; border:1px solid #2a2a2a; border-radius:8px; padding:14px 18px; margin:18px 0 24px; }
.anchor-title { font-family:'Inter',sans-serif; font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:#d4a855; margin-bottom:10px; }
.anchor-date { color:#9c9c9c; font-size:11px; margin-left:8px; text-transform:none; letter-spacing:0; }
.anchor-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px 16px; font-family:'JetBrains Mono',monospace; font-size:13px; }
@media (max-width:600px){.anchor-grid{grid-template-columns:repeat(2,1fr);}}
.anchor-grid .lbl { color:#9c9c9c; font-size:11px; display:block; }
.anchor-grid .val { color:#f3f3f3; font-size:14px; font-weight:600; }
.anchor-source { color:#6e6e6e; font-size:10px; margin-top:10px; font-style:italic; }
```

- [ ] **Step 4: Smoke import check**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 -c "import sys; sys.path.insert(0,'pipeline'); import daily_articles"`
Expected: no traceback.

- [ ] **Step 5: Commit**

```bash
git add pipeline/daily_articles.py
git commit -m "feat(articles): verify+gate before publish, prepend panel on pass"
```

---

## Task 11: Add defining-article template loader (graceful when missing)

**Files:**
- Modify: `pipeline/daily_articles.py`

- [ ] **Step 1: Add template loader**

In `pipeline/daily_articles.py`, near the top of `generate_article` AFTER `panel_lines` is built, add:

```python
    template_path = GIT_REPO / "articles" / "_template" / "regime-engine-defining.html"
    template_excerpt = ""
    if template_path.exists():
        try:
            tpl_html = template_path.read_text(encoding="utf-8")
            h1 = re.search(r"<h1>(.*?)</h1>", tpl_html, re.DOTALL)
            body_match = re.search(r'<div class="body">(.*?)</div>', tpl_html, re.DOTALL)
            if body_match:
                paras = re.findall(r"<p>(.*?)</p>", body_match.group(1), re.DOTALL)
                clean = [re.sub(r"<.*?>", "", p).strip() for p in paras[:3]]
                template_excerpt = (
                    f"\n# REFERENCE STYLE — match this voice, structure, and "
                    f"panel-anchored discipline:\n"
                    f"Headline: {h1.group(1).strip() if h1 else ''}\n"
                    f"Opening paragraphs:\n" + "\n\n".join(clean) + "\n"
                )
        except Exception as e:
            log.warning(f"Could not load defining-article template: {e}")
    else:
        log.info(f"No defining-article template at {template_path}; using fallback style")
```

Then concatenate `template_excerpt` into the prompt before the `grounding_block`.

- [ ] **Step 2: Smoke import check**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 -c "import sys; sys.path.insert(0,'pipeline'); import daily_articles"`
Expected: no traceback.

- [ ] **Step 3: Commit**

```bash
git add pipeline/daily_articles.py
git commit -m "feat(articles): load defining-article template as few-shot reference"
```

---

## Task 12: Create `pipeline/article_lifecycle.py` with `prune_old_articles()`

**Files:**
- Create: `pipeline/article_lifecycle.py`
- Create: `pipeline/tests/test_article_lifecycle.py`

- [ ] **Step 1: Write failing tests in `pipeline/tests/test_article_lifecycle.py`**

```python
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
    """Create a fake site layout: articles/, articles_index.json, articles/_archive/."""
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
    # Second run is a no-op
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
```

- [ ] **Step 2: Run; verify FAIL**

Run: `python -m pytest pipeline/tests/test_article_lifecycle.py -v`
Expected: import errors (module does not exist).

- [ ] **Step 3: Create `pipeline/article_lifecycle.py`**

```python
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

    # Trim index
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        arts = idx.get("articles", [])
        kept = [a for a in arts if a.get("filename") not in archived]
        # Also drop entries whose date is older than cutoff (defense in depth)
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
        # Unparseable date → keep (don't accidentally drop unknown entries)
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = prune_old_articles()
    print(f"Archived: {len(result['archived'])} files")
    for name in result["archived"]:
        print(f"  {name}")
    print(f"Index now has {result['kept']} articles")
```

- [ ] **Step 4: Run; verify PASS**

Run: `python -m pytest pipeline/tests/test_article_lifecycle.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/article_lifecycle.py pipeline/tests/test_article_lifecycle.py
git commit -m "feat(lifecycle): prune_old_articles archives 7d+ files, trims index"
```

---

## Task 13: Create `pipeline/scripts/prune_articles.bat`

**Files:**
- Create: `pipeline/scripts/prune_articles.bat`

- [ ] **Step 1: Write the bat file**

```batch
@echo off
REM Anka — daily article prune (>7 days → _archive/), runs after daily_articles
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 article_lifecycle.py >> logs\article_prune.log 2>&1
```

- [ ] **Step 2: Run it manually to confirm it works**

Run: `cd C:/Users/Claude_Anka/askanka.com && cmd //c pipeline/scripts/prune_articles.bat && echo DONE`
Expected: `DONE` and a fresh `pipeline/logs/article_prune.log` with the archive summary.

- [ ] **Step 3: Verify behavior**

Run: `cat pipeline/logs/article_prune.log`
Expected: lines like "Archived: N files" and a list (or "Archived: 0 files" if nothing qualifies yet).

- [ ] **Step 4: Commit**

```bash
git add pipeline/scripts/prune_articles.bat
git commit -m "feat(scheduling): bat wrapper for daily article prune"
```

---

## Task 14: Schedule `AnkaPruneArticles` daily at 04:50 IST

**Files:**
- (none — Windows Task Scheduler operation)

- [ ] **Step 1: Register the task**

Run:
```bash
cmd //c "schtasks /create /tn AnkaPruneArticles /tr \"C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat\" /sc DAILY /st 04:50 /f"
```
Expected: `SUCCESS: The scheduled task "AnkaPruneArticles" has successfully been created.`

- [ ] **Step 2: Verify the task is registered**

Run: `cmd //c "schtasks /query /tn AnkaPruneArticles /fo LIST" | grep -iE "next|status"`
Expected: shows next run time tomorrow 04:50, status Ready.

- [ ] **Step 3: No commit (Windows scheduler change is operational, not in repo)**

Make a note in the session log to document this.

---

## Task 15: End-to-end smoke test on today's data

**Files:**
- (none — verification only)

- [ ] **Step 1: Run daily_articles.py manually for today**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 pipeline/daily_articles.py 2>&1 | tail -50`

Expected outcome: ONE of the following per topic (war, epstein):

  a. **Article passes verification** → published to `articles/2026-04-15-{topic}.html` with the panel visible at the top, narrative numbers within ±2% of panel.

  b. **Article fails verification** → draft written to `articles/_failed/2026-04-15-{topic}.html`, log includes the violation list, telegram alert attempted.

Either outcome is acceptable; the system behaving correctly is what matters.

- [ ] **Step 2: Inspect the result**

If passed:
```bash
ls -la articles/2026-04-15-*.html
grep -n "market-anchor" articles/2026-04-15-war.html | head -3
```
Expected: file present, contains the panel section.

If failed:
```bash
ls -la articles/_failed/
cat pipeline/logs/article_violations.log
```
Expected: rejected draft + log entry.

- [ ] **Step 3: If both rejected, document and decide**

If both today's articles get rejected: that's actually the correct system behavior catching an unreliable LLM. Either:
  - Accept and wait for the defining-article template (Phase B) to land — daily generation will improve once the LLM has a strong reference.
  - Or manually iterate the prompt rules until one passes.

Either way, this is NOT a plan failure — it's the system working as designed. Note in the session.

- [ ] **Step 4: Commit any newly published articles + the violations log**

```bash
git add articles/ pipeline/logs/article_violations.log data/articles_index.json
git commit -m "chore(articles): first run of grounded generator + violations log"
```

(If nothing published, skip this step. The violations log alone may be worth committing — gives an audit trail.)

---

## Task 16: Push to live

**Files:**
- (none — deployment)

- [ ] **Step 1: Confirm with user before pushing**

Halt. Ask: "Article-grounding pipeline complete. Push to master / live?"

- [ ] **Step 2: If approved, push**

```bash
cd C:/Users/Claude_Anka/askanka.com && git push origin master
```

- [ ] **Step 3: Wait for deploy + spot-check live site**

Open `https://askanka.com`, hard-refresh. Check:
  - Hero, recommendations, positions still render (Wave 1 + Wave 2 regression check)
  - If any new article was published, open it: panel visible at top, prose numbers match panel
  - DevTools Console: zero new errors

---

## Self-Review Notes

**Spec coverage:**
- ✅ `load_market_context()` → Task 3
- ✅ `build_topic_panel()` with topic-aware schemas + missing→"—" → Task 4
- ✅ Number extraction (regex patterns) → Task 5
- ✅ Whitelist patterns → Task 6
- ✅ `verify_narrative()` with ±2% tolerance + Violation creation → Task 7
- ✅ Panel HTML rendering → Task 8
- ✅ Prompt grounding rules → Task 9
- ✅ Reject-on-violation, write to `_failed/`, log, telegram alert → Task 10
- ✅ Defining-article template loader (graceful when missing) → Task 11
- ✅ `prune_old_articles()` with 7-day retention → Task 12
- ✅ Scheduled prune at 04:50 IST → Tasks 13, 14
- ✅ End-to-end smoke + live verification → Tasks 15, 16
- ✅ All acceptance criteria from spec are covered

**Type consistency:**
- `panel` dict shape (label→str + `_raw` sub-dict of label→float|None) is consistent across Tasks 4, 7, 8, 9, 10
- `Violation` dataclass shape (number, text_excerpt, pattern_kind, closest_panel_value) consistent in Tasks 7, 10
- `Extraction` dataclass used internally in Tasks 5, 7
- Topic key strings ("war", "epstein") consistent throughout
- File paths (DAILY_DUMP_DIR, articles dir, _failed, _archive, _template) consistent

**Placeholder scan:** No "TBD", no "implement later", no "similar to". Each task has actual code shown, exact commands, expected outputs. Wave 4 deferrals are explicit.

**Phase B note:** Writing the defining article (`articles/_template/regime-engine-defining.html`) is creative work, not in this plan. The template loader handles its absence gracefully. After this plan ships, we'll co-author the template, then daily generation will use it as the few-shot reference.
