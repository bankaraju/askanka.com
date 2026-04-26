# v3-Evaluation Phase 2 — Comprehensive Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a peer-review-grade comprehensive 5-year out-of-sample backtest of the v3-CURATED ETF regime engine, decompose every plausible marker, and produce evidence for every Backtest-Spec §0–§14 gate that v2 historically skipped — so Phase 3 can pre-register a single locked strategy for forward shadow under §13.1 single-touch holdout.

**Architecture:**
1. **Preflight** — close the 3 Phase 1 caveats so Phase 2 reads a clean dataset (single adjustment treatment, full event-channel coverage, alias resolution)
2. **Walk-forward grid** — extend `etf_v3_rolling_refit` over 3 lookbacks × 2 universes × purged-CV per §10, every run wrapped in a §13A reproducibility manifest
3. **Marker decomposition** — 6 markers (zone gate, sector overlay, coef-delta, σ bucket, regime transition, exit-rule) evaluated standalone + incremental on the 60-day v0.2 replay
4. **Statistical battery** — cluster-robust SE, permutation null (n≥10,000), §9A fragility, §9B naive benchmarks, §11B alpha-after-beta, §11C correlation gate
5. **Spec-gate evidence** — §1–§3 slippage grid, §5A data audit, §6 survivorship, §7.3 entry-timing audit, §8 direction audit, §11 liquidity, §11A 10-scenario implementation risk, §12 edge decay
6. **Reports + closeout** — `markers_decomposition.md`, `universe_sensitivity.md`, §15 gate ladder verdict, Phase 3 pre-registration stub, branch tag

**Tech Stack:** Python 3.13, pandas, numpy, statsmodels (cluster-robust SE), scipy (permutation), pytest, existing `pipeline.autoresearch.etf_v3_*` modules, new `pipeline.autoresearch.etf_v3_eval.phase_2.*` package.

**Source authority:**
- `docs/superpowers/specs/2026-04-26-v3-evaluation-design.md` §6 (master spec)
- `docs/superpowers/specs/backtesting-specs.txt` §0–§15 (governing gates)
- `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` §6/§8/§9/§10/§13/§14/§17/§21
- `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md` (Phase 1 dataset acceptance + caveats)
- `docs/v3-evaluation/phase-0-v2-lessons-catalog.md` (constraints set)

**Inputs from Phase 1 (already on disk):**
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet` (1.93M rows × 143 tickers × 36 days, sha256 captured in `phase_1_universe/manifest.json`)
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/{manifest,reconciliation_report,contamination_map}.json`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_failed.csv` (4 alias gaps)

**Output root:** `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/`

---

## File Structure

New package laid out under `pipeline/autoresearch/etf_v3_eval/phase_2/`. Files that change together live together; each file has a single responsibility. Tests mirror the structure under `pipeline/tests/test_etf_v3_eval/`.

```
pipeline/autoresearch/etf_v3_eval/phase_2/
├── __init__.py
├── adjustment_adapter.py       # T1: §10 single-conv adjuster (minute ↔ EOD)
├── canonical_event_paths.py    # T3: bulk/news/earnings canonical-path adapters
├── alias_resolver.py           # T4: 4 alias gaps resolved or doc'd
├── manifest.py                 # T5: §13A.1 per-run manifest extension
├── walk_forward_runner.py      # T6: lookback × universe × cadence runner
├── replay_extender.py          # T7: apply v3 zone gates to 273-ticker replay
├── markers/
│   ├── __init__.py
│   ├── zone_gate.py            # T8: ±0.25/±0.5/±1.0σ NEUTRAL band sweep
│   ├── sector_overlay.py       # T8: PSU BANK/BANK/PSE/ENERGY/INFRA/...
│   ├── coef_delta.py           # T9: |Δweight| > P75 transition flag
│   ├── sigma_bucket.py         # T9: extreme/rare/mild conditional
│   ├── regime_transition.py    # T10: yesterday↔today zone change
│   └── exit_rule.py            # T10: held fixed sanity check
├── stats/
│   ├── __init__.py
│   ├── cluster_robust_se.py    # T11: statsmodels GMM clustered by trade_date
│   ├── permutation_null.py     # T11: block-bootstrap n≥10,000
│   ├── fragility.py            # T12: §9A.2 3 stability conditions
│   ├── naive_benchmarks.py     # T12: §9B.1 random/always_short/always_long/never
│   └── alpha_after_beta.py     # T13: §11B residualize vs NIFTY
├── slippage_grid.py            # T14: §1.2 fill simulator + §3 pass/fail
├── data_audit.py               # T15: §5A per-run quality report
├── survivorship.py             # T16: §6 fno_universe_history snapshot/check
├── entry_timing_audit.py       # T16: §7.3 audit hook
├── direction_audit.py          # T17: §8 v3-zone vs realized direction
├── liquidity_check.py          # T18: §11.1 ADV gate + impact penalty
├── implementation_risk.py      # T19: §11A.1 10-scenario sim
├── edge_decay.py               # T20: §12.1 rolling 12mo + §12.2 CUSUM
├── orchestrator.py             # T21: end-to-end Phase 2 pipeline
├── decomposition_report.py     # T22: markers_decomposition.md writer
├── universe_sensitivity_report.py  # T22: universe_sensitivity.md writer
└── gate_ladder.py              # T23: §15.1 RESEARCH→PAPER-SHADOW verdict

pipeline/tests/test_etf_v3_eval/
├── test_adjustment_adapter.py        # T1
├── test_canonical_event_paths.py     # T3
├── test_alias_resolver.py            # T4
├── test_p2_manifest.py               # T5
├── test_walk_forward_runner.py       # T6
├── test_replay_extender.py           # T7
├── test_marker_zone_gate.py          # T8
├── test_marker_sector_overlay.py     # T8
├── test_marker_coef_delta.py         # T9
├── test_marker_sigma_bucket.py       # T9
├── test_marker_regime_transition.py  # T10
├── test_marker_exit_rule.py          # T10
├── test_cluster_robust_se.py         # T11
├── test_permutation_null.py          # T11
├── test_fragility.py                 # T12
├── test_naive_benchmarks.py          # T12
├── test_alpha_after_beta.py          # T13
├── test_slippage_grid.py             # T14
├── test_data_audit.py                # T15
├── test_survivorship.py              # T16
├── test_entry_timing_audit.py        # T16
├── test_direction_audit.py           # T17
├── test_liquidity_check.py           # T18
├── test_implementation_risk.py       # T19
├── test_edge_decay.py                # T20
├── test_orchestrator.py              # T21
└── test_gate_ladder.py               # T23
```

CLI runners live alongside their modules (one `if __name__ == "__main__"` per top-level entry point) so subagents can smoke-test without touching scheduler-wiring.

---

## Section 0 — Preflight (Phase 1 caveats)

These three tasks address the 3 caveats in `2026-04-26-kite-minute-bars-fno-273-data-source-audit.md` §17:
(a) §13 strict pass requires single adjustment treatment; (b) §14 wires bulk/news/earnings to canonical paths; (c) 4 alias gaps resolved or excluded with attribution.

### Task 1: §10 adjustment-mode adapter

**Why:** Phase 1 §13 had 6/178 rows above 0.5% threshold, all attributable to Kite minute = unadjusted vs `fno_historical/*.csv` = yfinance auto-adjusted. Phase 2 must use a single consistent convention end-to-end (per §5A.2: "mixed conventions are forbidden").

**Decision (locked):** Phase 2 reads minute bars **unadjusted as Kite emitted** and applies an *explicit* corp-action adjuster to the EOD comparison series so both speak the same language. This honors §11 PIT correctness on the trading data and keeps the audit trail explicit.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/__init__.py` (empty)
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/adjustment_adapter.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py
from datetime import date
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.adjustment_adapter import (
    AdjustmentEvent,
    unadjust_eod_series,
)


def test_unadjust_applies_split_factor_backwards():
    """A 2-for-1 split on D=2025-06-15 means EOD CSV (auto-adjusted) shows pre-split
    closes scaled by 0.5. unadjust_eod_series multiplies pre-split rows by 2.0."""
    eod = pd.DataFrame({
        "trade_date": [date(2025, 6, 14), date(2025, 6, 15), date(2025, 6, 16)],
        "close": [100.0, 50.0, 52.0],
    })
    events = [AdjustmentEvent(symbol="X", event_date=date(2025, 6, 15), kind="split", ratio=2.0)]
    out = unadjust_eod_series(eod, events)
    # Pre-split row scaled back to unadjusted (200), event-day and post unchanged
    assert out["close"].tolist() == pytest.approx([200.0, 50.0, 52.0])


def test_unadjust_no_events_is_identity():
    eod = pd.DataFrame({"trade_date": [date(2025, 1, 1)], "close": [100.0]})
    out = unadjust_eod_series(eod, [])
    assert out["close"].tolist() == [100.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.autoresearch.etf_v3_eval.phase_2'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/adjustment_adapter.py
"""§10 single-convention adjustment adapter.

Phase 2 reads minute bars unadjusted (Kite default) and explicitly unadjusts the
EOD comparison series so reconciliation under §13 measures real divergence, not
mixed-convention ghosts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class AdjustmentEvent:
    symbol: str
    event_date: date
    kind: str   # "split" | "bonus" | "dividend"
    ratio: float   # split: post-split shares per pre-split (e.g. 2.0 for 2-for-1)


def unadjust_eod_series(eod: pd.DataFrame, events: Iterable[AdjustmentEvent]) -> pd.DataFrame:
    """Convert auto-adjusted EOD closes to unadjusted by multiplying pre-event
    rows by the event ratio (cumulative if multiple events).
    """
    df = eod.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for ev in events:
        if ev.kind in ("split", "bonus"):
            mask = df["trade_date"] < ev.event_date
            df.loc[mask, "close"] = df.loc[mask, "close"] * ev.ratio
    return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/__init__.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/adjustment_adapter.py \
        pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py
git commit -m "feat(v3-eval-p2): §10 adjustment-mode adapter (caveat fix)"
```

---

### Task 2: Re-run §13 reconciliation under adjustment adapter

**Why:** Caveat 1 in §17 audit. Show strict §13 (≤0.5% max delta) passes once both series share the same convention.

**Files:**
- Modify: `pipeline/autoresearch/etf_v3_eval/run_reconciliation.py` (read corp-action events from `pipeline/data/earnings_calendar/history.parquet` filtered to `kind in ("split","bonus")`, apply `unadjust_eod_series` to `eod_sample`, re-run, rewrite report)
- Out: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/reconciliation_strict.json`

- [ ] **Step 1: Inspect available corp-action events for the 5 sample tickers in window**

Run:
```bash
python -X utf8 -c "
import pandas as pd
from datetime import date
df = pd.read_parquet('pipeline/data/earnings_calendar/history.parquet')
df['event_date'] = pd.to_datetime(df['event_date']).dt.date
mask = (df['symbol'].isin(['ABB','ACC','ADANIENT','ABFRL','ABBOTINDIA'])
        & (df['event_date'] >= date(2026,2,26))
        & (df['event_date'] <= date(2026,4,23)))
print(df[mask][['symbol','event_date','kind','agenda_raw']].to_string())
"
```
Expected: list of events. If splits/bonuses present, log them. If only dividends/results, the strict failures may be from another cause — investigate before adapter step.

- [ ] **Step 2: Write a small test for the run_reconciliation adjustment hook**

Add to `pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py`:

```python
def test_eod_loader_calls_unadjuster(monkeypatch, tmp_path):
    """The run_reconciliation EOD loader, when an adjustment-event source is
    supplied, applies unadjust_eod_series to each ticker frame before merge."""
    from pipeline.autoresearch.etf_v3_eval import run_reconciliation as rr
    import pandas as pd
    from datetime import date

    csv = tmp_path / "X.csv"
    pd.DataFrame({"Date": ["2025-06-14","2025-06-15"], "Close":[100.0, 50.0]}).to_csv(csv, index=False)
    monkeypatch.setattr(rr, "EOD_DIR", tmp_path)

    events_by_ticker = {"X": [AdjustmentEvent("X", date(2025,6,15), "split", 2.0)]}
    out = rr.load_eod_for_tickers(["X"], events_by_ticker=events_by_ticker)
    assert out.loc[out["trade_date"] == date(2025,6,14), "close"].iloc[0] == 200.0
```

(Imports `AdjustmentEvent` from `phase_2.adjustment_adapter`.)

- [ ] **Step 3: Run test to verify it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py::test_eod_loader_calls_unadjuster -v`
Expected: TypeError on `events_by_ticker=` kwarg.

- [ ] **Step 4: Modify `run_reconciliation.py` to accept and apply adjustment events**

Edit `pipeline/autoresearch/etf_v3_eval/run_reconciliation.py`:

```python
# Add to imports:
from pipeline.autoresearch.etf_v3_eval.phase_2.adjustment_adapter import (
    AdjustmentEvent,
    unadjust_eod_series,
)

# Replace load_eod_for_tickers signature/body:
def load_eod_for_tickers(
    tickers: list[str],
    events_by_ticker: dict[str, list[AdjustmentEvent]] | None = None,
) -> pd.DataFrame:
    events_by_ticker = events_by_ticker or {}
    frames = []
    for t in tickers:
        path = EOD_DIR / f"{t}.csv"
        if not path.exists():
            logger.warning("EOD CSV missing for %s at %s", t, path)
            continue
        df = pd.read_csv(path).rename(columns={"Date": "trade_date", "Close": "close"})
        df["ticker"] = t
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df = df[["ticker", "trade_date", "close"]]
        if t in events_by_ticker:
            df = unadjust_eod_series(df, events_by_ticker[t])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ticker","trade_date","close"])
```

Add a `_load_corp_actions(tickers)` helper that reads `pipeline/data/earnings_calendar/history.parquet`, filters to `kind in ("split","bonus")`, and returns `dict[str, list[AdjustmentEvent]]`. For dividend events, treat ratio = `1.0 - dividend_pct` (need agenda_raw parser; if not present, skip and log as `dividend_unparsed`).

In `main()`, wire: `events = _load_corp_actions(SAMPLE_TICKERS); eod_sample = load_eod_for_tickers(SAMPLE_TICKERS, events_by_ticker=events)`.

Change OUT path to `Path("pipeline/data/research/etf_v3_evaluation/phase_2_backtest/reconciliation_strict.json")`.

- [ ] **Step 5: Run test, then run the strict reconciliation**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py -v
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.run_reconciliation
```

Expected: tests pass; strict reconciliation report shows `strict_pass=true` (rows_above_threshold=0) OR documents which residual mismatches remain (e.g. dividend events not parsed). If still failing, write the residual cause into the report `note` field — DO NOT fudge thresholds (§0.3).

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/run_reconciliation.py \
        pipeline/tests/test_etf_v3_eval/test_adjustment_adapter.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/reconciliation_strict.json
git commit -m "fix(v3-eval-p2): §13 strict reconciliation under single adjustment convention"
```

---

### Task 3: Wire bulk/news/earnings to canonical paths

**Why:** Caveat 2 in §17 audit — bulk/news/earnings frames were empty in Phase 1 because `run_contamination_map.py` defaults pointed at non-existent paths. Real canonical paths confirmed:
- bulk: `pipeline/data/bulk_deals/<date>.parquet` (already wired; window pre-2026-04-24 is genuinely empty per `reference_nse_bulk_deals_history_unavailable.md`)
- insider: `pipeline/data/insider_trades/<YYYY-MM>.parquet` (already wired, 95 hits)
- news: `pipeline/data/news_events_history.json` (list of dicts with `matched_stocks`, `published`)
- earnings: `pipeline/data/earnings_calendar/history.parquet` (cols: symbol, event_date, kind, ...)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/canonical_event_paths.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_canonical_event_paths.py`
- Modify: `pipeline/autoresearch/etf_v3_eval/run_contamination_map.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_canonical_event_paths.py
import json
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.canonical_event_paths import (
    load_news_events_history,
    load_earnings_history,
)


def test_load_news_events_history_emits_per_ticker_per_date(tmp_path):
    src = tmp_path / "news.json"
    src.write_text(json.dumps([
        {"matched_stocks": ["RELIANCE","TCS"], "published": "Tue, 23 Apr 2026 13:26:31 +0530"},
        {"matched_stocks": ["RELIANCE"],       "published": "Wed, 24 Apr 2026 09:00:00 +0530"},
        {"matched_stocks": [],                 "published": "Thu, 25 Apr 2026 10:00:00 +0530"},
    ]), encoding="utf-8")
    out = load_news_events_history(src)
    assert set(out.columns) == {"ticker","trade_date"}
    assert len(out) == 3
    assert (out["ticker"] == "RELIANCE").sum() == 2
    assert out[out["ticker"] == "TCS"]["trade_date"].iloc[0] == date(2026,4,23)


def test_load_earnings_history_renames_to_canonical(tmp_path):
    src = tmp_path / "earnings.parquet"
    pd.DataFrame({
        "symbol":["ABB"], "event_date":[date(2026,4,21)], "kind":["results"],
        "has_dividend":[False], "has_fundraise":[False], "agenda_raw":["x"], "asof":[date(2026,4,25)],
    }).to_parquet(src)
    out = load_earnings_history(src)
    assert {"ticker","trade_date","kind"}.issubset(out.columns)
    assert out["ticker"].iloc[0] == "ABB"
    assert out["trade_date"].iloc[0] == date(2026,4,21)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_canonical_event_paths.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement loaders**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/canonical_event_paths.py
"""Loaders for canonical event-channel paths used by §14 contamination map.

These wrap the actual on-disk locations used by the live pipeline:
- News:     pipeline/data/news_events_history.json (list of {matched_stocks, published, ...})
- Earnings: pipeline/data/earnings_calendar/history.parquet (symbol, event_date, kind, ...)
"""
from __future__ import annotations

import json
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

NEWS_HISTORY_PATH = Path("pipeline/data/news_events_history.json")
EARNINGS_HISTORY_PATH = Path("pipeline/data/earnings_calendar/history.parquet")


def _parse_rfc2822_to_date(s: str) -> date | None:
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        return None


def load_news_events_history(path: Path = NEWS_HISTORY_PATH) -> pd.DataFrame:
    """Explode news_events_history.json to one row per (ticker, trade_date)."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "trade_date"])
    items = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for it in items:
        d = _parse_rfc2822_to_date(it.get("published", ""))
        if d is None:
            continue
        for sym in it.get("matched_stocks", []) or []:
            rows.append({"ticker": str(sym).upper(), "trade_date": d})
    return pd.DataFrame(rows, columns=["ticker", "trade_date"])


def load_earnings_history(path: Path = EARNINGS_HISTORY_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "trade_date", "kind"])
    df = pd.read_parquet(path)
    df = df.rename(columns={"symbol": "ticker", "event_date": "trade_date"})
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    keep = ["ticker", "trade_date"] + [c for c in ("kind", "has_dividend", "has_fundraise") if c in df.columns]
    return df[keep]
```

- [ ] **Step 4: Wire run_contamination_map to use canonical loaders**

Edit `pipeline/autoresearch/etf_v3_eval/run_contamination_map.py`:

```python
# Replace top-level path constants and event-frame loading in main():
from pipeline.autoresearch.etf_v3_eval.phase_2.canonical_event_paths import (
    load_news_events_history,
    load_earnings_history,
    NEWS_HISTORY_PATH,
    EARNINGS_HISTORY_PATH,
)

# In main(), replace the news/earnings loads:
news = _normalize_event_frame(load_news_events_history(NEWS_HISTORY_PATH), None, None)
earnings = _normalize_event_frame(load_earnings_history(EARNINGS_HISTORY_PATH), None, None)

# Also change OUT path to Phase 2 location:
OUT = Path("pipeline/data/research/etf_v3_evaluation/phase_2_backtest/contamination_map_full.json")
```

- [ ] **Step 5: Run unit tests + re-run map + verify channel coverage**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_canonical_event_paths.py -v
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.run_contamination_map
python -X utf8 -c "
import json
m = json.load(open('pipeline/data/research/etf_v3_evaluation/phase_2_backtest/contamination_map_full.json'))
hits = {'bulk':0,'insider':0,'news':0,'earnings':0}
for t,d in m.items():
    for dt,ch in d.items():
        for k,v in ch.items():
            if v: hits[k] = hits.get(k,0) + 1
print(hits)
"
```
Expected: insider hits ≈ 95 (unchanged), news hits > 0, earnings hits > 0, bulk hits 0 (genuinely empty pre-2026-04-24, per `reference_nse_bulk_deals_history_unavailable.md` — log this in the report).

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/canonical_event_paths.py \
        pipeline/tests/test_etf_v3_eval/test_canonical_event_paths.py \
        pipeline/autoresearch/etf_v3_eval/run_contamination_map.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/contamination_map_full.json
git commit -m "fix(v3-eval-p2): §14 wire news+earnings to canonical paths (caveat fix)"
```

---

### Task 4: Resolve or document 4 alias gaps

**Why:** Caveat 3 in §17 audit. The 4 unresolved tickers (L&TFH, LTIM, MCDOWELL-N, ZOMATO) failed Phase 1 with "no instrument_token". Need to either resolve them via the alias registry or formally exclude them with attribution evidence.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/alias_resolver.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_alias_resolver.py`
- Out: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/aliases_resolution.md`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_alias_resolver.py
from pipeline.autoresearch.etf_v3_eval.phase_2.alias_resolver import (
    resolve_alias,
    KNOWN_ALIASES,
)


def test_known_aliases_present():
    """The 4 Phase 1 fail tickers are in the alias registry with explicit
    resolve-to symbol or NotTradable reason."""
    assert "L&TFH" in KNOWN_ALIASES
    assert "LTIM" in KNOWN_ALIASES
    assert "MCDOWELL-N" in KNOWN_ALIASES
    assert "ZOMATO" in KNOWN_ALIASES


def test_resolve_alias_returns_modern_symbol():
    assert resolve_alias("L&TFH") == "LTFH"   # name change
    assert resolve_alias("LTIM") == "LTIM"    # listed under same symbol; needs rescue
    assert resolve_alias("ZOMATO") == "ETERNAL"   # 2026 rebrand
    assert resolve_alias("MCDOWELL-N") == "UNITDSPR"  # delisting / merger lineage
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_alias_resolver.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement resolver — first verify mappings against truth source**

Read `memory/reference_pit_ticker_list.md` and `docs/superpowers/specs/tickers list .xlsx` for canonical name-change history. Confirm or correct each mapping. If a ticker truly cannot be resolved (e.g. delisted with no successor), set its value to `None` and document with reason in the resolution doc.

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/alias_resolver.py
"""Phase 2 alias resolver — close the 4 alias gaps from Phase 1 §17 caveat 3.

Truth source: docs/superpowers/specs/tickers list .xlsx + memory/reference_pit_ticker_list.md.
Each entry MUST cite the historical event in `aliases_resolution.md`.
"""
from __future__ import annotations

# value=None ⇒ documented exclusion (delisted with no tradable successor in window)
KNOWN_ALIASES: dict[str, str | None] = {
    # Phase 1 unresolved (verify each against tickers list .xlsx before committing)
    "L&TFH": "LTFH",         # symbol normalised — "&" stripped in modern Kite token list
    "LTIM": "LTIM",          # symbol unchanged but instrument_token regenerated post-LTIM-merger
    "ZOMATO": "ETERNAL",     # Eternal Limited rebrand 2026 (Zomato Ltd → Eternal Ltd)
    "MCDOWELL-N": "UNITDSPR",   # United Spirits absorbed McDowell N portfolio
}


def resolve_alias(ticker: str) -> str | None:
    """Return modern tradable symbol or None if delisted-without-successor."""
    return KNOWN_ALIASES.get(ticker, ticker)
```

- [ ] **Step 4: Run the test, then re-attempt Kite backfill for the 4 tickers**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_alias_resolver.py -v
```
Expected: PASS.

Then re-attempt backfill for the 4 (use Phase 1 orchestrator with overridden ticker list resolved through `resolve_alias`):

```bash
python -X utf8 -c "
from pipeline.autoresearch.etf_v3_eval.build_extended_replay import backfill_one
from pipeline.autoresearch.etf_v3_eval.phase_2.alias_resolver import resolve_alias, KNOWN_ALIASES
from pipeline.kite_auth import get_kite_client
kite = get_kite_client()
for t in KNOWN_ALIASES:
    resolved = resolve_alias(t)
    if resolved is None:
        print(f'{t}: documented exclusion'); continue
    df = backfill_one(kite, resolved)
    print(f'{t} -> {resolved}: {len(df)} rows')
"
```

If resolved tickers backfill cleanly, append to the v0.2 parquet OR write a separate `intraday_break_replay_60d_v0.2_minute_bars_aliased.parquet` and union them at read time (Phase 2 orchestrator handles union). If a resolved symbol still fails, mark it as documented exclusion in the resolution doc.

- [ ] **Step 5: Write resolution doc**

Create `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/aliases_resolution.md`:

```markdown
# Phase 1 → Phase 2 Alias Resolution

Source: `tickers list .xlsx`, `reference_pit_ticker_list.md`.

| Original | Resolved | Status | Citation | Outcome |
|---|---|---|---|---|
| L&TFH | LTFH | resolved | NSE symbol change 2025-XX-XX | <N rows backfilled> |
| LTIM | LTIM | resolved | instrument_token regenerated post-merger; alias_resolver re-fetched | <N rows> |
| ZOMATO | ETERNAL | resolved | Eternal Ltd rebrand 2026 | <N rows> |
| MCDOWELL-N | UNITDSPR | resolved-with-caveat | UNITDSPR is the surviving lineage entity; the underlying business overlap is partial | <N rows> |

Effective Phase 2 universe: <143 + N_resolved> tickers.
```

Fill in actual N's after backfill step.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/alias_resolver.py \
        pipeline/tests/test_etf_v3_eval/test_alias_resolver.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/aliases_resolution.md \
        pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars_aliased.parquet
git commit -m "fix(v3-eval-p2): resolve 4 Phase 1 alias gaps (caveat 3)"
```

---

## Section 1 — Walk-forward grid (§6.2 + §13A)

### Task 5: §13A.1 per-run manifest extension

**Why:** Phase 1 wrote a single dataset manifest. Phase 2 emits multiple walk-forward runs (3 lookbacks × 2 universes = 6 baseline runs, + slippage + fragility neighborhoods); each MUST emit its own §13A.1 manifest with `run_id`, `git_commit_hash`, `data_file_sha256_manifest`, `random_seed`, `cost_model_version`.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/manifest.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_p2_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_p2_manifest.py
import json
from pathlib import Path

import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import (
    write_run_manifest,
    RunConfig,
)


def test_write_run_manifest_emits_required_fields(tmp_path):
    cfg = RunConfig(
        run_id="wf_lb756_u126_seed0",
        strategy_version="v3-CURATED-30",
        cost_model_version="cm_2026-04-26_v1",
        random_seed=0,
        lookback_days=756,
        refit_interval_days=5,
        n_iterations=2000,
        universe="126",
        feature_set="curated",
    )
    inputs = {"replay_parquet": tmp_path / "x.parquet"}
    (tmp_path / "x.parquet").write_bytes(b"hello")
    out_path = tmp_path / "manifest.json"
    write_run_manifest(out_path, cfg, input_files=inputs)
    m = json.loads(out_path.read_text(encoding="utf-8"))
    for required in (
        "run_id","strategy_version","git_commit_hash","config_hash",
        "data_file_sha256_manifest","random_seed","cost_model_version",
        "report_generated_at","lookback_days","refit_interval_days","n_iterations",
        "universe","feature_set",
    ):
        assert required in m, f"missing {required}"
    assert m["data_file_sha256_manifest"]["replay_parquet"].startswith(
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"  # sha256("hello")
    )
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_p2_manifest.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/manifest.py
"""§13A.1 per-run manifest writer for Phase 2 backtest runs.

Extends pipeline/autoresearch/etf_v3_eval/manifest.py (Phase 1 dataset manifest)
with strategy_version, config_hash, lookback_days, n_iterations, universe.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    strategy_version: str
    cost_model_version: str
    random_seed: int
    lookback_days: int
    refit_interval_days: int
    n_iterations: int
    universe: str
    feature_set: str


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _config_hash(cfg: RunConfig) -> str:
    blob = json.dumps(asdict(cfg), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def write_run_manifest(
    path: Path,
    cfg: RunConfig,
    input_files: Mapping[str, Path],
) -> None:
    manifest = {
        **asdict(cfg),
        "git_commit_hash": _git_commit_hash(),
        "config_hash": _config_hash(cfg),
        "data_file_sha256_manifest": {
            name: _file_sha256(p) for name, p in input_files.items()
        },
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_p2_manifest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/manifest.py \
        pipeline/tests/test_etf_v3_eval/test_p2_manifest.py
git commit -m "feat(v3-eval-p2): §13A.1 per-run manifest writer"
```

---

### Task 6: Walk-forward runner (lookback × universe × cadence)

**Why:** §6.2 requires 3 lookbacks (756/1200/1236), refit cadence 5d, 2000 iterations per window, **purged walk-forward per §10**. The existing `etf_v3_rolling_refit.py` does the rolling refit but lacks §10.3 purging (5-day embargo + overlap purge). Wrap it with a §10-compliant runner.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/walk_forward_runner.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_walk_forward_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_walk_forward_runner.py
from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.walk_forward_runner import (
    purged_train_dates,
    PurgeConfig,
)


def test_purged_train_dates_drops_embargo_window():
    """Train dates within ±embargo_days of test window must be dropped (§10.2)."""
    train = pd.DatetimeIndex(pd.date_range("2025-01-01", "2025-01-31", freq="D"))
    test_start = pd.Timestamp("2025-01-20")
    test_end = pd.Timestamp("2025-01-22")
    cfg = PurgeConfig(embargo_days=5)
    out = purged_train_dates(train, test_start, test_end, cfg)
    # Drops anything within [2025-01-15, 2025-01-27]
    assert pd.Timestamp("2025-01-14") in out
    assert pd.Timestamp("2025-01-15") not in out
    assert pd.Timestamp("2025-01-27") not in out
    assert pd.Timestamp("2025-01-28") in out


def test_purged_train_dates_overlap_holding_period():
    """Trades in train that close within test window must be purged (§10.3)."""
    train = pd.DatetimeIndex(pd.date_range("2025-01-01", "2025-01-31", freq="D"))
    test_start = pd.Timestamp("2025-01-20")
    test_end = pd.Timestamp("2025-01-22")
    cfg = PurgeConfig(embargo_days=0, holding_period_days=5)
    out = purged_train_dates(train, test_start, test_end, cfg)
    # Trade opened 2025-01-16 closes 2025-01-21 — overlaps test → dropped
    assert pd.Timestamp("2025-01-16") not in out
    assert pd.Timestamp("2025-01-15") in out  # closes 01-20 — inclusive boundary
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_walk_forward_runner.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement runner**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/walk_forward_runner.py
"""§10 purged walk-forward wrapper around etf_v3_rolling_refit.

The rolling refit module produces per-window predictions but does NOT enforce
the §10.3 purging (training rows whose holding-period overlaps the test window)
nor the §10.2 5-day embargo. This module supplies both as composable pieces and
provides a Phase 2 entry point that produces:
- per-run manifest (§13A.1)
- per-window weights JSON
- ledger of (date, signal, zone, train_window, test_window)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import RunConfig, write_run_manifest
from pipeline.autoresearch.etf_v3_rolling_refit import RollingRefitConfig, run_rolling_refit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeConfig:
    embargo_days: int = 5            # §10.2
    holding_period_days: int = 0     # §10.3 — 0 for next-day-direction strategy


def purged_train_dates(
    train_dates: pd.DatetimeIndex,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    cfg: PurgeConfig,
) -> pd.DatetimeIndex:
    """Drop training rows that overlap the test window per §10.2 + §10.3."""
    embargo_lo = test_start - pd.Timedelta(days=cfg.embargo_days)
    embargo_hi = test_end + pd.Timedelta(days=cfg.embargo_days)
    in_embargo = (train_dates >= embargo_lo) & (train_dates <= embargo_hi)
    if cfg.holding_period_days > 0:
        # A trade opened on date d closes on d + H. If close ∈ test window, purge d.
        close_dates = train_dates + pd.Timedelta(days=cfg.holding_period_days)
        overlaps = (close_dates >= test_start) & (close_dates <= test_end)
    else:
        overlaps = pd.Series(False, index=range(len(train_dates))).values
    keep = ~(in_embargo | overlaps)
    return train_dates[keep]


def run_walk_forward(
    cfg: RunConfig,
    out_dir: Path,
    purge: PurgeConfig = PurgeConfig(),
) -> dict:
    """Run a single (lookback, universe, feature_set) walk-forward and emit manifest."""
    rr_cfg = RollingRefitConfig(
        refit_interval_days=cfg.refit_interval_days,
        lookback_days=cfg.lookback_days,
        n_iterations=cfg.n_iterations,
        seed=cfg.random_seed,
        feature_set=cfg.feature_set,
    )
    result = run_rolling_refit(rr_cfg)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rolling_refit.json").write_text(
        pd.io.json.dumps(result, default_handler=str), encoding="utf-8"
    )
    write_run_manifest(
        out_dir / "manifest.json",
        cfg,
        input_files={
            "replay_parquet": Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet"),
            "etf_panel":      Path("pipeline/autoresearch/data/etf_v3_panel.parquet"),
        },
    )
    return result
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_walk_forward_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/walk_forward_runner.py \
        pipeline/tests/test_etf_v3_eval/test_walk_forward_runner.py
git commit -m "feat(v3-eval-p2): §10 purged walk-forward runner"
```

---

### Task 7: Replay extender — apply v3-zone gates to 273-ticker replay

**Why:** §6.5 universe sensitivity test requires Phase 2 marker analysis to run on BOTH universes. Existing `etf_v3_60d_zone_pnl.py` reads the v0.1 (126-ticker) replay; Phase 2 needs to point it at v0.2 (143-ticker) too.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/replay_extender.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_replay_extender.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_replay_extender.py
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.replay_extender import (
    aggregate_minute_to_event_returns,
)


def test_aggregate_minute_to_event_returns_emits_per_event_row(tmp_path):
    """For each (ticker, trade_date) in minute parquet, emit one event row with
    open_to_1430 return and open_to_close return."""
    df = pd.DataFrame({
        "ticker":["A"]*4,
        "trade_date":[date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 09:45",
            "2026-03-03 14:30", "2026-03-03 15:30",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100.0,101.0,103.0,104.0],
        "high":[101.0,102.0,104.0,105.0],
        "low":[99.0,100.0,102.0,103.0],
        "close":[101.0,102.0,104.0,105.0],
        "volume":[1000]*4,
    })
    out = aggregate_minute_to_event_returns(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ticker"] == "A"
    assert row["trade_date"] == date(2026,3,3)
    assert row["open_to_1430_pct"] == pytest.approx((104.0 - 100.0)/100.0)  # noqa
    assert row["open_to_close_pct"] == pytest.approx((105.0 - 100.0)/100.0)  # noqa
```

(Add `import pytest` at top.)

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_replay_extender.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/replay_extender.py
"""Convert v0.2 minute-bar parquet to event-level rows for marker decomposition.

Each (ticker, trade_date) becomes one event with:
- open_to_1430_pct (TIME_STOP convention)
- open_to_close_pct
- open_to_1530_pct (alias)
- intraday_high_pct, intraday_low_pct (for ATR/stop testing)
"""
from __future__ import annotations

from datetime import time

import pandas as pd


def aggregate_minute_to_event_returns(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate one row per (ticker, trade_date) with directional return columns."""
    df = minute_df.copy()
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")

    df["clock"] = df["timestamp"].dt.time
    df = df.sort_values(["ticker", "trade_date", "timestamp"])

    rows = []
    for (t, d), g in df.groupby(["ticker", "trade_date"], sort=False):
        g = g.reset_index(drop=True)
        first = g.iloc[0]
        last  = g.iloc[-1]
        open_px = float(first["open"])
        close_px = float(last["close"])
        bar_1430 = g[g["clock"] == time(14, 30)]
        time_stop_px = float(bar_1430.iloc[0]["close"]) if len(bar_1430) else close_px
        rows.append({
            "ticker": t,
            "trade_date": d,
            "open_px": open_px,
            "close_px": close_px,
            "time_stop_px": time_stop_px,
            "intraday_high": float(g["high"].max()),
            "intraday_low": float(g["low"].min()),
            "open_to_1430_pct": (time_stop_px - open_px) / open_px,
            "open_to_close_pct": (close_px - open_px) / open_px,
            "open_to_close_pct_alias_1530": (close_px - open_px) / open_px,
            "intraday_high_pct": (float(g["high"].max()) - open_px) / open_px,
            "intraday_low_pct":  (float(g["low"].min()) - open_px) / open_px,
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_replay_extender.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/replay_extender.py \
        pipeline/tests/test_etf_v3_eval/test_replay_extender.py
git commit -m "feat(v3-eval-p2): event-level aggregator from v0.2 minute bars"
```

---

## Section 2 — Marker decomposition (§6.3)

Each marker is a function `(events_df, signal_df, ...) -> events_df_with_marker_column`. Decomposition computes standalone P&L + incremental contribution + cluster-robust SE + permutation null + fragility per marker. We split 6 markers into 3 tasks.

### Task 8: Markers — Zone gate + Sector overlay

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/__init__.py` (empty)
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/zone_gate.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/sector_overlay.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_zone_gate.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_sector_overlay.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_marker_zone_gate.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.zone_gate import (
    apply_zone_gate,
    ZoneGateConfig,
)


def test_zone_gate_drops_neutral_band():
    """Events on dates whose v3 z-signal is within ±band σ of mean are dropped."""
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03"]).date,
        "ret": [0.01, 0.02, -0.03],
    })
    signals = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03"]).date,
        "signal_z": [0.1, 1.5, -1.5],   # 03-01 inside ±0.5σ → drop
    })
    out = apply_zone_gate(events, signals, ZoneGateConfig(band_sigma=0.5))
    assert set(out["trade_date"]) == {pd.Timestamp("2026-03-02").date(), pd.Timestamp("2026-03-03").date()}
```

```python
# pipeline/tests/test_etf_v3_eval/test_marker_sector_overlay.py
import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.sector_overlay import (
    apply_sector_overlay,
    NEUTRAL_DAY_WINNER_SECTORS,
)


def test_sector_overlay_keeps_only_winners():
    events = pd.DataFrame({
        "ticker": ["SBIN","TCS","NTPC","ASIANPAINT"],
        "ret":    [0.01, 0.02, -0.03, 0.04],
        "sector": ["PSU BANK","IT","ENERGY","FMCG"],
    })
    out = apply_sector_overlay(events, sectors=NEUTRAL_DAY_WINNER_SECTORS)
    assert set(out["ticker"]) == {"SBIN","NTPC"}
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_zone_gate.py pipeline/tests/test_etf_v3_eval/test_marker_sector_overlay.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement zone_gate.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/zone_gate.py
"""§6.3 marker: NEUTRAL band sweep at ±band_sigma σ around the signal mean.

Events whose date's v3 signal falls inside the band are gated OUT. The sweep
rolls band ∈ {0.25, 0.5, 1.0} per spec.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ZoneGateConfig:
    band_sigma: float = 0.5


def apply_zone_gate(
    events: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: ZoneGateConfig,
) -> pd.DataFrame:
    """Return events whose date's signal is OUTSIDE the ±band_sigma neutral band."""
    s = signals.copy()
    mu = float(s["signal_z"].mean())
    sd = float(s["signal_z"].std(ddof=0))
    lo, hi = mu - cfg.band_sigma * sd, mu + cfg.band_sigma * sd
    out_band = s[(s["signal_z"] < lo) | (s["signal_z"] > hi)]
    return events.merge(out_band[["trade_date"]], on="trade_date", how="inner")
```

- [ ] **Step 4: Implement sector_overlay.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/sector_overlay.py
"""§6.3 marker: restrict event basket to NEUTRAL-day winning sectors.

Empirical winners on v3-NEUTRAL days per Phase 0 catalog:
PSU BANK, BANK, PSE, ENERGY, INFRA, FIN SERVICE, REALTY, METAL, CONSR DURBL.
"""
from __future__ import annotations

import pandas as pd

NEUTRAL_DAY_WINNER_SECTORS: tuple[str, ...] = (
    "PSU BANK", "BANK", "PSE", "ENERGY", "INFRA",
    "FIN SERVICE", "REALTY", "METAL", "CONSR DURBL",
)


def apply_sector_overlay(events: pd.DataFrame, sectors: tuple[str, ...]) -> pd.DataFrame:
    if "sector" not in events.columns:
        raise ValueError("events frame must include 'sector' column")
    return events[events["sector"].isin(sectors)].reset_index(drop=True)
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_zone_gate.py pipeline/tests/test_etf_v3_eval/test_marker_sector_overlay.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/markers/__init__.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/markers/zone_gate.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/markers/sector_overlay.py \
        pipeline/tests/test_etf_v3_eval/test_marker_zone_gate.py \
        pipeline/tests/test_etf_v3_eval/test_marker_sector_overlay.py
git commit -m "feat(v3-eval-p2): §6.3 markers — zone gate + sector overlay"
```

---

### Task 9: Markers — Coef-delta + σ bucket

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/coef_delta.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/sigma_bucket.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_coef_delta.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_sigma_bucket.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_marker_coef_delta.py
import json
from pathlib import Path
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.coef_delta import (
    compute_weekly_delta_magnitude,
    flag_high_rotation_dates,
)


def test_compute_weekly_delta_magnitude():
    weights_a = {"E1": 0.5, "E2": 0.5}
    weights_b = {"E1": 0.6, "E2": 0.4}   # |delta| L2 = sqrt(0.01+0.01) = 0.1414
    mag = compute_weekly_delta_magnitude(weights_a, weights_b)
    assert mag == pytest.approx(0.1414, abs=1e-3)


def test_flag_high_rotation_dates_uses_p75_threshold():
    df = pd.DataFrame({
        "refit_anchor": pd.to_datetime(["2026-01-01","2026-01-08","2026-01-15","2026-01-22"]),
        "delta_mag":    [0.1, 0.2, 0.3, 0.9],
    })
    out = flag_high_rotation_dates(df, percentile=75)
    # P75 = 0.45 → only 0.9 row passes
    assert out["high_rotation"].tolist() == [False, False, False, True]
```

```python
# pipeline/tests/test_etf_v3_eval/test_marker_sigma_bucket.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.sigma_bucket import (
    bucket_event_sigma,
    SigmaBucket,
)


def test_bucket_event_sigma_assigns_correct_bucket():
    events = pd.DataFrame({"break_z": [2.1, 2.6, 3.6, 4.0, 1.5]})
    out = bucket_event_sigma(events)
    assert out["bucket"].tolist() == [
        SigmaBucket.MILD, SigmaBucket.RARE,
        SigmaBucket.EXTREME, SigmaBucket.EXTREME,
        SigmaBucket.SUB_THRESHOLD,
    ]
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_coef_delta.py pipeline/tests/test_etf_v3_eval/test_marker_sigma_bucket.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement coef_delta.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/coef_delta.py
"""§6.3 marker: week-over-week |Δweight| > P75 ⇒ "regime in transition" flag.

Rationale (Phase 0 catalog): 51.8 std-units rotation on 2025-12-30 and 37.2 on
2026-04-16 aligned with v3 zone shifts. Big ETF coefficient rotation is itself
a regime-change marker.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def compute_weekly_delta_magnitude(
    prev: Mapping[str, float],
    curr: Mapping[str, float],
) -> float:
    keys = set(prev) | set(curr)
    sq = sum((curr.get(k, 0.0) - prev.get(k, 0.0)) ** 2 for k in keys)
    return float(np.sqrt(sq))


def flag_high_rotation_dates(
    rotation_df: pd.DataFrame,
    percentile: float = 75.0,
) -> pd.DataFrame:
    """rotation_df: cols [refit_anchor, delta_mag]. Adds bool 'high_rotation'."""
    threshold = float(np.percentile(rotation_df["delta_mag"], percentile))
    out = rotation_df.copy()
    out["high_rotation"] = out["delta_mag"] > threshold
    out.attrs["threshold"] = threshold
    return out
```

- [ ] **Step 4: Implement sigma_bucket.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/sigma_bucket.py
"""§6.3 marker: extreme/rare/mild σ-bucket conditional.

Phase 0 catalog: σ buckets couple with regime — must NOT be evaluated as
regime-independent. This module assigns the bucket; downstream code stratifies
by regime × bucket.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class SigmaBucket(str, Enum):
    SUB_THRESHOLD = "sub_threshold"   # |z| < 2.0
    MILD = "mild"                     # 2.0 ≤ |z| < 2.5
    RARE = "rare"                     # 2.5 ≤ |z| < 3.5
    EXTREME = "extreme"               # |z| ≥ 3.5


def bucket_event_sigma(events: pd.DataFrame, z_col: str = "break_z") -> pd.DataFrame:
    abs_z = events[z_col].abs()
    out = events.copy()
    out["bucket"] = SigmaBucket.SUB_THRESHOLD
    out.loc[(abs_z >= 2.0) & (abs_z < 2.5), "bucket"] = SigmaBucket.MILD
    out.loc[(abs_z >= 2.5) & (abs_z < 3.5), "bucket"] = SigmaBucket.RARE
    out.loc[abs_z >= 3.5, "bucket"] = SigmaBucket.EXTREME
    return out
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_coef_delta.py pipeline/tests/test_etf_v3_eval/test_marker_sigma_bucket.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/markers/coef_delta.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/markers/sigma_bucket.py \
        pipeline/tests/test_etf_v3_eval/test_marker_coef_delta.py \
        pipeline/tests/test_etf_v3_eval/test_marker_sigma_bucket.py
git commit -m "feat(v3-eval-p2): §6.3 markers — coef-delta + σ bucket"
```

---

### Task 10: Markers — Regime transition + Exit-rule fixed

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/regime_transition.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/exit_rule.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_regime_transition.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_marker_exit_rule.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_marker_regime_transition.py
import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.regime_transition import (
    flag_regime_transitions,
)


def test_flag_regime_transitions_marks_change_dates():
    z = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03","2026-03-04"]).date,
        "zone": ["NEUTRAL","NEUTRAL","RISK-ON","RISK-ON"],
    })
    out = flag_regime_transitions(z)
    # First row has no prior, returns False; transition flagged on 03-03.
    assert out["transition"].tolist() == [False, False, True, False]
```

```python
# pipeline/tests/test_etf_v3_eval/test_marker_exit_rule.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.exit_rule import (
    apply_fixed_exit_rule,
    ExitRule,
)


def test_apply_fixed_exit_rule_uses_time_stop_pct():
    events = pd.DataFrame({
        "open_to_1430_pct":  [0.012, -0.020, 0.005],
        "open_to_close_pct": [0.020, -0.030, 0.010],
    })
    out = apply_fixed_exit_rule(events, ExitRule.TIME_STOP_1430)
    assert out["realized_pct"].tolist() == [0.012, -0.020, 0.005]
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_regime_transition.py pipeline/tests/test_etf_v3_eval/test_marker_exit_rule.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement regime_transition.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/regime_transition.py
"""§6.3 marker: zone change yesterday → today flag.

Rationale: regime transitions historically carry asymmetric P&L. Flag the day's
events as in-transition when the v3 zone differs from the previous trading day's.
"""
from __future__ import annotations

import pandas as pd


def flag_regime_transitions(zones: pd.DataFrame) -> pd.DataFrame:
    """zones: cols [trade_date, zone]. Returns same + bool 'transition'."""
    df = zones.sort_values("trade_date").reset_index(drop=True).copy()
    df["transition"] = df["zone"] != df["zone"].shift(1)
    df.loc[0, "transition"] = False  # first row has no prior
    return df
```

- [ ] **Step 4: Implement exit_rule.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/markers/exit_rule.py
"""§6.3 marker: held-fixed exit rule sanity check.

Phase 2 holds the exit rule fixed at TIME_STOP 14:30 unless explicitly testing
alternatives. This module exposes the swap point so a single call site picks
the realized return column.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class ExitRule(str, Enum):
    TIME_STOP_1430 = "time_stop_1430"
    CLOSE          = "close"


def apply_fixed_exit_rule(events: pd.DataFrame, rule: ExitRule) -> pd.DataFrame:
    out = events.copy()
    if rule == ExitRule.TIME_STOP_1430:
        out["realized_pct"] = events["open_to_1430_pct"]
    elif rule == ExitRule.CLOSE:
        out["realized_pct"] = events["open_to_close_pct"]
    else:
        raise ValueError(f"unknown exit rule {rule}")
    return out
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_marker_regime_transition.py pipeline/tests/test_etf_v3_eval/test_marker_exit_rule.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/markers/regime_transition.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/markers/exit_rule.py \
        pipeline/tests/test_etf_v3_eval/test_marker_regime_transition.py \
        pipeline/tests/test_etf_v3_eval/test_marker_exit_rule.py
git commit -m "feat(v3-eval-p2): §6.3 markers — regime transition + exit rule"
```

---

## Section 3 — Statistical battery

### Task 11: Cluster-robust SE + permutation null

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/__init__.py` (empty)
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/cluster_robust_se.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/permutation_null.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_cluster_robust_se.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_permutation_null.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_cluster_robust_se.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.cluster_robust_se import (
    cluster_robust_mean_se,
)


def test_cluster_robust_se_collapses_within_cluster():
    """If all observations within a cluster are identical, SE depends on n_clusters,
    not n_observations. statsmodels reference: 100 obs in 5 clusters of 20 should
    have SE ≈ between-cluster SE / sqrt(5)."""
    np.random.seed(0)
    n_clusters, per = 5, 20
    cluster_means = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    rets = np.repeat(cluster_means, per)
    clusters = np.repeat(np.arange(n_clusters), per)
    out = cluster_robust_mean_se(rets, clusters)
    # mean = 3.0; cluster SE = std(cluster_means, ddof=1)/sqrt(5)
    expected_se = np.std(cluster_means, ddof=1) / np.sqrt(n_clusters)
    assert out["mean"] == pytest.approx(3.0)
    assert out["se"] == pytest.approx(expected_se, rel=1e-2)
    assert out["n_clusters"] == 5
    assert out["n_obs"] == 100
```

```python
# pipeline/tests/test_etf_v3_eval/test_permutation_null.py
import numpy as np
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.permutation_null import (
    permutation_test_mean,
)


def test_permutation_null_detects_real_signal():
    np.random.seed(0)
    pos = np.random.normal(loc=0.005, scale=0.01, size=200)
    neg = np.random.normal(loc=-0.005, scale=0.01, size=200)
    obs = pos.mean() - neg.mean()
    rng = np.random.default_rng(0)
    p = permutation_test_mean(pos, neg, n_permutations=2000, rng=rng)
    assert p < 0.01


def test_permutation_null_no_signal_returns_p_near_05():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.01, 200)
    b = rng.normal(0, 0.01, 200)
    p = permutation_test_mean(a, b, n_permutations=2000, rng=np.random.default_rng(1))
    assert 0.2 < p < 0.8
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_cluster_robust_se.py pipeline/tests/test_etf_v3_eval/test_permutation_null.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement cluster_robust_se.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/stats/cluster_robust_se.py
"""§9.3 / §11B: cluster-robust SE for mean-return estimates.

Cluster level = trade_date (per Phase 0 catalog: same-day events share a regime
and are not independent observations).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm


def cluster_robust_mean_se(
    returns: Sequence[float],
    clusters: Sequence,
) -> dict:
    """Regress returns on intercept-only with cluster-robust SE.

    Returns dict {mean, se, t, p, n_obs, n_clusters}.
    """
    y = np.asarray(returns, dtype=float)
    X = np.ones((len(y), 1))
    c = pd.Series(clusters)
    model = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": c.values})
    return {
        "mean": float(model.params[0]),
        "se": float(model.bse[0]),
        "t": float(model.tvalues[0]),
        "p": float(model.pvalues[0]),
        "n_obs": int(len(y)),
        "n_clusters": int(c.nunique()),
    }
```

- [ ] **Step 4: Implement permutation_null.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/stats/permutation_null.py
"""§9B.2: permutation / reality-check tests with n ≥ 10,000 default.

Two-sample mean-difference shuffle preserving total event count. Use this for
strategy-vs-naive-benchmark comparisons.
"""
from __future__ import annotations

import numpy as np


def permutation_test_mean(
    a: np.ndarray,
    b: np.ndarray,
    n_permutations: int = 10_000,
    rng: np.random.Generator | None = None,
) -> float:
    """Two-sided p-value: P(|shuffled mean diff| ≥ |observed mean diff|)."""
    rng = rng or np.random.default_rng(0)
    pooled = np.concatenate([a, b])
    n_a = len(a)
    obs = abs(a.mean() - b.mean())
    count_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(pooled)
        diff = abs(pooled[:n_a].mean() - pooled[n_a:].mean())
        if diff >= obs:
            count_extreme += 1
    return (count_extreme + 1) / (n_permutations + 1)
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_cluster_robust_se.py pipeline/tests/test_etf_v3_eval/test_permutation_null.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/stats/__init__.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/stats/cluster_robust_se.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/stats/permutation_null.py \
        pipeline/tests/test_etf_v3_eval/test_cluster_robust_se.py \
        pipeline/tests/test_etf_v3_eval/test_permutation_null.py
git commit -m "feat(v3-eval-p2): §9 cluster-robust SE + §9B.2 permutation null"
```

---

### Task 12: §9A fragility + §9B.1 naive benchmarks

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/fragility.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/naive_benchmarks.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_fragility.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_naive_benchmarks.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_fragility.py
from pipeline.autoresearch.etf_v3_eval.phase_2.stats.fragility import (
    evaluate_fragility,
    FragilityVerdict,
)


def test_fragility_passes_with_robust_neighborhood():
    chosen_pnl = 0.10
    neighborhood_pnls = [0.09, 0.08, 0.11, 0.10, 0.07,
                         0.09, 0.10, 0.08, 0.11, 0.09,
                         0.10, 0.08, 0.07, 0.09, 0.10,
                         0.08, 0.11, 0.09, 0.10, 0.07,
                         0.08, 0.09, 0.10, 0.07, 0.11]
    chosen_sharpe = 1.0
    neighborhood_sharpes = [0.9]*25
    v = evaluate_fragility(chosen_pnl, neighborhood_pnls, chosen_sharpe, neighborhood_sharpes)
    assert v.verdict == FragilityVerdict.STABLE
    assert v.pct_positive >= 0.6
    assert v.median_sharpe_ratio >= 0.7


def test_fragility_fails_with_sign_flipping_neighbors():
    chosen_pnl = 0.10
    flipping = [0.10, -0.10, 0.10, -0.10] * 7
    v = evaluate_fragility(chosen_pnl, flipping, 1.0, [0.5]*28)
    assert v.verdict == FragilityVerdict.FRAGILE
```

```python
# pipeline/tests/test_etf_v3_eval/test_naive_benchmarks.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.naive_benchmarks import (
    random_direction,
    always_long,
    always_short,
    never_trade,
)


def test_always_long_returns_event_returns_unchanged():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = always_long(events)
    assert out["benchmark_pnl"].tolist() == [0.01, -0.02, 0.03]


def test_always_short_inverts_returns():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = always_short(events)
    assert out["benchmark_pnl"].tolist() == [-0.01, 0.02, -0.03]


def test_never_trade_returns_zero():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = never_trade(events)
    assert out["benchmark_pnl"].tolist() == [0.0, 0.0, 0.0]


def test_random_direction_uses_seeded_rng():
    rng = np.random.default_rng(42)
    events = pd.DataFrame({"realized_pct": np.arange(100) * 0.001})
    out_a = random_direction(events, rng=np.random.default_rng(42))
    out_b = random_direction(events, rng=np.random.default_rng(42))
    assert out_a["benchmark_pnl"].equals(out_b["benchmark_pnl"])
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_fragility.py pipeline/tests/test_etf_v3_eval/test_naive_benchmarks.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement fragility.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/stats/fragility.py
"""§9A.2 — three stability conditions for parameter neighborhood.

Verdict STABLE iff ALL three hold:
- ≥ 60% of neighbors have positive net P&L
- median neighbor Sharpe ≥ 70% of chosen-point Sharpe
- no majority of neighbors exhibit opposite-direction inversion
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import numpy as np


class FragilityVerdict(str, Enum):
    STABLE = "stable"
    FRAGILE = "fragile"


@dataclass(frozen=True)
class FragilityReport:
    verdict: FragilityVerdict
    pct_positive: float
    median_sharpe_ratio: float
    pct_inverted: float


def evaluate_fragility(
    chosen_pnl: float,
    neighbor_pnls: Sequence[float],
    chosen_sharpe: float,
    neighbor_sharpes: Sequence[float],
) -> FragilityReport:
    n_pnls = np.asarray(neighbor_pnls, dtype=float)
    n_sh   = np.asarray(neighbor_sharpes, dtype=float)
    pct_positive = float((n_pnls > 0).mean())
    median_sharpe_ratio = float(np.median(n_sh) / chosen_sharpe) if chosen_sharpe else 0.0
    pct_inverted = float((np.sign(n_pnls) != np.sign(chosen_pnl)).mean())
    cond_a = pct_positive >= 0.60
    cond_b = median_sharpe_ratio >= 0.70
    cond_c = pct_inverted < 0.50
    verdict = FragilityVerdict.STABLE if (cond_a and cond_b and cond_c) else FragilityVerdict.FRAGILE
    return FragilityReport(verdict, pct_positive, median_sharpe_ratio, pct_inverted)
```

- [ ] **Step 4: Implement naive_benchmarks.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/stats/naive_benchmarks.py
"""§9B.1 — naive comparators required for every strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd


def always_long(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["benchmark_pnl"] = events["realized_pct"]
    return out


def always_short(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["benchmark_pnl"] = -events["realized_pct"]
    return out


def never_trade(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["benchmark_pnl"] = 0.0
    return out


def random_direction(events: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    out = events.copy()
    sign = rng.choice([-1.0, 1.0], size=len(events))
    out["benchmark_pnl"] = events["realized_pct"].to_numpy() * sign
    return out
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_fragility.py pipeline/tests/test_etf_v3_eval/test_naive_benchmarks.py -v`
Expected: PASS, 6 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/stats/fragility.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/stats/naive_benchmarks.py \
        pipeline/tests/test_etf_v3_eval/test_fragility.py \
        pipeline/tests/test_etf_v3_eval/test_naive_benchmarks.py
git commit -m "feat(v3-eval-p2): §9A fragility + §9B.1 naive benchmarks"
```

---

### Task 13: §11B alpha-after-beta regression

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/stats/alpha_after_beta.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_alpha_after_beta.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_alpha_after_beta.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.alpha_after_beta import (
    regress_against_benchmark,
)


def test_pure_benchmark_returns_zero_alpha_high_beta():
    rng = np.random.default_rng(0)
    nifty = rng.normal(0, 0.01, 500)
    strategy = nifty * 1.5
    out = regress_against_benchmark(strategy, nifty)
    assert out["alpha_annualized"] == pytest.approx(0.0, abs=1e-3)
    assert out["beta"] == pytest.approx(1.5, rel=1e-3)
    assert out["r_squared"] > 0.99


def test_residual_sharpe_independent_of_market():
    rng = np.random.default_rng(0)
    nifty = rng.normal(0, 0.01, 500)
    alpha_signal = rng.normal(0.001, 0.005, 500)
    strategy = 0.4 * nifty + alpha_signal
    out = regress_against_benchmark(strategy, nifty)
    assert abs(out["beta"] - 0.4) < 0.05
    assert out["residual_sharpe"] != 0.0
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_alpha_after_beta.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/stats/alpha_after_beta.py
"""§11B alpha-after-beta — daily-return regression of strategy on NIFTY.

Reports: beta (slope), alpha_annualized (intercept × 252), r_squared,
residual_sharpe (Sharpe of residuals after stripping β·NIFTY).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import statsmodels.api as sm


def regress_against_benchmark(
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    annualization: int = 252,
) -> dict:
    y = np.asarray(strategy_returns, dtype=float)
    x = np.asarray(benchmark_returns, dtype=float)
    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()
    intercept, beta = float(model.params[0]), float(model.params[1])
    residuals = y - (intercept + beta * x)
    res_mean, res_sd = float(residuals.mean()), float(residuals.std(ddof=1) or 1e-12)
    return {
        "alpha_annualized": intercept * annualization,
        "beta": beta,
        "r_squared": float(model.rsquared),
        "residual_sharpe": (res_mean / res_sd) * np.sqrt(annualization),
        "n_obs": int(len(y)),
    }
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_alpha_after_beta.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/stats/alpha_after_beta.py \
        pipeline/tests/test_etf_v3_eval/test_alpha_after_beta.py
git commit -m "feat(v3-eval-p2): §11B alpha-after-beta regression"
```

---

## Section 4 — Backtest-Spec gates

### Task 14: §1–§3 slippage grid

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/slippage_grid.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_slippage_grid.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_slippage_grid.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.slippage_grid import (
    SlippageLevel,
    apply_slippage,
    evaluate_pass_fail,
)


def test_slippage_s1_subtracts_30_bps_round_trip():
    """S1 = base + 10 bps per side ⇒ ~30 bps total round-trip cost."""
    events = pd.DataFrame({"gross_pnl_pct": [0.0050, -0.0040, 0.0010]})
    out = apply_slippage(events, SlippageLevel.S1)
    # Each leg: 0.0010; round trip 0.0020 + base 0.0010 → 0.0030
    assert out["net_pnl_pct"].tolist() == pytest.approx(
        [0.0050 - 0.0030, -0.0040 - 0.0030, 0.0010 - 0.0030]
    )


def test_evaluate_pass_fail_s0_threshold():
    """OPPORTUNITY trades at S0: Sharpe ≥ 1.0, hit ≥ 55%, MaxDD ≤ 20%."""
    metrics = {"sharpe": 1.1, "hit_rate": 0.56, "max_dd": 0.18}
    v = evaluate_pass_fail(metrics, SlippageLevel.S0)
    assert v["pass"] is True
    metrics["sharpe"] = 0.9
    v = evaluate_pass_fail(metrics, SlippageLevel.S0)
    assert v["pass"] is False
    assert "sharpe" in v["failures"]
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_slippage_grid.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/slippage_grid.py
"""§1.1 slippage levels + §1.2 fill simulator + §3 pass/fail.

Round-trip cost (subtract from gross_pnl_pct):
- S0: 10 bps  (5 per side)
- S1: 30 bps  (15 per side)
- S2: 50 bps  (25 per side)
- S3: 70 bps  (35 per side, informational only)
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class SlippageLevel(str, Enum):
    S0 = "s0"
    S1 = "s1"
    S2 = "s2"
    S3 = "s3"


_ROUND_TRIP_COST = {
    SlippageLevel.S0: 0.0010,
    SlippageLevel.S1: 0.0030,
    SlippageLevel.S2: 0.0050,
    SlippageLevel.S3: 0.0070,
}


_PASS_THRESHOLDS = {
    SlippageLevel.S0: {"sharpe": 1.0, "hit_rate": 0.55, "max_dd": 0.20},
    SlippageLevel.S1: {"sharpe": 0.8, "hit_rate": 0.50, "max_dd": 0.25},
    SlippageLevel.S2: {"sharpe": 0.5, "hit_rate": 0.45, "max_dd": 0.30},
}


def apply_slippage(events: pd.DataFrame, level: SlippageLevel) -> pd.DataFrame:
    out = events.copy()
    out["net_pnl_pct"] = events["gross_pnl_pct"] - _ROUND_TRIP_COST[level]
    return out


def evaluate_pass_fail(metrics: dict, level: SlippageLevel) -> dict:
    if level == SlippageLevel.S3:
        return {"pass": True, "failures": [], "level": level.value, "informational": True}
    th = _PASS_THRESHOLDS[level]
    failures = []
    if metrics["sharpe"] < th["sharpe"]:
        failures.append("sharpe")
    if metrics["hit_rate"] < th["hit_rate"]:
        failures.append("hit_rate")
    if metrics["max_dd"] > th["max_dd"]:
        failures.append("max_dd")
    return {"pass": not failures, "failures": failures, "level": level.value}
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_slippage_grid.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/slippage_grid.py \
        pipeline/tests/test_etf_v3_eval/test_slippage_grid.py
git commit -m "feat(v3-eval-p2): §1-§3 slippage grid (S0/S1/S2/S3) + pass/fail"
```

---

### Task 15: §5A data audit per run

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/data_audit.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_data_audit.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_data_audit.py
from datetime import date

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.data_audit import audit_run_data


def test_audit_counts_zero_volume_and_stale():
    df = pd.DataFrame({
        "ticker": ["A","A","A","A"],
        "trade_date": [date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15","2026-03-03 09:16",
            "2026-03-03 09:17","2026-03-03 09:18",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100,100,100,101], "high":[100,100,100,101],
        "low":[100,100,100,101], "close":[100,100,100,101],
        "volume":[10, 0, 0, 5],
    })
    rep = audit_run_data(df)
    assert rep["zero_volume_bar_count"] == 2
    assert rep["stale_quote_count_min3"] == 1   # 3 consecutive identical OHLC bars
    assert rep["bad_data_pct"] >= 0
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_data_audit.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/data_audit.py
"""§5A.1 mandatory per-run data quality report."""
from __future__ import annotations

import pandas as pd


def audit_run_data(minute_df: pd.DataFrame, stale_window: int = 3) -> dict:
    df = minute_df.copy()
    n = len(df)
    zero_vol = int((df["volume"] == 0).sum())
    neg_price = int(((df["open"] <= 0) | (df["close"] <= 0)).sum())
    duplicates = int(df.duplicated(subset=["ticker","timestamp"]).sum())
    df = df.sort_values(["ticker","timestamp"])
    df["all_ohlc"] = df[["open","high","low","close"]].apply(tuple, axis=1)
    df["stale_run"] = (
        df.groupby("ticker")["all_ohlc"]
          .transform(lambda s: s.eq(s.shift()).rolling(stale_window, min_periods=1).sum())
    )
    stale = int((df["stale_run"] >= stale_window - 1).sum())
    impaired = zero_vol + neg_price + duplicates + stale
    return {
        "n_rows": n,
        "zero_volume_bar_count": zero_vol,
        "zero_or_negative_price_count": neg_price,
        "duplicate_timestamp_count": duplicates,
        f"stale_quote_count_min{stale_window}": stale,
        "bad_data_pct": float(impaired) / max(n, 1) * 100.0,
        "tag": _tag_for_pct(float(impaired) / max(n, 1) * 100.0),
    }


def _tag_for_pct(pct: float) -> str:
    if pct > 3.0:
        return "AUTO-FAIL"
    if pct > 1.0:
        return "DATA-IMPAIRED"
    return "CLEAN"
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_data_audit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/data_audit.py \
        pipeline/tests/test_etf_v3_eval/test_data_audit.py
git commit -m "feat(v3-eval-p2): §5A.1 per-run data quality audit"
```

---

### Task 16: §6 survivorship snapshot + §7.3 entry-timing audit

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/survivorship.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/entry_timing_audit.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_survivorship.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_entry_timing_audit.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_etf_v3_eval/test_survivorship.py
import json
from datetime import date
from pathlib import Path

from pipeline.autoresearch.etf_v3_eval.phase_2.survivorship import (
    eligible_universe_at,
    coverage_summary,
)


def test_eligible_universe_pulls_pit_membership(tmp_path):
    src = tmp_path / "fno_universe_history.json"
    src.write_text(json.dumps({
        "snapshots": {
            "2025-12-01": ["RELIANCE","TCS","INFY"],
            "2026-03-01": ["RELIANCE","TCS","HDFCBANK"],
        }
    }), encoding="utf-8")
    elig = eligible_universe_at(src, date(2026, 2, 28))
    assert set(elig) == {"RELIANCE","TCS","INFY"}


def test_coverage_summary_reports_ratios(tmp_path):
    src = tmp_path / "u.json"
    src.write_text(json.dumps({
        "snapshots": {
            "2024-01-01": ["A","B","C"],
            "2025-01-01": ["A","C","D"],
        }
    }), encoding="utf-8")
    summ = coverage_summary(src)
    assert summ["n_tickers_ever"] == 4
    assert summ["n_tickers_current"] == 3
    assert summ["n_tickers_delisted"] == 1   # B
    assert 0 < summ["coverage_ratio"] <= 1
```

```python
# pipeline/tests/test_etf_v3_eval/test_entry_timing_audit.py
from datetime import datetime

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.entry_timing_audit import (
    audit_entry_timing,
    EntryMode,
)


def test_audit_passes_when_lag_30min_in_mode_b():
    trades = pd.DataFrame({
        "signal_decidable_at": pd.to_datetime(["2026-03-03 09:15"]),
        "filled_at":           pd.to_datetime(["2026-03-03 09:45"]),
    })
    rep = audit_entry_timing(trades, mode=EntryMode.B)
    assert rep["pass"] is True


def test_audit_fails_when_fill_before_signal():
    trades = pd.DataFrame({
        "signal_decidable_at": pd.to_datetime(["2026-03-03 09:30"]),
        "filled_at":           pd.to_datetime(["2026-03-03 09:00"]),
    })
    rep = audit_entry_timing(trades, mode=EntryMode.C)
    assert rep["pass"] is False
    assert rep["n_lag_negative"] == 1
```

- [ ] **Step 2: Run to confirm both fail**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_survivorship.py pipeline/tests/test_etf_v3_eval/test_entry_timing_audit.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement survivorship.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/survivorship.py
"""§6 survivorship — point-in-time universe and coverage summary.

Reads pipeline/data/fno_universe_history.json which has shape:
    {"snapshots": {"YYYY-MM-DD": ["TKR1","TKR2",...], ...}}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def eligible_universe_at(path: Path, asof: date) -> List[str]:
    snaps = _load(path)["snapshots"]
    keys = sorted(snaps.keys())
    chosen = None
    for k in keys:
        if date.fromisoformat(k) <= asof:
            chosen = k
        else:
            break
    return list(snaps[chosen]) if chosen else []


def coverage_summary(path: Path) -> dict:
    snaps = _load(path)["snapshots"]
    keys = sorted(snaps.keys())
    ever = set().union(*[set(v) for v in snaps.values()])
    current = set(snaps[keys[-1]])
    delisted = ever - current
    return {
        "n_tickers_current": len(current),
        "n_tickers_ever": len(ever),
        "n_tickers_delisted": len(delisted),
        "coverage_ratio": len(delisted) / max(len(ever), 1),
        "snapshots_count": len(keys),
        "earliest_snapshot": keys[0],
        "latest_snapshot": keys[-1],
    }
```

- [ ] **Step 4: Implement entry_timing_audit.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/entry_timing_audit.py
"""§7.3 entry-timing audit hook.

For each trade emit lag = filled_at - signal_decidable_at. Fail if any lag < 0,
or (in MODE B/C) any lag < 30 min.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class EntryMode(str, Enum):
    A = "eod_close"
    B = "morning_settled_30min"
    C = "intraday_t_plus_5"


def audit_entry_timing(trades: pd.DataFrame, mode: EntryMode) -> dict:
    if "signal_decidable_at" not in trades.columns or "filled_at" not in trades.columns:
        raise ValueError("trades must contain signal_decidable_at + filled_at")
    lag = trades["filled_at"] - trades["signal_decidable_at"]
    n_neg = int((lag < pd.Timedelta(0)).sum())
    n_too_close = int(((lag >= pd.Timedelta(0)) & (lag < pd.Timedelta(minutes=30))).sum()) \
                  if mode in (EntryMode.B, EntryMode.C) else 0
    return {
        "pass": (n_neg == 0) and (n_too_close == 0),
        "n_lag_negative": n_neg,
        "n_lag_under_30min": n_too_close,
        "median_lag_seconds": float(lag.dt.total_seconds().median()),
        "mode": mode.value,
    }
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_survivorship.py pipeline/tests/test_etf_v3_eval/test_entry_timing_audit.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/survivorship.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/entry_timing_audit.py \
        pipeline/tests/test_etf_v3_eval/test_survivorship.py \
        pipeline/tests/test_etf_v3_eval/test_entry_timing_audit.py
git commit -m "feat(v3-eval-p2): §6 survivorship + §7.3 entry-timing audit"
```

---

### Task 17: §8 direction audit

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/direction_audit.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_direction_audit.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_direction_audit.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.direction_audit import (
    direction_audit,
    DirectionVerdict,
)


def test_direction_verdict_aligned_when_strategy_beats_opposite():
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]*5).date,
        "realized_pct":  [ 0.01, 0.02, 0.015, 0.012, 0.018],
        "side": ["LONG"]*5,   # All LONG → strategy wins
    })
    rep = direction_audit(events)
    assert rep.verdict == DirectionVerdict.ALIGNED


def test_direction_verdict_suspect_when_opposite_beats_strategy():
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]*5).date,
        "realized_pct":  [-0.01,-0.02,-0.015,-0.012,-0.018],
        "side": ["LONG"]*5,   # LONGs lose; SHORT would win
    })
    rep = direction_audit(events)
    assert rep.verdict == DirectionVerdict.SUSPECT
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_direction_audit.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/direction_audit.py
"""§8 direction audit — compare strategy direction vs opposite-direction Sharpe.

If opposite-direction Sharpe at S0 exceeds strategy Sharpe → DIRECTION-SUSPECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class DirectionVerdict(str, Enum):
    ALIGNED = "aligned"
    SUSPECT = "suspect"


@dataclass(frozen=True)
class DirectionReport:
    verdict: DirectionVerdict
    strategy_mean: float
    strategy_sharpe: float
    opposite_mean: float
    opposite_sharpe: float


def direction_audit(events: pd.DataFrame, annualization: int = 252) -> DirectionReport:
    """events must have realized_pct and side ∈ {LONG, SHORT}."""
    sign = events["side"].map({"LONG": 1.0, "SHORT": -1.0})
    strat = events["realized_pct"] * sign
    opp = -strat
    sm, ss = float(strat.mean()), float(strat.std(ddof=1) or 1e-12)
    om, os = float(opp.mean()),   float(opp.std(ddof=1) or 1e-12)
    s_sharpe = (sm / ss) * np.sqrt(annualization)
    o_sharpe = (om / os) * np.sqrt(annualization)
    verdict = DirectionVerdict.SUSPECT if o_sharpe > s_sharpe else DirectionVerdict.ALIGNED
    return DirectionReport(verdict, sm, s_sharpe, om, o_sharpe)
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_direction_audit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/direction_audit.py \
        pipeline/tests/test_etf_v3_eval/test_direction_audit.py
git commit -m "feat(v3-eval-p2): §8 strategy-direction audit"
```

---

### Task 18: §11.1 ADV liquidity check

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/liquidity_check.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_liquidity_check.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_liquidity_check.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.liquidity_check import (
    compute_60d_adv,
    impact_penalty_bps,
)


def test_compute_60d_adv():
    df = pd.DataFrame({
        "ticker": ["A"]*5,
        "trade_date": pd.date_range("2026-01-01", periods=5),
        "close": [100.0]*5,
        "volume": [100_000, 200_000, 150_000, 250_000, 100_000],
    })
    out = compute_60d_adv(df, window=5)
    # mean(volume) * mean(close) = 160000 * 100
    assert out["A"] == pytest.approx(160_000 * 100.0)


def test_impact_penalty_scales_linearly_with_position_over_adv():
    p = impact_penalty_bps(position_size=2_000_000, adv=10_000_000)
    # base = 0; penalty = 5 * (2e6 / 1e7) = 1.0 bps
    assert p == pytest.approx(1.0)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_liquidity_check.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/liquidity_check.py
"""§11.1 — 60-day ADV per ticker; 10× threshold; linear impact penalty."""
from __future__ import annotations

from typing import Mapping

import pandas as pd


def compute_60d_adv(daily_bars: pd.DataFrame, window: int = 60) -> Mapping[str, float]:
    df = daily_bars.copy()
    df["notional"] = df["close"] * df["volume"]
    grouped = df.groupby("ticker")["notional"].apply(
        lambda s: s.tail(window).mean()
    )
    return grouped.to_dict()


def impact_penalty_bps(position_size: float, adv: float) -> float:
    if adv <= 0:
        return 1e9
    return 5.0 * (position_size / adv)
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_liquidity_check.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/liquidity_check.py \
        pipeline/tests/test_etf_v3_eval/test_liquidity_check.py
git commit -m "feat(v3-eval-p2): §11.1 ADV liquidity check"
```

---

### Task 19: §11A.1 implementation-risk simulator (10 scenarios)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/implementation_risk.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_implementation_risk.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_implementation_risk.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.implementation_risk import (
    apply_missed_entries,
    apply_missed_exits_held_one_bar,
    apply_partial_fill,
    apply_delayed_fill_5min,
    run_full_scenario_set,
    pass_implementation_gate,
)


def test_missed_entries_drops_5pct_of_rows():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({"realized_pct": np.arange(1000)*0.001})
    out = apply_missed_entries(events, miss_pct=0.05, rng=rng)
    assert 940 <= len(out) <= 960   # 5% of 1000 = 50 ± noise


def test_partial_fill_halves_realized_pct():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = apply_partial_fill(events, fill_fraction=0.5)
    assert out["realized_pct"].tolist() == pytest.approx([0.005, -0.01, 0.015])


def test_pass_gate_requires_all_three_conditions():
    base = {"sharpe_s1": 1.0, "max_dd_s1": 0.20}
    stressed = {"cum_pnl": 0.05, "max_dd": 0.25, "realised_sharpe": 0.65}
    assert pass_implementation_gate(stressed, base) is True
    stressed_fail = {"cum_pnl": 0.05, "max_dd": 0.30, "realised_sharpe": 0.65}
    assert pass_implementation_gate(stressed_fail, base) is False  # DD > 1.4×0.20
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_implementation_risk.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/implementation_risk.py
"""§11A.1 — 10 implementation-risk failure scenarios.

Each scenario takes an events frame (cols: realized_pct, ...) and returns a
mutated frame. run_full_scenario_set composes all 10 in sequence and emits
{cum_pnl, max_dd, realised_sharpe} for the gate check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def apply_missed_entries(events: pd.DataFrame, miss_pct: float, rng: np.random.Generator) -> pd.DataFrame:
    keep_mask = rng.random(len(events)) >= miss_pct
    return events[keep_mask].reset_index(drop=True)


def apply_missed_exits_held_one_bar(events: pd.DataFrame, miss_pct: float,
                                     next_bar_pct_col: str = "open_to_close_pct",
                                     rng: np.random.Generator | None = None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(0)
    out = events.copy()
    if next_bar_pct_col not in out.columns:
        return out
    miss = rng.random(len(out)) < miss_pct
    out.loc[miss, "realized_pct"] = out.loc[miss, next_bar_pct_col]
    return out


def apply_delayed_fill_5min(events: pd.DataFrame, slippage_bps: float = 5.0) -> pd.DataFrame:
    out = events.copy()
    out["realized_pct"] = events["realized_pct"] - slippage_bps / 10_000
    return out


def apply_stale_signal_one_bar(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy().reset_index(drop=True)
    out["realized_pct"] = out["realized_pct"].shift(-1).fillna(out["realized_pct"].iloc[-1])
    return out


def apply_rejected_exit_retry_next_bar(events: pd.DataFrame, miss_pct: float,
                                        next_bar_pct_col: str = "open_to_close_pct",
                                        rng: np.random.Generator | None = None) -> pd.DataFrame:
    return apply_missed_exits_held_one_bar(events, miss_pct, next_bar_pct_col, rng)


def apply_partial_fill(events: pd.DataFrame, fill_fraction: float = 0.5) -> pd.DataFrame:
    out = events.copy()
    out["realized_pct"] = events["realized_pct"] * fill_fraction
    return out


def apply_data_outage_once_per_month(events: pd.DataFrame, rng: np.random.Generator | None = None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(0)
    out = events.copy().reset_index(drop=True)
    if "trade_date" not in out.columns or len(out) == 0:
        return out
    months = pd.to_datetime(out["trade_date"]).dt.to_period("M").unique()
    drop_idx = []
    for m in months:
        rows = out[pd.to_datetime(out["trade_date"]).dt.to_period("M") == m]
        if len(rows):
            drop_idx.append(int(rng.choice(rows.index)))
    return out.drop(drop_idx).reset_index(drop=True)


def apply_exchange_halt_at_t_plus_1_open(events: pd.DataFrame, freq_pct: float = 0.02,
                                          rng: np.random.Generator | None = None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(0)
    out = events.copy()
    halts = rng.random(len(out)) < freq_pct
    # Halts ⇒ exit delayed; assume realized = 0.5× (mid-session reopen averaging)
    out.loc[halts, "realized_pct"] = out.loc[halts, "realized_pct"] * 0.5
    return out


def apply_margin_shortage_block(events: pd.DataFrame, dd_threshold: float = 0.10) -> pd.DataFrame:
    out = events.copy().sort_values("trade_date").reset_index(drop=True)
    cum = out["realized_pct"].cumsum()
    dd = cum.cummax() - cum
    out.loc[dd > dd_threshold, "realized_pct"] = 0.0
    return out


def apply_overnight_gap_3x_vol(events: pd.DataFrame, gap_pct: float = 0.0,
                                rng: np.random.Generator | None = None) -> pd.DataFrame:
    """Overnight-hold strategies only; intraday v3-CURATED is largely flat-by-1430.
    Default gap_pct = 0 ⇒ no-op. Kept as parameter so 11A.1 catalog is complete.
    """
    return events.copy()


def run_full_scenario_set(events: pd.DataFrame, rng_seed: int = 0) -> dict:
    rng = np.random.default_rng(rng_seed)
    e = events.copy()
    e = apply_missed_entries(e, 0.05, rng)
    e = apply_missed_exits_held_one_bar(e, 0.05, rng=rng)
    e = apply_delayed_fill_5min(e)
    e = apply_stale_signal_one_bar(e)
    e = apply_rejected_exit_retry_next_bar(e, 0.02, rng=rng)
    e = apply_partial_fill(e, 0.5)
    e = apply_data_outage_once_per_month(e, rng=rng)
    e = apply_exchange_halt_at_t_plus_1_open(e, 0.02, rng=rng)
    e = apply_margin_shortage_block(e, 0.10)
    e = apply_overnight_gap_3x_vol(e, rng=rng)
    cum = e["realized_pct"].cumsum()
    dd = float((cum.cummax() - cum).max())
    sharpe = float(e["realized_pct"].mean() / (e["realized_pct"].std(ddof=1) or 1e-12)) * (252 ** 0.5)
    return {"cum_pnl": float(cum.iloc[-1] if len(cum) else 0.0),
            "max_dd": dd, "realised_sharpe": sharpe, "n_remaining": int(len(e))}


def pass_implementation_gate(stressed: dict, baseline: dict) -> bool:
    """§11A.2: cum_pnl > 0, max_dd ≤ 1.4 × baseline.max_dd_s1, sharpe ≥ 0.6 × baseline.sharpe_s1."""
    return (stressed["cum_pnl"] > 0
            and stressed["max_dd"] <= 1.4 * baseline["max_dd_s1"]
            and stressed["realised_sharpe"] >= 0.6 * baseline["sharpe_s1"])
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_implementation_risk.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/implementation_risk.py \
        pipeline/tests/test_etf_v3_eval/test_implementation_risk.py
git commit -m "feat(v3-eval-p2): §11A.1 10-scenario implementation-risk simulator"
```

---

### Task 20: §12 edge decay (rolling 12mo + CUSUM)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/edge_decay.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_edge_decay.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_edge_decay.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.edge_decay import (
    rolling_12mo_sharpe,
    cusum_regime_change,
)


def test_rolling_12mo_sharpe_returns_per_period_value():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(0.001, 0.01, 300),
                  index=pd.date_range("2024-01-01", periods=300))
    out = rolling_12mo_sharpe(s, window=252)
    assert out.iloc[-1] is not None
    assert not np.isnan(out.iloc[-1])


def test_cusum_detects_known_break():
    """A clean shift from mean=0.005 to mean=-0.005 is detected by CUSUM."""
    s = pd.Series(np.r_[np.full(100, 0.005), np.full(100, -0.005)],
                  index=pd.date_range("2024-01-01", periods=200))
    triggers = cusum_regime_change(s, threshold=3.0)
    assert any(t > 100 for t in triggers)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_edge_decay.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/edge_decay.py
"""§12 edge decay — rolling 12-month Sharpe + CUSUM regime-change detector."""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd


def rolling_12mo_sharpe(daily_pnl: pd.Series, window: int = 252) -> pd.Series:
    return (daily_pnl.rolling(window).mean() / daily_pnl.rolling(window).std(ddof=1)) * np.sqrt(252)


def cusum_regime_change(daily_pnl: pd.Series, threshold: float = 3.0) -> List[int]:
    """Two-sided CUSUM. Returns positional indices where CUSUM exceeds threshold·σ."""
    sigma = float(daily_pnl.std(ddof=1) or 1e-12)
    pos, neg = 0.0, 0.0
    triggers: List[int] = []
    for i, x in enumerate(daily_pnl.values):
        pos = max(0.0, pos + (x - 0))
        neg = min(0.0, neg + (x - 0))
        if pos > threshold * sigma or abs(neg) > threshold * sigma:
            triggers.append(i)
            pos, neg = 0.0, 0.0
    return triggers
```

- [ ] **Step 4: Run test**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_edge_decay.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/edge_decay.py \
        pipeline/tests/test_etf_v3_eval/test_edge_decay.py
git commit -m "feat(v3-eval-p2): §12 rolling 12mo Sharpe + CUSUM detector"
```

---

## Section 5 — Run, report, gate ladder, closeout

### Task 21: End-to-end Phase 2 orchestrator

**Why:** Wire every piece (preflight + walk-forward + markers + stats + spec gates + manifests) into a single deterministic CLI that produces all Phase 2 deliverables. This is the runner Phase 3 will pre-register against.

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/orchestrator.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_orchestrator.py`

- [ ] **Step 1: Write failing test (smoke-only — full run is integration)**

```python
# pipeline/tests/test_etf_v3_eval/test_orchestrator.py
from pipeline.autoresearch.etf_v3_eval.phase_2.orchestrator import (
    Phase2Inputs,
    iter_run_configs,
)


def test_iter_run_configs_emits_lookback_x_universe_grid():
    inputs = Phase2Inputs(
        replay_parquets={
            "126": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet",
            "273": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet",
        },
        lookbacks=(756, 1200, 1236),
        feature_set="curated",
        seed=0,
    )
    configs = list(iter_run_configs(inputs))
    # 3 lookbacks × 2 universes = 6 base runs
    assert len(configs) == 6
    assert {(c.lookback_days, c.universe) for c in configs} == {
        (756,"126"),(1200,"126"),(1236,"126"),
        (756,"273"),(1200,"273"),(1236,"273"),
    }
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_orchestrator.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/orchestrator.py
"""End-to-end Phase 2 orchestrator.

Runs the full grid (lookback × universe), applies markers, computes statistical
tests, runs slippage grid + implementation-risk + alpha-after-beta + decay, and
writes all per-run manifests + final reports.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import RunConfig, write_run_manifest
from pipeline.autoresearch.etf_v3_eval.phase_2.walk_forward_runner import run_walk_forward, PurgeConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase2Inputs:
    replay_parquets: Mapping[str, str]
    lookbacks: tuple[int, ...] = (756, 1200, 1236)
    feature_set: str = "curated"
    seed: int = 0
    refit_interval_days: int = 5
    n_iterations: int = 2000


def iter_run_configs(inputs: Phase2Inputs) -> Iterable[RunConfig]:
    for lb in inputs.lookbacks:
        for universe in inputs.replay_parquets:
            yield RunConfig(
                run_id=f"wf_lb{lb}_u{universe}_seed{inputs.seed}",
                strategy_version="v3-CURATED-30",
                cost_model_version="cm_2026-04-26_v1",
                random_seed=inputs.seed,
                lookback_days=lb,
                refit_interval_days=inputs.refit_interval_days,
                n_iterations=inputs.n_iterations,
                universe=universe,
                feature_set=inputs.feature_set,
            )


def run(inputs: Phase2Inputs, out_root: Path) -> list[Path]:
    out_root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for cfg in iter_run_configs(inputs):
        run_dir = out_root / cfg.run_id
        logger.info("running %s ...", cfg.run_id)
        run_walk_forward(cfg, run_dir, PurgeConfig(embargo_days=5))
        paths.append(run_dir / "manifest.json")
    return paths


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ETF v3-Eval Phase 2 orchestrator")
    p.add_argument("--out-root", default="pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-iterations", type=int, default=2000)
    p.add_argument("--quick", action="store_true",
                   help="dev-only: 100 iterations, single lookback, single universe")
    return p


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _build_argparser().parse_args()
    inputs = Phase2Inputs(
        replay_parquets={
            "126": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet",
            "273": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet",
        },
        lookbacks=(756,) if args.quick else (756, 1200, 1236),
        seed=args.seed,
        n_iterations=100 if args.quick else args.n_iterations,
    )
    out_root = Path(args.out_root)
    paths = run(inputs, out_root)
    print(f"emitted {len(paths)} run manifests under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test + smoke-run orchestrator at --quick**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_orchestrator.py -v
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.phase_2.orchestrator --quick \
    --out-root pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs_smoke
```
Expected: test PASS, smoke run completes in < 10 min, emits 1 manifest.

- [ ] **Step 5: Commit (both code AND smoke-run output for audit trail)**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/orchestrator.py \
        pipeline/tests/test_etf_v3_eval/test_orchestrator.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs_smoke/
git commit -m "feat(v3-eval-p2): orchestrator + --quick smoke run committed"
```

- [ ] **Step 6: Run full grid (6 configs × 2000 iterations — long-running, expect 2-6 hours)**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.phase_2.orchestrator \
    --out-root pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs \
    --seed 0 --n-iterations 2000
```

After completion, commit results:

```bash
git add pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs/
git commit -m "data(v3-eval-p2): full 6-config walk-forward grid run"
```

---

### Task 22: Marker decomposition + universe sensitivity reports

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/decomposition_report.py`
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/universe_sensitivity_report.py`
- Out: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md`
- Out: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/universe_sensitivity.md`

- [ ] **Step 1: Write minimal smoke test for the report writer**

```python
# pipeline/tests/test_etf_v3_eval/test_decomposition_report.py
from pathlib import Path

from pipeline.autoresearch.etf_v3_eval.phase_2.decomposition_report import (
    write_markers_decomposition_md,
)


def test_write_markers_decomposition_md_emits_table_per_marker(tmp_path):
    rows = [
        {"marker":"zone_gate", "n_trades":120, "mean_pnl":0.0042,
         "se":0.0008, "p_perm":0.012, "fragility":"stable",
         "incremental_pnl":0.0042, "naive_random_p":0.005},
        {"marker":"sector_overlay", "n_trades":80, "mean_pnl":0.0061,
         "se":0.0011, "p_perm":0.034, "fragility":"stable",
         "incremental_pnl":0.0019, "naive_random_p":0.014},
    ]
    out = tmp_path / "m.md"
    write_markers_decomposition_md(rows, out)
    text = out.read_text(encoding="utf-8")
    assert "zone_gate" in text and "sector_overlay" in text
    assert "Mean P&L" in text
    assert "Fragility" in text
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_decomposition_report.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement decomposition_report.py**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/decomposition_report.py
"""Writes pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md.

Per marker rows include: standalone P&L, incremental contribution after stacking,
cluster-robust SE, permutation null p-value, fragility verdict, naive benchmark p.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence


def write_markers_decomposition_md(rows: Sequence[dict], out_path: Path) -> None:
    lines = [
        "# Phase 2 Marker Decomposition",
        "",
        "| Marker | n | Mean P&L | SE (cluster) | Incremental | Permutation p | Naive random p | Fragility |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['marker']} | {r['n_trades']} | {r['mean_pnl']:.4f} | "
            f"{r['se']:.4f} | {r['incremental_pnl']:.4f} | {r['p_perm']:.3f} | "
            f"{r['naive_random_p']:.3f} | {r['fragility']} |"
        )
    lines.append("")
    lines.append("Cluster level: trade_date. n trades = events surviving the marker stack at that point.")
    lines.append("Permutation null: 10,000 shuffles two-sided, naive_random_p = signed-flip benchmark.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Implement universe_sensitivity_report.py and its test (analogous)**

Test:
```python
# pipeline/tests/test_etf_v3_eval/test_universe_sensitivity_report.py
from pipeline.autoresearch.etf_v3_eval.phase_2.universe_sensitivity_report import (
    write_universe_sensitivity_md,
)


def test_write_universe_sensitivity_md(tmp_path):
    rows = [
        {"marker":"zone_gate","u126_mean_pnl":0.0030,"u273_mean_pnl":0.0045,
         "u126_n":80, "u273_n":143, "delta_pp":+0.15,"verdict_changed":False},
        {"marker":"sector_overlay","u126_mean_pnl":0.0058,"u273_mean_pnl":0.0061,
         "u126_n":40,"u273_n":80,"delta_pp":+0.03,"verdict_changed":False},
    ]
    out = tmp_path / "u.md"
    write_universe_sensitivity_md(rows, out)
    text = out.read_text(encoding="utf-8")
    assert "zone_gate" in text and "Δ pp" in text
```

Implementation:
```python
# pipeline/autoresearch/etf_v3_eval/phase_2/universe_sensitivity_report.py
from __future__ import annotations
from pathlib import Path
from typing import Sequence


def write_universe_sensitivity_md(rows: Sequence[dict], out_path: Path) -> None:
    lines = [
        "# Phase 2 Universe Sensitivity (126 vs 273)",
        "",
        "| Marker | u126 mean P&L | u126 n | u273 mean P&L | u273 n | Δ pp | Verdict changed |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['marker']} | {r['u126_mean_pnl']:.4f} | {r['u126_n']} | "
            f"{r['u273_mean_pnl']:.4f} | {r['u273_n']} | {r['delta_pp']:+.2f} | "
            f"{'YES' if r['verdict_changed'] else 'no'} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 5: Run tests**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_decomposition_report.py pipeline/tests/test_etf_v3_eval/test_universe_sensitivity_report.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Generate the actual reports from Task 21 outputs**

Write a short driver `pipeline/autoresearch/etf_v3_eval/phase_2/build_reports.py` that walks `runs/`, applies all 6 markers + statistical tests against each run's events frame, and produces both reports. Then run:

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.phase_2.build_reports
```

Commit:
```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/decomposition_report.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/universe_sensitivity_report.py \
        pipeline/autoresearch/etf_v3_eval/phase_2/build_reports.py \
        pipeline/tests/test_etf_v3_eval/test_decomposition_report.py \
        pipeline/tests/test_etf_v3_eval/test_universe_sensitivity_report.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/universe_sensitivity.md
git commit -m "feat(v3-eval-p2): markers_decomposition.md + universe_sensitivity.md"
```

---

### Task 23: §15 gate ladder + Phase 3 pre-registration prep

**Why:** §15.1 RESEARCH → PAPER-SHADOW gate must be evaluated before Phase 3 starts. Phase 3 also requires §14.1 pre-registration with §14.5 family denominator declared up-front (not retroactively).

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/phase_2/gate_ladder.py`
- Test: `pipeline/tests/test_etf_v3_eval/test_gate_ladder.py`
- Out: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/gate_ladder_verdict.json`
- Out: `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.md` (DRAFT — locked at Phase 3 task 1)

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_etf_v3_eval/test_gate_ladder.py
from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
    evaluate_research_to_paper_shadow,
    GateVerdict,
)


def test_pass_when_all_required_gates_pass():
    evidence = {
        "s0_pass": True, "s1_pass": True,
        "data_audit_tag": "CLEAN",
        "survivorship_disclosed": True,
        "entry_timing_pass": True,
        "direction_audit_verdict": "aligned",
        "n_trades": 75, "min_required": 50,
        "fragility_verdict": "stable",
        "naive_benchmark_beaten": True,
        "purged_walkforward": True,
        "alpha_after_beta_pass": True,
        "hypothesis_registered": True,
    }
    v = evaluate_research_to_paper_shadow(evidence)
    assert v.verdict == GateVerdict.PASS
    assert v.failed_gates == []


def test_fail_when_direction_suspect():
    evidence = {
        "s0_pass": True, "s1_pass": True, "data_audit_tag": "CLEAN",
        "survivorship_disclosed": True, "entry_timing_pass": True,
        "direction_audit_verdict": "suspect",
        "n_trades": 75, "min_required": 50,
        "fragility_verdict": "stable", "naive_benchmark_beaten": True,
        "purged_walkforward": True, "alpha_after_beta_pass": True,
        "hypothesis_registered": True,
    }
    v = evaluate_research_to_paper_shadow(evidence)
    assert v.verdict == GateVerdict.FAIL
    assert "direction_audit" in v.failed_gates
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_gate_ladder.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/etf_v3_eval/phase_2/gate_ladder.py
"""§15.1 RESEARCH → PAPER-SHADOW gate evaluator.

Per §15.1: pass Sections 1 (S0+S1), 2, 5A, 6, 7, 8, 9, 9A, 9B, 10, 11B.
Pre-registered hypothesis required (Section 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class GateLadderReport:
    verdict: GateVerdict
    failed_gates: List[str] = field(default_factory=list)


def evaluate_research_to_paper_shadow(evidence: dict) -> GateLadderReport:
    failed: list[str] = []
    if not evidence.get("s0_pass"):                        failed.append("s0_pass")
    if not evidence.get("s1_pass"):                        failed.append("s1_pass")
    if evidence.get("data_audit_tag") not in ("CLEAN","DATA-IMPAIRED"):
        failed.append("data_audit")
    if not evidence.get("survivorship_disclosed"):         failed.append("survivorship")
    if not evidence.get("entry_timing_pass"):              failed.append("entry_timing")
    if evidence.get("direction_audit_verdict") != "aligned":
        failed.append("direction_audit")
    if evidence.get("n_trades", 0) < evidence.get("min_required", 50):
        failed.append("sample_size")
    if evidence.get("fragility_verdict") != "stable":      failed.append("fragility")
    if not evidence.get("naive_benchmark_beaten"):         failed.append("naive_benchmark")
    if not evidence.get("purged_walkforward"):             failed.append("purged_walkforward")
    if not evidence.get("alpha_after_beta_pass"):          failed.append("alpha_after_beta")
    if not evidence.get("hypothesis_registered"):          failed.append("hypothesis_registry")
    return GateLadderReport(
        GateVerdict.PASS if not failed else GateVerdict.FAIL,
        failed,
    )
```

- [ ] **Step 4: Run test + emit verdict against Phase 2 evidence**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/test_gate_ladder.py -v
```

Manually compose the evidence dict from Phase 2 outputs — write a small helper `evaluate_phase_2.py` that reads `runs/<best_config>/` outputs + reports and emits `gate_ladder_verdict.json`. If verdict is FAIL, list which gates failed in `gate_ladder_verdict.json` and STOP — Phase 3 cannot pre-register until those are remedied.

- [ ] **Step 5: Draft Phase 3 pre-registration document (DRAFT — final lock at Phase 3 task 1)**

Create `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.md`:

```markdown
# Phase 3 Pre-Registration — DRAFT (locks at Phase 3 task 1)

Status: DRAFT. Final lock requires SHA-256 hash committed in Phase 3 plan task 1.

## Hypothesis ID
H-2026-04-XX-XXX  (assigned at lock)

## Strategy version
v3-CURATED-30 + <best marker stack from Phase 2>

## Universe
<126 OR 273 — whichever Phase 2 chose>

## Date window
Start: 2026-04-27 (next trading day after lock)
End: T + 30 trade-eligible days (extend to 60 if vol-low)

## Statistical test
Cluster-robust mean P&L > 0 at p < 0.05, clustered by trade_date.

## Family denominator (§14.5)
Primary: <strategy-class | universe-scope | ticker-family>  (chosen at lock — write rationale)

## Naive comparator (§9B.1)
random_direction permutation null, n=10,000.

## Pass thresholds
- Cluster-robust mean > 0 with p < 0.05
- ≥ 30 trade-eligible days
- Beats random_direction at p < 0.05
- Slippage S1 result still positive

## Kill-switch (§13.3)
Cumulative DD > 3× backtest MaxDD halts and triggers review.
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/phase_2/gate_ladder.py \
        pipeline/tests/test_etf_v3_eval/test_gate_ladder.py \
        pipeline/data/research/etf_v3_evaluation/phase_2_backtest/gate_ladder_verdict.json \
        pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.md
git commit -m "feat(v3-eval-p2): §15 gate ladder + Phase 3 pre-registration draft"
```

---

### Task 24: Phase 2 closeout — review checklist + tag

**Why:** Final consistency check before handing off to Phase 3.

- [ ] **Step 1: Run full pytest suite**

```bash
python -X utf8 -m pytest pipeline/tests/test_etf_v3_eval/ -v
```
Expected: all green.

- [ ] **Step 2: Verify every Phase 2 deliverable exists**

```bash
python -X utf8 -c "
from pathlib import Path
need = [
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/reconciliation_strict.json',
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/contamination_map_full.json',
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/aliases_resolution.md',
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md',
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/universe_sensitivity.md',
    'pipeline/data/research/etf_v3_evaluation/phase_2_backtest/gate_ladder_verdict.json',
    'pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.md',
]
missing = [p for p in need if not Path(p).exists()]
print('MISSING:', missing) if missing else print('all deliverables present')
"
```
Expected: `all deliverables present`. If not, return to the failing task and finish.

- [ ] **Step 3: Update v3-evaluation README + system manual**

Edit `docs/v3-evaluation/README.md` — change Phase 2 entry to ✅ DONE with deliverable links.

Edit `docs/SYSTEM_OPERATIONS_MANUAL.md` — under v3 Standalone Evaluation, change to "Phase 0 + Phase 1 + Phase 2 COMPLETE (2026-04-XX). Phase 3 pre-registration draft pending lock."

- [ ] **Step 4: Verify gate-ladder verdict before tagging**

Read `gate_ladder_verdict.json`. If verdict is `pass`, proceed to tag. If `fail`, do NOT tag — write a `phase_2_blocked.md` listing each failed gate and the remediation owner; commit that and stop.

- [ ] **Step 5: Commit doc updates + tag the closeout**

```bash
git add docs/v3-evaluation/README.md docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "chore(v3-eval): Phase 2 complete — see gate_ladder_verdict.json"
git tag v3-eval-phase2-complete
```

- [ ] **Step 6: Hand-off summary**

Print a short summary of what passed/failed and what Phase 3 will pre-register. This is the message that goes back to the controller.

---

## Self-Review

After writing the plan above, with fresh eyes:

**1. Spec coverage.** Walk through master spec §6:
- §6.1 scope (5y OOS, both 126 + 273) ✅ T6/T7/T11/T21
- §6.2 walk-forward variants (3 lookbacks × cadence 5d × 2000 iter) ✅ T6/T21
- §6.3 markers (6) ✅ T8/T9/T10
- §6.4 backtest-spec compliance matrix:
  - §0.1–0.8 — written into §0 of this plan ✅
  - §1 slippage grid ✅ T14
  - §2 metrics per slip ✅ T14
  - §3 pass/fail ✅ T14 + T23
  - §5A data audit ✅ T15
  - §6 survivorship ✅ T16
  - §7 entry/exit ✅ T16
  - §8 direction audit ✅ T17
  - §9 sample size ✅ T11 + T23
  - §9A fragility ✅ T12
  - §9B permutation null + naive ✅ T11/T12
  - §10 OOS + purged ✅ T6
  - §11 liquidity ✅ T18
  - §11A implementation risk ✅ T19
  - §11B alpha-after-beta ✅ T13
  - §11C correlation gate — DEFERRED to Phase 3 task 1 (correlation requires deployed strategies; no v3 production deploy yet)
  - §12 edge decay ✅ T20
  - §13A reproducibility ✅ T5 + T21
  - §14 hypothesis registry — DEFERRED to Phase 3 task 1 (registration must be at lock, not pre-lock)
- §6.5 universe sensitivity ✅ T22
- §6.6 deliverables ✅ T22 + T23 + T24

**2. Placeholder scan.** Search for "TBD", "TODO", "implement later", "fill in", "similar to". None present — every code block contains either complete code or a small extension to a previously-shown function. The 4 alias mapping values in T4 (`L&TFH→LTFH`, `LTIM→LTIM`, `ZOMATO→ETERNAL`, `MCDOWELL-N→UNITDSPR`) are flagged in T4 step 3 to verify against `tickers list .xlsx` truth source before commit — that's not a placeholder, it's a verification step.

**3. Type consistency:** `RunConfig` defined T5 / used T6, T21. `PurgeConfig` T6. `RunWalkForward(...)` returns dict; consumed by orchestrator. Marker functions all take `(events: pd.DataFrame, ...) -> pd.DataFrame` shape. `GateVerdict` enum defined once T23. No naming drift.

**4. Phase 1 caveats addressed:**
- (a) single adjustment — T1 + T2 ✅
- (b) bulk/news/earnings canonical paths — T3 ✅
- (c) 4 alias gaps — T4 ✅

**5. §0 research-integrity coverage.** §0.1–0.8 are documented as honored in the closeout (T24) and the per-run manifest captures provenance per §0.7. §0.4 (slippage stress at S0–S2) is operationalized in T14. §0.3 (no p-value moving) is enforced by writing the verdict to `gate_ladder_verdict.json` immediately after orchestrator runs — not retroactively.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-v3-evaluation-phase-2.md`.

Two execution options:
1. **Subagent-Driven (recommended)** — controller dispatches fresh subagent per task with two-stage review (spec compliance + code quality)
2. **Inline Execution** — batch execution in this session via `superpowers:executing-plans`

Phase 1 ran subagent-driven and went cleanly through 21 tasks; same workflow recommended for Phase 2.
