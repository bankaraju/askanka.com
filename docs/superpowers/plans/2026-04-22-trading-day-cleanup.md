# Trading-Day Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the 10 known issues that make each trading day start with bug-fixing instead of signal-watching. Make the terminal honest, the test suite green, and the Risk tab truthful in one day of focused work.

**Architecture:** Four phases executed in order — trading-visible fixes land first (market is open), test-suite hygiene second, Risk-page truth third, live-tick polling last. Each task ships: failing test → fix → passing test → docs/inventory updated → commit. No `--no-verify`, no "should work." Spec follows the doc-sync mandate from CLAUDE.md — code + SYSTEM_OPERATIONS_MANUAL.md + anka_inventory.json + memory updated together.

**Tech Stack:** Python 3.13, pytest, FastAPI (pipeline/terminal), vanilla JS (terminal static/), pandas/numpy, Windows Task Scheduler, git.

**Out of scope (separate plans or deferred):**
- Phase D — Slippage Stress Grid (see `2026-04-22-slippage-stress-grid.md`)
- Item 9 — TRUST_STRONG JS constant in public website (cosmetic, website only)
- Item 10 — MSI ribbon vs MSI panel dual-engine label (architectural, own spec)
- Item 11 — Phase C v5 ledgers v52–v55 empty (auto-resolves ~11:30 once intraday bars accumulate)

---

## File Map

**Modified:**
- `pipeline/news_intelligence.py` — classifier populates `matched_stocks` more aggressively (Item 1)
- `pipeline/news_backtest.py` — verdict rows always carry `category` even when `categories=[]` (Item 2)
- `pipeline/config/anka_inventory.json` — rewrite with proper UTF-8 em-dashes (Item 4)
- `pipeline/watchdog_inventory.py` — open with `encoding="utf-8"` (Item 7)
- `pipeline/spread_intelligence.py` — return `INACTIVE` when regime missing (Item 6)
- `pipeline/tests/test_signal_enrichment.py` — monkeypatch paths to tmp_path (Item 5)
- `pipeline/tests/test_website_exporter.py` — update cryptic-name + reason text assertions (Item 8)
- `pipeline/terminal/api/risk.py` (new) — regime-flip scenario from backtest CI (Item 12)
- `pipeline/terminal/api/live.py` (new) — /api/live_ltp endpoint (Item 13)
- `pipeline/terminal/static/js/components/live-ticker.js` (new) — DOM polling loop (Item 13)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — update news pipeline + risk page sections
- `memory/project_terminal_todo.md` — mark items resolved
- `memory/feedback_doc_sync_mandate.md` — add this cleanup as the "once and for all" reference

**Created:**
- `pipeline/tests/test_news_intelligence_matching.py`
- `pipeline/tests/test_news_backtest_category.py`
- `pipeline/tests/test_risk_regime_flip.py`
- `pipeline/tests/test_live_ltp_endpoint.py`
- `pipeline/tests/terminal/test_live_ticker_js.py`

---

## Phase A — Trading-Visible (market-open urgency)

### Task A1: News classifier attributes stocks to more events (Item 1)

**Problem:** 1449 events written today; nearly all have `matched_stocks: []`. `_name_match_stocks` in `pipeline/news_intelligence.py` only matches stocks when the F&O ticker name appears literally in the headline. "HDB Financial Services shares in focus on strong Q4 results" never matches because "HDB" ≠ "HDFC".

**Root cause:** The F&O universe has official tickers; news uses human company names, subsidiary names, and aliases. No alias table is loaded.

**Files:**
- Create: `pipeline/config/news_aliases.json` — map human name → F&O ticker
- Modify: `pipeline/news_intelligence.py:222-228` — augment `classify_event` with alias lookup
- Create: `pipeline/tests/test_news_intelligence_matching.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_news_intelligence_matching.py
from pipeline.news_intelligence import classify_event, _load_universe

UNIVERSE = ["HDFCBANK", "SUZLON", "RELIANCE"]

def test_alias_resolves_hdb_to_hdfcbank(monkeypatch, tmp_path):
    aliases = tmp_path / "news_aliases.json"
    aliases.write_text('{"HDB Financial Services": "HDFCBANK", "HDFC Bank": "HDFCBANK"}')
    monkeypatch.setattr("pipeline.news_intelligence.ALIASES_FILE", aliases)
    item = {
        "title": "HDB Financial Services shares in focus on strong Q4 results",
        "source": "MoneyControl", "url": "x", "published": "2026-04-22",
    }
    result = classify_event(item, UNIVERSE)
    assert result is not None
    assert "HDFCBANK" in result["matched_stocks"]

def test_direct_ticker_match_still_works(monkeypatch, tmp_path):
    aliases = tmp_path / "news_aliases.json"
    aliases.write_text("{}")
    monkeypatch.setattr("pipeline.news_intelligence.ALIASES_FILE", aliases)
    item = {"title": "RELIANCE hits 52-week high", "source": "x", "url": "x", "published": "x"}
    result = classify_event(item, UNIVERSE)
    assert "RELIANCE" in result["matched_stocks"]

def test_no_alias_and_no_ticker_returns_none_or_empty_stocks():
    item = {"title": "Gold prices rise on global cues", "source": "x", "url": "x", "published": "x"}
    result = classify_event(item, UNIVERSE)
    # Either rejected (None) OR returned with policy match but empty stocks — both acceptable
    assert result is None or result["matched_stocks"] == []
```

- [ ] **Step 2: Run tests — expect failure (no alias lookup yet)**

```bash
python -m pytest pipeline/tests/test_news_intelligence_matching.py -v
```
Expected: first two tests fail with `ModuleNotFoundError` for `ALIASES_FILE` or `"HDFCBANK" not in matched_stocks`.

- [ ] **Step 3: Seed `pipeline/config/news_aliases.json`**

Start with the top-30 F&O stocks that have distinct common-name variants:
```json
{
  "HDB Financial Services": "HDFCBANK",
  "HDFC Bank": "HDFCBANK",
  "Reliance Industries": "RELIANCE",
  "Tata Consultancy Services": "TCS",
  "Infosys": "INFY",
  "Bharti Airtel": "BHARTIARTL",
  "Bharat Electronics": "BEL",
  "Hindustan Aeronautics": "HAL",
  "Bharat Dynamics": "BDL",
  "State Bank of India": "SBIN",
  "Larsen & Toubro": "LT",
  "Mahindra & Mahindra": "M&M",
  "Tech Mahindra": "TECHM",
  "ICICI Bank": "ICICIBANK",
  "Kotak Mahindra": "KOTAKBANK",
  "Axis Bank": "AXISBANK",
  "Bajaj Finance": "BAJFINANCE",
  "Bajaj Finserv": "BAJAJFINSV",
  "Sun Pharma": "SUNPHARMA",
  "Dr Reddy": "DRREDDY",
  "Dr. Reddy's": "DRREDDY",
  "Maruti Suzuki": "MARUTI",
  "Hero MotoCorp": "HEROMOTOCO",
  "Eicher Motors": "EICHERMOT",
  "UltraTech Cement": "ULTRACEMCO",
  "Asian Paints": "ASIANPAINT",
  "Titan Company": "TITAN",
  "Adani Enterprises": "ADANIENT",
  "Adani Ports": "ADANIPORTS",
  "Power Grid": "POWERGRID"
}
```

- [ ] **Step 4: Wire alias lookup in `classify_event`**

In `pipeline/news_intelligence.py` near top:
```python
ALIASES_FILE = Path(__file__).parent / "config" / "news_aliases.json"

def _load_aliases() -> dict:
    if not ALIASES_FILE.exists():
        return {}
    try:
        return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

_ALIASES_CACHE: dict | None = None

def _alias_match_stocks(title: str, universe: list[str]) -> list[str]:
    global _ALIASES_CACHE
    if _ALIASES_CACHE is None:
        _ALIASES_CACHE = _load_aliases()
    title_lower = title.lower()
    matches: list[str] = []
    for phrase, ticker in _ALIASES_CACHE.items():
        if phrase.lower() in title_lower and ticker in universe and ticker not in matches:
            matches.append(ticker)
    return matches
```

Then in `classify_event` at line 224:
```python
matched_stocks = _name_match_stocks(title, universe)
matched_stocks.extend(
    t for t in _alias_match_stocks(title, universe) if t not in matched_stocks
)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
python -m pytest pipeline/tests/test_news_intelligence_matching.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run the full news_intelligence scan to produce fresh output**

```bash
python -m pipeline.news_intelligence --full
```
Confirm `pipeline/data/news_events_today.json` has some events with populated `matched_stocks` (> 0 is the minimum success).

```bash
python -c "
import json
d = json.load(open('pipeline/data/news_events_today.json'))
e = d['events']
total = len(e)
with_stocks = sum(1 for x in e if x.get('matched_stocks'))
print(f'events={total} with_stocks={with_stocks} pct={100*with_stocks/total:.1f}%')
"
```
Expected: `with_stocks > 0` and `pct > 5%` (baseline — will improve as alias table grows).

- [ ] **Step 7: Commit**

```bash
git add pipeline/news_intelligence.py pipeline/config/news_aliases.json pipeline/tests/test_news_intelligence_matching.py
git commit -m "feat(news): alias table so subsidiary/common names attribute to F&O ticker

HDB Financial Services → HDFCBANK, Dr. Reddy's → DRREDDY, etc.
Seeds top-30 common variants. Expands as we find unattributed events.

Fixes matched_stocks=[] blocking verdict generation (was ~99% empty)."
```

ETA: 45 min.

---

### Task A2: News backtest guarantees non-empty category per verdict (Item 2)

**Problem:** Verdicts in `pipeline/data/news_verdicts.json` have `category: ''` when the event's `categories` list is empty. `_build_news_recs()` in website_exporter joins events to verdicts by `(symbol, category)` — with either side empty, no match → news_driven=0.

**Root cause:** `news_backtest.py:176` does `category = categories[0] if categories else ""`. If events arrive without a category (low-confidence classifier output), verdicts get `""` and never match UI-side events (which have real categories).

**Fix strategy:** Drop events entirely when `categories=[]` (mirrors the `if not stocks: continue` guard), so the only verdicts we write are match-joinable. Alternative (more lenient) is to default to `"uncategorized"` but that creates a category that doesn't exist on the UI join side.

**Files:**
- Modify: `pipeline/news_backtest.py:168-183`
- Create: `pipeline/tests/test_news_backtest_category.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_news_backtest_category.py
import json
from pipeline.news_backtest import run_backtest

def test_verdicts_all_carry_nonempty_category(tmp_path, monkeypatch):
    events = {
        "last_scan": "2026-04-22T09:00:00+05:30",
        "events": [
            {"title": "SUZLON Q4 results beat", "matched_stocks": ["SUZLON"],
             "categories": ["results_announcement"]},
            {"title": "Mystery news", "matched_stocks": ["RELIANCE"], "categories": []},
        ],
    }
    events_file = tmp_path / "news_events_today.json"
    events_file.write_text(json.dumps(events))
    verdicts_file = tmp_path / "news_verdicts.json"
    monkeypatch.setattr("pipeline.news_backtest.EVENTS_TODAY", events_file)
    monkeypatch.setattr("pipeline.news_backtest.VERDICTS_FILE", verdicts_file)
    monkeypatch.setattr("pipeline.news_backtest.EVENTS_HISTORY", tmp_path / "missing.json")
    monkeypatch.setattr("pipeline.news_backtest.load_stock_prices", lambda s: None)

    run_backtest(target_date="2026-04-22")

    written = json.loads(verdicts_file.read_text())
    assert len(written) == 1  # mystery event without categories is dropped
    assert written[0]["symbol"] == "SUZLON"
    assert written[0]["category"] == "results_announcement"
    assert written[0]["category"] != ""
```

- [ ] **Step 2: Run test — expect failure**

```bash
python -m pytest pipeline/tests/test_news_backtest_category.py -v
```
Expected: FAIL — `len(written) == 2` (both verdicts written, second has `category=""`).

- [ ] **Step 3: Add the guard**

In `pipeline/news_backtest.py` at line ~169:
```python
    for event in events:
        stocks = event.get("matched_stocks", [])
        categories = event.get("categories", [])
        if not stocks:
            continue
        if not categories:
            # Verdict needs category for (symbol, category) join in website_exporter.
            # Uncategorized events are dropped rather than stored with empty category,
            # which would silently fail the downstream match.
            continue
        for symbol in stocks[:3]:
            ...
```

- [ ] **Step 4: Run test — expect pass**

```bash
python -m pytest pipeline/tests/test_news_backtest_category.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Regenerate verdicts against today's events**

```bash
python -m pipeline.news_backtest
```
Then verify `news_verdicts.json` has 0 rows with empty category:

```bash
python -c "
import json
v = json.load(open('pipeline/data/news_verdicts.json'))
empty = [x for x in v if not x.get('category')]
print(f'total={len(v)} empty_category={len(empty)}')
"
```
Expected: `empty_category=0`.

- [ ] **Step 6: Verify news_driven now populates in website_exporter output**

```bash
python -m pipeline.website_exporter
python -c "
import json
d = json.load(open('data/today_recommendations.json'))
print('news_driven count:', len(d['news_driven']))
for n in d['news_driven']:
    print(' ', n['ticker'], n['category'], n['direction'])
"
```
Expected: `news_driven count: > 0`. If still 0, the upstream events truly don't have qualifying (HIGH_IMPACT/MODERATE) verdicts today — not a bug but a signal-quality observation; record in memory as the Phase A completion note.

- [ ] **Step 7: Commit**

```bash
git add pipeline/news_backtest.py pipeline/tests/test_news_backtest_category.py
git commit -m "fix(news): skip events without categories so verdicts always join-safe

Empty category silently broke the (symbol, category) join in
website_exporter._build_news_recs, leaving News panel blank.
Upstream contract: events without categories are noise for this
pipeline and are dropped at verdict generation."
```

ETA: 30 min.

---

### Task A3: Root-cause yesterday's 4 failed scheduler tasks (Item 3)

**Problem:** `AnkaSignal0942` (exit -1 = uncaught exception), `AnkaSignal1012` (exit 1), `AnkaSignal1142` (exit 2), `AnkaPhaseCShadowOpen` (exit 1) all failed yesterday. No test covers them; logs are the only source.

**Files:**
- Read: `pipeline/logs/signals.log`, `pipeline/logs/phase_c_shadow.log`, `pipeline/logs/shadow.log`
- Modify: whichever script the errors point to
- Modify: `pipeline/config/anka_inventory.json` — bump grace_multiplier if the failure was flaky-timing

- [ ] **Step 1: Extract yesterday's stderr for each task**

```bash
# Windows Event Viewer → Task Scheduler log has the launch/exit info.
# Python-level traceback is in the task's own log file.
grep -iE "error|traceback|exception" pipeline/logs/signals.log | tail -40
grep -iE "error|traceback|exception" pipeline/logs/phase_c_shadow.log | tail -40
grep -iE "error|traceback|exception" pipeline/logs/shadow.log | tail -40
```

For each failure, find the timestamp range and the exception type. Document in plan comments.

- [ ] **Step 2: For each distinct root cause, write a failing regression test**

Example if the failure is `KeyError: 'entry_price'` when signal_tracker processes a signal missing that field:

```python
# pipeline/tests/test_signal_tracker_missing_fields.py
from pipeline.signal_tracker import update_signal_row

def test_missing_entry_price_doesnt_crash():
    row = {"signal_id": "X", "ticker": "HAL", "ltp": 100}  # no entry_price
    result = update_signal_row(row, current_ltp=105)
    assert result is not None  # graceful skip, not crash
    assert result.get("status") in (None, "PENDING_ENTRY", "SKIPPED")
```

- [ ] **Step 3: Run tests — expect fail**
- [ ] **Step 4: Fix the script (guard the missing field, log + skip)**
- [ ] **Step 5: Run tests — expect pass**

- [ ] **Step 6: Record in memory**

Write `memory/project_scheduler_failures_2026_04_21.md` with: which task, which log line, root cause, fix commit. So next time a similar failure shows up the pattern is already logged.

- [ ] **Step 7: Commit**

```bash
git add pipeline/<script>.py pipeline/tests/test_<name>.py memory/project_scheduler_failures_2026_04_21.md
git commit -m "fix(scheduler): guard <N>4 failed intraday tasks from 2026-04-21

AnkaSignal0942/1012/1142/PhaseCShadowOpen — see
memory/project_scheduler_failures_2026_04_21.md for log details."
```

ETA: 60 min (longer if multiple distinct root causes).

---

### Task A4: Rewrite anka_inventory.json with proper UTF-8 (Item 4)

**Problem:** `pipeline/config/anka_inventory.json` has `â€"` mojibake where em-dashes (`—`) should be. This is Windows-1252 bytes decoded as UTF-8. Causes `UnicodeDecodeError` when `watchdog_inventory.py` reads it (related to Item 7).

**Files:**
- Modify: `pipeline/config/anka_inventory.json` — single rewrite with UTF-8

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_inventory_utf8.py
from pathlib import Path
import json

INV = Path(__file__).parent.parent / "config" / "anka_inventory.json"

def test_inventory_is_valid_utf8_no_mojibake():
    raw = INV.read_bytes()
    # Must decode as UTF-8 cleanly
    text = raw.decode("utf-8")
    # No Windows-1252 mojibake for em-dash
    assert "â€" not in text, "inventory has Windows-1252 em-dash mojibake"
    # Must parse as valid JSON
    data = json.loads(text)
    assert "tasks" in data
```

- [ ] **Step 2: Run test — expect fail (mojibake present)**

- [ ] **Step 3: Rewrite the file**

```bash
python -c "
from pathlib import Path
import json
p = Path('pipeline/config/anka_inventory.json')
# Read as-is (may have mojibake), replace the mojibake with the real character
raw = p.read_bytes().decode('utf-8', errors='replace')
fixed = raw.replace('â€\"', '—').replace('â€\u201d', '—').replace('â€\u201c', '—')
# Parse + re-dump with ensure_ascii=False so em-dashes stay as UTF-8
data = json.loads(fixed)
p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print('rewritten')
"
```

- [ ] **Step 4: Run test — expect pass**

- [ ] **Step 5: Commit**

```bash
git add pipeline/config/anka_inventory.json pipeline/tests/test_inventory_utf8.py
git commit -m "fix(inventory): rewrite with proper UTF-8 em-dashes

Mojibake 'â€—' was the Windows-1252 artifact of an editor that
saved in cp1252. Reload with utf-8 strict + add a regression test."
```

ETA: 15 min.

---

## Phase B — Test Suite Hygiene

### Task B5: signal_enrichment tests read isolated fixtures (Item 5)

**Problem:** 5 tests in `pipeline/tests/test_signal_enrichment.py` load real `data/trust_scores.json` and assert grades that drifted in production (GAIL was A, now F).

**Files:**
- Modify: `pipeline/tests/test_signal_enrichment.py:140-330`

- [ ] **Step 1: Identify the load path being read**

```bash
grep -n "load_trust_scores\|data/trust_scores" pipeline/tests/test_signal_enrichment.py | head -10
grep -n "TRUST_SCORES_FILE\|load_trust_scores" pipeline/signal_enrichment.py | head -10
```

- [ ] **Step 2: Wrap each of the 5 failing tests with tmp_path monkeypatch of the data constant**

```python
def test_load_trust_scores_returns_dict_by_symbol(tmp_path, monkeypatch):
    fake = tmp_path / "trust.json"
    fake.write_text('{"GAIL": {"trust_grade": "A", "trust_score": 82.0}}')
    monkeypatch.setattr("pipeline.signal_enrichment.TRUST_SCORES_FILE", fake)
    from pipeline.signal_enrichment import load_trust_scores
    result = load_trust_scores()
    assert result["GAIL"]["trust_grade"] == "A"
```

Repeat the pattern for the other 4 tests. Each test gets its own tmp_path fixture so no cross-contamination.

- [ ] **Step 3: Run tests — expect 5 pass**

```bash
python -m pytest pipeline/tests/test_signal_enrichment.py -v
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/tests/test_signal_enrichment.py
git commit -m "test(signal_enrichment): isolate from production trust_scores.json

Tests were asserting GAIL grade=A but production data has drifted
to F. Fix: monkeypatch TRUST_SCORES_FILE to tmp_path per test.
Tests now exercise the loader contract, not production data."
```

ETA: 30 min.

---

### Task B6: spread_intelligence returns INACTIVE when regime missing (Item 6)

**Problem:** `test_gate_regime_inactive` expects status `"INACTIVE"`, gate returns `"INSUFFICIENT_DATA"`. The status code drifted.

**Files:**
- Read: `pipeline/spread_intelligence.py` — find where `INSUFFICIENT_DATA` is returned
- Modify: either the source (return INACTIVE when regime missing) or the test (expand accepted set)

**Design decision:** `INACTIVE` is the correct user-facing term when regime is explicitly "this spread doesn't apply." `INSUFFICIENT_DATA` is for "we couldn't determine." They're distinct signals; UI should show them differently. Keep both, but make the specific case (regime absent) return `INACTIVE`, and the case (regime fetch failed) return `INSUFFICIENT_DATA`.

- [ ] **Step 1: Read the gate function**

```bash
grep -n "INSUFFICIENT_DATA\|INACTIVE\|def gate" pipeline/spread_intelligence.py | head -10
```

- [ ] **Step 2: Identify the branch returning wrong code**

- [ ] **Step 3: Write the failing test exactly as current spec intends (both codes distinct)**

```python
# extend pipeline/tests/test_spread_intelligence.py
def test_gate_regime_inactive():
    # Regime is explicitly not in eligible_spreads → INACTIVE
    result = gate(regime={"zone": "RISK-OFF", "eligible_spreads": {}}, ...)
    assert result["status"] == "INACTIVE"

def test_gate_regime_missing_returns_insufficient_data():
    # Regime data absent entirely → INSUFFICIENT_DATA
    result = gate(regime={}, ...)
    assert result["status"] == "INSUFFICIENT_DATA"
```

- [ ] **Step 4: Fix gate logic so both branches hit their correct status code**

- [ ] **Step 5: Run tests — expect pass**

- [ ] **Step 6: Commit**

```bash
git add pipeline/spread_intelligence.py pipeline/tests/test_spread_intelligence.py
git commit -m "fix(spread_intelligence): distinguish INACTIVE vs INSUFFICIENT_DATA

INACTIVE = regime explicitly excludes this spread (expected, show muted).
INSUFFICIENT_DATA = regime fetch failed (alert, show warning)."
```

ETA: 15 min.

---

### Task B7: watchdog_inventory reads UTF-8 (Item 7)

**Problem:** `pipeline/watchdog_inventory.py:31` calls `json.load(f)` with a file opened without explicit encoding — defaults to cp1252 on Windows and crashes on the em-dashes.

**Files:**
- Modify: `pipeline/watchdog_inventory.py:28-32`

- [ ] **Step 1: Read current `load_inventory`**

- [ ] **Step 2: Modify to specify encoding**

```python
def load_inventory(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 3: Run the existing test — expect pass**

```bash
python -m pytest pipeline/tests/test_watchdog_errors.py::TestLoadInventory -v
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/watchdog_inventory.py
git commit -m "fix(watchdog): read inventory with explicit utf-8 encoding

Default open() was cp1252 on Windows which crashed on em-dashes.
Pairs with inventory rewrite (Item 4)."
```

ETA: 5 min.

---

### Task B8: Update cosmetic website_exporter test assertions (Item 8)

**Problem:** 4 tests assert old text that production has evolved past:
- `test_live_status_only_positions_and_fragility` expects `"Defence vs IT"` — actual is `"Sovereign Shield Alpha"` (cryptic names intentional, see `_CRYPTIC_NAMES`)
- `test_news_sorted_by_hit_rate_desc`, `test_news_card_fields` — currently fail on empty news_driven; should pass after Tasks A1+A2 fix the pipeline
- `test_daily_stop_reason_unchanged` expects `"Trailing stop"` — actual is `"Daily stop"` (signal_tracker text changed)

**Files:**
- Modify: `pipeline/tests/test_website_exporter.py`

- [ ] **Step 1: Update `test_live_status_only_positions_and_fragility` to accept cryptic name**

```python
assert pos["spread_name"] == "Sovereign Shield Alpha"  # cryptic of Defence vs IT
```

- [ ] **Step 2: Re-run news tests (should now pass if A1/A2 are done)**

```bash
python -m pytest pipeline/tests/test_website_exporter.py::test_news_sorted_by_hit_rate_desc pipeline/tests/test_website_exporter.py::test_news_card_fields -v
```

If still fail, the fixture needs an update — match fixture event's `categories` to fixture verdict's `category`. Inspect `_patch_all_sources` in the test file.

- [ ] **Step 3: Fix `test_daily_stop_reason_unchanged`**

Update the assertion to match actual signal_tracker output:
```python
assert "Daily stop" in reason or "Trailing stop" in reason
```

- [ ] **Step 4: Run full website_exporter suite — expect all pass**

```bash
python -m pytest pipeline/tests/test_website_exporter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/tests/test_website_exporter.py
git commit -m "test(website_exporter): sync assertions with current production strings

- Spread names now use cryptic variants (Sovereign Shield Alpha)
- Daily-stop reason text updated in signal_tracker"
```

ETA: 15 min.

---

## Phase B.5 — Risk Page Truth (Item 12)

### Task B5.12: Regime-flip scenario from ETF engine backtest CI

**Problem:** Terminal Risk tab shows `"Regime flip from RISK-OFF (placeholder: -2%/position)"` — literally hardcoded. Trader cannot trust the number.

**User-confirmed spec:** Replace with backtest-derived worst-case drawdown at a confidence interval. For the current regime (e.g. RISK-OFF), find all prior flips in the 716-day backtest, compute per-position drawdown distribution, use p95 as the displayed loss. Display carries "p95 of N=k historical flips" subtext.

**Files:**
- Create: `pipeline/terminal/api/risk.py`
- Create: `pipeline/autoresearch/regime_flip_analyzer.py` — computes CI from backtest
- Modify: `pipeline/terminal/app.py` — mount `/api/risk/regime-flip`
- Modify: `pipeline/terminal/static/js/pages/risk.js` — render backtest-derived figure + subtext
- Create: `pipeline/tests/test_risk_regime_flip.py`

- [ ] **Step 1: Inspect backtest output**

```bash
python -c "
import json
d = json.load(open('pipeline/autoresearch/backtest_results.json'))
print(list(d.keys())[:20])
"
```
Expected: the backtest stores daily regime + price series.

- [ ] **Step 2: Write the failing test**

```python
# pipeline/tests/test_risk_regime_flip.py
import json
from pathlib import Path
from pipeline.autoresearch.regime_flip_analyzer import compute_flip_drawdown_ci

def test_ci_returned_with_sample_count(tmp_path):
    backtest = {
        "daily": [
            {"date": "2024-01-01", "zone": "RISK-OFF", "pnl_pct": 0.0},
            {"date": "2024-01-02", "zone": "RISK-OFF", "pnl_pct": 1.2},
            {"date": "2024-01-03", "zone": "RISK-ON",  "pnl_pct": -3.5},
            {"date": "2024-01-04", "zone": "RISK-ON",  "pnl_pct": 0.8},
            {"date": "2024-02-01", "zone": "RISK-OFF", "pnl_pct": 0.0},
            {"date": "2024-02-02", "zone": "RISK-ON",  "pnl_pct": -2.1},
        ]
    }
    bt_file = tmp_path / "bt.json"
    bt_file.write_text(json.dumps(backtest))

    result = compute_flip_drawdown_ci(bt_file, from_zone="RISK-OFF", to_zone="RISK-ON",
                                      percentile=95)
    assert result["n_flips"] == 2
    assert result["p95_drawdown_pct"] < 0  # worst case is a loss
    assert -3.5 <= result["p95_drawdown_pct"] <= -2.1
    assert result["from_zone"] == "RISK-OFF"
```

- [ ] **Step 3: Run — expect ImportError**

- [ ] **Step 4: Implement `compute_flip_drawdown_ci`**

```python
# pipeline/autoresearch/regime_flip_analyzer.py
import json
from pathlib import Path
import numpy as np

def compute_flip_drawdown_ci(backtest_path: Path, from_zone: str, to_zone: str,
                              percentile: int = 95) -> dict:
    """Find historical regime flips and compute drawdown CI per position.

    For each day the zone changes from `from_zone` to `to_zone`, record
    the next-day pnl_pct. Return the given percentile of those pnls as the
    "worst realistic" loss per position.
    """
    data = json.loads(Path(backtest_path).read_text(encoding="utf-8"))
    daily = data.get("daily", [])
    flip_pnls: list[float] = []
    prev_zone = None
    for i, row in enumerate(daily):
        zone = row.get("zone")
        if prev_zone == from_zone and zone == to_zone and i + 1 < len(daily):
            next_row = daily[i]  # the flip day itself — use same-day pnl as the drawdown
            flip_pnls.append(float(next_row.get("pnl_pct", 0)))
        prev_zone = zone

    if not flip_pnls:
        return {"n_flips": 0, "p95_drawdown_pct": None,
                "from_zone": from_zone, "to_zone": to_zone}

    p95 = float(np.percentile(flip_pnls, 100 - percentile))  # worst = low percentile of returns
    return {"n_flips": len(flip_pnls), "p95_drawdown_pct": p95,
            "from_zone": from_zone, "to_zone": to_zone,
            "sample_pnls": flip_pnls}
```

- [ ] **Step 5: Test passes**

- [ ] **Step 6: Add `/api/risk/regime-flip` FastAPI endpoint**

```python
# pipeline/terminal/api/risk.py
from fastapi import APIRouter
from pathlib import Path
from pipeline.autoresearch.regime_flip_analyzer import compute_flip_drawdown_ci

router = APIRouter()
_BT = Path(__file__).parent.parent.parent / "autoresearch" / "backtest_results.json"

@router.get("/api/risk/regime-flip")
def regime_flip(from_zone: str = "RISK-OFF", to_zone: str = "RISK-ON"):
    if not _BT.exists():
        return {"error": "backtest not available", "n_flips": 0}
    return compute_flip_drawdown_ci(_BT, from_zone, to_zone, percentile=95)
```

Mount in `pipeline/terminal/app.py`:
```python
from pipeline.terminal.api import risk as risk_api
app.include_router(risk_api.router)
```

- [ ] **Step 7: Write endpoint test**

```python
# pipeline/tests/test_live_ltp_endpoint.py (reuse file)
from fastapi.testclient import TestClient
from pipeline.terminal.app import app

def test_regime_flip_endpoint_returns_ci():
    client = TestClient(app)
    r = client.get("/api/risk/regime-flip?from_zone=RISK-OFF&to_zone=RISK-ON")
    assert r.status_code == 200
    data = r.json()
    assert "n_flips" in data
```

- [ ] **Step 8: Update `risk.js` to consume the endpoint**

```javascript
// pipeline/terminal/static/js/pages/risk.js — replace the placeholder row
async function renderRegimeFlipScenario() {
  const data = await fetch('/api/risk/regime-flip?from_zone=RISK-OFF&to_zone=RISK-ON').then(r => r.json());
  const cell = document.querySelector('.regime-flip-pnl');
  if (data.n_flips === 0) {
    cell.textContent = 'n/a (0 historical flips)';
    return;
  }
  const positions = window.currentPositions?.length || 6;
  const aggregate = (data.p95_drawdown_pct * positions).toFixed(2);
  cell.textContent = `${aggregate}%`;
  cell.title = `p95 of N=${data.n_flips} historical RISK-OFF→RISK-ON flips — ${data.p95_drawdown_pct.toFixed(2)}% per position`;
}
```

- [ ] **Step 9: Verify in browser** — reload terminal, Risk tab shows real p95 figure with tooltip showing N=k.

- [ ] **Step 10: Commit**

```bash
git add pipeline/autoresearch/regime_flip_analyzer.py pipeline/terminal/api/risk.py \
        pipeline/terminal/app.py pipeline/terminal/static/js/pages/risk.js \
        pipeline/tests/test_risk_regime_flip.py
git commit -m "feat(risk): regime-flip scenario from 716-day backtest p95, not -2% placeholder

Risk tab's regime-flip row was hardcoded -2%/position. Now it
reads /api/risk/regime-flip which computes p95 drawdown from all
historical RISK-OFF→RISK-ON transitions in backtest_results.json,
carrying 'p95 of N=k flips' subtext so trader sees sample size."
```

ETA: 45 min.

---

## Phase C — Live Feel (Item 13)

### Task C13: Frontend live-tick poller with /api/live_ltp backend

**Problem:** Terminal P&L and LTP rows appear frozen because `live_status.json` only refreshes every 15 min during the intraday batch. Between batches, rendered prices are stale.

**Solution:** Add `/api/live_ltp?tickers=HAL,BEL,TCS` backend endpoint that returns current LTPs via the existing Kite session. Frontend polls every 5s and patches the DOM `current` cells in place. `live_status.json` remains the snapshot authority; polling is a presentation layer.

**Files:**
- Create: `pipeline/terminal/api/live.py`
- Create: `pipeline/terminal/static/js/components/live-ticker.js`
- Modify: `pipeline/terminal/static/js/pages/trading.js` — call `startLivePolling()` on page load
- Modify: `pipeline/terminal/app.py` — mount new router
- Create: `pipeline/tests/test_live_ltp_endpoint.py`

- [ ] **Step 1: Write backend test**

```python
# pipeline/tests/test_live_ltp_endpoint.py
from fastapi.testclient import TestClient
from pipeline.terminal.app import app

def test_live_ltp_returns_dict_per_ticker(monkeypatch):
    monkeypatch.setattr("pipeline.terminal.api.live.fetch_ltps",
                        lambda tickers: {t: 100.0 + i for i, t in enumerate(tickers)})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,BEL,TCS")
    assert r.status_code == 200
    assert r.json() == {"HAL": 100.0, "BEL": 101.0, "TCS": 102.0}

def test_live_ltp_rejects_empty_tickers():
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=")
    assert r.status_code == 400

def test_live_ltp_caps_request_size():
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=" + ",".join([f"T{i}" for i in range(100)]))
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect fail (module doesn't exist)**

- [ ] **Step 3: Implement backend**

```python
# pipeline/terminal/api/live.py
from fastapi import APIRouter, HTTPException, Query
from pipeline.signal_tracker import fetch_current_prices

router = APIRouter()

def fetch_ltps(tickers: list[str]) -> dict[str, float]:
    """Shim for test monkeypatching — production uses signal_tracker."""
    return fetch_current_prices(tickers) or {}

@router.get("/api/live_ltp")
def live_ltp(tickers: str = Query(...)):
    tickers_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not tickers_list:
        raise HTTPException(400, "tickers parameter is empty")
    if len(tickers_list) > 50:
        raise HTTPException(400, "max 50 tickers per request")
    result = fetch_ltps(tickers_list)
    return {t: float(result.get(t, 0.0)) for t in tickers_list}
```

Mount in `pipeline/terminal/app.py`:
```python
from pipeline.terminal.api import live as live_api
app.include_router(live_api.router)
```

- [ ] **Step 4: Run tests — expect 3 pass**

- [ ] **Step 5: Implement frontend poller**

```javascript
// pipeline/terminal/static/js/components/live-ticker.js
export function startLivePolling(intervalMs = 5000) {
  let timer = null;
  const tick = async () => {
    const cells = document.querySelectorAll('[data-live-ltp-ticker]');
    if (cells.length === 0) return;
    const tickers = [...new Set([...cells].map(c => c.dataset.liveLtpTicker))];
    if (tickers.length === 0) return;
    try {
      const data = await fetch('/api/live_ltp?tickers=' + tickers.join(',')).then(r => r.json());
      cells.forEach(c => {
        const t = c.dataset.liveLtpTicker;
        if (data[t]) {
          const entry = parseFloat(c.dataset.entry || '0');
          const ltp = data[t];
          c.textContent = `₹${ltp.toFixed(2)}`;
          if (entry > 0) {
            const isLong = c.dataset.side === 'long';
            const pnl = isLong ? (ltp / entry - 1) * 100 : (1 - ltp / entry) * 100;
            const pnlCell = c.closest('tr')?.querySelector('.pnl-cell');
            if (pnlCell) pnlCell.textContent = `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`;
          }
        }
      });
    } catch (e) {
      console.warn('[live-ticker] poll failed:', e);
    }
  };
  tick();
  timer = setInterval(tick, intervalMs);
  return () => clearInterval(timer);
}
```

- [ ] **Step 6: Annotate DOM cells in live-status render**

Wherever the LTP cell is rendered (likely `signals-table.js` or `live-status.js`), add `data-live-ltp-ticker="HAL" data-entry="4284.8" data-side="long"` attributes.

- [ ] **Step 7: Call `startLivePolling()` on trading-page load**

```javascript
// pipeline/terminal/static/js/pages/trading.js
import { startLivePolling } from '/static/js/components/live-ticker.js';
// At page ready:
startLivePolling(5000);
```

- [ ] **Step 8: Verify in browser**

- Open terminal (http://localhost:8501)
- Network tab: `/api/live_ltp?tickers=...` fires every 5s
- LTP cells + P&L cells update between 15-min batches
- No UI freeze / jank

- [ ] **Step 9: Commit**

```bash
git add pipeline/terminal/api/live.py pipeline/terminal/app.py \
        pipeline/terminal/static/js/components/live-ticker.js \
        pipeline/terminal/static/js/pages/trading.js \
        pipeline/tests/test_live_ltp_endpoint.py
git commit -m "feat(terminal): 5s live LTP polling — no more frozen P&L between batches

/api/live_ltp?tickers=... returns current prices from Kite session
live-ticker.js polls every 5s, patches DOM cells in place
live_status.json remains the snapshot source — this is render-only"
```

ETA: 60 min.

---

## Phase Z — Docs + Memory (always last, always required)

### Task Z1: Update SYSTEM_OPERATIONS_MANUAL.md

**Sections to touch:**
- Add `/api/live_ltp` + `/api/risk/regime-flip` to the API endpoint reference
- Update News Intelligence section: alias table is now a requirement, events without categories are dropped
- Update Risk page description: regime-flip uses backtest p95
- Note that intraday cycle is a snapshot (15-min) and frontend polls supplement

- [ ] **Step 1: Edit doc**
- [ ] **Step 2: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs: sync operations manual with 2026-04-22 cleanup changes"
```

ETA: 15 min.

### Task Z2: Update memory files

- Mark `project_terminal_todo.md` items resolved
- Add `project_trading_day_cleanup_2026_04_22.md` — summary of the 13-item burndown
- Update `feedback_doc_sync_mandate.md` — reference this cleanup as the "once and for all" case

- [ ] **Step 1: Edit memory files**
- [ ] **Step 2: Update MEMORY.md index**
- [ ] **Step 3: Commit**

```bash
git add memory/
git commit -m "memory: log 2026-04-22 trading-day cleanup + mark resolved items"
```

ETA: 10 min.

---

## Total ETA

- Phase A (trading-visible): 2h 30min
- Phase B (test hygiene): 1h 5min
- Phase B.5 (risk truth): 45min
- Phase C (live feel): 1h
- Phase Z (docs + memory): 25min

**~6 hours end-to-end** with the test/commit cadence. Could compress to 4 hours if phases B + Z are batched.

## Execution Flags

**Deploy mid-day (Phase A items safe to land during market hours):**
- A1, A2, A4 — pure fixes, no live-data schema changes
- A3 — only ships a fix + test; failure patterns for yesterday

**Deploy next intraday cycle boundary (15-min window):**
- B.5 (Risk page) — browser refresh needed to see new endpoint
- C13 (live polling) — browser refresh needed

**Safe to deploy anytime (no runtime impact):**
- B5, B6, B7, B8 — test suite only
- Z1, Z2 — docs/memory only
