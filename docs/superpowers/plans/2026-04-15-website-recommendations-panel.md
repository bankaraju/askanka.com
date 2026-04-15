# Website Wave 2 — Today's Recommendations Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single "Today's Recommendations" panel below the Global Regime Score hero on `index.html` that surfaces output from `spread_intelligence`, `reverse_regime_ranker`, and `news_intelligence` as a 3-column grid with per-card freshness pills.

**Architecture:** New exporter function `export_today_recommendations()` in `pipeline/website_exporter.py` reads 5 engine-output files, builds 3 ranked lists (top 3 each), tags each card with `is_stale` and `source_timestamp`, and writes `data/today_recommendations.json`. `run_export()` writes the new file alongside the existing two. `index.html` gains one section + matching CSS + JS that fetches and renders. Bat-file wiring already exists from Wave 1.

**Tech Stack:** Python 3.13, pytest, vanilla HTML/JS, Windows Task Scheduler (no change).

**Spec:** `docs/superpowers/specs/2026-04-15-website-recommendations-panel-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `pipeline/website_exporter.py` | Modify | Add constants + `stale_check()` helper + `export_today_recommendations()` + extend `run_export()` |
| `pipeline/tests/test_website_exporter.py` | Modify | Add tests for new helper + new function |
| `pipeline/tests/fixtures/recommendations_fixture.json` | Create | Spread engine sample |
| `pipeline/tests/fixtures/regime_ranker_state_fixture.json` | Create | Ranker state sample with non-empty `active_recommendations` |
| `pipeline/tests/fixtures/news_events_today_fixture.json` | Create | News events sample (small) |
| `pipeline/tests/fixtures/news_verdicts_fixture.json` | Create | News verdicts sample (small) |
| `index.html` | Modify | Add `<section id="today-recs">` + CSS + JS |
| `data/today_recommendations.json` | Created at runtime | Canonical website file |

---

## Task 1: Create fixtures for the four new source files

**Files:**
- Create: `pipeline/tests/fixtures/recommendations_fixture.json`
- Create: `pipeline/tests/fixtures/regime_ranker_state_fixture.json`
- Create: `pipeline/tests/fixtures/news_events_today_fixture.json`
- Create: `pipeline/tests/fixtures/news_verdicts_fixture.json`

- [ ] **Step 1: Create `recommendations_fixture.json`**

Content:

```json
{
  "timestamp": "2026-04-15T09:25:08.000+05:30",
  "regime": "NEUTRAL",
  "msi_score": 43.7,
  "recommendations": [
    {"name": "Upstream vs Downstream", "gate_status": "BELOW_2STD", "spread_return": -2.1, "reason": "Z_BELOW_MEAN_2STD", "score": 85, "action": "ENTER", "conviction": "HIGH", "z_score": -2.05},
    {"name": "Defence vs IT", "gate_status": "ABOVE_1STD", "spread_return": 1.2, "reason": "Z_ABOVE_MEAN_1STD", "score": 60, "action": "ENTER", "conviction": "MEDIUM", "z_score": 1.42},
    {"name": "PSU Banks vs Private", "gate_status": "AT_MEAN", "spread_return": 0.0, "reason": "AT_MEAN", "score": 0, "action": "INACTIVE", "conviction": "NONE", "z_score": -0.02},
    {"name": "Metals vs Cement", "gate_status": "BELOW_1STD", "spread_return": -0.8, "reason": "Z_BELOW_MEAN_1STD", "score": 50, "action": "ENTER", "conviction": "MEDIUM", "z_score": -1.18},
    {"name": "Pharma vs Auto", "gate_status": "ABOVE_2STD", "spread_return": 2.5, "reason": "Z_ABOVE_MEAN_2STD", "score": 90, "action": "ENTER", "conviction": "HIGH", "z_score": 2.31}
  ]
}
```

- [ ] **Step 2: Create `regime_ranker_state_fixture.json`**

Content:

```json
{
  "last_zone": "NEUTRAL",
  "updated": "2026-04-15 09:25:00",
  "active_recommendations": [
    {"ticker": "HAL", "direction": "LONG", "conviction": "HIGH", "trigger": "regime_active_NEUTRAL"},
    {"ticker": "INFY", "direction": "SHORT", "conviction": "MEDIUM", "trigger": "regime_active_NEUTRAL"},
    {"ticker": "RELIANCE", "direction": "LONG", "conviction": "MEDIUM", "trigger": "regime_active_NEUTRAL"},
    {"ticker": "ITC", "direction": "LONG", "conviction": "LOW", "trigger": "regime_active_NEUTRAL"}
  ]
}
```

- [ ] **Step 3: Create `news_events_today_fixture.json`**

Content:

```json
{
  "date": "2026-04-15",
  "last_scan": "2026-04-15T08:21:00.000+05:30",
  "scan_type": "morning",
  "events": [
    {"symbol": "RELIANCE", "title": "Q4 results beat estimates by 8%", "category": "earnings"},
    {"symbol": "TCS", "title": "Wins $500M deal with European bank", "category": "deal_win"},
    {"symbol": "HDFCBANK", "title": "RBI fines bank Rs 5 crore", "category": "regulatory_action"}
  ],
  "summary": {"total": 3}
}
```

- [ ] **Step 4: Create `news_verdicts_fixture.json`**

Content:

```json
[
  {"symbol": "RELIANCE", "category": "earnings", "event_title": "Q4 results beat estimates by 8%", "event_date": "2026-04-15", "impact": "positive", "recommendation": "BUY", "direction": "LONG", "shelf_life": "short", "shelf_days": 3, "price_reaction_1d": 1.4, "historical_avg_5d": 2.8, "historical_hit_rate": 0.71, "precedent_count": 14},
  {"symbol": "TCS", "category": "deal_win", "event_title": "Wins $500M deal with European bank", "event_date": "2026-04-15", "impact": "positive", "recommendation": "BUY", "direction": "LONG", "shelf_life": "short", "shelf_days": 5, "price_reaction_1d": 0.9, "historical_avg_5d": 3.1, "historical_hit_rate": 0.65, "precedent_count": 22},
  {"symbol": "HDFCBANK", "category": "regulatory_action", "event_title": "RBI fines bank Rs 5 crore", "event_date": "2026-04-15", "impact": "negative", "recommendation": "SELL", "direction": "SHORT", "shelf_life": "short", "shelf_days": 2, "price_reaction_1d": -0.6, "historical_avg_5d": -1.4, "historical_hit_rate": 0.58, "precedent_count": 9},
  {"symbol": "OLDSTUFF", "category": "earnings", "event_title": "irrelevant historical entry", "event_date": "2025-08-01", "impact": "positive", "recommendation": "HOLD", "direction": "NEUTRAL", "shelf_life": "long", "shelf_days": 30, "price_reaction_1d": 0.1, "historical_avg_5d": 0.2, "historical_hit_rate": 0.50, "precedent_count": 2}
]
```

- [ ] **Step 5: Commit fixtures**

```bash
git add pipeline/tests/fixtures/recommendations_fixture.json pipeline/tests/fixtures/regime_ranker_state_fixture.json pipeline/tests/fixtures/news_events_today_fixture.json pipeline/tests/fixtures/news_verdicts_fixture.json
git commit -m "test: fixtures for Wave 2 recommendations panel"
```

---

## Task 2: Test + implement `stale_check()` helper

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Append failing test to `pipeline/tests/test_website_exporter.py`**

Append at end of file:

```python
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def test_stale_check_recent_returns_false():
    from website_exporter import stale_check
    recent = (datetime.now(IST) - timedelta(hours=1)).isoformat()
    assert stale_check(recent) is False


def test_stale_check_old_returns_true():
    from website_exporter import stale_check
    old = (datetime.now(IST) - timedelta(hours=5)).isoformat()
    assert stale_check(old) is True


def test_stale_check_none_returns_true():
    from website_exporter import stale_check
    assert stale_check(None) is True


def test_stale_check_empty_string_returns_true():
    from website_exporter import stale_check
    assert stale_check("") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_website_exporter.py::test_stale_check_recent_returns_false -v`
Expected: ImportError — `stale_check` does not exist.

- [ ] **Step 3: Add `STALE_HOURS` constant + `stale_check()` to `pipeline/website_exporter.py`**

Locate the section with `TODAY_REGIME_FILE = DATA_DIR / "today_regime.json"` (added in Wave 1). Immediately AFTER that line, add:

```python
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
RANKER_STATE_FILE = DATA_DIR / "regime_ranker_state.json"
NEWS_EVENTS_FILE = DATA_DIR / "news_events_today.json"
NEWS_VERDICTS_FILE = DATA_DIR / "news_verdicts.json"
STALE_HOURS = 4
```

Then locate `def export_global_regime() -> dict:` and insert immediately BEFORE it:

```python
def stale_check(timestamp_str) -> bool:
    """Return True if the given ISO timestamp is older than STALE_HOURS or unparseable."""
    if not timestamp_str:
        return True
    try:
        ts = datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    age = datetime.now(IST) - ts
    return age > timedelta(hours=STALE_HOURS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k stale_check -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): add stale_check helper + Wave 2 file constants"
```

---

## Task 3: Test + implement `export_today_recommendations()` skeleton with top-level fields

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Append failing test**

Append at end of `pipeline/tests/test_website_exporter.py`:

```python
RECS_FIXTURE = Path(__file__).parent / "fixtures" / "recommendations_fixture.json"
RANKER_FIXTURE = Path(__file__).parent / "fixtures" / "regime_ranker_state_fixture.json"
NEWS_EVENTS_FIXTURE = Path(__file__).parent / "fixtures" / "news_events_today_fixture.json"
NEWS_VERDICTS_FIXTURE = Path(__file__).parent / "fixtures" / "news_verdicts_fixture.json"


def _patch_all_sources(monkeypatch):
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    monkeypatch.setattr("website_exporter.RECOMMENDATIONS_FILE", RECS_FIXTURE)
    monkeypatch.setattr("website_exporter.RANKER_STATE_FILE", RANKER_FIXTURE)
    monkeypatch.setattr("website_exporter.NEWS_EVENTS_FILE", NEWS_EVENTS_FIXTURE)
    monkeypatch.setattr("website_exporter.NEWS_VERDICTS_FILE", NEWS_VERDICTS_FIXTURE)


def test_today_recommendations_top_level_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert set(out.keys()) == {"updated_at", "regime_zone", "regime_source_timestamp",
                                "spreads", "stocks", "news_driven", "holiday_mode"}
    assert out["regime_zone"] == "NEUTRAL"
    assert out["regime_source_timestamp"] == "2026-04-14T09:25:08.354943+05:30"
    assert out["holiday_mode"] is False
    assert isinstance(out["spreads"], list)
    assert isinstance(out["stocks"], list)
    assert isinstance(out["news_driven"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_website_exporter.py::test_today_recommendations_top_level_fields -v`
Expected: ImportError — `export_today_recommendations` does not exist.

- [ ] **Step 3: Add the skeleton function to `pipeline/website_exporter.py`**

Insert immediately AFTER `def export_global_regime() -> dict:` ... function body (before `def export_live_status()`):

```python
def export_today_recommendations() -> dict:
    """Build the unified recommendations view for the website.

    Reads spread engine, ranker, and news intelligence outputs; returns top-3
    of each as a single dict with per-card freshness flags.
    """
    regime_raw = _load_json(TODAY_REGIME_FILE) or {}
    regime_zone = regime_raw.get("regime", "UNKNOWN")
    regime_ts = regime_raw.get("timestamp")

    spreads = _build_spread_recs()
    stocks = _build_stock_recs()
    news_driven = _build_news_recs()

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "regime_zone": regime_zone,
        "regime_source_timestamp": regime_ts,
        "spreads": spreads,
        "stocks": stocks,
        "news_driven": news_driven,
        "holiday_mode": False,
    }


def _build_spread_recs() -> list:
    return []


def _build_stock_recs() -> list:
    return []


def _build_news_recs() -> list:
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_website_exporter.py::test_today_recommendations_top_level_fields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): export_today_recommendations skeleton + top-level fields"
```

---

## Task 4: Test + implement spread recommendation builder

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Append failing tests**

Append at end of `pipeline/tests/test_website_exporter.py`:

```python
def test_spreads_drop_inactive_and_none(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    names = [s["name"] for s in out["spreads"]]
    assert "PSU Banks vs Private" not in names  # action=INACTIVE conv=NONE


def test_spreads_top_3_by_conviction_then_zscore(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert len(out["spreads"]) <= 3
    # Fixture: HIGH (Pharma z=2.31, Upstream z=-2.05), MEDIUM (Defence 1.42, Metals -1.18)
    # Expected order: Pharma, Upstream, Defence
    assert [s["name"] for s in out["spreads"]] == ["Pharma vs Auto", "Upstream vs Downstream", "Defence vs IT"]


def test_spread_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    s = out["spreads"][0]
    assert set(s.keys()) == {"name", "action", "conviction", "z_score", "reason",
                              "source_timestamp", "is_stale"}
    assert s["source_timestamp"] == "2026-04-15T09:25:08.000+05:30"
    assert s["is_stale"] in (True, False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k spread -v`
Expected: at least 3 FAILs (`out["spreads"]` is empty).

- [ ] **Step 3: Implement `_build_spread_recs()` in `pipeline/website_exporter.py`**

Replace the stub `def _build_spread_recs() -> list: return []` with:

```python
_CONV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}


def _build_spread_recs() -> list:
    raw = _load_json(RECOMMENDATIONS_FILE) or {}
    src_ts = raw.get("timestamp")
    stale = stale_check(src_ts)
    out = []
    for r in raw.get("recommendations", []) or []:
        if r.get("action") not in ("ENTER", "EXIT"):
            continue
        if r.get("conviction") in (None, "NONE"):
            continue
        out.append({
            "name": r.get("name", ""),
            "action": r.get("action", ""),
            "conviction": r.get("conviction", "NONE"),
            "z_score": r.get("z_score", 0),
            "reason": r.get("reason", ""),
            "source_timestamp": src_ts,
            "is_stale": stale,
        })
    out.sort(key=lambda s: (-_CONV_RANK.get(s["conviction"], 0), -abs(s.get("z_score") or 0)))
    return out[:3]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k spread -v`
Expected: all spread tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): build spread recommendations (filter, sort, top-3)"
```

---

## Task 5: Test + implement stock recommendation builder

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Append failing tests**

Append at end of `pipeline/tests/test_website_exporter.py`:

```python
def test_stocks_top_3_from_ranker(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert len(out["stocks"]) <= 3
    tickers = [s["ticker"] for s in out["stocks"]]
    # Fixture: HAL (HIGH), INFY (MED), RELIANCE (MED), ITC (LOW)
    # ITC (LOW) drops out at top-3
    assert "HAL" in tickers
    assert "ITC" not in tickers


def test_stock_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    s = out["stocks"][0]
    assert set(s.keys()) == {"ticker", "direction", "conviction", "trigger",
                              "source", "source_timestamp", "is_stale"}
    assert s["ticker"] == "HAL"
    assert s["direction"] == "LONG"
    assert s["conviction"] == "HIGH"
    assert s["source"] == "ranker"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k stock -v`
Expected: FAILs (stocks list empty).

- [ ] **Step 3: Implement `_build_stock_recs()` in `pipeline/website_exporter.py`**

Replace the stub `def _build_stock_recs() -> list: return []` with:

```python
def _build_stock_recs() -> list:
    raw = _load_json(RANKER_STATE_FILE) or {}
    src_ts = raw.get("updated")
    stale = stale_check(src_ts)
    out = []
    for r in raw.get("active_recommendations", []) or []:
        out.append({
            "ticker": r.get("ticker", ""),
            "direction": r.get("direction", ""),
            "conviction": r.get("conviction", "NONE"),
            "trigger": r.get("trigger", ""),
            "source": "ranker",
            "source_timestamp": src_ts,
            "is_stale": stale,
        })
    out.sort(key=lambda s: -_CONV_RANK.get(s["conviction"], 0))
    return out[:3]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k stock -v`
Expected: all stock tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): build stock recommendations from ranker state"
```

---

## Task 6: Test + implement news-driven recommendation builder

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Append failing tests**

Append at end of `pipeline/tests/test_website_exporter.py`:

```python
def test_news_only_today_events(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    tickers = [n["ticker"] for n in out["news_driven"]]
    # OLDSTUFF is in verdicts but not in today's events — must be excluded
    assert "OLDSTUFF" not in tickers


def test_news_drops_hold_recommendations(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    # All fixture today-events have BUY/SELL verdicts; no HOLD should appear
    assert all(n["direction"] in ("LONG", "SHORT") for n in out["news_driven"])


def test_news_sorted_by_hit_rate_desc(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    rates = [n["historical_hit_rate"] for n in out["news_driven"]]
    assert rates == sorted(rates, reverse=True)
    # RELIANCE hit_rate 0.71 wins
    assert out["news_driven"][0]["ticker"] == "RELIANCE"


def test_news_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    n = out["news_driven"][0]
    assert set(n.keys()) == {"ticker", "headline", "category", "direction",
                              "shelf_days", "historical_hit_rate", "precedent_count",
                              "source_timestamp", "is_stale"}
    assert n["headline"] == "Q4 results beat estimates by 8%"
    assert n["historical_hit_rate"] == 0.71
    assert n["precedent_count"] == 14
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k news -v`
Expected: FAILs (news_driven empty).

- [ ] **Step 3: Implement `_build_news_recs()` in `pipeline/website_exporter.py`**

Replace the stub `def _build_news_recs() -> list: return []` with:

```python
def _build_news_recs() -> list:
    events_raw = _load_json(NEWS_EVENTS_FILE) or {}
    verdicts_raw = _load_json(NEWS_VERDICTS_FILE) or []
    src_ts = events_raw.get("last_scan")
    stale = stale_check(src_ts)

    # Index latest verdict per (symbol, category)
    verdict_idx = {}
    for v in verdicts_raw:
        key = (v.get("symbol"), v.get("category"))
        verdict_idx[key] = v  # last write wins; verdicts file is append-order

    out = []
    for ev in events_raw.get("events", []) or []:
        v = verdict_idx.get((ev.get("symbol"), ev.get("category")))
        if not v:
            continue
        if v.get("recommendation") not in ("BUY", "SELL"):
            continue
        out.append({
            "ticker": ev.get("symbol", ""),
            "headline": ev.get("title", ""),
            "category": ev.get("category", ""),
            "direction": v.get("direction", ""),
            "shelf_days": v.get("shelf_days", 0),
            "historical_hit_rate": v.get("historical_hit_rate", 0),
            "precedent_count": v.get("precedent_count", 0),
            "source_timestamp": src_ts,
            "is_stale": stale,
        })
    out.sort(key=lambda n: -(n.get("historical_hit_rate") or 0))
    return out[:3]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -k news -v`
Expected: all news tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): build news-driven recommendations from events + verdicts"
```

---

## Task 7: Test + handle missing source files gracefully

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`

- [ ] **Step 1: Append failing test**

Append at end of `pipeline/tests/test_website_exporter.py`:

```python
def test_missing_engine_files_returns_empty_lists(tmp_path, monkeypatch):
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.RECOMMENDATIONS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.RANKER_STATE_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.NEWS_EVENTS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.NEWS_VERDICTS_FILE", tmp_path / "missing.json")
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert out["spreads"] == []
    assert out["stocks"] == []
    assert out["news_driven"] == []
    assert out["regime_zone"] == "UNKNOWN"
    assert out["holiday_mode"] is False
```

- [ ] **Step 2: Run test to verify behaviour**

Run: `python -m pytest pipeline/tests/test_website_exporter.py::test_missing_engine_files_returns_empty_lists -v`
Expected: PASS (the existing implementation already handles missing files via `_load_json` returning falsy and the `or {}` / `or []` guards).

If FAIL, inspect `_load_json()` behaviour and add a `try/except` returning `None` for missing files. Re-run.

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/test_website_exporter.py
git commit -m "test: missing engine files produce empty recommendation lists"
```

---

## Task 8: Wire `export_today_recommendations()` into `run_export()`

**Files:**
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Read the current `run_export()` body**

Open `pipeline/website_exporter.py` and find `def run_export():`. The current body (from Wave 1):

```python
def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")
```

- [ ] **Step 2: Replace it with the extended version**

Replace the function body with:

```python
def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()
    recs = export_today_recommendations()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
        ("today_recommendations.json", recs),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")
    print(f"  Recommendations: {len(recs['spreads'])} spreads, "
          f"{len(recs['stocks'])} stocks, {len(recs['news_driven'])} news")
```

- [ ] **Step 3: Run the exporter end-to-end**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 pipeline/website_exporter.py`
Expected output (approximate):
```
  Exported global_regime.json (...\data\global_regime.json)
  Exported live_status.json (...\data\live_status.json)
  Exported today_recommendations.json (...\data\today_recommendations.json)

Website data exported to ...\data
  Regime zone:    NEUTRAL (score 43.7)
  Open positions: 1
  Recommendations: <n> spreads, <n> stocks, <n> news
```

- [ ] **Step 4: Verify the produced JSON is valid + has expected keys**

Run:
```bash
python -X utf8 -c "import json; d=json.load(open('data/today_recommendations.json',encoding='utf-8')); print(sorted(d.keys())); print('spreads:',len(d['spreads']),'stocks:',len(d['stocks']),'news:',len(d['news_driven']))"
```
Expected keys: `['holiday_mode', 'news_driven', 'regime_source_timestamp', 'regime_zone', 'spreads', 'stocks', 'updated_at']`

- [ ] **Step 5: Commit**

```bash
git add pipeline/website_exporter.py
git commit -m "feat(exporter): wire today_recommendations into run_export"
```

---

## Task 9: Add HTML section to `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Locate the insertion point**

Find the closing `</section>` of `<section id="regime-hero">` in `index.html`. The new section goes immediately after it, before `<section id="live-positions">`.

- [ ] **Step 2: Insert the HTML block**

Use the Edit tool. Search for the line containing the closing tag of the regime-hero section followed by the opening tag of `live-positions`. Insert this block between them:

```html
<!-- Today's Recommendations (Wave 2) -->
<section id="today-recs" class="recs-block">
  <h2 class="block-title">Today's Recommendations</h2>
  <div class="recs-grid">
    <div class="rec-column">
      <div class="rec-header">Spread Trades</div>
      <div class="rec-cards" id="recs-spreads"><div class="rec-empty">Loading…</div></div>
    </div>
    <div class="rec-column">
      <div class="rec-header">Standalone Stocks</div>
      <div class="rec-cards" id="recs-stocks"><div class="rec-empty">Loading…</div></div>
    </div>
    <div class="rec-column">
      <div class="rec-header">News-Driven</div>
      <div class="rec-cards" id="recs-news"><div class="rec-empty">Loading…</div></div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Visual sanity check**

Open `index.html` in a browser. The new section should appear (with "Loading…" placeholders) between the hero and Live Positions. CSS will be ugly until the next task.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(site): add Today's Recommendations section markup"
```

---

## Task 10: Add CSS for recommendations panel

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Locate the existing `<style>` block**

Use Grep: `grep -n "</style>" index.html` to find the end of the inline style block.

- [ ] **Step 2: Insert CSS immediately before `</style>`**

Use the Edit tool. Add this block:

```css
/* Today's Recommendations (Wave 2) */
.recs-block { padding: 24px; max-width: 1200px; margin: 0 auto; border-bottom: 1px solid #2a2a2a; }
.recs-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
@media (max-width: 800px) { .recs-grid { grid-template-columns: 1fr; } }
.rec-column { background: #161616; border-radius: 8px; padding: 14px; }
.rec-header { font-family: 'Inter', sans-serif; font-size: 11px; text-transform: uppercase;
              letter-spacing: 0.08em; color: #9c9c9c; margin-bottom: 10px; }
.rec-cards { display: flex; flex-direction: column; gap: 10px; }
.rec-card { background: #1f1f1f; border-radius: 6px; padding: 10px 12px;
            font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #f3f3f3; }
.rec-card .name { font-size: 14px; font-weight: 600; }
.rec-card .meta { color: #9c9c9c; font-size: 11px; margin-top: 4px; }
.rec-card .stale-pill { display: inline-block; padding: 1px 6px; background: #3a2a18; color: #ffa94d;
                       border-radius: 3px; font-size: 10px; margin-left: 6px; text-transform: uppercase; }
.rec-card .conv-HIGH   { color: #69db7c; }
.rec-card .conv-MEDIUM { color: #f59e0b; }
.rec-card .conv-LOW    { color: #9c9c9c; }
.rec-card .dir-LONG  { color: #69db7c; }
.rec-card .dir-SHORT { color: #ff6b6b; }
.rec-empty { color: #6e6e6e; font-size: 12px; font-style: italic; }
```

- [ ] **Step 3: Visual sanity check**

Reload `index.html` in browser. The 3 columns should now have dark backgrounds, proper headers, and "Loading…" placeholders. Layout collapses to single column at <800px width.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(site): add CSS for recommendations panel"
```

---

## Task 11: Add JS to fetch and render recommendations

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Locate the existing `<script>` block**

Use Grep: `grep -n "loadGlobalRegime\|loadLivePositions" index.html` to find where the existing fetch handlers live. Add the new handler near them.

- [ ] **Step 2: Insert the JS**

Use the Edit tool. Add this block immediately AFTER the existing `loadLivePositions()` function and its `setInterval` line:

```javascript
async function loadTodayRecs() {
  try {
    const res = await fetch('data/today_recommendations.json?t=' + Date.now());
    if (!res.ok) throw new Error('fetch failed');
    const d = await res.json();
    renderRecColumn('recs-spreads', d.spreads, renderSpreadCard,
      'No spread setups today — regime stable');
    renderRecColumn('recs-stocks', d.stocks, renderStockCard,
      'No standalone stock signals today');
    renderRecColumn('recs-news', d.news_driven, renderNewsCard,
      'No news-driven trades today');
  } catch (e) {
    ['recs-spreads', 'recs-stocks', 'recs-news'].forEach(id =>
      document.getElementById(id).innerHTML = '<div class="rec-empty">Offline</div>');
  }
}

function renderRecColumn(elId, items, renderFn, emptyMsg) {
  const el = document.getElementById(elId);
  el.innerHTML = '';
  if (!items || items.length === 0) {
    el.innerHTML = '<div class="rec-empty">' + emptyMsg + '</div>';
    return;
  }
  items.forEach(it => el.insertAdjacentHTML('beforeend', renderFn(it)));
}

function stalePill(it) { return it.is_stale ? '<span class="stale-pill">stale</span>' : ''; }

function renderSpreadCard(s) {
  return '<div class="rec-card">' +
    '<div class="name">' + s.name + stalePill(s) + '</div>' +
    '<div class="meta"><span class="conv-' + s.conviction + '">' + s.conviction + '</span>' +
    ' &middot; ' + s.action + ' &middot; z=' + Number(s.z_score).toFixed(2) + ' &middot; ' + s.reason + '</div>' +
    '</div>';
}

function renderStockCard(s) {
  return '<div class="rec-card">' +
    '<div class="name"><span class="dir-' + s.direction + '">' + s.direction + '</span> ' +
    s.ticker + stalePill(s) + '</div>' +
    '<div class="meta"><span class="conv-' + s.conviction + '">' + s.conviction + '</span>' +
    ' &middot; ' + s.trigger + '</div>' +
    '</div>';
}

function renderNewsCard(n) {
  return '<div class="rec-card">' +
    '<div class="name"><span class="dir-' + n.direction + '">' + n.direction + '</span> ' +
    n.ticker + stalePill(n) + '</div>' +
    '<div class="meta">' + n.headline + '</div>' +
    '<div class="meta">hit ' + Math.round(n.historical_hit_rate * 100) + '%' +
    ' &middot; ' + n.precedent_count + ' precedents &middot; ' + n.shelf_days + 'd shelf</div>' +
    '</div>';
}

loadTodayRecs();
setInterval(loadTodayRecs, 60000);
```

- [ ] **Step 3: Visual smoke-test in browser**

Hard-refresh `index.html` (Ctrl+Shift+R). Open DevTools.

Expected:
- `Network` tab shows `today_recommendations.json` returning 200
- `Console` shows zero errors
- The 3-column block renders cards with conviction colors, direction colors, no stale pills (data is fresh from this morning's run)
- If a column has no items, it shows the friendly empty message

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(site): fetch + render Today's Recommendations panel"
```

---

## Task 12: End-to-end + regression smoke test

**Files:**
- (none — verification)

- [ ] **Step 1: Run all exporter tests**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_website_exporter.py -v`
Expected: every test PASSES (Wave 1 + Wave 2 combined).

- [ ] **Step 2: Run the exporter once more, confirm fresh files**

Run: `python -X utf8 pipeline/website_exporter.py`
Expected: prints all 3 export lines, no traceback.

Run: `ls -la data/global_regime.json data/live_status.json data/today_recommendations.json`
Expected: all 3 files dated within the last minute.

- [ ] **Step 3: Browser checklist**

Open `index.html`, hard-refresh. Walk the page top-to-bottom:

- [ ] Hero block: NEUTRAL badge, score visible, drivers list (Wave 1, regression check)
- [ ] **Today's Recommendations**: 3 columns visible, each shows cards or honest empty message
- [ ] Live Positions: open spreads still render (Wave 1, regression check)
- [ ] Articles: still render (regression)
- [ ] F&O News: still renders (regression)
- [ ] DevTools Console: zero errors, zero new 404s

- [ ] **Step 4: Network tab check**

DevTools → Network → reload. Expected JSON requests:
- `global_regime.json` ✓
- `live_status.json` ✓
- `today_recommendations.json` ✓ (NEW)
- `articles_index.json` ✓
- `fno_news.json` ✓

No requests for: `track_record.json`, `spread_universe.json`, `weekly_index.json`, `msi_history.json`, anything else.

---

## Task 13: Push to live

**Files:**
- (none — deployment)

- [ ] **Step 1: Confirm with user before pushing**

Halt and ask: "Wave 2 ready to push to master / live askanka.com?"

If approved:

- [ ] **Step 2: Push**

```bash
cd C:/Users/Claude_Anka/askanka.com && git push origin master
```

- [ ] **Step 3: Wait for GitHub Pages to deploy (~1-2 minutes)**

- [ ] **Step 4: Open https://askanka.com, hard-refresh, repeat browser checklist from Task 12**

Confirm the live site shows the recommendations panel and no console errors.

---

## Self-Review Notes

**Spec coverage check:**
- ✅ `export_today_recommendations()` function → Tasks 3–7
- ✅ `stale_check()` helper → Task 2
- ✅ Constants (`RECOMMENDATIONS_FILE` etc., `STALE_HOURS`) → Task 2
- ✅ Spread filtering (drop INACTIVE/NONE) → Task 4
- ✅ Top-3 limit per column → Tasks 4, 5, 6
- ✅ Conviction-based sort + abs(z) tiebreak → Task 4
- ✅ Hit-rate sort for news → Task 6
- ✅ Per-card `source_timestamp` + `is_stale` → Tasks 4, 5, 6
- ✅ `holiday_mode: false` field hooked → Task 3
- ✅ Missing-file graceful fallback → Task 7
- ✅ `run_export()` writes new file → Task 8
- ✅ HTML section + CSS + JS → Tasks 9, 10, 11
- ✅ Empty-state honest messages → Task 11 JS
- ✅ Wave 1 regression coverage → Task 12
- ✅ Live verification → Task 13
- ✅ Bat-file wiring already from Wave 1 — explicitly noted, no task needed

**Type consistency check:**
- `RECOMMENDATIONS_FILE` defined Task 2, used Task 4 — consistent name
- `RANKER_STATE_FILE` defined Task 2, used Task 5 — consistent
- `NEWS_EVENTS_FILE` + `NEWS_VERDICTS_FILE` defined Task 2, used Task 6 — consistent
- `_CONV_RANK` defined Task 4, reused Task 5 — consistent
- Spread card keys: `name, action, conviction, z_score, reason, source_timestamp, is_stale` — match between Task 4 impl, Task 4 test assertion, and Task 11 `renderSpreadCard` (`s.name`, `s.conviction`, `s.action`, `s.z_score`, `s.reason`, `s.is_stale`)
- Stock card keys: `ticker, direction, conviction, trigger, source, source_timestamp, is_stale` — match Task 5 impl + Task 11 `renderStockCard`
- News card keys: `ticker, headline, category, direction, shelf_days, historical_hit_rate, precedent_count, source_timestamp, is_stale` — match Task 6 impl + Task 11 `renderNewsCard`
- Element IDs: `recs-spreads`, `recs-stocks`, `recs-news` — match Task 9 markup + Task 11 JS

**Placeholder scan:** No "TBD", no "implement later", no "similar to". Each task has actual code shown.

**Scope:** Single panel, single exporter fn, single HTML section. Right-sized for one plan.
