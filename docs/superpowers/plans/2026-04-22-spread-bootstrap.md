# Spread Bootstrap — Same-Day Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Whenever `regime_scanner.py` marks a spread eligible and that spread is missing from `pipeline/data/spread_stats.json`, compute its per-regime distribution inline — before the 09:30 intraday cycle starts — so the gate can actually grade it today, not a week from Sunday. Tier each regime bucket by sample count so the trader can see which grades are fully-supported vs provisional.

**Architecture:** New module `pipeline/spread_bootstrap.py` reuses the existing EODHD fetch + `compute_spread_return` primitives from `pipeline/spread_statistics.py`, restricted to a 2-year window. Hook point: end of `regime_scanner.scan_regime()` after `eligible_spreads` is built — iterate unknown names, call `bootstrap.ensure()`, merge results into `spread_stats.json`. Defensive second hook: `spread_intelligence.compute_gate` calls `ensure()` before giving up with INSUFFICIENT_DATA. **Tiering rule applied at both write and read time:**

- `n_samples ≥ 30` → **FULL** tier (grade normally, conviction HIGH/MEDIUM/LOW as computed)
- `15 ≤ n_samples < 30` → **PROVISIONAL** tier (grade, but downstream consumers see a `tier: "PROVISIONAL"` flag so the UI can show the sample count and a soft-confidence badge)
- `n_samples < 15` → **dropped at write time** (never lands in spread_stats.json)

Tier is derived from `n_samples` at read time — the data file just stores `n_samples, mean, std`. No schema migration if thresholds change later. No new scheduled task; weekly `AnkaSpreadStats` stays refresh-only but applies the same drop-below-15 filter.

**Tech Stack:** Python 3.13, pytest, pandas/numpy (already loaded), EODHD API (existing `eodhd_client.fetch_eod_series`), JSON.

**Out of scope:**
- Weekly refresh redesign (stays as-is)
- Dynamic Project B pairs (separate file, separate pipeline)
- UI changes — the fix to how `Conviction: NONE` is populated in `eligible_spreads` is a different plan (Task 0 below flags it)

---

## File Map

**Created:**
- `pipeline/spread_bootstrap.py` — `ensure(name, long_legs, short_legs, window_days=730, min_samples=30) -> dict` + CLI
- `pipeline/tests/test_spread_bootstrap.py`

**Modified:**
- `pipeline/regime_scanner.py` — call bootstrap for unknown eligible_spreads before writing today_regime.json
- `pipeline/spread_intelligence.py` — defensive `ensure()` at top of `compute_gate`
- `pipeline/spread_statistics.py` — `compute_regime_stats` now drops buckets with < `MIN_SAMPLES=30`
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — new "Spread Bootstrap" sub-section in the Station 2 row
- `memory/project_spread_bootstrap.md` — new memory + MEMORY.md pointer

---

## Task 0 (context note, not a coding task)

**IMPORTANT:** This plan fixes the *data* gap — it does NOT fix the wiring gap where `today_regime.json['eligible_spreads'][name]` lacks a `conviction` field and thus the candidates API defaults to `"NONE"`. That's a separate plan (`gate-to-eligible_spreads wiring`). After this plan lands, all 6 visible static spreads will have complete stats, but the terminal will still show `NONE` conviction until the wiring plan lands. Flag this explicitly to the user in the implementation report so expectations are aligned.

---

## Task 1: Create `spread_bootstrap.ensure()` — TDD

**Files:**
- Create: `pipeline/spread_bootstrap.py`
- Create: `pipeline/tests/test_spread_bootstrap.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_spread_bootstrap.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spread_bootstrap import ensure


def _seed_msi_history(path, rows):
    """rows: list of (date_str, msi_score) — regime classified by MSI thresholds."""
    path.write_text(json.dumps([{"date": d, "msi_score": s} for d, s in rows]),
                    encoding="utf-8")


def _fake_eod(legs_prices):
    """Return a fake fetch_eod_series that returns canned series per ticker."""
    def fetch(ticker, start, end):
        return [{"date": d, "close": p} for d, p in legs_prices.get(ticker, [])]
    return fetch


def test_ensure_writes_three_regime_buckets(tmp_path, monkeypatch):
    msi = tmp_path / "msi_history.json"
    stats = tmp_path / "spread_stats.json"
    stats.write_text("{}", encoding="utf-8")

    # 120 days: 40 in each regime — well above MIN_SAMPLES=30
    rows = []
    for i in range(40): rows.append((f"2025-01-{i+1:02d}", 80))   # MACRO_STRESS
    for i in range(40): rows.append((f"2025-03-{i+1:02d}", 50))   # MACRO_NEUTRAL
    for i in range(40): rows.append((f"2025-05-{i+1:02d}", 20))   # MACRO_EASY
    _seed_msi_history(msi, rows)

    # Monotonic prices so spread returns are non-zero and finite
    long_prices  = {f"2025-{r[0][5:7]}-{r[0][8:]}": 100 + i for i, r in enumerate(rows)}
    short_prices = {f"2025-{r[0][5:7]}-{r[0][8:]}": 200 - i * 0.5 for i, r in enumerate(rows)}
    fake = _fake_eod({
        "SUNPHARMA": list(long_prices.items()),
        "HDFCBANK":  list(short_prices.items()),
    })

    monkeypatch.setattr("spread_bootstrap.MSI_HISTORY_FILE", msi)
    monkeypatch.setattr("spread_bootstrap.SPREAD_STATS_FILE", stats)
    monkeypatch.setattr("spread_bootstrap.fetch_eod_series", fake)

    result = ensure("Pharma vs Banks", ["SUNPHARMA"], ["HDFCBANK"])
    assert result["name"] == "Pharma vs Banks"
    assert set(result["regimes"].keys()) == {"MACRO_STRESS", "MACRO_NEUTRAL", "MACRO_EASY"}
    for bucket in result["regimes"].values():
        assert bucket["n_samples"] >= 30
        assert "mean" in bucket and "std" in bucket

    on_disk = json.loads(stats.read_text(encoding="utf-8"))
    assert "Pharma vs Banks" in on_disk


def test_ensure_tiers_buckets_by_sample_count(tmp_path, monkeypatch):
    """n>=30 -> FULL, 15<=n<30 -> PROVISIONAL, n<15 -> dropped."""
    msi = tmp_path / "msi_history.json"
    stats = tmp_path / "spread_stats.json"
    stats.write_text("{}", encoding="utf-8")

    # 40 MACRO_STRESS (FULL), 20 MACRO_NEUTRAL (PROVISIONAL), 10 MACRO_EASY (dropped)
    rows = [(f"2025-01-{i+1:02d}", 80) for i in range(40)] + \
           [(f"2025-02-{i+1:02d}", 50) for i in range(20)] + \
           [(f"2025-03-{i+1:02d}", 20) for i in range(10)]
    _seed_msi_history(msi, rows)

    prices = {r[0]: 100 + i for i, r in enumerate(rows)}
    fake = _fake_eod({"A": list(prices.items()), "B": list(prices.items())})
    monkeypatch.setattr("spread_bootstrap.MSI_HISTORY_FILE", msi)
    monkeypatch.setattr("spread_bootstrap.SPREAD_STATS_FILE", stats)
    monkeypatch.setattr("spread_bootstrap.fetch_eod_series", fake)

    result = ensure("Test Pair", ["A"], ["B"])
    assert result["regimes"]["MACRO_STRESS"]["n_samples"] == 40
    assert result["regimes"]["MACRO_NEUTRAL"]["n_samples"] == 20
    assert "MACRO_EASY" not in result["regimes"]  # 10 < 15, dropped at write

    # Derived tier helper
    from spread_bootstrap import tier_from_n
    assert tier_from_n(40) == "FULL"
    assert tier_from_n(20) == "PROVISIONAL"
    assert tier_from_n(10) is None  # would have been dropped


def test_ensure_skips_if_already_present(tmp_path, monkeypatch):
    stats = tmp_path / "spread_stats.json"
    stats.write_text(json.dumps({"Already Here": {"regimes": {"MACRO_EASY": {"mean": 0, "std": 1, "n_samples": 100}}}}),
                     encoding="utf-8")
    fetch_called = []
    def fake(ticker, start, end): fetch_called.append(ticker); return []
    monkeypatch.setattr("spread_bootstrap.SPREAD_STATS_FILE", stats)
    monkeypatch.setattr("spread_bootstrap.fetch_eod_series", fake)

    result = ensure("Already Here", ["X"], ["Y"])
    assert result["skipped"] is True
    assert fetch_called == []  # no network call if already bootstrapped


def test_ensure_returns_skipped_with_reason_on_fetch_failure(tmp_path, monkeypatch):
    msi = tmp_path / "msi_history.json"
    stats = tmp_path / "spread_stats.json"
    stats.write_text("{}", encoding="utf-8")
    _seed_msi_history(msi, [(f"2025-01-{i+1:02d}", 50) for i in range(60)])

    def failing_fetch(ticker, start, end):
        raise RuntimeError("EODHD 503")
    monkeypatch.setattr("spread_bootstrap.MSI_HISTORY_FILE", msi)
    monkeypatch.setattr("spread_bootstrap.SPREAD_STATS_FILE", stats)
    monkeypatch.setattr("spread_bootstrap.fetch_eod_series", failing_fetch)

    result = ensure("Bad Spread", ["X"], ["Y"])
    assert result["skipped"] is True
    assert "error" in result
    assert "Bad Spread" not in json.loads(stats.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run tests — expect fail (module doesn't exist)**

```bash
python -m pytest pipeline/tests/test_spread_bootstrap.py -v
```
Expected: `ModuleNotFoundError: No module named 'spread_bootstrap'`

- [ ] **Step 3: Implement `spread_bootstrap.py`**

```python
# pipeline/spread_bootstrap.py
"""Same-day backfill of per-regime spread stats.

Called from regime_scanner after eligible_spreads is built; for any spread
not yet in spread_stats.json, fetches 2y of leg prices from EODHD, classifies
each day by msi_history, computes per-regime distribution, drops buckets
with n_samples < MIN_SAMPLES, appends to spread_stats.json.

Entry point:
    python -m pipeline.spread_bootstrap --ensure "Pharma vs Banks" \\
        --long SUNPHARMA DRREDDY --short HDFCBANK ICICIBANK
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from eodhd_client import fetch_eod_series  # type: ignore
from spread_statistics import (  # type: ignore
    compute_spread_return,
    MSI_MACRO_STRESS_MIN,
    MSI_MACRO_NEUTRAL_MIN,
)

log = logging.getLogger("anka.spread_bootstrap")

_DATA = Path(__file__).parent.parent / "data"
MSI_HISTORY_FILE   = _DATA / "msi_history.json"
SPREAD_STATS_FILE  = _DATA / "spread_stats.json"

DEFAULT_WINDOW_DAYS = 730
MIN_SAMPLES_FULL = 30          # >= this -> FULL-tier grade
MIN_SAMPLES_PROVISIONAL = 15   # [15, 30) -> PROVISIONAL; < 15 dropped at write


def tier_from_n(n: int) -> str | None:
    """Classify a bucket's confidence tier from its sample count.

    None means the bucket should not exist on disk (write-time drop).
    """
    if n >= MIN_SAMPLES_FULL:        return "FULL"
    if n >= MIN_SAMPLES_PROVISIONAL: return "PROVISIONAL"
    return None


def _classify_regime(msi_score: float) -> str:
    if msi_score >= MSI_MACRO_STRESS_MIN:  return "MACRO_STRESS"
    if msi_score >= MSI_MACRO_NEUTRAL_MIN: return "MACRO_NEUTRAL"
    return "MACRO_EASY"


def _load_msi_by_date() -> dict[str, str]:
    if not MSI_HISTORY_FILE.exists():
        return {}
    raw = json.loads(MSI_HISTORY_FILE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in raw:
        d = row.get("date")
        s = row.get("msi_score")
        if d and s is not None:
            out[d] = _classify_regime(float(s))
    return out


def _load_stats() -> dict:
    if not SPREAD_STATS_FILE.exists():
        return {}
    return json.loads(SPREAD_STATS_FILE.read_text(encoding="utf-8"))


def _save_stats(stats: dict) -> None:
    tmp = SPREAD_STATS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SPREAD_STATS_FILE)


def _fetch_window(tickers: list[str], window_days: int) -> dict[str, dict[str, float]]:
    end = date.today()
    start = end - timedelta(days=window_days)
    out: dict[str, dict[str, float]] = {}
    for t in tickers:
        series = fetch_eod_series(t, start.isoformat(), end.isoformat())
        out[t] = {row["date"]: float(row["close"]) for row in series if "date" in row and "close" in row}
    return out


def _daily_spread_returns(
    long_legs: list[str], short_legs: list[str], prices: dict[str, dict[str, float]]
) -> list[tuple[str, float]]:
    """Equal-weight per-leg, mean across long / short legs. Returns [(date, ret), ...] sorted."""
    # Intersect dates across all legs — skip days missing on any leg
    common_dates = None
    for t in long_legs + short_legs:
        d = set(prices.get(t, {}).keys())
        common_dates = d if common_dates is None else (common_dates & d)
    if not common_dates:
        return []
    sorted_dates = sorted(common_dates)
    returns: list[tuple[str, float]] = []
    for i in range(1, len(sorted_dates)):
        prev_d, curr_d = sorted_dates[i - 1], sorted_dates[i]
        per_leg_returns = []
        for t in long_legs:
            per_leg_returns.append((prices[t][curr_d] / prices[t][prev_d] - 1) * 100)
        long_side = sum(per_leg_returns) / len(per_leg_returns)
        per_leg_returns = []
        for t in short_legs:
            per_leg_returns.append((prices[t][curr_d] / prices[t][prev_d] - 1) * 100)
        short_side = sum(per_leg_returns) / len(per_leg_returns)
        returns.append((curr_d, long_side - short_side))
    return returns


def _regime_stats(returns: list[tuple[str, float]], regime_by_date: dict[str, str],
                  min_samples: int = MIN_SAMPLES_PROVISIONAL) -> dict[str, dict]:
    """Compute per-regime distribution, dropping buckets below the write-time floor.

    Buckets with n < min_samples are NEVER written (default = MIN_SAMPLES_PROVISIONAL=15).
    Tier classification (FULL vs PROVISIONAL) is derived at read time via tier_from_n.
    """
    buckets: dict[str, list[float]] = {"MACRO_STRESS": [], "MACRO_NEUTRAL": [], "MACRO_EASY": []}
    for d, r in returns:
        reg = regime_by_date.get(d)
        if reg:
            buckets[reg].append(r)
    out: dict[str, dict] = {}
    for reg, vals in buckets.items():
        n = len(vals)
        if n < min_samples:
            continue
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / max(n - 1, 1)
        std = var ** 0.5
        out[reg] = {"n_samples": n, "mean": round(mean, 4), "std": round(std, 4)}
    return out


def ensure(
    name: str,
    long_legs: list[str],
    short_legs: list[str],
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_samples: int = MIN_SAMPLES_PROVISIONAL,
) -> dict:
    """Bootstrap per-regime stats for `name` if not already in spread_stats.json.

    Returns:
      {name, regimes: {...}} on success/update
      {name, skipped: True, reason: str} on short-circuit or failure
    """
    stats = _load_stats()
    if name in stats and stats[name].get("regimes"):
        return {"name": name, "skipped": True, "reason": "already_present"}

    try:
        prices = _fetch_window(long_legs + short_legs, window_days)
    except Exception as exc:
        log.warning("bootstrap %s: fetch failed — %s", name, exc)
        return {"name": name, "skipped": True, "error": str(exc)}

    returns = _daily_spread_returns(long_legs, short_legs, prices)
    if not returns:
        return {"name": name, "skipped": True, "reason": "no_common_dates"}

    regime_by_date = _load_msi_by_date()
    regimes = _regime_stats(returns, regime_by_date, min_samples)
    if not regimes:
        return {"name": name, "skipped": True, "reason": "all_buckets_below_min_samples",
                "observed": {r: sum(1 for d, _ in returns if regime_by_date.get(d) == r)
                             for r in ("MACRO_STRESS", "MACRO_NEUTRAL", "MACRO_EASY")}}

    stats[name] = {
        "long_legs": long_legs, "short_legs": short_legs,
        "regimes": regimes,
        "bootstrapped_at": date.today().isoformat(),
        "window_days": window_days,
    }
    _save_stats(stats)
    log.info("bootstrap %s: wrote %d regime buckets", name, len(regimes))
    return {"name": name, "regimes": regimes}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensure", required=True, help="Spread name")
    parser.add_argument("--long",   nargs="+", required=True, help="Long leg tickers")
    parser.add_argument("--short",  nargs="+", required=True, help="Short leg tickers")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = ensure(args.ensure, args.long, args.short, args.window_days, args.min_samples)
    print(json.dumps(result, indent=2))
    return 0 if not result.get("skipped") or result.get("reason") == "already_present" else 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest pipeline/tests/test_spread_bootstrap.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/spread_bootstrap.py pipeline/tests/test_spread_bootstrap.py
git commit -m "feat(spread_bootstrap): same-day backfill for newly-eligible spreads

ensure(name, long_legs, short_legs) fetches 2y leg prices from EODHD,
classifies each day by msi_history, writes per-regime {mean, std,
n_samples} to spread_stats.json. Buckets with < 30 samples are dropped.
Called inline from regime_scanner after eligible_spreads is built, so
a new spread is tradeable same-day, not next Sunday."
```

---

## Task 2: Integrate into `regime_scanner.scan_regime()`

**File:** `pipeline/regime_scanner.py` — around line 234 where `eligible_spreads` is assigned to `today_regime`.

- [ ] **Step 1: Write the failing integration test**

```python
# pipeline/tests/test_regime_scanner_bootstrap.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_scan_regime_calls_bootstrap_for_unknown_spreads(monkeypatch, tmp_path):
    """When eligible_spreads contains a name missing from spread_stats,
    scan_regime invokes bootstrap.ensure for it."""
    called_with = []

    def fake_ensure(name, long_legs, short_legs, **kw):
        called_with.append((name, tuple(long_legs), tuple(short_legs)))
        return {"name": name, "regimes": {"MACRO_STRESS": {"n_samples": 40, "mean": 0.1, "std": 1.0}}}

    monkeypatch.setattr("spread_bootstrap.ensure", fake_ensure)

    # Seed a minimal today_regime scenario — eligible_spreads has 2 entries,
    # stats file has 1 → bootstrap fires for 1 spread only
    stats = tmp_path / "spread_stats.json"
    stats.write_text(json.dumps({"Defence vs IT": {"regimes": {"MACRO_STRESS": {"n_samples": 100, "mean": 0, "std": 1}}}}),
                     encoding="utf-8")
    monkeypatch.setattr("spread_bootstrap.SPREAD_STATS_FILE", stats)

    from regime_scanner import _ensure_eligible_spreads_bootstrapped
    eligible = {
        "Defence vs IT":    {"long_legs": ["HAL"], "short_legs": ["TCS"]},
        "Pharma vs Banks":  {"long_legs": ["SUNPHARMA"], "short_legs": ["HDFCBANK"]},
    }
    _ensure_eligible_spreads_bootstrapped(eligible)

    assert len(called_with) == 1
    assert called_with[0][0] == "Pharma vs Banks"
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Add `_ensure_eligible_spreads_bootstrapped` and invoke it**

In `pipeline/regime_scanner.py` — add near the top (after imports):

```python
import spread_bootstrap


def _ensure_eligible_spreads_bootstrapped(eligible_spreads: dict) -> list[dict]:
    """For any eligible spread missing from spread_stats, bootstrap it inline.

    Returns list of bootstrap results (for logging / notification).
    """
    existing = {}
    if spread_bootstrap.SPREAD_STATS_FILE.exists():
        existing = json.loads(spread_bootstrap.SPREAD_STATS_FILE.read_text(encoding="utf-8"))
    results = []
    for name, entry in eligible_spreads.items():
        if name in existing and existing[name].get("regimes"):
            continue
        long_legs  = entry.get("long_legs")  or []
        short_legs = entry.get("short_legs") or []
        if not long_legs or not short_legs:
            log.warning("cannot bootstrap %s: missing leg info", name)
            continue
        results.append(spread_bootstrap.ensure(name, long_legs, short_legs))
    return results
```

Then, in `scan_regime()` right after the existing `eligible_spreads` enrichment block (around line 181) and **before** the `today_regime = {...}` assignment (around line 219):

```python
        bootstrap_results = _ensure_eligible_spreads_bootstrapped(eligible_spreads)
        new_count = sum(1 for r in bootstrap_results if not r.get("skipped"))
        if new_count > 0:
            log.info("Bootstrapped %d new spread(s) today", new_count)
```

- [ ] **Step 4: Run test — expect pass**

```bash
python -m pytest pipeline/tests/test_regime_scanner_bootstrap.py -v
```

- [ ] **Step 5: Run broader suite to confirm no regressions**

```bash
python -m pytest pipeline/tests/ --tb=no -q --ignore=pipeline/tests/tests 2>&1 | tail -5
```
Expected: `N passed, 1 failed` (the pre-existing website cosmetic test).

- [ ] **Step 6: Commit**

```bash
git add pipeline/regime_scanner.py pipeline/tests/test_regime_scanner_bootstrap.py
git commit -m "feat(regime_scanner): bootstrap unknown eligible_spreads inline

Before writing today_regime.json, scan for spreads that are eligible
per the trade_map but missing from spread_stats.json, and run
spread_bootstrap.ensure() for each. Logs the count of new spreads
backfilled so the morning_scan log line shows it."
```

---

## Task 3: Defensive `ensure()` in `spread_intelligence.compute_gate`

The morning-scan path covers the primary case. This task adds a safety net: if any other caller (correlation_scan, manual replay) asks the gate to grade a spread and stats are missing, bootstrap inline and retry before returning INSUFFICIENT_DATA.

**File:** `pipeline/spread_intelligence.py` — the function that returns `INSUFFICIENT_DATA` for missing stats (around line 90 per earlier diagnostic).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_spread_intelligence_bootstrap.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_gate_calls_bootstrap_when_stats_missing(monkeypatch, tmp_path):
    from spread_intelligence import gate_spread
    called = []
    def fake_ensure(name, long_legs, short_legs, **kw):
        called.append(name)
        return {"name": name, "skipped": True, "reason": "no_common_dates"}
    monkeypatch.setattr("spread_intelligence._maybe_bootstrap", lambda name, stats, regime_data: fake_ensure(name, regime_data.get("eligible_spreads", {}).get(name, {}).get("long_legs", []), regime_data.get("eligible_spreads", {}).get(name, {}).get("short_legs", [])))

    regime_data = {"regime": "MACRO_STRESS",
                   "eligible_spreads": {"New Pair": {"long_legs": ["A"], "short_legs": ["B"]}}}
    spread_stats = {}  # empty, so gate would normally return INSUFFICIENT_DATA
    result = gate_spread("New Pair", regime_data=regime_data, spread_stats=spread_stats,
                         regime="MACRO_STRESS", today_spread_return=0.0)
    assert called == ["New Pair"]
    assert result["status"] == "INSUFFICIENT_DATA"  # bootstrap skipped, so still INSUFFICIENT_DATA
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Add `_maybe_bootstrap` helper and call at the top of gate_spread**

In `pipeline/spread_intelligence.py` — top of file:

```python
import spread_bootstrap


def _maybe_bootstrap(name: str, spread_stats: dict, regime_data: dict) -> dict | None:
    """Bootstrap a spread inline if missing from stats. Returns refreshed stats entry or None."""
    if name in spread_stats and spread_stats[name].get("regimes"):
        return None
    eligible = regime_data.get("eligible_spreads") or {}
    entry = eligible.get(name) or {}
    long_legs  = entry.get("long_legs")  or []
    short_legs = entry.get("short_legs") or []
    if not long_legs or not short_legs:
        return None
    spread_bootstrap.ensure(name, long_legs, short_legs)
    # Re-read after bootstrap
    if spread_bootstrap.SPREAD_STATS_FILE.exists():
        refreshed = json.loads(spread_bootstrap.SPREAD_STATS_FILE.read_text(encoding="utf-8"))
        if name in refreshed:
            spread_stats[name] = refreshed[name]
            return refreshed[name]
    return None
```

Then at the top of `gate_spread` (or whatever the gate function is called — verify by reading the file), before the `if not spread_entry:` branch:

```python
    _maybe_bootstrap(spread_name, spread_stats, regime_data)
    spread_entry = spread_stats.get(spread_name)
    if not spread_entry:
        # ... existing INACTIVE/INSUFFICIENT_DATA logic
```

- [ ] **Step 4: Run — expect pass, plus existing test_spread_intelligence.py still passes**

```bash
python -m pytest pipeline/tests/test_spread_intelligence.py pipeline/tests/test_spread_intelligence_bootstrap.py -v
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/spread_intelligence.py pipeline/tests/test_spread_intelligence_bootstrap.py
git commit -m "feat(spread_intelligence): defensive bootstrap before INSUFFICIENT_DATA

gate_spread now calls spread_bootstrap._maybe_bootstrap before giving
up. Covers non-morning_scan callers (correlation_scan, manual replay).
If bootstrap yields ≥30 samples the gate grades normally; otherwise
falls through to the existing INSUFFICIENT_DATA / INACTIVE logic."
```

---

## Task 4: Apply `MIN_SAMPLES=30` filter in weekly `spread_statistics.compute_regime_stats`

**Why:** The weekly refresh currently writes buckets with any sample count (including n=5 or n=10). Bootstrap drops <30 but refresh doesn't — creating inconsistent file state over time. Align both paths on the same threshold.

**File:** `pipeline/spread_statistics.py` — `compute_regime_stats()` function.

- [ ] **Step 1: Write the failing test**

```python
# Extend pipeline/tests/test_spread_statistics.py (or new file)
def test_compute_regime_stats_drops_below_min_samples():
    from spread_statistics import compute_regime_stats, MIN_SAMPLES
    assert MIN_SAMPLES == 30
    rows = [{"date": f"2025-01-{i+1:02d}", "return": 0.1, "regime": "MACRO_STRESS"} for i in range(5)]
    rows += [{"date": f"2025-02-{i+1:02d}", "return": 0.2, "regime": "MACRO_NEUTRAL"} for i in range(40)]
    out = compute_regime_stats(rows)
    assert "MACRO_STRESS" not in out  # 5 < 30, dropped
    assert "MACRO_NEUTRAL" in out
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Add `MIN_SAMPLES=30` constant + filter at end of `compute_regime_stats`**

- [ ] **Step 4: Run — expect pass, plus existing tests**

- [ ] **Step 5: Regenerate the stats file once to clean existing sub-30 buckets**

```bash
python -m pipeline.spread_statistics
python -c "
import json
s = json.load(open('pipeline/data/spread_stats.json', encoding='utf-8'))
from collections import Counter
c = Counter()
for name, e in s.items():
    for bucket, stats in (e.get('regimes') or {}).items():
        c[f'{bucket}_n>=30'] += int(stats.get('n_samples', 0) >= 30)
        c[f'{bucket}_n<30']  += int(stats.get('n_samples', 0) < 30)
print(c)
"
```
Expected: every `*_n<30` is 0.

- [ ] **Step 6: Commit (separate from code change)**

```bash
git add pipeline/data/spread_stats.json
git commit -m "data: regenerate spread_stats.json with MIN_SAMPLES=30 filter applied"
```

---

## Task 5: Logging + summary in morning_scan output

**File:** `pipeline/morning_scan.py` (or wherever the morning flow aggregates its summary) — read the file first to identify the existing summary block.

- [ ] **Step 1: Find the summary block** — look for where `log.info("...summary...")` or a Telegram post is composed at the end of the scan.

- [ ] **Step 2: Add a one-liner summarizing bootstrap results**

Something like:
```python
if bootstrap_results:
    new = [r for r in bootstrap_results if not r.get("skipped")]
    skipped = [r for r in bootstrap_results if r.get("skipped") and r.get("reason") != "already_present"]
    if new or skipped:
        log.info("Spread bootstrap: %d new, %d skipped (%s)",
                 len(new), len(skipped),
                 ", ".join(r.get("reason", "err") for r in skipped[:3]))
```

- [ ] **Step 3: Manual verify** — trigger a morning-scan replay against a tmp spread_stats.json that's missing an entry; confirm the log line appears.

- [ ] **Step 4: Commit**

```bash
git add pipeline/morning_scan.py
git commit -m "chore(morning_scan): log spread bootstrap summary in scan output"
```

---

## Task 6: Docs sync

- [ ] **Step 1: Update `docs/SYSTEM_OPERATIONS_MANUAL.md`** — in the Station 2 / regime_scanner section, add a "Spread Bootstrap" sub-section:
  > Whenever the morning scan emits an eligible spread not yet in `spread_stats.json`, `spread_bootstrap.ensure()` fetches 2 years of leg prices and writes per-regime mean/std. Buckets with fewer than 30 samples are dropped. Runs inline before the 09:30 intraday — a new spread is graded same-day, not Sunday. Log line: `Spread bootstrap: N new, M skipped (...)`.

- [ ] **Step 2: Create `memory/project_spread_bootstrap.md`**:

```markdown
---
name: Spread Bootstrap (same-day backfill)
description: Inline backfill of per-regime spread stats when regime_scanner sees a newly-eligible spread missing from spread_stats.json. Threshold: 30 samples/regime.
type: project
---

Why: the static_config spread universe evolves (news flow, sector rotation). Before this, new spreads appeared in `eligible_spreads` but `spread_statistics` only refreshed known ones — new entries waited until Sunday 22:00, blocking same-day signals.

How to apply: any time you see a spread showing `NONE / INSUFFICIENT_DATA` in the terminal's trading tab, first verify `pipeline/data/spread_stats.json` has an entry with ≥30 samples for today's regime. If not, run `python -m pipeline.spread_bootstrap --ensure "<name>" --long A B --short C D` manually; the morning scan should have done this automatically — investigate why it didn't.

Hook points:
- `pipeline/regime_scanner.py::_ensure_eligible_spreads_bootstrapped` — called inline after eligible_spreads is built, before today_regime.json write.
- `pipeline/spread_intelligence.py::_maybe_bootstrap` — defensive fallback for non-morning_scan callers.

Threshold: `MIN_SAMPLES=30` applied in both `spread_bootstrap` and `spread_statistics.compute_regime_stats` so the file never contains low-confidence buckets.
```

- [ ] **Step 3: Add pointer to `memory/MEMORY.md`** — insert near the project_trading_day_cleanup_2026_04_22 entry:

```
- [Spread Bootstrap](project_spread_bootstrap.md) — inline same-day backfill of spread_stats.json for newly-eligible spreads; threshold 30 samples/regime
```

- [ ] **Step 4: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md memory/project_spread_bootstrap.md memory/MEMORY.md
git commit -m "docs: spread_bootstrap — same-day backfill semantics + memory"
```

---

## Total ETA

- Task 1 (module + tests): 60 min
- Task 2 (regime_scanner hook): 30 min
- Task 3 (defensive gate hook): 20 min
- Task 4 (MIN_SAMPLES filter in refresh): 20 min
- Task 5 (logging): 15 min
- Task 6 (docs + memory): 15 min

**~2h 40min end-to-end.** Network-bound on Task 1 Step 3+4 runs (EODHD fetch is the slow part). Tasks 1-3 can ship before EOD today.

## Execution Flags

- **Safe to deploy mid-market (all tasks):** bootstrap runs only when stats are missing; no overwrite of existing grades. Failure modes return `skipped` without mutating state.
- **Weekly cadence unchanged.** No new scheduled task. `AnkaSpreadStats` (Sun 22:00) remains refresh-only.
- **Network dependency:** EODHD must be reachable. If down, bootstrap returns `skipped:error` and the gate falls through to the existing INSUFFICIENT_DATA path — no new failure mode.
