# v3 Evaluation — Phase 0 + Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the v3 standalone evaluation project by (a) cataloging every v2 discovery + meta-lesson into a single constraint document, and (b) extending the 60-day intraday-break replay from 126 tickers to all 273 F&O tickers under full Data Policy §6/§9/§11/§13/§17 compliance.

**Architecture:** Phase 0 produces a single markdown catalog file referenced by all subsequent phases. Phase 1 adds a new module `pipeline/autoresearch/etf_v3_eval/` containing the Kite minute-bar backfill script, schema validator, cleanliness gate runner, cross-source reconciliation tool, and contamination map generator. The new module produces an extended replay parquet `intraday_break_replay_60d_v0.2_ungated.parquet` plus a §6 dataset-registration audit document. Phase 2 (separate plan) starts only after the §17 acceptance ladder confirms Approved-for-Tier-2-research status on the new dataset.

**Tech Stack:** Python 3.13, pandas, pyarrow, kiteconnect (existing wrapper at `pipeline/kite_session.py`), pytest, hashlib for SHA-256 manifests.

**Plan scope:** Phase 0 + Phase 1 of 4. Spec: `docs/superpowers/specs/2026-04-26-v3-evaluation-design.md`. Phase 2/3/4 plans written after this one completes.

---

## File Structure

**New files (Phase 0):**
- `docs/v3-evaluation/phase-0-v2-lessons-catalog.md` — single constraint document for the project
- `docs/v3-evaluation/README.md` — index of all v3-evaluation deliverables

**New files (Phase 1):**
- `pipeline/autoresearch/etf_v3_eval/__init__.py`
- `pipeline/autoresearch/etf_v3_eval/missing_tickers.py` — identify tickers in canonical_fno_v3 but not in replay
- `pipeline/autoresearch/etf_v3_eval/kite_backfill.py` — Kite minute-bar pull for missing tickers
- `pipeline/autoresearch/etf_v3_eval/schema_validator.py` — §8 schema contract enforcement
- `pipeline/autoresearch/etf_v3_eval/cleanliness_gates.py` — §9 cleanliness audit
- `pipeline/autoresearch/etf_v3_eval/cross_source_reconciliation.py` — §13 minute→daily aggregation vs EOD
- `pipeline/autoresearch/etf_v3_eval/contamination_map.py` — §14 channel mapping
- `pipeline/autoresearch/etf_v3_eval/build_extended_replay.py` — orchestrator producing v0.2 parquet
- `pipeline/autoresearch/etf_v3_eval/manifest.py` — §13A run manifest writer (commit, pip_freeze, seed, hash)
- `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md` — §6 registration doc

**New tests:**
- `pipeline/tests/test_etf_v3_eval/test_missing_tickers.py`
- `pipeline/tests/test_etf_v3_eval/test_kite_backfill.py`
- `pipeline/tests/test_etf_v3_eval/test_schema_validator.py`
- `pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py`
- `pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py`
- `pipeline/tests/test_etf_v3_eval/test_contamination_map.py`
- `pipeline/tests/test_etf_v3_eval/test_manifest.py`

**Modified files:**
- `pipeline/config/anka_inventory.json` — add nothing (no scheduled task in this phase; ad-hoc runs only)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — add a paragraph in "Research" section pointing to v3-evaluation deliverables

**Output artifacts (gitignored, not committed):**
- `pipeline/data/research/etf_v3_evaluation/phase_0_v2_lessons/catalog.md` (mirrored from docs/)
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/kite_backfill_log.txt`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_failed.csv`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/cleanliness_report.json`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/reconciliation_report.json`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/contamination_map.json`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json`
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_ungated.parquet`

---

## PHASE 0 — v2 Lessons Catalog

### Task 1: Create the v3-evaluation docs index

**Files:**
- Create: `docs/v3-evaluation/README.md`

- [ ] **Step 1: Create the directory and index file**

```bash
mkdir -p docs/v3-evaluation
```

Write `docs/v3-evaluation/README.md`:

```markdown
# v3 Standalone Evaluation Project — Documentation Index

Spec: [docs/superpowers/specs/2026-04-26-v3-evaluation-design.md](../superpowers/specs/2026-04-26-v3-evaluation-design.md)

## Phase 0 — v2 Lessons Catalog
- [phase-0-v2-lessons-catalog.md](phase-0-v2-lessons-catalog.md) — single constraint document for all subsequent phases

## Phase 1 — Universe Extension (data engineering)
- Data audit: [../superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md](../superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md)

## Phase 2 — Comprehensive Backtest
- Plan written after Phase 1 completes.

## Phase 3 — Forward Shadow
- Plan written after Phase 2 completes.

## Phase 4 — Attribution Catalog & Go/No-Go
- Plan written after Phase 3 window closes.
```

- [ ] **Step 2: Commit**

```bash
git add docs/v3-evaluation/README.md
git commit -m "docs(v3-eval): create v3-evaluation documentation index"
```

### Task 2: Write v2 lessons catalog — discoveries section

**Files:**
- Create: `docs/v3-evaluation/phase-0-v2-lessons-catalog.md`

- [ ] **Step 1: Create the catalog file with discoveries section**

Write `docs/v3-evaluation/phase-0-v2-lessons-catalog.md`:

```markdown
# v3 Evaluation — Phase 0: v2 Lessons Catalog

**Date:** 2026-04-26
**Spec:** [2026-04-26-v3-evaluation-design.md](../superpowers/specs/2026-04-26-v3-evaluation-design.md) §4
**Purpose:** Single constraint document referenced by every Phase 1–4 task. Re-read at the start of each phase.

## 1. v2 Discoveries — what we learned from running v2 in production

| # | Discovery | Evidence | Implication for v3 design | Test v3 must pass |
|---|---|---|---|---|
| D1 | regime_history.csv contamination — built with hindsight v2 weights, NOT a production audit trail | `memory/reference_regime_history_csv_contamination.md` | v3 must record zone-as-emitted, not zone-as-rebuilt | Phase 2 backtest reads only zone-as-emitted snapshots; Phase 3 shadow ledger writes zone at the moment of decision |
| D2 | PCR/OI multi-confirmation throttled trades historically | `memory/project_etf_v3_failed_2026_04_26.md` | v3 must not bolt PCR/OI back on as a second gate | Phase 2 marker decomposition does NOT include a PCR/OI marker; if added later requires its own holdout |
| D3 | OPPORTUNITY split into LAG/OVERSHOOT (#107 audit) — pooling masked failure | `memory/project_phase_c_follow_vs_fade_audit.md` | v3 gate must be tested separately on LAG vs OVERSHOOT slices | Phase 2 marker decomposition tables are stratified by LAG/OVERSHOOT; pooled-only verdicts are forbidden |
| D4 | σ bucket × regime coupling — buckets are NOT regime-independent | session 2026-04-26 conversation | v3 evaluation must condition σ buckets on regime | Phase 2 marker decomposition includes σ × regime cross-tab |
| D5 | POSSIBLE_OPPORTUNITY (+41.67pp/328) beat OPPORTUNITY_LAG (−3.30pp/60) — wrong slice was kept live | `memory/project_mechanical_60day_replay.md` | v3 gate granularity must match the actual P&L-bearing slice, not a category label | Phase 2 emits P&L per-slice; Phase 4 catalog flags any case where pooled verdict ≠ slice verdict |
| D6 | Single-touch holdout discipline (§13.1) burned 3 times in April | hypothesis-registry.jsonl entries for H-2026-04-25-001/002, H-2026-04-26-003 | v3 forward-test window must be pre-registered, single-use | Phase 3 pre-registration document SHA-256 hashed before window opens; rerun requires new hypothesis ID |
| D7 | SECTOR_FLIP exit reason is the leak (−69 bps mean, 9% hit, 83-min hold) | `pipeline/data/research/etf_v3/2026-04-26-exit-time-observations.md` | exit-rule changes interact with regime; v3 evaluation must hold exit rule fixed unless explicitly testing it | Phase 2 default exit = TIME_STOP 14:30 + ATR(14)×2 stop; alternative exits require their own marker entry |
| D8 | Z_CROSS in NEUTRAL = +41 bps refinement candidate | `pipeline/data/research/etf_v3/2026-04-26-neutral-tradability.md` | v3-NEUTRAL-day refinements have unexploited room | Phase 2 marker decomposition includes Z_CROSS-conditional sub-marker |
| D9 | Sector dynamics on NEUTRAL days are real — PSU BANK/BANK/PSE/ENERGY/INFRA SHORT-fades win (+200 to +390 bps); AUTO/IT/FMCG lose | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §3 | sector-conditional gating is a credible Phase 2 marker | Phase 2 includes sector-overlay marker with explicit per-sector P&L attribution |
| D10 | ETF coefficient rotation magnitude is a real "regime change marker" — 51.8 std units on 2025-12-30, 37.2 on 2026-04-16 align with v3 zone shifts | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §2 | coef-delta marker should be tested as a second-tier signal | Phase 2 includes coef-delta marker test |
| D11 | 5y vs 3y lookback is +6.3pp pooled OOS edge swing — v3 with longer history is materially better | `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb1200_curated.json` | v3 evaluation tests 3y vs 5y vs full-panel | Phase 2 walk-forward includes lookback-variant sweep |
| D12 | v3 NEUTRAL gate misapplied to H-001 SHORT engine kills P&L (NEUTRAL gate captures 4.3% of available SHORT P&L) | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §3 | v3 forecasts next-day NIFTY direction; H-001 fades intraday extremes — different time scales | Phase 2 must test v3 zone gate AND v3-direction-prior separately, not assume gate is the right application |
```

- [ ] **Step 2: Commit**

```bash
git add docs/v3-evaluation/phase-0-v2-lessons-catalog.md
git commit -m "docs(v3-eval): Phase 0 catalog — 12 v2 discoveries with implication + test"
```

### Task 3: Add meta-lessons section to catalog

**Files:**
- Modify: `docs/v3-evaluation/phase-0-v2-lessons-catalog.md`

- [ ] **Step 1: Append meta-lessons section**

Append to `docs/v3-evaluation/phase-0-v2-lessons-catalog.md`:

```markdown
## 2. Meta-lessons — gates v2 (and the spread engine) never had

These are gates that v2 systematically lacked. v3 evaluation treats them as table-stakes.

| # | Gate v2 lacked | Why it mattered | How v3 honors it |
|---|---|---|---|
| M1 | 5y training history | v2 trained on 3y → missed regime cycles; cycle-3 acc was 47% | Phase 2 walk-forward tests 3y / 5y / full-panel lookback variants; pooled OOS edge reported per variant |
| M2 | Data validation policy (§6 registration) | ETF panel was used without §6 audit; bit us when SectorMapper artifacts went missing on Contabo | Phase 1 dataset registration is a HARD gate; Phase 2 backtests refuse to read parquet without §17 Approved-for-Tier-2-research stamp |
| M3 | §13A run-manifest reproducibility | Spread engine results not reproducible — no commit hash, no requirements freeze, no seed disclosure | Every Phase 1+2+3 run produces a manifest with commit, pip_freeze, seed, config, file hashes |
| M4 | §14 hypothesis pre-registration with §14.5 family denominator | ~20 spread variants tested without declaring family — multiplicity denominator was retroactive | Phase 3 hypothesis pre-registered with family denominator declared at lock; Phase 2 family declared at start of marker decomposition |
| M5 | §11A implementation-risk simulation | v2 backtests assumed perfect execution; real Phase C had missed entries unmodeled | Phase 2 runs all 10 §11A.1 failure scenarios (missed entries, missed exits, delayed fills, halts, etc.) |
| M6 | §10.4 single-use OOS | H-001/H-002/H-003 re-tested against same 60d window — 3 holdout burns this month | Phase 3 window single-use; rerun requires new window + new hypothesis ID |
| M7 | §9A parameter fragility | Cadence-sweep verdict was on a single seed; never proved local stability | Phase 2 fragility test mandatory (3 stability conditions per §9A.2) |
| M8 | Cross-source reconciliation (§13) | Kite minute bars never sample-checked against EOD parquet | Phase 1 mandates 5-ticker sample reconciliation (max delta < 0.5%) before §17 acceptance |

## 3. How this catalog is used

- Each Phase 1–4 task references the discoveries (Dn) and meta-lessons (Mn) it honors
- At end of each phase: review this catalog; flag any unresolved discovery/lesson
- Phase 4 final go/no-go must include a per-Dn and per-Mn pass/fail verdict
```

- [ ] **Step 2: Commit**

```bash
git add docs/v3-evaluation/phase-0-v2-lessons-catalog.md
git commit -m "docs(v3-eval): Phase 0 catalog — add meta-lessons (M1-M8) section"
```

### Task 4: Cross-link catalog from spec + system manual

**Files:**
- Modify: `docs/superpowers/specs/2026-04-26-v3-evaluation-design.md` (add catalog link to §4.3)
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` (add Research section reference)

- [ ] **Step 1: Update spec §4.3 to link the live catalog**

Find the line in `docs/superpowers/specs/2026-04-26-v3-evaluation-design.md` that says:

```
`docs/v3-evaluation/phase-0-v2-lessons-catalog.md` — committed before Phase 1 starts. Re-read at start of each subsequent phase as constraint review.
```

Replace with:

```
[`docs/v3-evaluation/phase-0-v2-lessons-catalog.md`](../../v3-evaluation/phase-0-v2-lessons-catalog.md) — committed before Phase 1 starts. Re-read at start of each subsequent phase as constraint review. **Status:** committed at Phase 0 task 3.
```

- [ ] **Step 2: Append a Research section reference to SYSTEM_OPERATIONS_MANUAL**

Find the last `## ` section in `docs/SYSTEM_OPERATIONS_MANUAL.md` and append a new section:

```markdown
## Research Projects (active)

- **v3 Standalone Evaluation** — comprehensive backtest + forward-shadow project for the v3-CURATED ETF regime engine. Spec: [docs/superpowers/specs/2026-04-26-v3-evaluation-design.md](superpowers/specs/2026-04-26-v3-evaluation-design.md). Phase 0 catalog: [docs/v3-evaluation/phase-0-v2-lessons-catalog.md](v3-evaluation/phase-0-v2-lessons-catalog.md). Status: Phase 0 + Phase 1 in progress.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-26-v3-evaluation-design.md docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs(v3-eval): cross-link Phase 0 catalog from spec + system manual"
```

---

## PHASE 1 — Universe Extension

### Task 5: Identify the 147 missing tickers

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/__init__.py`
- Create: `pipeline/autoresearch/etf_v3_eval/missing_tickers.py`
- Create: `pipeline/tests/test_etf_v3_eval/__init__.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_missing_tickers.py`

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_etf_v3_eval/__init__.py` (empty file).

Write `pipeline/tests/test_etf_v3_eval/test_missing_tickers.py`:

```python
"""Tests for missing-ticker identification."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.missing_tickers import (
    list_canonical_fno_tickers,
    list_replay_tickers,
    compute_missing,
)


def test_list_canonical_fno_tickers_returns_strings(tmp_path: Path) -> None:
    canon_file = tmp_path / "canon.json"
    canon_file.write_text('{"tickers": ["RELIANCE", "TCS", "INFY"]}', encoding="utf-8")
    result = list_canonical_fno_tickers(canon_file)
    assert result == ["RELIANCE", "TCS", "INFY"]


def test_list_replay_tickers_returns_unique_set(tmp_path: Path) -> None:
    parquet = tmp_path / "replay.parquet"
    pd.DataFrame({"ticker": ["TCS", "TCS", "INFY"], "trade_date": ["2026-01-01"] * 3}).to_parquet(parquet)
    result = list_replay_tickers(parquet)
    assert sorted(result) == ["INFY", "TCS"]


def test_compute_missing_returns_canon_minus_replay() -> None:
    canon = ["RELIANCE", "TCS", "INFY"]
    replay = ["TCS", "INFY"]
    assert compute_missing(canon, replay) == ["RELIANCE"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_missing_tickers.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.autoresearch.etf_v3_eval'`

- [ ] **Step 3: Implement missing_tickers**

Create `pipeline/autoresearch/etf_v3_eval/__init__.py` (empty file).

Write `pipeline/autoresearch/etf_v3_eval/missing_tickers.py`:

```python
"""Identify F&O tickers in canonical universe but not yet in 60-day replay."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def list_canonical_fno_tickers(path: Path) -> list[str]:
    """Read canonical_fno_research_v3.json and return ticker list."""
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "tickers" in data:
        return [str(t).upper() for t in data["tickers"]]
    if isinstance(data, list):
        return [str(t).upper() for t in data]
    if isinstance(data, dict):
        return [str(t).upper() for t in data.keys()]
    raise ValueError(f"Unrecognized canonical universe format: {type(data)}")


def list_replay_tickers(path: Path) -> list[str]:
    """Read intraday-break replay parquet and return unique ticker list."""
    df = pd.read_parquet(path)
    return sorted({str(t).upper() for t in df["ticker"].unique()})


def compute_missing(canonical: list[str], replay: list[str]) -> list[str]:
    """Return tickers in canonical but not in replay, sorted."""
    return sorted(set(canonical) - set(replay))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_missing_tickers.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/__init__.py pipeline/autoresearch/etf_v3_eval/missing_tickers.py pipeline/tests/test_etf_v3_eval/__init__.py pipeline/tests/test_etf_v3_eval/test_missing_tickers.py
git commit -m "feat(v3-eval): identify missing tickers between canonical F&O and replay"
```

### Task 6: Run missing-ticker discovery against live files + write CSV

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/run_missing.py`

- [ ] **Step 1: Write the runner script**

Write `pipeline/autoresearch/etf_v3_eval/run_missing.py`:

```python
"""CLI to identify missing tickers and write tickers_added.csv."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.missing_tickers import (
    compute_missing,
    list_canonical_fno_tickers,
    list_replay_tickers,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Identify F&O tickers missing from replay")
    parser.add_argument("--canon", default="pipeline/data/canonical_fno_research_v3.json")
    parser.add_argument("--replay", default="pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet")
    parser.add_argument("--out", default="pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv")
    args = parser.parse_args()

    canon = list_canonical_fno_tickers(Path(args.canon))
    replay = list_replay_tickers(Path(args.replay))
    missing = compute_missing(canon, replay)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": missing}).to_csv(out_path, index=False)

    print(f"canonical: {len(canon)} tickers")
    print(f"replay:    {len(replay)} tickers")
    print(f"missing:   {len(missing)} tickers")
    print(f"wrote:     {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run script against live data**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.run_missing
```

Expected output:
```
canonical: 273 tickers
replay:    126 tickers
missing:   147 tickers
wrote:     pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv
```

- [ ] **Step 3: Commit the script**

```bash
git add pipeline/autoresearch/etf_v3_eval/run_missing.py
git commit -m "feat(v3-eval): CLI to write tickers_added.csv (147 missing identified)"
```

### Task 7: Write §6 data-source audit document for Kite minute backfill

**Files:**
- Create: `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`

- [ ] **Step 1: Write the audit document**

Use the template structure from `docs/superpowers/specs/2026-04-25-earnings-data-source-audit.md` if it exists; otherwise write from Data Policy §6 fields. Write `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`:

```markdown
# Kite Minute Bars — F&O 273 Universe Data Source Audit

**Date:** 2026-04-26
**Dataset name:** `intraday_break_replay_60d_v0.2_ungated`
**Owner:** Bharat Ankaraju
**Tier:** Tier 2 (research input feeding deployable strategy)
**Status:** Pending acceptance — to be promoted at Phase 1 task 18

## §6.1 Source identification
- **Vendor:** Zerodha Kite Connect
- **Endpoint:** `kite.historical_data(token, from, to, interval='minute')`
- **Wrapper:** `pipeline/kite_session.py`
- **Authentication:** persisted session refresh (per AnkaRefreshKite 09:00 IST job)

## §6.2 Live verification at onboarding
- Sample retrieval: 1-day pull on RELIANCE (2026-04-23) verified non-empty + non-zero volume bars
- Schema field presence: `date`, `open`, `high`, `low`, `close`, `volume` — confirmed

## §7 Lineage
- Per-ticker manifest entry: ticker symbol, instrument token, retrieval timestamp UTC, code commit hash, request parameters
- Stored at `pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json`

## §8 Schema contract
Frozen contract (one row per minute per ticker):

| Column | Type | Constraint |
|---|---|---|
| ticker | str | NSE F&O symbol, uppercase |
| trade_date | date | trading day (IST) |
| timestamp | datetime64[ns, Asia/Kolkata] | minute granularity, 09:15:00 ≤ t ≤ 15:30:00 |
| open, high, low, close | float64 | > 0; high ≥ low |
| volume | int64 | ≥ 0 |

## §9 Cleanliness gates (acceptance thresholds)
- Missing-bar % per ticker per day: ≤ 5% (375 minutes per session × 0.05 = ≤ 19 missing minutes)
- Zero-volume bars: tracked but not blocking
- After-hours bars (outside 09:15–15:30 IST): must be 0
- Holiday handling: NSE trading-day calendar enforced; non-trading days produce no bars
- Acceptance threshold per §9.2: any ticker exceeding missing-bar % is moved to `tickers_failed.csv` and excluded from the v0.2 parquet

## §10 Adjustment mode
- Mode declaration: **Unadjusted** intraday bars per Kite default
- Corporate action handling: any ticker with corp-action in window 2026-02-26 → 2026-04-23 logged with date + type
- Downstream backtest must apply consistent adjustment treatment

## §11 PIT correctness
- Bars written exactly as Kite emitted at retrieval time
- No ex-post correction of historical values
- Restated bars (Kite revisions) flagged with retrieval-timestamp diff in manifest

## §12 Survivorship
- Universe construction: `canonical_fno_research_v3.json` (273 tickers, snapshot 2026-04-26)
- Any ticker delisted between 2026-02-26 and 2026-04-23 documented in `tickers_failed.csv` with reason
- 5 active aliases per `memory/reference_pit_ticker_list.md` resolved before retrieval

## §13 Cross-source reconciliation
- 5 sample tickers (RELIANCE, TCS, HDFC BANK, ICICIBANK, INFY) aggregated minute → daily OHLC
- Compared to EOD parquet `pipeline/data/historical_bars/<ticker>.parquet`
- Acceptance: max |Δclose| < 0.5% per ticker per day in window
- Report: `pipeline/data/research/etf_v3_evaluation/phase_1_universe/reconciliation_report.json`

## §14 Contamination map
Channels mapped per ticker for the 60-day window:
- Bulk-deals (NSE bulk + block CSV) — joined on trade_date
- Insider trades (NSE PIT disclosures) — joined on trade_date ± 7d
- News (existing news pipeline output) — joined on trade_date
- Earnings calendar (IndianAPI corporate_actions) — joined on trade_date ± 1d
- Output: `pipeline/data/research/etf_v3_evaluation/phase_1_universe/contamination_map.json`

## §17 Acceptance ladder
| Status | Criteria | Reached when |
|---|---|---|
| Onboarded | §6 + §7 fields present | After Phase 1 task 8 |
| Validated | §8 + §9 + §11 pass | After Phase 1 task 14 |
| Reconciled | §13 max-delta < 0.5% | After Phase 1 task 16 |
| **Approved-for-Tier-2-research** | All above + §14 contamination map present + §10 adjustments declared | **After Phase 1 task 18** |

## §21 Model binding
- Downstream model: v3-CURATED regime engine
- Approved status of this dataset is REQUIRED for v3 Phase 2 backtest
- Demotion of this dataset (e.g., schema drift, freshness violation) automatically demotes any v3 result built on it
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md
git commit -m "spec(v3-eval): §6 data-source audit for Kite minute bars FNO 273"
```

### Task 8: Build the run-manifest writer

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/manifest.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_manifest.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_manifest.py`:

```python
"""Tests for run-manifest writer (Backtest Spec §13A)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline.autoresearch.etf_v3_eval.manifest import write_manifest


def test_write_manifest_records_required_fields(tmp_path: Path) -> None:
    out = tmp_path / "manifest.json"
    config = {"lookback_days": 1200, "seed": 42}
    sample_file = tmp_path / "sample.parquet"
    sample_file.write_bytes(b"hello")

    write_manifest(
        out_path=out,
        run_id="test_run_1",
        config=config,
        seed=42,
        artifact_paths=[sample_file],
    )

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_id"] == "test_run_1"
    assert data["config"] == config
    assert data["seed"] == 42
    assert "git_commit" in data
    assert "generated_at_utc" in data
    assert "pip_freeze_sha256" in data
    assert "artifacts" in data
    expected_hash = hashlib.sha256(b"hello").hexdigest()
    assert data["artifacts"][str(sample_file)] == expected_hash
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_manifest.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.autoresearch.etf_v3_eval.manifest'`

- [ ] **Step 3: Implement manifest writer**

Write `pipeline/autoresearch/etf_v3_eval/manifest.py`:

```python
"""Run manifest writer per Backtest Spec §13A.1."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def _pip_freeze_sha256() -> str:
    try:
        result = subprocess.run(
            ["pip", "freeze"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    out_path: Path,
    run_id: str,
    config: dict[str, Any],
    seed: int,
    artifact_paths: list[Path],
) -> None:
    """Write a §13A.1-compliant run manifest."""
    manifest = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "git_commit": _git_commit_hash(),
        "pip_freeze_sha256": _pip_freeze_sha256(),
        "seed": seed,
        "config": config,
        "artifacts": {str(p): _file_sha256(p) for p in artifact_paths if Path(p).exists()},
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_manifest.py -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/manifest.py pipeline/tests/test_etf_v3_eval/test_manifest.py
git commit -m "feat(v3-eval): §13A.1 run-manifest writer with commit + pip_freeze + file SHAs"
```

### Task 9: Build Kite minute-bar backfill (single-ticker function)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/kite_backfill.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_kite_backfill.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_kite_backfill.py`:

```python
"""Tests for Kite minute-bar backfill."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.kite_backfill import (
    fetch_minute_bars,
    BackfillFailure,
)


def _kite_response_factory():
    """Mock Kite response for one ticker, two minutes."""
    return [
        {"date": pd.Timestamp("2026-04-23 09:15:00+0530"), "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 1000},
        {"date": pd.Timestamp("2026-04-23 09:16:00+0530"), "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1500},
    ]


def test_fetch_minute_bars_returns_dataframe() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {"NSE:RELIANCE": {"instrument_token": 738561}}
    kite.historical_data.return_value = _kite_response_factory()
    df = fetch_minute_bars(kite, "RELIANCE", date(2026, 4, 23), date(2026, 4, 23))
    assert len(df) == 2
    assert set(df.columns) >= {"ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"}
    assert (df["ticker"] == "RELIANCE").all()


def test_fetch_minute_bars_raises_on_empty_response() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {"NSE:GHOST": {"instrument_token": 999999}}
    kite.historical_data.return_value = []
    with pytest.raises(BackfillFailure, match="empty"):
        fetch_minute_bars(kite, "GHOST", date(2026, 4, 23), date(2026, 4, 23))


def test_fetch_minute_bars_raises_on_unknown_ticker() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {}
    with pytest.raises(BackfillFailure, match="instrument_token"):
        fetch_minute_bars(kite, "UNKNOWN", date(2026, 4, 23), date(2026, 4, 23))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_kite_backfill.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.autoresearch.etf_v3_eval.kite_backfill'`

- [ ] **Step 3: Implement kite_backfill**

Write `pipeline/autoresearch/etf_v3_eval/kite_backfill.py`:

```python
"""Kite minute-bar backfill for F&O tickers — single-ticker fetcher.

Per Data Policy §6 (source registration), §7 (lineage), §11 (PIT correctness):
this module retrieves historical minute bars exactly as Kite emits them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

import pandas as pd


class BackfillFailure(Exception):
    """Ticker could not be backfilled (no instrument token, empty response, schema violation)."""


class KiteClient(Protocol):
    def ltp(self, symbols: list[str]) -> dict: ...
    def historical_data(self, token: int, from_: datetime, to: datetime, interval: str) -> list[dict]: ...


def fetch_minute_bars(kite: KiteClient, ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch minute bars for one ticker over [start, end] inclusive.

    Returns DataFrame with columns: ticker, trade_date, timestamp, open, high, low, close, volume.
    Raises BackfillFailure on empty response or unknown ticker.
    """
    nse_symbol = f"NSE:{ticker}"
    ltp = kite.ltp([nse_symbol])
    if nse_symbol not in ltp or "instrument_token" not in ltp[nse_symbol]:
        raise BackfillFailure(f"no instrument_token for {ticker}")
    token = ltp[nse_symbol]["instrument_token"]

    bars = kite.historical_data(
        token,
        datetime.combine(start, datetime.min.time()),
        datetime.combine(end, datetime.max.time()),
        "minute",
    )
    if not bars:
        raise BackfillFailure(f"empty response for {ticker}")

    df = pd.DataFrame(bars)
    df = df.rename(columns={"date": "timestamp"})
    df["ticker"] = ticker
    df["trade_date"] = df["timestamp"].dt.date
    cols = ["ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"]
    return df[cols]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_kite_backfill.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/kite_backfill.py pipeline/tests/test_etf_v3_eval/test_kite_backfill.py
git commit -m "feat(v3-eval): single-ticker Kite minute-bar fetcher with explicit failures"
```

### Task 10: Build schema validator (§8 contract enforcement)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/schema_validator.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_schema_validator.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_schema_validator.py`:

```python
"""Tests for §8 schema contract validator."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.schema_validator import (
    SchemaViolation,
    validate_minute_bars_schema,
)


def _good_df() -> pd.DataFrame:
    ts = pd.Timestamp("2026-04-23 09:15:00", tz="Asia/Kolkata")
    return pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "timestamp": [ts],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [1000],
    })


def test_validate_passes_on_good_dataframe() -> None:
    validate_minute_bars_schema(_good_df())  # should not raise


def test_validate_rejects_missing_column() -> None:
    df = _good_df().drop(columns=["volume"])
    with pytest.raises(SchemaViolation, match="missing columns"):
        validate_minute_bars_schema(df)


def test_validate_rejects_non_positive_price() -> None:
    df = _good_df()
    df["open"] = -1.0
    with pytest.raises(SchemaViolation, match="non-positive"):
        validate_minute_bars_schema(df)


def test_validate_rejects_high_below_low() -> None:
    df = _good_df()
    df.loc[0, "high"] = 50.0
    df.loc[0, "low"] = 100.0
    with pytest.raises(SchemaViolation, match="high < low"):
        validate_minute_bars_schema(df)


def test_validate_rejects_negative_volume() -> None:
    df = _good_df()
    df["volume"] = -1
    with pytest.raises(SchemaViolation, match="negative volume"):
        validate_minute_bars_schema(df)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_schema_validator.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement schema_validator**

Write `pipeline/autoresearch/etf_v3_eval/schema_validator.py`:

```python
"""Schema contract validator per Data Policy §8."""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = {"ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"}
PRICE_COLS = ["open", "high", "low", "close"]


class SchemaViolation(Exception):
    """Frame violates the §8 contract."""


def validate_minute_bars_schema(df: pd.DataFrame) -> None:
    """Raise SchemaViolation if the contract is broken; return None on pass."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise SchemaViolation(f"missing columns: {sorted(missing)}")

    for col in PRICE_COLS:
        if (df[col] <= 0).any():
            raise SchemaViolation(f"non-positive value in {col}")

    if (df["high"] < df["low"]).any():
        raise SchemaViolation("high < low in at least one row")

    if (df["volume"] < 0).any():
        raise SchemaViolation("negative volume in at least one row")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_schema_validator.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/schema_validator.py pipeline/tests/test_etf_v3_eval/test_schema_validator.py
git commit -m "feat(v3-eval): §8 schema contract validator for minute bars"
```

### Task 11: Build cleanliness gate runner (§9.2 thresholds)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/cleanliness_gates.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py`:

```python
"""Tests for §9 cleanliness gates."""
from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.cleanliness_gates import (
    GateResult,
    run_cleanliness_gates,
    EXPECTED_MINUTES_PER_SESSION,
)


def _build_session(ticker: str, day: date, n_minutes: int) -> pd.DataFrame:
    """Build n_minutes consecutive 1-min bars starting at 09:15 IST."""
    rows = []
    for i in range(n_minutes):
        ts = pd.Timestamp.combine(day, time(9, 15)).tz_localize("Asia/Kolkata") + pd.Timedelta(minutes=i)
        rows.append({
            "ticker": ticker, "trade_date": day, "timestamp": ts,
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100,
        })
    return pd.DataFrame(rows)


def test_full_session_passes() -> None:
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION)
    result = run_cleanliness_gates(df)
    assert result.passed
    assert result.missing_pct == 0.0


def test_missing_above_threshold_fails() -> None:
    # 5% threshold = 18.75 minutes; 50 missing > threshold
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION - 50)
    result = run_cleanliness_gates(df)
    assert not result.passed
    assert "missing" in result.failures[0]


def test_after_hours_bar_fails() -> None:
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION)
    bad_ts = pd.Timestamp.combine(date(2026, 4, 23), time(16, 0)).tz_localize("Asia/Kolkata")
    bad_row = pd.DataFrame([{
        "ticker": "RELIANCE", "trade_date": date(2026, 4, 23), "timestamp": bad_ts,
        "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100,
    }])
    df_bad = pd.concat([df, bad_row], ignore_index=True)
    result = run_cleanliness_gates(df_bad)
    assert not result.passed
    assert "after-hours" in result.failures[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement cleanliness_gates**

Write `pipeline/autoresearch/etf_v3_eval/cleanliness_gates.py`:

```python
"""§9 cleanliness gates for minute-bar parquet."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import pandas as pd

EXPECTED_MINUTES_PER_SESSION = 375  # 09:15 to 15:30 IST = 6h15m
MISSING_PCT_THRESHOLD = 0.05  # §9.2 acceptance threshold
SESSION_START = time(9, 15)
SESSION_END = time(15, 30)


@dataclass
class GateResult:
    passed: bool
    missing_pct: float
    failures: list[str] = field(default_factory=list)


def run_cleanliness_gates(df: pd.DataFrame) -> GateResult:
    """Apply §9.2 acceptance thresholds. Returns GateResult."""
    failures: list[str] = []

    n_dates = df["trade_date"].nunique()
    expected_total = n_dates * EXPECTED_MINUTES_PER_SESSION
    actual_total = len(df)
    missing_pct = max(0.0, (expected_total - actual_total) / expected_total) if expected_total else 0.0

    if missing_pct > MISSING_PCT_THRESHOLD:
        failures.append(
            f"missing-bar % = {missing_pct:.4f} exceeds threshold {MISSING_PCT_THRESHOLD}"
        )

    times = df["timestamp"].dt.time
    after_hours = ((times < SESSION_START) | (times > SESSION_END)).sum()
    if after_hours > 0:
        failures.append(f"after-hours bars present: {after_hours}")

    return GateResult(passed=len(failures) == 0, missing_pct=missing_pct, failures=failures)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/cleanliness_gates.py pipeline/tests/test_etf_v3_eval/test_cleanliness_gates.py
git commit -m "feat(v3-eval): §9.2 cleanliness gates (missing-bar %, after-hours)"
```

### Task 12: Build cross-source reconciliation (§13)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/cross_source_reconciliation.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py`:

```python
"""Tests for §13 cross-source reconciliation."""
from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.cross_source_reconciliation import (
    aggregate_minute_to_daily,
    compare_to_eod,
    ReconciliationFailure,
    MAX_DELTA_PCT,
)


def _minute_session(close_path: list[float]) -> pd.DataFrame:
    """Build a session of `len(close_path)` minutes; close prices follow the path."""
    rows = []
    for i, close in enumerate(close_path):
        ts = pd.Timestamp.combine(date(2026, 4, 23), time(9, 15)).tz_localize("Asia/Kolkata") + pd.Timedelta(minutes=i)
        rows.append({
            "ticker": "RELIANCE", "trade_date": date(2026, 4, 23), "timestamp": ts,
            "open": close, "high": close, "low": close, "close": close, "volume": 100,
        })
    return pd.DataFrame(rows)


def test_aggregate_yields_daily_ohlc() -> None:
    minute_df = _minute_session([100.0, 105.0, 95.0, 102.0])
    daily = aggregate_minute_to_daily(minute_df)
    assert len(daily) == 1
    row = daily.iloc[0]
    assert row["open"] == 100.0
    assert row["high"] == 105.0
    assert row["low"] == 95.0
    assert row["close"] == 102.0


def test_compare_passes_when_within_threshold() -> None:
    minute_df = _minute_session([100.0, 100.0, 100.0, 100.0])
    eod_df = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "close": [100.2],
    })
    report = compare_to_eod(minute_df, eod_df)
    assert report["max_delta_pct"] < MAX_DELTA_PCT


def test_compare_raises_when_above_threshold() -> None:
    minute_df = _minute_session([100.0])
    eod_df = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "close": [105.0],  # 5% delta — way over 0.5%
    })
    with pytest.raises(ReconciliationFailure, match="exceeds"):
        compare_to_eod(minute_df, eod_df, raise_on_failure=True)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement cross_source_reconciliation**

Write `pipeline/autoresearch/etf_v3_eval/cross_source_reconciliation.py`:

```python
"""§13 cross-source reconciliation: aggregate minutes → daily, compare to EOD parquet."""
from __future__ import annotations

import pandas as pd

MAX_DELTA_PCT = 0.005  # §13 acceptance: max 0.5% delta


class ReconciliationFailure(Exception):
    """Aggregated minute-bar daily OHLC diverges from EOD source beyond threshold."""


def aggregate_minute_to_daily(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Group minute bars into daily OHLC + volume per ticker per trade_date."""
    g = minute_df.sort_values("timestamp").groupby(["ticker", "trade_date"], as_index=False)
    return g.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )


def compare_to_eod(minute_df: pd.DataFrame, eod_df: pd.DataFrame, raise_on_failure: bool = False) -> dict:
    """Compare minute-aggregated daily close to EOD source close.

    Returns report dict with max_delta_pct + per-row deltas.
    Raises ReconciliationFailure if raise_on_failure and max_delta_pct > MAX_DELTA_PCT.
    """
    daily = aggregate_minute_to_daily(minute_df)
    merged = daily[["ticker", "trade_date", "close"]].rename(columns={"close": "close_minute"}).merge(
        eod_df[["ticker", "trade_date", "close"]].rename(columns={"close": "close_eod"}),
        on=["ticker", "trade_date"],
    )
    merged["delta_pct"] = (merged["close_minute"] - merged["close_eod"]).abs() / merged["close_eod"]
    max_delta = float(merged["delta_pct"].max()) if len(merged) else 0.0
    report = {
        "max_delta_pct": max_delta,
        "n_rows_compared": len(merged),
        "rows_above_threshold": int((merged["delta_pct"] > MAX_DELTA_PCT).sum()),
    }
    if raise_on_failure and max_delta > MAX_DELTA_PCT:
        raise ReconciliationFailure(
            f"max_delta_pct {max_delta:.4f} exceeds threshold {MAX_DELTA_PCT}"
        )
    return report
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/cross_source_reconciliation.py pipeline/tests/test_etf_v3_eval/test_cross_source_reconciliation.py
git commit -m "feat(v3-eval): §13 cross-source reconciliation, 0.5% close-delta threshold"
```

### Task 13: Build contamination map (§14)

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/contamination_map.py`
- Create: `pipeline/tests/test_etf_v3_eval/test_contamination_map.py`

- [ ] **Step 1: Write the failing test**

Write `pipeline/tests/test_etf_v3_eval/test_contamination_map.py`:

```python
"""Tests for §14 contamination map."""
from __future__ import annotations

from datetime import date

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.contamination_map import build_contamination_map


def test_map_records_bulk_deals_per_ticker_per_date() -> None:
    tickers = ["RELIANCE", "TCS"]
    dates = [date(2026, 4, 23)]
    bulk_deals = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "qty": [100000],
        "client": ["FII-A"],
    })
    insider = pd.DataFrame(columns=["ticker", "trade_date", "value"])
    news = pd.DataFrame(columns=["ticker", "trade_date", "headline"])
    earnings = pd.DataFrame(columns=["ticker", "trade_date", "event"])

    cm = build_contamination_map(tickers, dates, bulk_deals, insider, news, earnings)
    rel = cm["RELIANCE"]["2026-04-23"]
    assert rel["bulk_deals"] == 1
    assert rel["insider"] == 0
    assert rel["news"] == 0
    assert rel["earnings"] == 0
    tcs = cm["TCS"]["2026-04-23"]
    assert tcs["bulk_deals"] == 0


def test_map_returns_empty_when_no_events() -> None:
    cm = build_contamination_map(
        ["RELIANCE"], [date(2026, 4, 23)],
        pd.DataFrame(columns=["ticker", "trade_date", "qty", "client"]),
        pd.DataFrame(columns=["ticker", "trade_date", "value"]),
        pd.DataFrame(columns=["ticker", "trade_date", "headline"]),
        pd.DataFrame(columns=["ticker", "trade_date", "event"]),
    )
    assert cm["RELIANCE"]["2026-04-23"] == {"bulk_deals": 0, "insider": 0, "news": 0, "earnings": 0}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_contamination_map.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement contamination_map**

Write `pipeline/autoresearch/etf_v3_eval/contamination_map.py`:

```python
"""§14 contamination map — count event-channel hits per ticker per trade_date."""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def _count_per_ticker_date(events: pd.DataFrame, ticker: str, day: date) -> int:
    if events.empty:
        return 0
    mask = (events["ticker"] == ticker) & (events["trade_date"] == day)
    return int(mask.sum())


def build_contamination_map(
    tickers: list[str],
    dates: list[date],
    bulk_deals: pd.DataFrame,
    insider: pd.DataFrame,
    news: pd.DataFrame,
    earnings: pd.DataFrame,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {ticker: {date_iso: {channel: count}}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for ticker in tickers:
        out[ticker] = {}
        for day in dates:
            iso = day.isoformat()
            out[ticker][iso] = {
                "bulk_deals": _count_per_ticker_date(bulk_deals, ticker, day),
                "insider": _count_per_ticker_date(insider, ticker, day),
                "news": _count_per_ticker_date(news, ticker, day),
                "earnings": _count_per_ticker_date(earnings, ticker, day),
            }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/test_contamination_map.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_v3_eval/contamination_map.py pipeline/tests/test_etf_v3_eval/test_contamination_map.py
git commit -m "feat(v3-eval): §14 contamination map (bulk-deals/insider/news/earnings counts)"
```

### Task 14: Build the orchestrator that drives Phase 1 end-to-end

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/build_extended_replay.py`

- [ ] **Step 1: Write the orchestrator script**

Write `pipeline/autoresearch/etf_v3_eval/build_extended_replay.py`:

```python
"""Phase 1 orchestrator: backfill 147 missing F&O tickers, validate, reconcile, write v0.2 parquet.

Usage:
    python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --dry-run
    python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --tickers-csv pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.cleanliness_gates import run_cleanliness_gates
from pipeline.autoresearch.etf_v3_eval.kite_backfill import BackfillFailure, fetch_minute_bars
from pipeline.autoresearch.etf_v3_eval.manifest import write_manifest
from pipeline.autoresearch.etf_v3_eval.schema_validator import (
    SchemaViolation,
    validate_minute_bars_schema,
)
from pipeline.kite_client import get_kite

logger = logging.getLogger(__name__)

START_DATE = date(2026, 2, 26)
END_DATE = date(2026, 4, 23)
OUTPUT_DIR = Path("pipeline/data/research/etf_v3_evaluation/phase_1_universe")
RAW_OUTPUT = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")


def backfill_one(kite, ticker: str) -> tuple[pd.DataFrame | None, str | None]:
    """Return (frame, None) on success, (None, reason) on failure."""
    try:
        df = fetch_minute_bars(kite, ticker, START_DATE, END_DATE)
    except BackfillFailure as e:
        return None, f"backfill: {e}"
    try:
        validate_minute_bars_schema(df)
    except SchemaViolation as e:
        return None, f"schema: {e}"
    gates = run_cleanliness_gates(df)
    if not gates.passed:
        return None, f"cleanliness: {gates.failures}"
    return df, None


def run(tickers: list[str], dry_run: bool = False) -> dict:
    """Backfill the supplied tickers; return summary dict."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failed_rows: list[dict] = []
    success_frames: list[pd.DataFrame] = []

    if dry_run:
        logger.info("DRY RUN — would backfill %d tickers", len(tickers))
        return {"dry_run": True, "n_tickers": len(tickers)}

    kite = get_kite()
    for i, ticker in enumerate(tickers, start=1):
        logger.info("[%d/%d] %s", i, len(tickers), ticker)
        df, err = backfill_one(kite, ticker)
        if err is not None:
            failed_rows.append({"ticker": ticker, "reason": err})
            continue
        success_frames.append(df)

    pd.DataFrame(failed_rows).to_csv(OUTPUT_DIR / "tickers_failed.csv", index=False)

    if success_frames:
        full = pd.concat(success_frames, ignore_index=True)
        RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        full.to_parquet(RAW_OUTPUT, index=False)

    summary = {
        "n_requested": len(tickers),
        "n_succeeded": len(success_frames),
        "n_failed": len(failed_rows),
        "raw_output": str(RAW_OUTPUT) if success_frames else None,
    }
    (OUTPUT_DIR / "backfill_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    write_manifest(
        out_path=OUTPUT_DIR / "manifest.json",
        run_id=f"phase1_backfill_{START_DATE.isoformat()}_{END_DATE.isoformat()}",
        config={"start": START_DATE.isoformat(), "end": END_DATE.isoformat(), "n_tickers": len(tickers)},
        seed=0,
        artifact_paths=[RAW_OUTPUT, OUTPUT_DIR / "tickers_failed.csv", OUTPUT_DIR / "backfill_summary.json"],
    )
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers-csv", default=str(OUTPUT_DIR / "tickers_added.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tickers = pd.read_csv(args.tickers_csv)["ticker"].tolist()
    summary = run(tickers, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Dry-run the orchestrator to verify wiring**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --dry-run
```

Expected output (JSON):
```
{
  "dry_run": true,
  "n_tickers": 147
}
```

- [ ] **Step 3: Commit the orchestrator**

```bash
git add pipeline/autoresearch/etf_v3_eval/build_extended_replay.py
git commit -m "feat(v3-eval): Phase 1 orchestrator — backfill + validate + manifest"
```

### Task 15: Smoke-test orchestrator on 1 ticker

**Files:** none new (uses existing orchestrator)

- [ ] **Step 1: Run orchestrator on RELIANCE only**

```bash
python -X utf8 -c "import pandas as pd; pd.DataFrame({'ticker':['RELIANCE']}).to_csv('pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_smoke.csv', index=False)"
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --tickers-csv pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_smoke.csv
```

Expected output (JSON; n_succeeded should be 1):
```
{
  "n_requested": 1,
  "n_succeeded": 1,
  "n_failed": 0,
  "raw_output": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet"
}
```

- [ ] **Step 2: Verify the parquet content**

```bash
python -X utf8 -c "
import pandas as pd
df = pd.read_parquet('pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet')
print('rows:', len(df))
print('tickers:', df['ticker'].nunique())
print('dates:', df['trade_date'].nunique())
print('first 3:'); print(df.head(3))
"
```

Expected: rows in the thousands (~375 minutes × ~40 trading days = ~15000), tickers=1, dates ≈ 40.

- [ ] **Step 3: Commit smoke artifacts manifest only (parquet is gitignored)**

```bash
git add pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json 2>/dev/null || true
git commit --allow-empty -m "test(v3-eval): smoke-test Phase 1 orchestrator on RELIANCE — 1 ticker pass"
```

### Task 16: Run full 147-ticker backfill

**Files:** none new

- [ ] **Step 1: Run full backfill**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay 2>&1 | tee pipeline/data/research/etf_v3_evaluation/phase_1_universe/kite_backfill_log.txt
```

Expected runtime: 30–60 minutes (Kite rate limits). Expected JSON summary at end:
```
{
  "n_requested": 147,
  "n_succeeded": <≥130 hopefully>,
  "n_failed": <remainder, all listed in tickers_failed.csv with reason>,
  "raw_output": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet"
}
```

- [ ] **Step 2: Sanity-check the raw output parquet**

```bash
python -X utf8 -c "
import pandas as pd
df = pd.read_parquet('pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet')
print('total rows:', len(df))
print('unique tickers:', df['ticker'].nunique())
print('date range:', df['trade_date'].min(), '→', df['trade_date'].max())
print('per-ticker bar count summary:')
print(df.groupby('ticker').size().describe())
"
```

- [ ] **Step 3: Commit log + summary (parquet gitignored)**

```bash
git add pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json
git commit --allow-empty -m "data(v3-eval): Phase 1 full 147-ticker Kite minute-bar backfill complete"
```

### Task 17: Run cross-source reconciliation on 5 sample tickers

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/run_reconciliation.py`

- [ ] **Step 1: Write the reconciliation runner**

Write `pipeline/autoresearch/etf_v3_eval/run_reconciliation.py`:

```python
"""Phase 1 reconciliation runner — compare minute-aggregated daily close to EOD parquet for 5 sample tickers."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.cross_source_reconciliation import compare_to_eod

logger = logging.getLogger(__name__)

SAMPLE_TICKERS = ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY"]
MINUTE_PARQUET = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")
EOD_DIR = Path("pipeline/data/historical_bars")
OUT = Path("pipeline/data/research/etf_v3_evaluation/phase_1_universe/reconciliation_report.json")


def load_eod_for_tickers(tickers: list[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        path = EOD_DIR / f"{t}.parquet"
        if not path.exists():
            logger.warning("EOD parquet missing for %s at %s", t, path)
            continue
        df = pd.read_parquet(path)
        df = df.rename(columns={"Date": "trade_date", "Close": "close"})
        df["ticker"] = t
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        frames.append(df[["ticker", "trade_date", "close"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ticker", "trade_date", "close"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    minute_all = pd.read_parquet(MINUTE_PARQUET)
    minute_sample = minute_all[minute_all["ticker"].isin(SAMPLE_TICKERS)].copy()
    eod_sample = load_eod_for_tickers(SAMPLE_TICKERS)

    report = compare_to_eod(minute_sample, eod_sample, raise_on_failure=False)
    report["sample_tickers"] = SAMPLE_TICKERS
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run reconciliation**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.run_reconciliation
```

Expected: max_delta_pct < 0.005 across all sample tickers; rows_above_threshold = 0.

- [ ] **Step 3: Commit the runner + verify report**

```bash
git add pipeline/autoresearch/etf_v3_eval/run_reconciliation.py
git commit -m "feat(v3-eval): §13 reconciliation runner on 5 sample tickers"
```

### Task 18: Build the contamination-map runner + run it

**Files:**
- Create: `pipeline/autoresearch/etf_v3_eval/run_contamination_map.py`

- [ ] **Step 1: Write the contamination-map runner**

Write `pipeline/autoresearch/etf_v3_eval/run_contamination_map.py`:

```python
"""Phase 1 contamination-map runner — join Kite-backfilled tickers with bulk-deals/insider/news/earnings."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.contamination_map import build_contamination_map

logger = logging.getLogger(__name__)

MINUTE_PARQUET = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")
OUT = Path("pipeline/data/research/etf_v3_evaluation/phase_1_universe/contamination_map.json")
BULK_DIR = Path("pipeline/data/bulk_deals")
INSIDER_DIR = Path("pipeline/data/insider_trades")
NEWS_PATH = Path("pipeline/data/news_events.parquet")
EARNINGS_PATH = Path("pipeline/data/earnings_calendar.parquet")


def _load_or_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists() and path.is_file():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=columns)


def _load_dir_parquets(dir_path: Path) -> pd.DataFrame:
    if not dir_path.exists():
        return pd.DataFrame()
    frames = [pd.read_parquet(p) for p in dir_path.glob("*.parquet")]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    minute = pd.read_parquet(MINUTE_PARQUET)
    tickers = sorted(minute["ticker"].unique())
    dates = sorted({d for d in minute["trade_date"].unique()})

    bulk = _load_dir_parquets(BULK_DIR)
    if not bulk.empty and "trade_date" not in bulk.columns and "date" in bulk.columns:
        bulk = bulk.rename(columns={"date": "trade_date"})

    insider = _load_dir_parquets(INSIDER_DIR)
    news = _load_or_empty(NEWS_PATH, ["ticker", "trade_date", "headline"])
    earnings = _load_or_empty(EARNINGS_PATH, ["ticker", "trade_date", "event"])

    cm = build_contamination_map(tickers, list(dates), bulk, insider, news, earnings)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cm, indent=2, default=str), encoding="utf-8")
    n_hits = sum(1 for t in cm.values() for d in t.values() if any(d.values()))
    print(f"contamination map written: {OUT}")
    print(f"ticker-date pairs with ≥1 channel hit: {n_hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run contamination map**

```bash
python -X utf8 -m pipeline.autoresearch.etf_v3_eval.run_contamination_map
```

Expected: prints path written + non-zero ticker-date hit count.

- [ ] **Step 3: Commit the runner**

```bash
git add pipeline/autoresearch/etf_v3_eval/run_contamination_map.py
git commit -m "feat(v3-eval): §14 contamination-map runner across 4 channels"
```

### Task 19: Update §17 acceptance ladder in the audit doc

**Files:**
- Modify: `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`

- [ ] **Step 1: Append acceptance status to the audit doc**

Append to `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`:

```markdown
## §17 Acceptance — final status

**Promoted to Approved-for-Tier-2-research on 2026-04-XX (fill date when task runs).**

Evidence:
- §6 + §7: `pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json`
- §8: schema validator unit tests pass (`pipeline/tests/test_etf_v3_eval/test_schema_validator.py`)
- §9: cleanliness gate runner used in orchestrator; per-ticker pass/fail in `tickers_failed.csv`
- §10: adjustment mode declared as Unadjusted; corp-actions in window: see manifest
- §11: bars written exactly as Kite emitted; no ex-post correction performed
- §12: 273-ticker universe from `canonical_fno_research_v3.json`; failed tickers in `tickers_failed.csv`
- §13: reconciliation report at `pipeline/data/research/etf_v3_evaluation/phase_1_universe/reconciliation_report.json` shows max_delta_pct < 0.005
- §14: contamination map at `pipeline/data/research/etf_v3_evaluation/phase_1_universe/contamination_map.json`
- §21 binding: any v3 backtest that reads this dataset is now bound by the model approval ladder

**Phase 2 backtests are now unblocked.**
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md
git commit -m "spec(v3-eval): §17 acceptance — Approved-for-Tier-2-research, Phase 2 unblocked"
```

### Task 20: Update inventory + system manual + Phase 0 catalog

**Files:**
- Modify: `pipeline/config/anka_inventory.json` (no entry — ad-hoc only, but document the rationale)
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `docs/v3-evaluation/README.md`

- [ ] **Step 1: Update SYSTEM_OPERATIONS_MANUAL.md to record Phase 1 status**

In the "Research Projects (active)" section added in Task 4, find the v3 line and update its status:

```markdown
- **v3 Standalone Evaluation** — comprehensive backtest + forward-shadow project for the v3-CURATED ETF regime engine. Spec: [docs/superpowers/specs/2026-04-26-v3-evaluation-design.md](superpowers/specs/2026-04-26-v3-evaluation-design.md). Phase 0 catalog: [docs/v3-evaluation/phase-0-v2-lessons-catalog.md](v3-evaluation/phase-0-v2-lessons-catalog.md). **Status: Phase 0 + Phase 1 COMPLETE. Phase 2 plan pending.**
```

- [ ] **Step 2: Update README.md status badges for both phases**

In `docs/v3-evaluation/README.md`, change the "Phase 0" line:
```markdown
## Phase 0 — v2 Lessons Catalog ✅ DONE
```

And the "Phase 1" line:
```markdown
## Phase 1 — Universe Extension (data engineering) ✅ DONE
```

- [ ] **Step 3: Commit doc updates**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md docs/v3-evaluation/README.md
git commit -m "docs(v3-eval): Phase 0 + Phase 1 marked complete; Phase 2 next"
```

### Task 21: End-of-Phase-1 review checklist

**Files:** none new — pure verification

- [ ] **Step 1: Verify all v2 catalog discoveries (Dn) and meta-lessons (Mn) honored by Phase 1 are addressable**

Re-read `docs/v3-evaluation/phase-0-v2-lessons-catalog.md`. For each row whose "How v3 honors it" mentions Phase 1, confirm the corresponding artifact exists:
- M2 (data validation §6) → audit doc + acceptance status: `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md` exists
- M3 (run-manifest reproducibility) → `manifest.json` exists at `pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json`
- M8 (cross-source reconciliation) → `reconciliation_report.json` exists with max_delta_pct < 0.005

If any row lacks evidence, file a follow-up task before claiming Phase 1 done.

- [ ] **Step 2: Run full test suite to confirm no regressions**

```bash
python -m pytest pipeline/tests/test_etf_v3_eval/ -v
```

Expected: all green.

- [ ] **Step 3: Final commit + tag**

```bash
git tag -a v3-eval-phase1-complete -m "v3 evaluation Phase 0 + Phase 1 complete; Phase 2 unblocked"
git commit --allow-empty -m "chore(v3-eval): Phase 0 + Phase 1 complete"
```

---

## Self-Review Notes (for the implementer)

**Spec coverage check:**
- Spec §4 (Phase 0 — v2 lessons catalog): Tasks 1-4 ✓
- Spec §5 (Phase 1 — universe extension): Tasks 5-19 ✓
- Spec §5.3 (data-policy §6/§7/§8/§9/§10/§11/§12/§13/§14/§17 compliance): Tasks 7-19 ✓
- Spec §5.4 (deliverables): all output paths created by Tasks 6, 14, 16, 17, 18 ✓

**Out of scope for this plan (per scope decision):**
- Spec §6 (Phase 2 backtest) — separate plan after this completes
- Spec §7 (Phase 3 forward shadow) — separate plan after Phase 2
- Spec §8 (Phase 4 attribution catalog) — separate plan after Phase 3

**TDD discipline:** Each code-producing task has fail-test → implement → pass-test → commit pattern. Doc-only tasks have explicit content blocks, no placeholders.

**Type consistency check:** `BackfillFailure`, `SchemaViolation`, `ReconciliationFailure`, `GateResult`, `KiteClient` (Protocol), `write_manifest()`, `fetch_minute_bars()`, `validate_minute_bars_schema()`, `run_cleanliness_gates()`, `compare_to_eod()`, `build_contamination_map()` — all defined in their respective modules and re-used consistently across orchestrator / runners.

**Frequent commits:** 21 tasks × ~4 commits per code task = ~50 commits. DRY (each helper has one home), YAGNI (no premature abstractions), TDD (test-first throughout).
