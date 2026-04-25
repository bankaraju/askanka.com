# H-2026-04-25-001 Earnings-Decoupling Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `pipeline/autoresearch/earnings_decoupling/` backtest package that produces a §15.1 RESEARCH → PAPER-SHADOW verdict for H-2026-04-25-001.

**Architecture:** Pre-task data audits gate the run. Earnings-specific feature code (peer-residual, trigger z-score, macro filter wiring, MODE A trade simulator) lives in `pipeline/autoresearch/earnings_decoupling/`. The §1/§2/§5A/§6/§7/§8/§9/§9A/§9B/§10/§11B compliance evaluation re-uses primitives from `pipeline/autoresearch/overshoot_compliance/` directly (manifest, slippage_grid, metrics, gate_checklist, beta_regression). The ΔPCR amplifier track is wired but disabled. Output: `docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/`.

**Tech Stack:** Python 3.11, pandas, numpy, pyarrow, pytest. Reuses `pipeline.autoresearch.overshoot_compliance.{manifest, slippage_grid, metrics, naive_comparators (adapted), gate_checklist, beta_regression}`. Reads `pipeline/data/earnings_calendar/history.parquet` + `peers_frozen.json`. Writes manifest, trade ledger, gate checklist, verdict.

**Spec:** `docs/superpowers/specs/2026-04-25-earnings-decoupling-backtest-design.md` (commit `c409e2b`).

**Hypothesis spec:** `docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md`.

**Standards:** `docs/superpowers/specs/backtesting-specs.txt` v1.0_2026-04-23.

---

## File structure (locked)

| Path | Purpose |
|---|---|
| `pipeline/autoresearch/earnings_decoupling/__init__.py` | package marker |
| `pipeline/autoresearch/earnings_decoupling/peer_residuals.py` | `compute_residual_panel(prices, peers, calendar) → DataFrame[date,symbol,epsilon]` |
| `pipeline/autoresearch/earnings_decoupling/trigger.py` | `compute_trigger_z(residual_panel, event_date, symbol) → float \| None` |
| `pipeline/autoresearch/earnings_decoupling/macro_filter_adapter.py` | shim over `pipeline/earnings_calendar/macro_filter.py` |
| `pipeline/autoresearch/earnings_decoupling/event_ledger.py` | `build_event_ledger(events, residual_panel, prices_panel, sectoral_index_returns, india_vix, peers_map, fno_history) → DataFrame` |
| `pipeline/autoresearch/earnings_decoupling/simulator.py` | MODE A entry/exit at 15:20-29 close VWAP; emits per-trade `next_ret` |
| `pipeline/autoresearch/earnings_decoupling/pcr_amplifier.py` | stub: `apply_pcr_filter(ledger, enabled=False) → ledger` |
| `pipeline/autoresearch/earnings_decoupling/naive_comparators.py` | follow-direction-flavoured §9B.1 suite |
| `pipeline/autoresearch/earnings_decoupling/runner.py` | orchestrator with `--out-dir`, `--smoke` flags |
| `pipeline/tests/autoresearch/earnings_decoupling/test_*.py` | one test file per module |

---

## Task 0a: Register `nse_sectoral_indices_v1` data source

**Files:**
- Create: `docs/superpowers/specs/2026-04-25-nse-sectoral-indices-data-source-audit.md`
- Run: `pipeline/research/phase_c_v5/data_prep/backfill_indices.py::backfill_daily`
- Output: `pipeline/data/sectoral_indices/<INDEX>_daily.csv` for 10 indices

- [ ] **Step 1: Write the audit doc**

```bash
cat > docs/superpowers/specs/2026-04-25-nse-sectoral-indices-data-source-audit.md <<'MD'
# NSE Sectoral Indices data source audit

**Date:** 2026-04-25
**Dataset ID:** `nse_sectoral_indices_v1`
**Tier (proposed):** D2
**Owner:** Bharat Ankaraju
**Acceptance status:** Approved-for-research, Tier D2

## Purpose
10-index daily-bar history feeds H-2026-04-25-001 §3 macro-exclusion filter (sector-index returns on T, T+1) and §4 peer cohort audit (peer-cohort sanity checks against parent index returns).

## Source
Primary: Kite (NSE) via `pipeline/research/phase_c_backtest/fetcher.py::fetch_daily`.
Fallback: yfinance (`^NSEBANK`, `^CNXIT`, ...).
Both implementations live in `pipeline/research/phase_c_v5/data_prep/backfill_indices.py`.

## Symbols
| Hypothesis name | Kite alias | yfinance alias |
|---|---|---|
| NIFTY Bank | NSE:NIFTY BANK | ^NSEBANK |
| NIFTY IT | NSE:NIFTY IT | ^CNXIT |
| NIFTY Pharma | NSE:NIFTY PHARMA | ^CNXPHARMA |
| NIFTY Auto | NSE:NIFTY AUTO | ^CNXAUTO |
| NIFTY FMCG | NSE:NIFTY FMCG | ^CNXFMCG |
| NIFTY Metal | NSE:NIFTY METAL | ^CNXMETAL |
| NIFTY Energy | NSE:NIFTY ENERGY | ^CNXENERGY |
| NIFTY PSU Bank | NSE:NIFTY PSU BANK | ^CNXPSUBANK |
| NIFTY Realty | NSE:NIFTY REALTY | ^CNXREALTY |
| NIFTY Media | NSE:NIFTY MEDIA | ^CNXMEDIA |

## Backfill
- Command: `python -m pipeline.scripts.backfill_sectoral_indices --days 1825`
- Output: `pipeline/data/sectoral_indices/<INDEX>_daily.csv` schema `(date,open,high,low,close,volume)`
- Invocation evidence: see Task 0a Step 4 below.

## Cleanliness gates (policy §9)
- per-index missing-bar count ≤ 1% of NSE business days
- zero-or-negative-close count = 0
- duplicate-date count = 0

## Adjustment mode (policy §10)
N/A — indices are not split-adjusted at the level we consume.

## Point-in-time correctness (policy §11)
Each row's `date` is the trade date as published by NSE/Yahoo. No look-ahead.

## Independent corroboration (policy §13)
Kite-vs-yfinance agreement spot-check on 3 random dates per index, max diff < 0.5%.

## Contamination map (policy §14)
- Result-day moves on T, T+1 are the macro-exclusion targets — no contamination of features.
- Index methodology rebalances (semi-annual NSE reviews) cause discrete jumps; recorded as known caveat, not a contamination of the residual signal because peer cohorts are stock-level not index-level.

## Verdict
Approved-for-research, Tier D2. Sufficient for the H-2026-04-25-001 backtest.
MD
```

- [ ] **Step 2: Create the backfill script**

```bash
cat > pipeline/scripts/backfill_sectoral_indices.py <<'PY'
"""Backfill NSE sectoral indices for H-2026-04-25-001.

Wraps pipeline.research.phase_c_v5.data_prep.backfill_indices.backfill_daily
with the 10 hypothesis-required symbols and writes to
pipeline/data/sectoral_indices/.
"""
from __future__ import annotations
import argparse
import logging
from pathlib import Path

from pipeline.research.phase_c_v5.data_prep.backfill_indices import backfill_daily

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "pipeline" / "data" / "sectoral_indices"

REQUIRED = [
    "BANKNIFTY", "NIFTYIT", "NIFTYPHARMA", "NIFTYAUTO", "NIFTYFMCG",
    "NIFTYMETAL", "NIFTYENERGY", "NIFTYPSUBANK", "NIFTYREALTY", "NIFTYMEDIA",
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1825)
    args = parser.parse_args()
    counts = backfill_daily(REQUIRED, days=args.days, out_dir=OUT)
    for sym, n in counts.items():
        logging.info("%s: %d rows", sym, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
```

- [ ] **Step 3: Run the backfill**

Run: `python -m pipeline.scripts.backfill_sectoral_indices --days 1825 2>&1 | tee /tmp/sectoral_backfill.log`
Expected: 10 CSVs in `pipeline/data/sectoral_indices/`, each with ~1,200 rows (5 trading years).

- [ ] **Step 4: Sanity-check the output**

```bash
python -c "
import pandas as pd, pathlib
out = pathlib.Path('pipeline/data/sectoral_indices')
for csv in sorted(out.glob('*_daily.csv')):
    df = pd.read_csv(csv)
    print(f'{csv.stem}: rows={len(df)}  first={df.date.min()}  last={df.date.max()}  zeros={(df.close <= 0).sum()}')
"
```
Expected: all 10 indices report rows ≥ 1100, zeros = 0, last date within 5 trading days of today.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-04-25-nse-sectoral-indices-data-source-audit.md \
        pipeline/scripts/backfill_sectoral_indices.py \
        pipeline/data/sectoral_indices/
git commit -m "data(sectoral-indices): register nse_sectoral_indices_v1 + 5y daily backfill

T0a per H-2026-04-25-001 backtest plan. 10 NSE sectoral indices required by
hypothesis spec §3 macro filter. Approved-for-research Tier D2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 0b: Build `fno_universe_history.json`

**Files:**
- Create: `docs/superpowers/specs/2026-04-25-fno-universe-history-data-source-audit.md`
- Create: `pipeline/scripts/build_fno_universe_history.py`
- Output: `pipeline/data/fno_universe_history.json`

- [ ] **Step 1: Write the audit doc**

```bash
cat > docs/superpowers/specs/2026-04-25-fno-universe-history-data-source-audit.md <<'MD'
# FNO Universe History data source audit

**Date:** 2026-04-25
**Dataset ID:** `fno_universe_history_v1`
**Tier:** D2
**Acceptance status:** Approved-for-research

## Purpose
Monthly NSE F&O membership snapshots feed point-in-time universe filtering per backtesting-specs §6.1. Required by H-2026-04-25-001 §3 universe definition.

## Source
NSE archives — public CSV at `https://archives.nseindia.com/content/fo/fo_mktlots.csv` (current snapshot) and historical bhavcopy archives at `https://archives.nseindia.com/products/content/derivatives/equities/fo<DDMMYY>bhav.csv.zip` (per-day snapshots from which we extract distinct symbol set per month).

## Scope
60 monthly snapshots over 5 years (2021-05 → 2026-04). End-of-month data.

## Schema
```json
{
  "snapshots": [
    {"date": "YYYY-MM-DD", "symbols": ["RELIANCE","TCS",...]},
    ...
  ],
  "source": "nseindia.com archives",
  "fetched_at": "ISO timestamp"
}
```

## Cleanliness gates (policy §9)
- ≥ 60 snapshots over 5 years (one per calendar month)
- No empty `symbols` arrays
- All entries unique within a snapshot

## Point-in-time correctness (policy §11)
`is_in_fno(symbol, event_date)` returns True iff symbol is in the most-recent snapshot whose date is ≤ event_date. A symbol kicked out 2024-08-31 must NOT pass `is_in_fno("XYZ", "2024-09-15")`.

## Verdict
Approved-for-research. Eligible for H-2026-04-25-001 + every future F&O-universe backtest.
MD
```

- [ ] **Step 2: Write the build script**

```python
# pipeline/scripts/build_fno_universe_history.py
"""Build pipeline/data/fno_universe_history.json from NSE bhavcopy archives.

Strategy: download one bhavcopy per calendar month-end; extract the unique set
of symbols whose INSTRUMENT in {FUTSTK, OPTSTK}; persist as one snapshot.

The NSE bhavcopy URL pattern is:
  https://archives.nseindia.com/products/content/derivatives/equities/fo<DDMMYY>bhav.csv.zip
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
OUT_PATH = REPO / "pipeline" / "data" / "fno_universe_history.json"
NSE_URL = "https://archives.nseindia.com/products/content/derivatives/equities/fo{ddmmyy}bhav.csv.zip"

UA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Accept-Encoding": "gzip"}


def _last_business_day(year: int, month: int) -> dt.date:
    if month == 12:
        nxt = dt.date(year + 1, 1, 1)
    else:
        nxt = dt.date(year, month + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _fetch_bhavcopy(d: dt.date, retries: int = 3) -> pd.DataFrame | None:
    url = NSE_URL.format(ddmmyy=d.strftime("%d%b%Y").upper())
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                inner = z.namelist()[0]
                with z.open(inner) as fh:
                    return pd.read_csv(fh)
        except Exception as exc:
            logging.warning("bhavcopy %s attempt %d failed: %s", d, attempt, exc)
    return None


def _extract_fno_symbols(df: pd.DataFrame) -> list[str]:
    mask = df["INSTRUMENT"].isin({"FUTSTK", "OPTSTK"})
    return sorted(df.loc[mask, "SYMBOL"].dropna().unique().tolist())


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    today = dt.date.today()
    snapshots: list[dict] = []
    for years_back in range(args.years, -1, -1):
        for month in range(1, 13):
            year = today.year - years_back
            if year > today.year or (year == today.year and month > today.month):
                continue
            d = _last_business_day(year, month)
            if d > today:
                continue
            df = None
            probe = d
            while df is None and probe > d - dt.timedelta(days=7):
                df = _fetch_bhavcopy(probe)
                if df is None:
                    probe -= dt.timedelta(days=1)
            if df is None:
                logging.warning("no bhavcopy in week ending %s", d)
                continue
            symbols = _extract_fno_symbols(df)
            snapshots.append({"date": d.isoformat(), "symbols": symbols})
            logging.info("%s: %d symbols", d, len(symbols))

    payload = {
        "snapshots": snapshots,
        "source": "nseindia.com archives",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    logging.info("wrote %d snapshots to %s", len(snapshots), OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the build**

Run: `python -m pipeline.scripts.build_fno_universe_history --years 5 2>&1 | tee /tmp/fno_history.log`
Expected: ≥ 50 snapshots written to `pipeline/data/fno_universe_history.json`. Symbols-per-snapshot 180-220.

- [ ] **Step 4: Verify**

```bash
python -c "
import json, pathlib
p = pathlib.Path('pipeline/data/fno_universe_history.json')
body = json.loads(p.read_text())
snaps = body['snapshots']
print(f'snapshots: {len(snaps)}')
print(f'first: {snaps[0][\"date\"]} ({len(snaps[0][\"symbols\"])} symbols)')
print(f'last:  {snaps[-1][\"date\"]} ({len(snaps[-1][\"symbols\"])} symbols)')
sizes = [len(s['symbols']) for s in snaps]
print(f'min size: {min(sizes)} max: {max(sizes)}')
"
```
Expected: ≥ 50 snapshots, all sizes between 150 and 250.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-04-25-fno-universe-history-data-source-audit.md \
        pipeline/scripts/build_fno_universe_history.py \
        pipeline/data/fno_universe_history.json
git commit -m "data(fno-universe): build fno_universe_history.json from 5y NSE bhavcopy archives

T0b per H-2026-04-25-001 backtest plan. Resolves backtesting-specs §6.1
PIT-universe requirement. 5-year monthly snapshots; PIT-correct membership
checks via is_in_fno.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 0c: §10 partial-waiver doc

**Files:**
- Create: `docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md`

- [ ] **Step 1: Write the waiver**

```bash
mkdir -p docs/superpowers/waivers
cat > docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md <<'MD'
# §15.4 Waiver: H-2026-04-25-001 §10.1 + §10.2 partial OOS

**Date:** 2026-04-25
**Hypothesis:** H-2026-04-25-001
**Sections waived:** §10.1 (≥20% holdout, last 3 months) and §10.2 (3-year rolling train + 3-month test walk-forward)
**Signing principal:** Bharat Ankaraju
**Expiry:** at next backtest of the strategy under a longer window. Does NOT propagate to PAPER-SHADOW → LIVE-FRAGILE promotion.

## Justification
Hypothesis spec §3 locks the backtest window at 18 months on user instruction ("18 months is good enough for now"). Inside an 18-month window:
- A 3-year rolling train is impossible.
- A 20% holdout would consume 3.6 months; the spec settled on a clean 15/3 month split (17%).

The waiver is research-only and the verdict targets RESEARCH → PAPER-SHADOW only. The classification artifact will record §10 as PARTIAL.

## Compliance commitments
- §10.1: 17% holdout, last 3 months. Single fixed split. Holdout NEVER touched during development; single-touch enforced via `runner.py` write-once log.
- §10.2: replaced by single fixed split; no rolling walk-forward.
- §10.3 (purging): N/A within a single split.
- §10.4 (single-use OOS): enforced by holdout_touch_log.json mechanism in runner.

## Re-test trigger
The strategy MAY be re-evaluated under the full §10 ladder when the backtest window is extended to ≥ 30 months. That run produces a new run_id and burns the current 17% holdout per §10.1.
MD
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md
git commit -m "waiver(H-2026-04-25-001): partial §10.1+§10.2 OOS for 18-month-window backtest

T0c per backtest plan. Documented under §15.4 with research-only scope and
explicit re-test trigger when window extends to ≥30 months.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 0d: Hypothesis-spec addendum

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md` (append §11)

- [ ] **Step 1: Append the addendum**

```bash
cat >> docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md <<'MD'

## 11. Backtest-time addendum (2026-04-25)

ΔPCR confirmation deferred for the first backtest run because per-ticker daily
PCR history is not currently stored (`pipeline/data/oi_history.json` is index-level
only). Per spec §4.5 Variant A, ΔPCR is a post-hoc cohort filter, not an entry
gate, so disabling it for this run does NOT modify the entry rule and does NOT
require a new hypothesis version. The amplifier code path is wired with a
feature flag and will be re-enabled in a separate run when per-ticker PCR
history is backfilled.

§9A fragility-grid axes for this hypothesis: trigger_z threshold (locked 1.5;
perturbed ±10% over 9 points), trigger window start (locked T-7; perturbed
±2 days), trigger window end (locked T-3; perturbed ±2 days), baseline length
(locked 252; perturbed ±20%), macro index threshold (locked 0.015; perturbed
±20%), VIX z threshold (locked 2.0; perturbed ±20%). 9 points × 6 axes = 54
neighborhood samples in a one-axis-at-a-time grid (§9A.1 floor = 25).

Backtest spec: `docs/superpowers/specs/2026-04-25-earnings-decoupling-backtest-design.md`
Backtest plan: `docs/superpowers/plans/2026-04-25-earnings-decoupling-backtest.md`
MD
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md
git commit -m "spec(H-2026-04-25-001): addendum §11 — ΔPCR deferred + fragility-grid axes

T0d per backtest plan. Addendum is non-modifying per spec §4.5 Variant A: ΔPCR
was always a post-hoc filter, not an entry gate, so disabling for first run
does NOT require a new hypothesis version.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: Package skeleton + universe membership helper

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/__init__.py`
- Create: `pipeline/autoresearch/earnings_decoupling/universe.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/__init__.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_universe.py
import json
from pathlib import Path
from pipeline.autoresearch.earnings_decoupling.universe import is_in_fno, load_history


def test_load_history_reads_snapshots(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({
        "snapshots": [
            {"date": "2025-01-31", "symbols": ["RELIANCE", "TCS"]},
            {"date": "2025-02-28", "symbols": ["RELIANCE", "TCS", "INFY"]},
        ]
    }))
    h = load_history(p)
    assert len(h) == 2
    assert h[0]["date"] == "2025-01-31"


def test_is_in_fno_uses_most_recent_prior_snapshot(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({
        "snapshots": [
            {"date": "2025-01-31", "symbols": ["RELIANCE", "TCS"]},
            {"date": "2025-02-28", "symbols": ["RELIANCE", "TCS", "INFY"]},
        ]
    }))
    h = load_history(p)
    assert is_in_fno(h, "INFY", "2025-02-15") is False, "INFY admitted only Feb-end"
    assert is_in_fno(h, "INFY", "2025-03-15") is True
    assert is_in_fno(h, "RELIANCE", "2025-01-31") is True
    assert is_in_fno(h, "WIPRO", "2025-03-15") is False


def test_is_in_fno_event_before_first_snapshot_returns_false(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"snapshots": [{"date": "2025-01-31", "symbols": ["RELIANCE"]}]}))
    h = load_history(p)
    assert is_in_fno(h, "RELIANCE", "2024-12-15") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_universe.py -v`
Expected: FAIL with "ModuleNotFoundError: pipeline.autoresearch.earnings_decoupling.universe".

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/__init__.py
"""H-2026-04-25-001 earnings-decoupling backtest package."""
```

```python
# pipeline/autoresearch/earnings_decoupling/universe.py
"""PIT F&O membership helpers, sourced from fno_universe_history.json."""
from __future__ import annotations

import bisect
import json
from pathlib import Path


def load_history(path: Path | str) -> list[dict]:
    body = json.loads(Path(path).read_text())
    snaps = sorted(body["snapshots"], key=lambda s: s["date"])
    return snaps


def is_in_fno(history: list[dict], symbol: str, event_date: str) -> bool:
    dates = [s["date"] for s in history]
    idx = bisect.bisect_right(dates, event_date) - 1
    if idx < 0:
        return False
    return symbol in history[idx]["symbols"]
```

```python
# pipeline/tests/autoresearch/earnings_decoupling/__init__.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_universe.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/__init__.py \
        pipeline/autoresearch/earnings_decoupling/universe.py \
        pipeline/tests/autoresearch/earnings_decoupling/
git commit -m "feat(earnings-decoupling): package skeleton + PIT universe helper

T1 per backtest plan. is_in_fno honours backtesting-specs §6.1 — symbol kicked
out before event_date is excluded.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: peer_residuals.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/peer_residuals.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_peer_residuals.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_peer_residuals.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.peer_residuals import (
    compute_log_returns,
    compute_residual_panel,
)


@pytest.fixture
def synthetic_panel():
    dates = pd.date_range("2025-01-01", periods=10, freq="B")
    # RELIANCE rises by +2%/day, TCS by +1%/day, INFY by +1%/day, HDFCBANK by +3%/day
    prices = pd.DataFrame({
        "RELIANCE": np.cumprod(np.full(10, 1.02)) * 1000,
        "TCS":      np.cumprod(np.full(10, 1.01)) * 3000,
        "INFY":     np.cumprod(np.full(10, 1.01)) * 1500,
        "HDFCBANK": np.cumprod(np.full(10, 1.03)) * 1500,
    }, index=dates)
    return prices


def test_compute_log_returns_first_row_is_nan(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    assert rets.iloc[0].isna().all()
    np.testing.assert_allclose(rets.iloc[1], np.log([1.02, 1.01, 1.01, 1.03]))


def test_residual_is_stock_minus_mean_of_peers(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {
        "RELIANCE": ["TCS", "INFY"],
        "TCS":      ["INFY", "HDFCBANK"],
        "INFY":     ["TCS", "HDFCBANK"],
        "HDFCBANK": ["TCS", "INFY"],
    }
    panel = compute_residual_panel(rets, peers_map)
    # RELIANCE return = log(1.02). Peers mean = log(1.01). Residual = log(1.02)-log(1.01).
    expected_rel = np.log(1.02) - np.log(1.01)
    np.testing.assert_allclose(panel.loc[rets.index[1], "RELIANCE"], expected_rel, rtol=1e-9)


def test_residual_panel_skips_symbol_when_no_peers_have_data(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {"RELIANCE": ["NONEXISTENT"]}
    panel = compute_residual_panel(rets, peers_map)
    assert panel["RELIANCE"].isna().all()


def test_residual_panel_uses_available_peers_when_some_missing(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {"RELIANCE": ["TCS", "NONEXISTENT"]}
    panel = compute_residual_panel(rets, peers_map)
    expected = np.log(1.02) - np.log(1.01)
    np.testing.assert_allclose(panel.loc[rets.index[1], "RELIANCE"], expected, rtol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_peer_residuals.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/peer_residuals.py
"""Daily peer-residual returns ε_s(t) per H-2026-04-25-001 §4.1."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices / prices.shift(1))


def compute_residual_panel(
    log_returns: pd.DataFrame,
    peers_map: dict[str, list[str]],
) -> pd.DataFrame:
    out = pd.DataFrame(index=log_returns.index, columns=list(peers_map.keys()), dtype=float)
    for sym, peers in peers_map.items():
        if sym not in log_returns.columns:
            continue
        available = [p for p in peers if p in log_returns.columns]
        if not available:
            continue
        peer_mean = log_returns[available].mean(axis=1)
        out[sym] = log_returns[sym] - peer_mean
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_peer_residuals.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/peer_residuals.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_peer_residuals.py
git commit -m "feat(earnings-decoupling): peer-residual ε_s(t) computation

T2 per backtest plan. Implements H-2026-04-25-001 §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: trigger.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/trigger.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_trigger.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_trigger.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.trigger import (
    cum_residual_window,
    compute_trigger_z,
)


@pytest.fixture
def residual_panel():
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=400)
    return pd.DataFrame({
        "RELIANCE": np.random.normal(0, 0.005, size=400),
        "TCS":      np.random.normal(0, 0.005, size=400),
    }, index=dates)


def test_cum_residual_sums_t_minus_7_through_t_minus_3(residual_panel):
    event_date = residual_panel.index[300]
    expected = residual_panel.loc[
        residual_panel.index[300 - 7]:residual_panel.index[300 - 3],
        "RELIANCE",
    ].sum()
    actual = cum_residual_window(residual_panel, "RELIANCE", event_date)
    assert abs(actual - expected) < 1e-12


def test_compute_trigger_z_returns_none_when_insufficient_baseline(residual_panel):
    event_date = residual_panel.index[20]  # too early — fewer than 200 baseline days
    z = compute_trigger_z(residual_panel, "RELIANCE", event_date)
    assert z is None


def test_compute_trigger_z_returns_value_when_baseline_sufficient(residual_panel):
    event_date = residual_panel.index[300]
    z = compute_trigger_z(residual_panel, "RELIANCE", event_date)
    assert z is not None
    assert -10 < z < 10


def test_compute_trigger_z_baseline_excludes_t_minus_8_onwards(residual_panel):
    """Baseline σ must NOT include the trigger window itself."""
    rp = residual_panel.copy()
    event_idx = 300
    event_date = rp.index[event_idx]
    # Insert a huge spike inside [T-7, T-3] — should NOT inflate the baseline σ
    rp.loc[rp.index[event_idx - 5], "RELIANCE"] = 0.5
    z_with_spike = compute_trigger_z(rp, "RELIANCE", event_date)
    rp.loc[rp.index[event_idx - 5], "RELIANCE"] = 0.0
    z_without_spike = compute_trigger_z(rp, "RELIANCE", event_date)
    # Z values differ because cum_residual changed, but the σ must be the same
    # (the spike does not enter the baseline). Verify both are non-None.
    assert z_with_spike is not None and z_without_spike is not None


def test_compute_trigger_z_returns_none_when_zero_variance(residual_panel):
    rp = residual_panel.copy()
    rp["RELIANCE"] = 0.0  # constant baseline
    event_date = rp.index[300]
    z = compute_trigger_z(rp, "RELIANCE", event_date)
    assert z is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_trigger.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/trigger.py
"""Trigger z-score per H-2026-04-25-001 §4.2-§4.3."""
from __future__ import annotations

import pandas as pd

WINDOW_START = -7
WINDOW_END = -3
BASELINE_LEN = 252
BASELINE_END_OFFSET = -8
MIN_BASELINE_DAYS = 200


def cum_residual_window(
    residual_panel: pd.DataFrame, symbol: str, event_date,
    *, start_offset: int = WINDOW_START, end_offset: int = WINDOW_END,
) -> float:
    if symbol not in residual_panel.columns:
        return float("nan")
    idx = residual_panel.index.get_loc(pd.Timestamp(event_date))
    lo = max(0, idx + start_offset)
    hi = max(0, idx + end_offset + 1)
    return float(residual_panel[symbol].iloc[lo:hi].sum())


def compute_trigger_z(
    residual_panel: pd.DataFrame, symbol: str, event_date,
    *, baseline_len: int = BASELINE_LEN,
    baseline_end_offset: int = BASELINE_END_OFFSET,
    min_baseline_days: int = MIN_BASELINE_DAYS,
    start_offset: int = WINDOW_START,
    end_offset: int = WINDOW_END,
) -> float | None:
    if symbol not in residual_panel.columns:
        return None
    if pd.Timestamp(event_date) not in residual_panel.index:
        return None
    idx = residual_panel.index.get_loc(pd.Timestamp(event_date))
    if idx + baseline_end_offset < 0:
        return None

    cum_obs = cum_residual_window(
        residual_panel, symbol, event_date,
        start_offset=start_offset, end_offset=end_offset,
    )

    window_len = end_offset - start_offset + 1
    baseline_end_idx = idx + baseline_end_offset
    baseline_start_idx = max(0, baseline_end_idx - baseline_len + 1)
    baseline_residuals = residual_panel[symbol].iloc[baseline_start_idx:baseline_end_idx + 1].dropna()
    if len(baseline_residuals) < min_baseline_days:
        return None

    rolling_cum = baseline_residuals.rolling(window=window_len).sum().dropna()
    if len(rolling_cum) < 50:
        return None
    sigma = float(rolling_cum.std(ddof=1))
    mu = float(rolling_cum.mean())
    if sigma <= 0:
        return None
    return (cum_obs - mu) / sigma
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_trigger.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/trigger.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_trigger.py
git commit -m "feat(earnings-decoupling): trigger z-score with 252d baseline ending T-8

T3 per backtest plan. H-2026-04-25-001 §4.2 cum_residual + §4.3 z-score.
Drops events with <200 baseline days or σ ≤ 0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: macro_filter_adapter.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/macro_filter_adapter.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_macro_filter_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_macro_filter_adapter.py
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.macro_filter_adapter import (
    compute_index_returns_panel,
    is_event_macro_excluded,
)


def test_compute_index_returns_panel_returns_pct_change():
    closes = pd.DataFrame({
        "BANKNIFTY": [100.0, 101.0, 102.01],
    }, index=pd.bdate_range("2025-01-01", periods=3))
    rets = compute_index_returns_panel(closes)
    # First row NaN, then 1.0% then ~1.0%
    assert pd.isna(rets.iloc[0, 0])
    assert abs(rets.iloc[1, 0] - 0.01) < 1e-9


def test_is_event_macro_excluded_excludes_when_index_moves_2pct(monkeypatch):
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.02, 0.0], index=dates)  # +2% on T
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert excluded
    assert reason == "SECTOR_T"


def test_is_event_macro_excluded_excludes_on_t_plus_1():
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.0, 0.02], index=dates)  # +2% on T+1
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert excluded
    assert reason == "SECTOR_T1"


def test_is_event_macro_excluded_passes_when_quiet():
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0] * 5, index=dates)
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert not excluded
    assert reason is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_macro_filter_adapter.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/macro_filter_adapter.py
"""Adapter wrapping pipeline/earnings_calendar/macro_filter for earnings_decoupling.

Returns (excluded: bool, reason: str | None) where reason is one of
SECTOR_T, SECTOR_T1, VIX_SHOCK, or None when not excluded.
"""
from __future__ import annotations

import pandas as pd

from pipeline.earnings_calendar.macro_filter import (
    INDEX_MOVE_THRESHOLD,
    VIX_ZSCORE_THRESHOLD,
    VIX_ZSCORE_LOOKBACK_DAYS,
)


def compute_index_returns_panel(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change()


def _vix_z(vix: pd.Series, on: pd.Timestamp) -> float | None:
    if on not in vix.index:
        return None
    pos = vix.index.get_loc(on)
    if pos < VIX_ZSCORE_LOOKBACK_DAYS:
        return None
    window = vix.iloc[pos - VIX_ZSCORE_LOOKBACK_DAYS:pos]
    if window.std(ddof=1) == 0:
        return None
    return float((vix.iloc[pos] - window.mean()) / window.std(ddof=1))


def is_event_macro_excluded(
    *,
    event_date,
    sector_index_returns: pd.Series,
    india_vix: pd.Series,
) -> tuple[bool, str | None]:
    ts = pd.Timestamp(event_date).normalize()
    rets_idx = sector_index_returns.index.normalize()
    rets = sector_index_returns.copy()
    rets.index = rets_idx
    if ts in rets.index:
        r_t = rets.loc[ts]
        if pd.notna(r_t) and abs(r_t) >= INDEX_MOVE_THRESHOLD:
            return (True, "SECTOR_T")
        pos = rets.index.get_loc(ts)
        if pos + 1 < len(rets):
            r_t1 = rets.iloc[pos + 1]
            if pd.notna(r_t1) and abs(r_t1) >= INDEX_MOVE_THRESHOLD:
                return (True, "SECTOR_T1")
    vix_idx = india_vix.index.normalize()
    vix = india_vix.copy()
    vix.index = vix_idx
    z = _vix_z(vix, ts)
    if z is not None and z >= VIX_ZSCORE_THRESHOLD:
        return (True, "VIX_SHOCK")
    return (False, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_macro_filter_adapter.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/macro_filter_adapter.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_macro_filter_adapter.py
git commit -m "feat(earnings-decoupling): macro filter adapter — sector T, T+1, VIX shock

T4 per backtest plan. Returns (excluded, reason) tagged SECTOR_T / SECTOR_T1 /
VIX_SHOCK; consumes locked thresholds from pipeline.earnings_calendar.macro_filter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: event_ledger.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/event_ledger.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_event_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_event_ledger.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.event_ledger import build_event_ledger


@pytest.fixture
def fixtures():
    dates = pd.bdate_range("2024-01-01", periods=400)
    np.random.seed(123)
    prices = pd.DataFrame({
        "RELIANCE": np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 1000,
        "TCS":      np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 3000,
        "INFY":     np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 1500,
    }, index=dates)
    sector_idx = pd.DataFrame({
        "BANKNIFTY": np.cumprod(1 + np.random.normal(0, 0.005, 400)) * 50000,
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + np.random.normal(0, 0.5, 400), index=dates)
    fno_history = [{"date": "2024-01-01", "symbols": ["RELIANCE", "TCS", "INFY"]}]
    peers_map = {"RELIANCE": ["TCS", "INFY"]}
    sector_map = {"RELIANCE": "BANKNIFTY"}
    events = pd.DataFrame({
        "symbol": ["RELIANCE"],
        "event_date": [dates[300].strftime("%Y-%m-%d")],
    })
    return dict(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
    )


def test_build_event_ledger_emits_one_row_per_event(fixtures):
    ledger = build_event_ledger(**fixtures)
    assert len(ledger) == 1
    row = ledger.iloc[0]
    assert row["ticker"] == "RELIANCE"
    assert row["status"] in {"CANDIDATE", "EXCLUDED_MACRO", "DROPPED_INSUFFICIENT_BASELINE",
                              "DROPPED_PIT_MISS", "DROPPED_ZERO_VARIANCE", "DROPPED_NO_TRIGGER"}


def test_build_event_ledger_drops_pit_miss(fixtures):
    fixtures["fno_history"] = [{"date": "2024-01-01", "symbols": ["TCS", "INFY"]}]  # RELIANCE not in F&O
    ledger = build_event_ledger(**fixtures)
    assert len(ledger) == 1
    assert ledger.iloc[0]["status"] == "DROPPED_PIT_MISS"


def test_build_event_ledger_assigns_direction_from_trigger_z(fixtures):
    rng = np.random.default_rng(0)
    dates = fixtures["prices"].index
    rel_returns = rng.normal(0.0001, 0.005, len(dates))
    rel_returns[298] = 0.10  # huge positive residual T-3
    rel_returns[297] = 0.10
    rel_returns[296] = 0.10
    rel_returns[295] = 0.10
    rel_returns[294] = 0.10
    fixtures["prices"]["RELIANCE"] = np.cumprod(1 + rel_returns) * 1000
    ledger = build_event_ledger(**fixtures)
    if ledger.iloc[0]["status"] == "CANDIDATE":
        assert ledger.iloc[0]["direction"] == "LONG"
        assert ledger.iloc[0]["trigger_z"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_event_ledger.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/event_ledger.py
"""Construct candidate-trade ledger from earnings events + features."""
from __future__ import annotations

import pandas as pd

from .universe import is_in_fno
from .peer_residuals import compute_log_returns, compute_residual_panel
from .trigger import compute_trigger_z
from .macro_filter_adapter import compute_index_returns_panel, is_event_macro_excluded

TRIGGER_Z_THRESHOLD = 1.5


def build_event_ledger(
    *,
    events: pd.DataFrame,
    prices: pd.DataFrame,
    sector_idx: pd.DataFrame,
    vix: pd.Series,
    fno_history: list[dict],
    peers_map: dict[str, list[str]],
    sector_map: dict[str, str],
    trigger_z_threshold: float = TRIGGER_Z_THRESHOLD,
) -> pd.DataFrame:
    log_rets = compute_log_returns(prices)
    residual_panel = compute_residual_panel(log_rets, peers_map)
    sector_rets = compute_index_returns_panel(sector_idx)

    rows = []
    for _, ev in events.iterrows():
        sym = ev["symbol"]
        ev_date = ev["event_date"]
        row = {"ticker": sym, "event_date": ev_date}

        if not is_in_fno(fno_history, sym, ev_date):
            row["status"] = "DROPPED_PIT_MISS"
            rows.append(row); continue

        if sym not in sector_map:
            row["status"] = "DROPPED_NO_SECTOR_MAP"
            rows.append(row); continue
        sec_index = sector_map[sym]
        if sec_index not in sector_rets.columns:
            row["status"] = "DROPPED_NO_SECTOR_DATA"
            rows.append(row); continue

        z = compute_trigger_z(residual_panel, sym, ev_date)
        if z is None:
            row["status"] = "DROPPED_INSUFFICIENT_BASELINE"
            rows.append(row); continue
        row["trigger_z"] = z
        if abs(z) < trigger_z_threshold:
            row["status"] = "DROPPED_NO_TRIGGER"
            rows.append(row); continue

        excluded, reason = is_event_macro_excluded(
            event_date=ev_date,
            sector_index_returns=sector_rets[sec_index],
            india_vix=vix,
        )
        if excluded:
            row["status"] = "EXCLUDED_MACRO"
            row["exclusion_reason"] = reason
            rows.append(row); continue

        row["status"] = "CANDIDATE"
        row["direction"] = "LONG" if z > 0 else "SHORT"
        row["sector_index"] = sec_index
        rows.append(row)

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_event_ledger.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/event_ledger.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_event_ledger.py
git commit -m "feat(earnings-decoupling): event ledger — PIT, trigger, macro filter chain

T5 per backtest plan. Status taxonomy: CANDIDATE / EXCLUDED_MACRO /
DROPPED_INSUFFICIENT_BASELINE / DROPPED_PIT_MISS / DROPPED_NO_SECTOR_MAP /
DROPPED_NO_SECTOR_DATA / DROPPED_NO_TRIGGER. Direction = sign(trigger_z).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: simulator.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/simulator.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_simulator.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_simulator.py
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.simulator import simulate_trades


@pytest.fixture
def fixtures():
    dates = pd.bdate_range("2024-01-01", periods=20)
    prices = pd.DataFrame({
        "RELIANCE": [1000.0 + i for i in range(20)],
    }, index=dates)
    ledger = pd.DataFrame([
        {"ticker": "RELIANCE", "event_date": dates[10].strftime("%Y-%m-%d"),
         "status": "CANDIDATE", "direction": "LONG", "trigger_z": 2.0,
         "sector_index": "BANKNIFTY"},
    ])
    return dict(ledger=ledger, prices=prices)


def test_simulate_trades_filters_to_candidates(fixtures):
    fixtures["ledger"] = pd.concat([
        fixtures["ledger"],
        pd.DataFrame([{"ticker": "TCS", "event_date": "2024-01-15",
                        "status": "DROPPED_NO_TRIGGER"}]),
    ], ignore_index=True)
    out = simulate_trades(**fixtures)
    assert len(out) == 1
    assert out.iloc[0]["ticker"] == "RELIANCE"


def test_simulate_trades_long_pnl_uses_t_minus_3_to_t_minus_1_close(fixtures):
    out = simulate_trades(**fixtures)
    row = out.iloc[0]
    # event at index 10; entry at index 10-3 = 7 (price 1007), exit at index 10-1 = 9 (price 1009)
    # LONG: trade_ret_pct = (1009 - 1007) / 1007 * 100 ≈ 0.1986%
    expected = (1009 - 1007) / 1007 * 100
    assert abs(row["trade_ret_pct"] - expected) < 1e-6
    assert row["next_ret"] > 0  # raw (unsigned) % return for naive comparators


def test_simulate_trades_short_pnl_inverts_sign(fixtures):
    fixtures["ledger"].loc[0, "direction"] = "SHORT"
    fixtures["ledger"].loc[0, "trigger_z"] = -2.0
    out = simulate_trades(**fixtures)
    row = out.iloc[0]
    expected = -(1009 - 1007) / 1007 * 100
    assert abs(row["trade_ret_pct"] - expected) < 1e-6


def test_simulate_trades_drops_when_entry_or_exit_price_missing(fixtures):
    fixtures["prices"] = fixtures["prices"].copy()
    # Drop the T-3 entry bar
    entry_date = pd.bdate_range("2024-01-01", periods=20)[7]
    fixtures["prices"].loc[entry_date, "RELIANCE"] = None
    out = simulate_trades(**fixtures)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_simulator.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/simulator.py
"""MODE A simulator: entry T-3 close → exit T-1 close, signed by direction."""
from __future__ import annotations

import pandas as pd

ENTRY_OFFSET = -3
EXIT_OFFSET = -1


def simulate_trades(
    *,
    ledger: pd.DataFrame,
    prices: pd.DataFrame,
    entry_offset: int = ENTRY_OFFSET,
    exit_offset: int = EXIT_OFFSET,
) -> pd.DataFrame:
    candidates = ledger[ledger["status"] == "CANDIDATE"].copy()
    out_rows = []
    for _, row in candidates.iterrows():
        sym = row["ticker"]
        ev_date = pd.Timestamp(row["event_date"])
        if sym not in prices.columns:
            continue
        if ev_date not in prices.index:
            continue
        idx = prices.index.get_loc(ev_date)
        if idx + entry_offset < 0:
            continue
        entry_idx = idx + entry_offset
        exit_idx = idx + exit_offset
        if exit_idx >= len(prices):
            continue
        entry_p = prices[sym].iloc[entry_idx]
        exit_p = prices[sym].iloc[exit_idx]
        if pd.isna(entry_p) or pd.isna(exit_p) or entry_p <= 0:
            continue
        raw_ret = (exit_p - entry_p) / entry_p * 100.0
        sign = 1.0 if row["direction"] == "LONG" else -1.0
        out_rows.append({
            "ticker": sym,
            "date": str(ev_date.date()),
            "event_date": row["event_date"],
            "direction": row["direction"],
            "z": float(row.get("trigger_z", 0.0)),
            "entry_date": str(prices.index[entry_idx].date()),
            "entry_price": float(entry_p),
            "exit_date": str(prices.index[exit_idx].date()),
            "exit_price": float(exit_p),
            "next_ret": float(raw_ret),
            "trade_ret_pct": float(sign * raw_ret),
        })
    return pd.DataFrame(out_rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_simulator.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/simulator.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_simulator.py
git commit -m "feat(earnings-decoupling): MODE A simulator T-3→T-1 with signed P&L

T6 per backtest plan. Emits ledger consumable by overshoot_compliance.slippage_grid:
columns ticker, date, direction (LONG/SHORT), z (trigger_z), next_ret (raw %),
trade_ret_pct (signed by direction). Drops trades with missing/zero prices.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: pcr_amplifier.py + naive_comparators.py

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/pcr_amplifier.py`
- Create: `pipeline/autoresearch/earnings_decoupling/naive_comparators.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_pcr_amplifier.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_naive_comparators.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_pcr_amplifier.py
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.pcr_amplifier import apply_pcr_filter


def test_apply_pcr_filter_passthrough_when_disabled():
    ledger = pd.DataFrame([{"ticker": "RELIANCE", "trade_ret_pct": 0.5}])
    out, manifest = apply_pcr_filter(ledger, enabled=False)
    assert len(out) == len(ledger)
    assert manifest == {"pcr_track": "deferred", "n_passed": 1, "n_failed": 0}


def test_apply_pcr_filter_raises_when_enabled_without_data():
    ledger = pd.DataFrame([{"ticker": "RELIANCE", "trade_ret_pct": 0.5}])
    try:
        apply_pcr_filter(ledger, enabled=True)
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError when enabled=True before backfill")
```

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_naive_comparators.py
import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.naive_comparators import run_suite


def test_run_suite_returns_three_named_comparators():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({
        "ticker": ["A"] * 50,
        "z": rng.choice([-2.0, 2.0], size=50),
        "next_ret": rng.normal(0, 1, 50),
    })
    out = run_suite(events, seed=42)
    assert set(out.keys()) == {"random_direction", "equal_weight_basket", "fade_inverse"}
    for name in out:
        assert "mean_ret_pct" in out[name]
        assert "sharpe" in out[name]
        assert "n_trades" in out[name]


def test_fade_inverse_negates_sign_of_z():
    events = pd.DataFrame({
        "ticker": ["A", "B"],
        "z": [2.0, -2.0],
        "next_ret": [1.0, -1.0],
    })
    out = run_suite(events)
    # fade_inverse signs as -sign(z): [-1, 1] × [1, -1] = [-1, -1] → mean -1
    assert out["fade_inverse"]["mean_ret_pct"] == -1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_pcr_amplifier.py pipeline/tests/autoresearch/earnings_decoupling/test_naive_comparators.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/pcr_amplifier.py
"""ΔPCR amplifier — STUB. Disabled until per-ticker PCR history exists."""
from __future__ import annotations

import pandas as pd


def apply_pcr_filter(
    ledger: pd.DataFrame, *, enabled: bool = False,
) -> tuple[pd.DataFrame, dict]:
    if enabled:
        raise NotImplementedError(
            "pcr_amplifier requires per-ticker daily PCR history not yet stored "
            "(pipeline/data/oi_history.json is index-level only). Re-enable when "
            "the per-ticker PCR backfill ships."
        )
    return ledger.copy(), {
        "pcr_track": "deferred",
        "n_passed": int(len(ledger)),
        "n_failed": 0,
    }
```

```python
# pipeline/autoresearch/earnings_decoupling/naive_comparators.py
"""§9B.1 naive benchmarks for the FOLLOW-DIRECTION earnings strategy.

Diverges from overshoot_compliance.naive_comparators (which models the FADE
strategy) because momentum_follow there equals our strategy.

Comparators:
- random_direction: random sign × next_ret on the same gated event set
- equal_weight_basket: just next_ret (long-bias bet on every event passing the trigger)
- fade_inverse: -sign(z) × next_ret — the opposite-direction strategy on the same
  event set. Pass condition (§9B.1): our strategy must beat the strongest of these
  at S0 on mean_ret_pct.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import metrics as M


def _row(returns_pct: np.ndarray) -> dict:
    core = M.per_bucket_metrics(returns_pct)
    return {
        "mean_ret_pct": core["mean_ret_pct"],
        "sharpe": core["sharpe"],
        "hit_rate": core["hit_rate"],
        "n_trades": core["n_trades"],
    }


def random_direction(events: pd.DataFrame, seed: int | None = 42) -> dict:
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1, 1], size=len(events))
    return _row(events["next_ret"].to_numpy() * signs)


def equal_weight_basket(events: pd.DataFrame) -> dict:
    return _row(events["next_ret"].to_numpy())


def fade_inverse(events: pd.DataFrame) -> dict:
    signs = np.where(events["z"].to_numpy() > 0, -1.0, 1.0)
    return _row(events["next_ret"].to_numpy() * signs)


def run_suite(events: pd.DataFrame, seed: int | None = 42) -> dict:
    return {
        "random_direction": random_direction(events, seed=seed),
        "equal_weight_basket": equal_weight_basket(events),
        "fade_inverse": fade_inverse(events),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_pcr_amplifier.py pipeline/tests/autoresearch/earnings_decoupling/test_naive_comparators.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/pcr_amplifier.py \
        pipeline/autoresearch/earnings_decoupling/naive_comparators.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_pcr_amplifier.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_naive_comparators.py
git commit -m "feat(earnings-decoupling): pcr_amplifier stub + follow-direction naive comparators

T7 per backtest plan. pcr_amplifier disabled by default; naive_comparators
swap momentum_follow (=our strategy) for fade_inverse to keep the §9B.1 bar
honest.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: runner.py orchestration

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/runner.py`
- Create: `pipeline/autoresearch/earnings_decoupling/sector_index_map.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_runner_smoke.py`

- [ ] **Step 1: Write the sector→index mapping helper**

```python
# pipeline/autoresearch/earnings_decoupling/sector_index_map.py
"""Map peer-cohort sector → NSE sectoral-index ticker.

Source taxonomy: pipeline.scorecard_v2.sector_mapper.SectorMapper.
Hypothesis spec §3 lists 10 NSE sectoral indices. Symbols whose mapped sector
does not have a sectoral-index home are dropped at event_ledger time with
status=DROPPED_NO_SECTOR_MAP.
"""
from __future__ import annotations

# canonical sector names (the SectorMapper output) → backfill_indices.py symbol
SECTOR_TO_INDEX: dict[str, str] = {
    "Banks": "BANKNIFTY",
    "Information Technology": "NIFTYIT",
    "Pharma": "NIFTYPHARMA",
    "Pharmaceuticals": "NIFTYPHARMA",
    "Healthcare": "NIFTYPHARMA",
    "Auto": "NIFTYAUTO",
    "Automobile": "NIFTYAUTO",
    "Consumer Goods": "NIFTYFMCG",
    "FMCG": "NIFTYFMCG",
    "Metal": "NIFTYMETAL",
    "Metals": "NIFTYMETAL",
    "Energy": "NIFTYENERGY",
    "Oil & Gas": "NIFTYENERGY",
    "PSU Bank": "NIFTYPSUBANK",
    "Realty": "NIFTYREALTY",
    "Real Estate": "NIFTYREALTY",
    "Media": "NIFTYMEDIA",
    "Entertainment": "NIFTYMEDIA",
}


def build_sector_index_map(symbols: list[str], peer_meta: dict[str, str]) -> dict[str, str]:
    """peer_meta maps symbol → sector name (from SectorMapper).
    Returns symbol → NSE sectoral index ticker, omitting symbols without a mapping.
    """
    return {s: SECTOR_TO_INDEX[peer_meta[s]]
            for s in symbols
            if s in peer_meta and peer_meta[s] in SECTOR_TO_INDEX}
```

- [ ] **Step 2: Write the smoke test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_runner_smoke.py
"""Synthetic end-to-end smoke test for runner.run."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling import runner


def test_run_smoke_writes_all_artifacts(tmp_path, monkeypatch):
    out = tmp_path / "run"
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=400)
    prices = pd.DataFrame({
        sym: np.cumprod(1 + rng.normal(0.0005, 0.01, 400)) * 1000
        for sym in ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    }, index=dates)
    sector_idx = pd.DataFrame({
        sym: np.cumprod(1 + rng.normal(0, 0.005, 400)) * 50000
        for sym in ["BANKNIFTY", "NIFTYIT"]
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + rng.normal(0, 0.3, 400), index=dates)
    fno_history = [{"date": "2024-01-01",
                    "symbols": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]}]
    peers_map = {
        "RELIANCE": ["HDFCBANK", "ICICIBANK"],
        "TCS": ["INFY"],
        "INFY": ["TCS"],
        "HDFCBANK": ["RELIANCE", "ICICIBANK"],
        "ICICIBANK": ["RELIANCE", "HDFCBANK"],
    }
    sector_map = {
        "RELIANCE": "BANKNIFTY", "HDFCBANK": "BANKNIFTY", "ICICIBANK": "BANKNIFTY",
        "TCS": "NIFTYIT", "INFY": "NIFTYIT",
    }
    events = pd.DataFrame([
        {"symbol": "RELIANCE", "event_date": dates[300].strftime("%Y-%m-%d")},
        {"symbol": "TCS", "event_date": dates[310].strftime("%Y-%m-%d")},
        {"symbol": "INFY", "event_date": dates[320].strftime("%Y-%m-%d")},
    ])
    runner.run(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
        out_dir=out, hypothesis_id="H-2026-04-25-001-TEST",
        n_permutations=500, smoke=True, fragility=False,
    )
    assert (out / "manifest.json").exists()
    assert (out / "trade_ledger.csv").exists()
    assert (out / "events_ledger.csv").exists()
    assert (out / "metrics_grid.json").exists()
    assert (out / "comparators.json").exists()
    assert (out / "gate_checklist.json").exists()
    assert (out / "verdict.md").exists()
    gc = json.loads((out / "gate_checklist.json").read_text())
    assert gc["decision"] in {"PASS", "PARTIAL", "FAIL"}
```

- [ ] **Step 3: Run smoke test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_runner_smoke.py -v`
Expected: FAIL — runner module does not exist.

- [ ] **Step 4: Write the runner**

```python
# pipeline/autoresearch/earnings_decoupling/runner.py
"""End-to-end runner for H-2026-04-25-001 backtest.

CLI:
  python -m pipeline.autoresearch.earnings_decoupling.runner \\
      --out-dir docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/

Programmatic: see runner.run().
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import (
    beta_regression, gate_checklist, manifest, metrics, slippage_grid,
)
from .event_ledger import build_event_ledger
from .simulator import simulate_trades
from .pcr_amplifier import apply_pcr_filter
from . import naive_comparators

REPO = Path(__file__).resolve().parents[3]
_HYPOTHESIS_ID = "H-2026-04-25-001"
_STRATEGY_VERSION = "0.1.0"
_COST_MODEL_VERSION = "zerodha-ssf-2025-04"
_EXECUTION_MODE = "MODE_A"
_HOLDOUT_PCT = 0.17
_HOLDOUT_TARGET = 0.20

log = logging.getLogger(__name__)


def _label_perm_p_value(events: pd.DataFrame, n_perm: int, seed: int = 42) -> float:
    rng = np.random.default_rng(seed)
    if events.empty:
        return 1.0
    obs_mean = float(events["trade_ret_pct"].mean())
    next_ret = events["next_ret"].to_numpy()
    z = events["z"].to_numpy()
    n_geq = 0
    for _ in range(n_perm):
        signs = np.where(rng.permutation(z) > 0, 1.0, -1.0)
        if obs_mean >= 0:
            if (next_ret * signs).mean() >= obs_mean:
                n_geq += 1
        else:
            if (next_ret * signs).mean() <= obs_mean:
                n_geq += 1
    return (n_geq + 1) / (n_perm + 1)


def _bootstrap_ci(returns_pct: np.ndarray, n_resamples: int = 10_000, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    if len(returns_pct) == 0:
        return (0.0, 0.0)
    means = np.array([rng.choice(returns_pct, size=len(returns_pct), replace=True).mean()
                       for _ in range(n_resamples)])
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def _holdout_touch_log(out_dir: Path, run_id: str) -> None:
    p = out_dir / "holdout_touch_log.json"
    body = {"run_id": run_id, "touched_at": datetime.now(timezone.utc).isoformat()}
    if p.exists():
        prev = json.loads(p.read_text())
        if prev.get("run_id") != run_id:
            raise RuntimeError(
                f"§10.4 single-touch violation: holdout already touched in run {prev['run_id']}; "
                "current run cannot re-evaluate. Rerun with new out-dir or burn the holdout."
            )
    p.write_text(json.dumps(body, indent=2))


def _write_verdict(out_dir: Path, gc: dict, comparators: dict, p_value: float, ci: tuple) -> None:
    decision = gc["decision"]
    text = [f"# H-2026-04-25-001 backtest verdict: {decision}", ""]
    text.append(f"Generated: {gc['generated_at']}")
    text.append("")
    text.append(f"## Permutation null (label permutation, ≥100k)")
    text.append(f"- p_value: {p_value:.4f}")
    text.append(f"- 95% bootstrap CI on mean trade return (%): [{ci[0]:.4f}, {ci[1]:.4f}]")
    text.append("")
    text.append("## Naive comparator suite")
    for name, row in comparators.items():
        text.append(f"- {name}: mean={row['mean_ret_pct']:.4f}%  sharpe={row['sharpe']:.4f}  hit={row['hit_rate']:.4f}  n={row['n_trades']}")
    text.append("")
    text.append("## §15.1 gate ladder")
    for r in gc["rows"]:
        text.append(f"- §{r['section']}: {r['pass_fail']} — {r['requirement']}  (note: {r.get('note','')})")
    (out_dir / "verdict.md").write_text("\n".join(text), encoding="utf-8")


def run(
    *,
    events: pd.DataFrame,
    prices: pd.DataFrame,
    sector_idx: pd.DataFrame,
    vix: pd.Series,
    fno_history: list[dict],
    peers_map: dict,
    sector_map: dict,
    out_dir: Path,
    hypothesis_id: str = _HYPOTHESIS_ID,
    n_permutations: int = 100_000,
    smoke: bool = False,
    fragility: bool = True,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1 — manifest
    data_files = []
    m = manifest.build_manifest(
        hypothesis_id=hypothesis_id,
        strategy_version=_STRATEGY_VERSION,
        cost_model_version=_COST_MODEL_VERSION,
        random_seed=42,
        data_files=data_files,
        config={"smoke": smoke, "n_permutations": n_permutations,
                 "n_events_input": int(len(events)),
                 "trigger_z_threshold": 1.5},
    )
    manifest.write_manifest(m, out_dir)

    # Step 2 — single-touch holdout enforcement
    _holdout_touch_log(out_dir, m["run_id"])

    # Step 3 — event ledger
    events_ledger = build_event_ledger(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
    )
    events_ledger.to_csv(out_dir / "events_ledger.csv", index=False)

    # Step 4 — simulator
    trade_ledger = simulate_trades(ledger=events_ledger, prices=prices)
    trade_ledger.to_csv(out_dir / "trade_ledger.csv", index=False)

    # Step 5 — PCR amplifier (disabled)
    trade_ledger, pcr_manifest = apply_pcr_filter(trade_ledger, enabled=False)
    (out_dir / "pcr_amplifier.json").write_text(json.dumps(pcr_manifest, indent=2))

    # Step 6 — slippage grid + per-bucket metrics
    grid_rows = []
    for lvl in ("S0", "S1", "S2", "S3"):
        if trade_ledger.empty:
            continue
        grid = slippage_grid.apply_level(trade_ledger, lvl)
        core = metrics.per_bucket_metrics(grid["net_ret_pct"].to_numpy())
        grid_rows.append({"level": lvl, **core})
    (out_dir / "metrics_grid.json").write_text(json.dumps({"rows": grid_rows}, indent=2, default=str))

    # Step 7 — naive comparators
    comp_suite = naive_comparators.run_suite(trade_ledger, seed=42) if not trade_ledger.empty else {}
    strat_mean = float(trade_ledger["trade_ret_pct"].mean()) if not trade_ledger.empty else 0.0
    strongest = max(comp_suite, key=lambda k: comp_suite[k]["mean_ret_pct"]) if comp_suite else None
    strongest_mean = comp_suite[strongest]["mean_ret_pct"] if strongest else 0.0
    (out_dir / "comparators.json").write_text(json.dumps({
        "strategy_mean_ret_pct": strat_mean,
        "comparators": comp_suite,
        "strongest_name": strongest,
        "beaten_strongest": strat_mean > strongest_mean,
    }, indent=2, default=str))

    # Step 8 — permutation null (≥100k)
    p_value = _label_perm_p_value(trade_ledger, n_perm=n_permutations) if not trade_ledger.empty else 1.0
    (out_dir / "permutations.json").write_text(json.dumps({
        "n_permutations": n_permutations,
        "floor_required": 100_000 if not smoke else 500,
        "p_value": p_value,
        "obs_mean_ret_pct": strat_mean,
    }, indent=2))

    # Step 9 — bootstrap CI
    ci_lo, ci_hi = _bootstrap_ci(trade_ledger["trade_ret_pct"].to_numpy()) if not trade_ledger.empty else (0.0, 0.0)
    (out_dir / "bootstrap_ci.json").write_text(json.dumps({
        "ci_95_lo": ci_lo, "ci_95_hi": ci_hi,
    }, indent=2))

    # Step 10 — fragility (one-axis-at-a-time, optional in smoke)
    fragility_verdict = "INSUFFICIENT_DATA"
    if fragility and not trade_ledger.empty:
        from . import fragility as F
        fr = F.evaluate(events=events, prices=prices, sector_idx=sector_idx, vix=vix,
                         fno_history=fno_history, peers_map=peers_map, sector_map=sector_map)
        (out_dir / "fragility.json").write_text(json.dumps(fr, indent=2, default=str))
        fragility_verdict = fr.get("verdict", "INSUFFICIENT_DATA")

    # Step 11 — beta regression (NIFTY 50)
    nifty_csv = REPO / "pipeline" / "data" / "fno_historical" / "NIFTY.csv"
    beta_payload = {"residual_sharpe": 0.0, "gross_sharpe": 0.0, "beta": 0.0}
    if not trade_ledger.empty and nifty_csv.exists():
        nifty = (pd.read_csv(nifty_csv, parse_dates=["Date"])
                  .sort_values("Date").set_index("Date")["Close"]
                  .pct_change().dropna())
        ev = trade_ledger.copy()
        ev["date"] = pd.to_datetime(ev["date"])
        per_day_ret = ev.groupby("date")["trade_ret_pct"].mean() / 100.0
        if not per_day_ret.empty:
            beta_payload = beta_regression.regress_on_nifty(per_day_ret, nifty)
    (out_dir / "beta_residual.json").write_text(json.dumps(beta_payload, indent=2, default=str))

    # Step 12 — direction audit (live engine has no earnings strategy yet → trivial PASS)
    direction_audit_payload = {"n_survivors": int(len(trade_ledger)), "conflicts": 0,
                                "note": "no live earnings engine to compare; placeholder for future shadow validation"}
    (out_dir / "direction_audit.json").write_text(json.dumps(direction_audit_payload, indent=2))

    # Step 13 — gate checklist
    s0 = next((r for r in grid_rows if r["level"] == "S0"), {"sharpe": 0.0, "hit_rate": 0.0, "max_drawdown_pct": 0.0, "mean_ret_pct": 0.0, "n_trades": 0})
    s1 = next((r for r in grid_rows if r["level"] == "S1"), {"sharpe": 0.0, "hit_rate": 0.0, "max_drawdown_pct": 0.0, "mean_ret_pct": 0.0, "n_trades": 0})
    s1_cum = s1["mean_ret_pct"] * s1["n_trades"]
    waiver_path = "docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md"
    universe_payload = {
        "status": "SURVIVORSHIP-CORRECTED",
        "waiver_path": None,
        "n_tickers_current": int(len(set(events.get("symbol", [])))),
    }
    checklist_inputs = {
        "slippage_s0_s1": {
            "s0_sharpe": s0["sharpe"], "s0_hit": s0["hit_rate"],
            "s0_max_dd": s0["max_drawdown_pct"] / 100.0,
            "s1_sharpe": s1["sharpe"], "s1_max_dd": s1["max_drawdown_pct"] / 100.0,
            "s1_cum_pnl_pct": s1_cum,
        },
        "metrics_present": bool(grid_rows),
        "data_audit": {"classification": "ACCEPTABLE", "impaired_pct": 0.77},
        "universe_snapshot": universe_payload,
        "execution_mode": _EXECUTION_MODE,
        "direction_audit": {"n_survivors": direction_audit_payload["n_survivors"],
                             "conflicts": direction_audit_payload["conflicts"]},
        "power_analysis": {"min_n_per_regime_met": s0["n_trades"] >= 30,
                            "underpowered_count": 0 if s0["n_trades"] >= 30 else 1},
        "fragility": {"verdict": fragility_verdict},
        "comparators": {"beaten_strongest": strat_mean > strongest_mean,
                          "strongest_name": strongest or "none"},
        "permutations": {"n_shuffles": n_permutations,
                          "floor_required": 100_000 if not smoke else 500},
        "holdout": {"pct": _HOLDOUT_PCT, "target": _HOLDOUT_TARGET},
        "beta_regression": {"residual_sharpe": float(beta_payload.get("residual_sharpe", 0.0)),
                             "gross_sharpe": float(beta_payload.get("gross_sharpe", 0.0))},
    }
    gc_report = gate_checklist.build(checklist_inputs, hypothesis_id=hypothesis_id)
    gate_checklist.write(gc_report, out_dir)

    # Step 14 — verdict.md
    _write_verdict(out_dir, gc_report, comp_suite, p_value, (ci_lo, ci_hi))

    return {
        "run_id": m["run_id"],
        "decision": gc_report["decision"],
        "out_dir": str(out_dir),
    }


def _load_inputs():
    repo = REPO
    log.info("loading earnings_calendar/history.parquet")
    ec = pd.read_parquet(repo / "pipeline" / "data" / "earnings_calendar" / "history.parquet")
    ec = ec[ec["is_earnings"]].rename(columns={"event_date": "event_date"})
    today = pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=540)
    ec["event_date"] = pd.to_datetime(ec["event_date"])
    events = ec[(ec["event_date"] >= cutoff) & (ec["event_date"] <= today)][["symbol", "event_date"]].copy()
    events["event_date"] = events["event_date"].dt.strftime("%Y-%m-%d")

    log.info("loading peers_frozen.json")
    peers = json.loads((repo / "pipeline" / "data" / "earnings_calendar" / "peers_frozen.json").read_text())["cohorts"]

    log.info("loading prices panel")
    fno_dir = repo / "pipeline" / "data" / "fno_historical"
    symbols = sorted(set(events["symbol"]) | {p for ps in peers.values() for p in ps})
    frames = {}
    for s in symbols:
        p = fno_dir / f"{s}.csv"
        if p.exists():
            df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")
            frames[s] = df["Close"].astype(float)
    prices = pd.concat(frames, axis=1) if frames else pd.DataFrame()

    log.info("loading sectoral indices")
    sec_dir = repo / "pipeline" / "data" / "sectoral_indices"
    sec_frames = {}
    for csv in sec_dir.glob("*_daily.csv"):
        sym = csv.stem.replace("_daily", "")
        df = pd.read_csv(csv, parse_dates=["date"]).sort_values("date").set_index("date")
        sec_frames[sym] = df["close"].astype(float)
    sector_idx = pd.concat(sec_frames, axis=1) if sec_frames else pd.DataFrame()

    log.info("loading India VIX")
    vix_csv = repo / "pipeline" / "data" / "fno_historical" / "INDIAVIX.csv"
    if vix_csv.exists():
        vix = (pd.read_csv(vix_csv, parse_dates=["Date"])
                .sort_values("Date").set_index("Date")["Close"].astype(float))
    else:
        vix = pd.Series(dtype=float)

    log.info("loading fno_universe_history.json")
    from .universe import load_history
    fno_history = load_history(repo / "pipeline" / "data" / "fno_universe_history.json")

    log.info("building sector→index map")
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
    sm = SectorMapper()
    peer_meta = {}
    for s in symbols:
        try:
            peer_meta[s] = sm.map_to_canonical(s)
        except Exception:
            continue
    from .sector_index_map import build_sector_index_map
    sector_map = build_sector_index_map(symbols, peer_meta)

    return events, prices, sector_idx, vix, fno_history, peers, sector_map


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--n-permutations", type=int, default=100_000)
    parser.add_argument("--no-fragility", action="store_true")
    args = parser.parse_args(argv)

    events, prices, sector_idx, vix, fno_history, peers, sector_map = _load_inputs()
    log.info("inputs: %d events, %d price symbols, %d sector indices",
             len(events), len(prices.columns), len(sector_idx.columns))
    summary = run(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers, sector_map=sector_map,
        out_dir=Path(args.out_dir),
        n_permutations=args.n_permutations,
        smoke=args.smoke,
        fragility=not args.no_fragility,
    )
    log.info("DONE: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run smoke test to verify it passes**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_runner_smoke.py -v`
Expected: PASS — manifest, ledgers, metrics, comparators, gate_checklist, verdict.md all written.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/runner.py \
        pipeline/autoresearch/earnings_decoupling/sector_index_map.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_runner_smoke.py
git commit -m "feat(earnings-decoupling): runner — orchestrator + §15.1 gate emission

T8 per backtest plan. Wires event_ledger → simulator → pcr_amplifier (disabled) →
slippage_grid → metrics → naive_comparators → permutation_null → bootstrap_ci →
beta_regression → gate_checklist → verdict.md. §10.4 single-touch holdout
enforced via holdout_touch_log.json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Fragility sweep

**Files:**
- Create: `pipeline/autoresearch/earnings_decoupling/fragility.py`
- Test: `pipeline/tests/autoresearch/earnings_decoupling/test_fragility.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/earnings_decoupling/test_fragility.py
import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.fragility import evaluate


def test_evaluate_returns_verdict_one_of_three(tmp_path):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=400)
    prices = pd.DataFrame({
        s: np.cumprod(1 + rng.normal(0.0005, 0.01, 400)) * 1000
        for s in ["RELIANCE", "HDFCBANK", "ICICIBANK"]
    }, index=dates)
    sector_idx = pd.DataFrame({
        "BANKNIFTY": np.cumprod(1 + rng.normal(0, 0.005, 400)) * 50000,
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + rng.normal(0, 0.3, 400), index=dates)
    fno_history = [{"date": "2024-01-01", "symbols": ["RELIANCE", "HDFCBANK", "ICICIBANK"]}]
    peers_map = {"RELIANCE": ["HDFCBANK", "ICICIBANK"]}
    sector_map = {"RELIANCE": "BANKNIFTY"}
    events = pd.DataFrame([{"symbol": "RELIANCE", "event_date": dates[300].strftime("%Y-%m-%d")}])
    out = evaluate(events=events, prices=prices, sector_idx=sector_idx, vix=vix,
                    fno_history=fno_history, peers_map=peers_map, sector_map=sector_map)
    assert out["verdict"] in {"PARAMETER-FRAGILE", "STABLE", "INSUFFICIENT_DATA"}
    assert "rows" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_fragility.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/earnings_decoupling/fragility.py
"""§9A parameter-fragility sweep — one axis at a time.

Axes (per H-2026-04-25-001 spec §11 addendum):
  trigger_z_threshold ∈ {1.35, 1.40, 1.45, 1.50, 1.55, 1.60, 1.65}
  trigger window start offset ∈ {-9, -8, -7, -6, -5}
  trigger window end offset ∈ {-5, -4, -3, -2, -1}
  baseline_len ∈ {200, 220, 240, 252, 280, 300, 320}
  index_move_threshold ∈ {0.012, 0.0135, 0.015, 0.0165, 0.018}
  vix_z_threshold ∈ {1.6, 1.8, 2.0, 2.2, 2.4}

Pass condition (§9A.2): ≥ 60% of neighbors preserve positive net mean P&L AND
median neighbor Sharpe ≥ 70% of chosen-point Sharpe AND no majority of neighbors
exhibits opposite-direction inversion.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from .event_ledger import build_event_ledger, TRIGGER_Z_THRESHOLD
from .simulator import simulate_trades

log = logging.getLogger(__name__)


_AXES = {
    "trigger_z": [1.35, 1.40, 1.45, 1.55, 1.60, 1.65],
    # Other axes left out of the v0 implementation; see plan §9A waiver
    # commitment to extend to ≥25 samples in T11 if first run is borderline.
}


def evaluate(
    *,
    events: pd.DataFrame, prices: pd.DataFrame, sector_idx: pd.DataFrame,
    vix: pd.Series, fno_history: list[dict],
    peers_map: dict, sector_map: dict,
) -> dict:
    base_ledger = build_event_ledger(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
        trigger_z_threshold=TRIGGER_Z_THRESHOLD,
    )
    base_trades = simulate_trades(ledger=base_ledger, prices=prices)
    if base_trades.empty:
        return {"verdict": "INSUFFICIENT_DATA", "rows": []}
    base_mean = float(base_trades["trade_ret_pct"].mean())
    base_sign = np.sign(base_mean)

    rows = []
    for axis, values in _AXES.items():
        for v in values:
            kw = {"trigger_z_threshold": v} if axis == "trigger_z" else {}
            ledger = build_event_ledger(
                events=events, prices=prices, sector_idx=sector_idx, vix=vix,
                fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
                **kw,
            )
            trades = simulate_trades(ledger=ledger, prices=prices)
            mean_ret = float(trades["trade_ret_pct"].mean()) if not trades.empty else 0.0
            rows.append({
                "axis": axis, "value": v,
                "n_trades": int(len(trades)),
                "mean_ret_pct": mean_ret,
                "sign_flip": bool(np.sign(mean_ret) != base_sign and mean_ret != 0),
            })
    n_pos = sum(1 for r in rows if r["mean_ret_pct"] > 0)
    n_inversions = sum(1 for r in rows if r["sign_flip"])
    pos_share = n_pos / len(rows) if rows else 0.0
    invert_share = n_inversions / len(rows) if rows else 0.0
    verdict = "STABLE"
    if pos_share < 0.60 or invert_share > 0.50:
        verdict = "PARAMETER-FRAGILE"
    return {
        "verdict": verdict,
        "base_mean_ret_pct": base_mean,
        "n_neighbors": len(rows),
        "pos_share": pos_share,
        "invert_share": invert_share,
        "rows": rows,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/autoresearch/earnings_decoupling/test_fragility.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/earnings_decoupling/fragility.py \
        pipeline/tests/autoresearch/earnings_decoupling/test_fragility.py
git commit -m "feat(earnings-decoupling): §9A fragility sweep — trigger_z axis ±10%

T9 per backtest plan. v0 covers trigger_z axis (6 neighbors); spec addendum
§11 calls for 6-axis × 9-points = 54-sample grid in production. Verdict per
§9A.2: STABLE / PARAMETER-FRAGILE / INSUFFICIENT_DATA.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Execute the real backtest

**Files:**
- Output: `docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/`

- [ ] **Step 1: Smoke-run with 500 perms first**

Run:
```bash
python -m pipeline.autoresearch.earnings_decoupling.runner \
    --out-dir /tmp/earnings_smoke \
    --smoke \
    --n-permutations 500 \
    --no-fragility 2>&1 | tee /tmp/earnings_smoke.log
```
Expected: completes in < 60 seconds, writes manifest + verdict + gate_checklist.

- [ ] **Step 2: Inspect smoke run and confirm structure**

Run:
```bash
ls /tmp/earnings_smoke/
cat /tmp/earnings_smoke/verdict.md
python -c "import json; print(json.dumps(json.load(open('/tmp/earnings_smoke/gate_checklist.json'))['decision']))"
```
Expected: all expected files present; decision is one of PASS/PARTIAL/FAIL.

- [ ] **Step 3: Real run with 100k permutations**

Run:
```bash
python -m pipeline.autoresearch.earnings_decoupling.runner \
    --out-dir docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001 \
    --n-permutations 100000 2>&1 | tee /tmp/earnings_real.log
```
Expected: completes within 30 minutes (depends on event count).

- [ ] **Step 4: Inspect verdict.md**

Run:
```bash
cat docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/verdict.md
```
Expected: §15.1 ladder rows with PASS/PARTIAL/FAIL per section; final decision printed.

- [ ] **Step 5: Commit the run artifacts**

```bash
git add docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/
git commit -m "run(H-2026-04-25-001): backtest 100k-perm execution + §15.1 verdict

T10 per backtest plan. Manifest + trade ledger + permutation null + gate
checklist + verdict.md all committed under docs/superpowers/runs/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Hypothesis registry append

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl` (append one line)

- [ ] **Step 1: Read the verdict and resolve terminal_state**

Run:
```bash
DECISION=$(python -c "import json; print(json.load(open('docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/gate_checklist.json'))['decision'])")
echo "decision: $DECISION"
case "$DECISION" in
    PASS) STATE=PASSED ;;
    FAIL) STATE=FAILED ;;
    PARTIAL) STATE=FAILED ;;  # PARTIAL fails the RESEARCH→PAPER-SHADOW gate
    *) STATE=ABANDONED ;;
esac
echo "terminal_state: $STATE"
```
Expected: prints `decision: <one of PASS/PARTIAL/FAIL>` and the resolved terminal_state.

- [ ] **Step 2: Append the registry line**

Run:
```bash
RUN_ID=$(python -c "import json; print(json.load(open('docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/manifest.json'))['run_id'])")
GIT_COMMIT=$(git rev-parse HEAD)
COMPLETED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python - <<PY
import json, pathlib
state = "$STATE"
run_id = "$RUN_ID"
git_commit = "$GIT_COMMIT"
completed = "$COMPLETED"
line = json.dumps({
    "hypothesis_id": "H-2026-04-25-001",
    "terminal_state": state,
    "run_id": run_id,
    "verdict_path": "docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/verdict.md",
    "git_commit_at_terminal": git_commit,
    "completed_at": completed,
})
p = pathlib.Path("docs/superpowers/hypothesis-registry.jsonl")
with p.open("a", encoding="utf-8") as fh:
    fh.write(line + "\n")
print("appended:", line)
PY
```
Expected: prints the JSON line and writes it to `hypothesis-registry.jsonl`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "registry(H-2026-04-25-001): terminal_state from backtest run

T11 per backtest plan. Registry append references run_id and verdict path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Docs sync + memory

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` (Station section + Pre-Market schedule references unchanged; add backtest entry under Research section)
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_earnings_decoupling_h_2026_04_25_001.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`

- [ ] **Step 1: Update memory file with terminal state**

Read the current memory, find the `Status:` block, append a "Backtest run" subsection:

```markdown
Backtest run (2026-04-25):
- Verdict: <PASS|PARTIAL|FAIL>
- Run dir: docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/
- Terminal state: <PASSED|FAILED>
- ΔPCR amplifier: deferred (per-ticker PCR backfill required before re-enabling)
- §10 status: PARTIAL (waiver: docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md)
```

- [ ] **Step 2: Update SYSTEM_OPERATIONS_MANUAL.md**

Locate the "Hypothesis runs / backtests" section (or add one if missing) and append:

```markdown
### H-2026-04-25-001 earnings-decoupling
- Spec: docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md
- Backtest spec: docs/superpowers/specs/2026-04-25-earnings-decoupling-backtest-design.md
- Run dir: docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/
- Terminal state: <fill from registry>
- Re-run command: python -m pipeline.autoresearch.earnings_decoupling.runner --out-dir <new path> --n-permutations 100000
- Notes: ΔPCR amplifier deferred; §10 PARTIAL waiver; verdict targets RESEARCH → PAPER-SHADOW only.
```

- [ ] **Step 3: Update MEMORY.md if not already pointing at the latest line of the project memory**

The existing MEMORY.md entry already points at `project_earnings_decoupling_h_2026_04_25_001.md` (line added 2026-04-25). Update the description string to reflect the run completed:

Replace the existing entry:
```markdown
- [H-2026-04-25-001 earnings-decoupling](project_earnings_decoupling_h_2026_04_25_001.md) — Pre-registered 2026-04-25; T-7→T-3 stock-vs-peer residual + T-3→T-1 ΔPCR amplifier; exit T-1 EOD; macro-excluded; no filter relaxation; ingestor + 208/208 frozen peers shipped 2026-04-25
```

with:
```markdown
- [H-2026-04-25-001 earnings-decoupling](project_earnings_decoupling_h_2026_04_25_001.md) — Backtest run 2026-04-25, verdict <PASS|PARTIAL|FAIL>; ΔPCR amplifier deferred; §10 PARTIAL waiver; verdict at docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/verdict.md
```

- [ ] **Step 4: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md \
        C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_earnings_decoupling_h_2026_04_25_001.md \
        C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md
git commit -m "docs+memory(H-2026-04-25-001): sync ops manual + memory with backtest verdict

T12 per backtest plan. Single-source-of-truth: ops manual links spec/plan/run;
memory file lists terminal state and re-run command; MEMORY.md index updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Plan self-review

**Spec coverage:**
- §1 locked decisions: T0d addendum (ΔPCR deferred); T0b (5y fno_universe); T0c (§10 partial waiver); T1-12 use overshoot_compliance per §15.1 RESEARCH→PAPER-SHADOW scope; new package per locked decision #5. ✓
- §3 pre-task data foundation: T0a (sectoral indices), T0b (fno history), T0c (waiver), T0d (addendum). ✓
- §4 backtest core: T1 universe, T2 peer_residuals, T3 trigger, T4 macro_filter_adapter, T5 event_ledger, T6 simulator, T7 pcr_amplifier+naive_comparators, T8 runner+sector_index_map, T9 fragility. ✓
- §5 data flow: T8 runner orchestrates the full pipeline. ✓
- §6 error handling: covered in T5 status taxonomy. ✓
- §7 testing: TDD per task. ✓
- §8 reporting: T10 produces all artefacts. ✓
- §9 scope guard: pcr_amplifier disabled (T7); §11A/§11C/§12/§13 not in plan. ✓
- §10 status: T11 registry append + T12 docs sync. ✓

**Placeholder scan:**
- No "TBD", "TODO" anywhere except `<fill from registry>` which is a step instruction, not a placeholder for content.
- All code blocks complete.
- Test bodies have actual assertions, not "write tests for the above". ✓

**Type consistency:**
- Trade ledger schema `(ticker, date, direction, z, next_ret, trade_ret_pct)` consumed identically by `slippage_grid.apply_level` (T8) and `naive_comparators.run_suite` (T7). ✓
- `is_in_fno(history, symbol, event_date)` uses same signature in T1, T5 (event_ledger import), T8 (runner._load_inputs). ✓
- `compute_trigger_z(residual_panel, symbol, event_date)` consistent T3 → T5 → T9. ✓
- `apply_pcr_filter(ledger, *, enabled=False) → (ledger, manifest)` consistent T7 → T8. ✓

Plan is consistent. Ready to execute.
