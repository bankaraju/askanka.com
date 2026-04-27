# Intraday Sector RS Pair (SECRSI) — Design Doc

**Status:** SCOPING (pre-implementation, pre-registration)
**Owner:** Anka research
**Started:** 2026-04-27
**Trigger:** User-proposed intraday sector momentum-pair hypothesis, 2026-04-27 chat
**Cross-references:**
- `NEUTRAL_Trading_Strategy_Framework.md` H2 + H3 (fused, regime-extended variant)
- `2026-04-27-neutral-overlay-engine-design.md` (orthogonal — fade-direction, NEUTRAL-only)
- `backtesting-specs.txt §0-16` (governance)
- H-2026-04-26-001/002 (template for entry/exit/stop alignment)

---

## 1 — One-line hypothesis

> Sector winners and losers identified at 11:00 IST persist until 14:30 IST. A market-neutral basket (long top-2 stocks of top-2 sectors, short bottom-2 stocks of bottom-2 sectors) earns positive net P&L after S1 slippage.

This is **trend-continuation**, opposite sign from H-001 (fade) and from the NEUTRAL_OVERLAY engine (also fade). Useful for portfolio diversification regardless of whether it earns standalone edge.

## 2 — Why this differs from existing H rows

| H | Direction | Regime | Sector ID | Status |
|---|---|---|---|---|
| **H-001** (this work-stream) | Fade (intraday corr-break) | All | n/a (per-stock z) | Forward holdout 2026-04-27 → 2026-05-26 |
| **NEUTRAL_OVERLAY** | Fade (sector ≥2σ) | NEUTRAL only | Catalog list (PSU/ENERGY) | Pre-implementation Stage A |
| **H2 (NEUTRAL framework)** | Continuation, long-only | NEUTRAL only | Drift-based ranking | Drafted, not built |
| **H3 (NEUTRAL framework)** | Cross-sectional L/S | NEUTRAL only | Stock z, ignores sector | Drafted, not built |
| **SECRSI (this doc)** | Continuation, market-neutral | **All regimes** | **Intraday %chg at 11:00** | This spec |

The SECRSI hypothesis is **not redundant** — it generalises H2's winning-sector mechanism to also short losing sectors, and removes the NEUTRAL filter so it gets ~250 trading days/yr instead of ~210.

## 3 — Mechanics (mechanical, no judgement)

### 3.1 Snapshot (11:00 IST ± 5 min)

For each of the 215 F&O-eligible stocks:
- `stock_pct_chg = (price_11:00 - open_today) / open_today`

For each of ~25 sectors (via `pipeline.scorecard_v2.sector_mapper.SectorMapper`):
- `sector_score = median(stock_pct_chg for stocks in sector)` (median, not mean — robust to one runaway)
- Require `n_stocks_in_sector >= 4` for sector to qualify (else exclude — too few stocks for robust median)

### 3.2 Sector ranking

- `top_sectors = sectors_qualified.sort_by(sector_score, desc).head(2)`
- `bottom_sectors = sectors_qualified.sort_by(sector_score, asc).head(2)`

### 3.3 Stock selection within sector

For each sector in `top_sectors`:
- LONG the 2 stocks with the **highest** `stock_pct_chg` within that sector (4 longs total)

For each sector in `bottom_sectors`:
- SHORT the 2 stocks with the **lowest** `stock_pct_chg` within that sector (4 shorts total)

### 3.4 Sizing

- Equal notional per leg: capital / 8 per stock
- Dollar-neutral by construction (4 longs = 4 shorts in notional)
- No leverage assumed in backtest (1× cash)

### 3.5 Stops & exits

- **Stop per leg:** ATR(14) × 2.0, computed via `pipeline.atr_stops.compute_atr_stop` (matches H-001)
- **Exit:** 14:30 IST mechanical TIME_STOP for any surviving leg (matches H-001)
- **No trailing stop, no Z-cross exit** (matches the cleanup that landed in commit 8d0ce32)

### 3.6 Edge cases

- **Stock not tradable today** (suspended, circuit-breaker, no quote at 11:00) → drop from selection, do NOT substitute. Basket runs with fewer legs that day.
- **Tied sector scores or stock %chg** → break ties alphabetically (deterministic).
- **Fewer than 4 qualifying sectors** → no trade that day, log `INSUFFICIENT_SECTORS`.
- **Same stock appears in both winning and losing slate** (impossible by construction — sectors are disjoint, but defensive check) → drop the stock from both.

## 4 — Pre-registration (per backtesting-specs.txt §0-16)

### 4.1 Universe

- 215 F&O stocks, point-in-time via `pipeline/data/fno_universe_history.json`
- Survivorship: PIT-correct
- Sector mapping: `pipeline/data/canonical_fno_research_v3.json` (frozen at registration date)

### 4.2 Sample window

- **In-sample backtest:** 2024-04-27 → 2026-04-26 (2 years, ~500 trading days)
- **Holdout (single-touch §10.4):** 2026-04-28 → 2026-07-31 (~65 trading days)
- **Hold-out gate:** ≥40 trading days observed before verdict (per §11A); auto-extend if below

### 4.3 Claimed edge

| Metric | Threshold | Units | Notes |
|---|---|---|---|
| Mean basket P&L (net of S1 slippage) | ≥ 0.30 | % per day | Per-basket, not annualised |
| Hit rate | ≥ 55 | % | (basket P&L > 0) days |
| Sharpe (annualised, daily basket P&L) | ≥ 1.0 | — | Conservative |
| α for significance | 0.05 | — | Single hypothesis, no multiplicity correction |

### 4.4 Statistical test

- **Method:** Label-permutation null (shuffle long/short assignments within each day, recompute P&L, repeat 10,000 times). Same approach as H-2026-04-26-001.
- **Pass criterion:** p_raw ≤ 0.05 on holdout-only sample.

### 4.5 Slippage model

- **S1 (per backtesting-specs.txt §15):** 5 bps per side per leg = 20 bps round-trip per stock = 160 bps for 8-leg basket. Edge claim is **net of this**.
- **Sensitivity:** report S0 (zero), S1 (5 bps), S2 (10 bps) in reports for transparency. Verdict reads S1.

### 4.6 Cohort robustness (Tier C)

Stratify in-sample results by:
- Regime (RISK-OFF / RISK-ON / EUPHORIA / NEUTRAL / CAUTION) — does edge concentrate in one regime?
- Day-of-week — Monday vs Friday spurious patterns?
- Sector pairs that recur most (e.g., METAL vs IT) — single-pair dependence?
- VIX bucket (low/mid/high) — vol-regime dependence?

Verdict in any one cell with n ≥ 30 must not flip sign vs the aggregate. (FRAGILE if it does.)

## 5 — What this engine does NOT do

- **Does not modify any live trading.** Pure backtest + forward-shadow paper.
- **Does not consume any other holdout.** SECRSI gets its own 65-day single-touch window.
- **Does not gate or modify H-001/002.** Independent work-stream.
- **Does not assume the hypothesis is right.** Equal-likely outcomes: confirmed / failed / fragile.

## 6 — Module file paths (planned)

```
pipeline/research/h_2026_04_27_secrsi/
  __init__.py
  hypothesis.json                  # registry-style metadata, mirrors registry row
  sector_snapshot.py               # 11:00 IST snapshot + sector aggregation
  basket_builder.py                # top-2/bottom-2 sector selection + stock picking
  secrsi_backtest.py               # full historical replay, daily basket P&L
  forward_shadow.py                # 11:00 daily entry, 14:30 exit, paper ledger writer
  reports/
    in_sample_verdict.md
    holdout_verdict.md             # written ONLY at end of 2026-07-31

pipeline/tests/test_secrsi/
  test_sector_snapshot.py
  test_basket_builder.py
  test_secrsi_backtest.py
```

## 7 — Strategy gate compliance

- File `secrsi_backtest.py` matches `*_backtest.py` glob → strategy gate triggers on its first commit.
- That commit MUST include hypothesis-registry row `H-2026-04-27-SECRSI-001` in the same diff.
- Registry row template: see `H-2026-04-26-001` for shape (sigma-break-mechanical-v1).

## 8 — Schedule (planned, pending sign-off)

| Time | Task | Cadence |
|---|---|---|
| 11:00 IST | `AnkaSecrsiSnap1100` | Daily, capture sector snapshot + freeze basket |
| 11:01 IST | `AnkaSecrsiPaperOpen` | Daily, write paper-OPEN rows to ledger |
| 14:30 IST | `AnkaSecrsiPaperClose` | Daily, mechanical TIME_STOP at Kite LTP |
| 16:30 IST | `AnkaSecrsiEod` | Daily, append to `pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv` |

These align with the existing `AnkaPhaseCShadow*` and `AnkaH20260426001Paper*` cadence so all three paper books update on the same clock.

## 9 — Open questions for next session

- **Should this share the H-001 ATR(14)×2 stop, or use a wider stop given the basket holds 8 legs and can absorb individual hits?** Default to ATR(14)×2 for alignment; revisit if holdout shows excess stop-outs.
- **Entry time tolerance:** is 11:00 ± 5min the right window, or should we widen to ± 15 min to handle Kite tick gaps? Spec says ± 5; revisit if data hygiene reveals holes.
- **Sector mapping snapshot date:** the spec freezes `canonical_fno_research_v3.json` at registration date. If the file is updated mid-holdout (rare), the holdout still reads the frozen snapshot. Acceptable per §11.
- **Capital:** the absolute number doesn't matter for backtest (P&L computed in %), but the forward shadow ledger should record a notional capital so position-sized P&L is interpretable. Default ₹5L total = ₹62.5K per leg.

## 10 — Decision needed before engine build

User confirms one of:

1. **Approve as written** → proceed to write registry row + engine package skeleton in single commit.
2. **Redirect on parameters** → adjust spec, re-confirm.
3. **Slot into H2/H3 fusion under NEUTRAL_OVERLAY family** → rewrite as a NEUTRAL-only variant, drop the regime-agnostic claim. (Smaller scope, less interesting.)

Default if no redirect: option 1 with the parameters in §3 and §4 as written.
