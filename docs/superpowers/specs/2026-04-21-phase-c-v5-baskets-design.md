# Phase C V5 — Baskets, Index Hedges & Options Validation

**Date:** 2026-04-21
**Author:** Anka Research
**Status:** Draft, pending user approval

## Problem

Phase C v1 validated 162 OPPORTUNITY signals as **single-stock futures trades** (intraday open → 14:30 close). Verdict: FAIL — 43.5% hit rate, Sharpe CI [-3.59, -0.35], binomial p=0.0012 against random.

But that validated the wrong unit. Anka's edge framework is **regime-anchored basket trades**, not single-stock punts. The Spread Intelligence Engine already proves baskets work where stocks don't (Banks Pvt vs PSU, Refiners vs Upstream). Phase C OPPORTUNITY signals were never tested as:

1. Pairs/triplets emerging from same-regime, same-sector co-firings
2. Stock vs sector-index hedges (long HDFCBANK fut / short BANKNIFTY fut)
3. Options structures via Station 6.5 synthetic pricer (long call / long put)
4. Multi-day holds (T+1, T+2, T+3, T+5)
5. Index-routed trades when 2-of-3 top constituents align

This study tests all five framings on the **same 60-day Kite 1-min forward window** plus 4-year daily in-sample, using the same statistical rigor (Bonferroni α=0.01, walk-forward, bootstrap Sharpe CI, binomial hit-rate).

The book-growth motivation: stock futures absorb ~₹50k/leg today but degrade above ~₹5L/leg. Index futures absorb 100x. If the edge survives index-routing, the strategy scales.

## Goals

1. **Determine whether basket-level Phase C edge exists** that single-stock validation missed.
2. **Test options structures** (long ATM call / long ATM put) as alternative to futures, using existing Station 6.5 pricer (MAPE 0.95% validated).
3. **Test hold-horizon sensitivity** — is the 14:30 mechanical exit even the right horizon?
4. **Identify the index-routing path** for book scaling (when stock signal effectively IS the index, route through the index).

Single research output, comparable cost model across variants, single verdict per variant. Same publication-grade rigor as Phase C v1.

## Non-Goals

- Live trading. F3 forward shadow continues separately (uses v1 single-stock OPPORTUNITY).
- Reinventing spread engine. We borrow its sector classifier and basket-formation logic — we do not duplicate it.
- Cross-strategy combination (e.g., Phase C × News × Trust). Reserved for V6 if any V5 variant survives.

## Architecture

```
pipeline/research/phase_c_v5/
├── __init__.py
├── data_prep/
│   ├── backfill_indices.py         # Kite → 5y daily + 60d 1-min for 14 sectorals
│   ├── concentration.py             # build sector_concentration.json
│   └── tradeable_indices.py         # NSE live-quote check; which sectorals have F&O
├── variants/
│   ├── v51_sector_pair.py           # long top-OPP / short bot-OPP in same sector
│   ├── v52_stock_vs_index.py        # long stock fut / short sector index fut
│   ├── v53_nifty_overlay.py         # every Phase C trade + NIFTY beta hedge
│   ├── v54_banknifty_dispersion.py  # leader-strong / index-flat divergence
│   ├── v55_leader_routing.py        # 2-of-3 leaders align → trade index, not stock
│   ├── v56_horizon_sweep.py         # exit at 14:30 / T+1 / T+2 / T+3 / T+5
│   └── v57_options_overlay.py       # long ATM call/put via Station 6.5 pricer
├── basket_builder.py                # shared: groups Phase C signals into baskets
├── cost_model.py                    # extends phase_c_backtest cost_model for index + options
├── simulator.py                     # shared replay engine (1-min and daily)
├── stats.py                         # Bonferroni, bootstrap Sharpe, binomial — reused
├── ablation.py                      # variant-vs-variant comparison
├── report.py                        # 11-section research doc generator
└── run_v5.py                        # CLI entry point
```

Each variant emits its own ledger to `data/research/phase_c_v5/<variant>_ledger.parquet`. The `report.py` step builds a single comparative document.

## Data Prerequisites

**Indices to backfill:**
- BANKNIFTY, NIFTY 50, NIFTY NEXT 50, FINNIFTY, MIDCPNIFTY (known F&O)
- NIFTY IT, NIFTY METAL, NIFTY PSU BANK (verified F&O via NSE)
- NIFTY AUTO, NIFTY PHARMA, NIFTY FMCG, NIFTY ENERGY, NIFTY REALTY, NIFTY MEDIA, NIFTY PVT BANK, NIFTY FIN SERVICE (verify per-symbol via `https://www.nseindia.com/get-quotes/derivatives?symbol=<INDEX>` before treating as tradeable)

**Storage:**
- `pipeline/data/india_historical/indices/<INDEX>_daily.csv` — 5 years
- `pipeline/data/india_historical/indices/intraday/<INDEX>_1min.parquet` — 60 days

**Concentration map (`pipeline/config/sector_concentration.json`):**
```json
{
  "BANKNIFTY": {
    "constituents": [
      {"symbol": "HDFCBANK", "weight": 0.28},
      {"symbol": "ICICIBANK", "weight": 0.24},
      {"symbol": "SBIN", "weight": 0.10},
      {"symbol": "AXISBANK", "weight": 0.08},
      {"symbol": "KOTAKBANK", "weight": 0.07}
    ],
    "top_n_threshold": 0.70
  }
}
```

The `top_n_threshold` defines when "stock signal effectively IS the index" (e.g., signal on a name in the top-70%-weight bucket).

## Variants

### V5.1 — Sector-neutral pair

For each sector with ≥2 Phase C OPPORTUNITY signals on the same day: long the highest-conviction (expected_return × confidence) signal, short the lowest. Equal notional. Hold to 14:30.

**Hypothesis:** Stripping sector beta isolates stock-specific alpha. If pair survives, the basket framing is correct and v1 was right to fail.

**Universe constraint:** Both legs must be in F&O. Skip sectors with <2 signals same day.

### V5.2 — Stock vs sector-index

Every Phase C OPPORTUNITY trade gets paired with an opposite-direction position in its sector index futures, sized to neutralize beta (rolling 60-day OLS β).

**Hypothesis:** Removing sector noise reveals or destroys edge. If hit rate jumps materially, v1 failure was sector-noise masking.

### V5.3 — NIFTY beta overlay

Same as V5.2 but uses NIFTY 50 as the universal hedge (not sector-specific). Cheaper liquidity, simpler implementation.

**Hypothesis:** Even broad-market hedge restores edge. If v5.3 ≥ v5.2, sector-specific hedging adds no value.

### V5.4 — BANKNIFTY (and NIFTY IT) dispersion

For BANKNIFTY: when Phase C OPPORTUNITY fires bullish on one of the top-3 weighted names (HDFCBANK, ICICIBANK, SBIN) but BANKNIFTY itself is flat or weak (rolling 5-bar return below the stock's), go long the stock and short BANKNIFTY. Mirror logic for NIFTY IT (TCS, INFY, HCLTECH).

**Hypothesis:** Captures the well-known "leader-strong / index-lagging" edge that punters historically extract from BANKNIFTY.

### V5.5 — Leader → index routing

When ≥2 of the top-3 BANKNIFTY (or NIFTY IT) constituents fire same-direction Phase C OPPORTUNITY on the same day, take the trade via the **index** futures, not the constituent stocks.

**Hypothesis:** Same edge, 10x liquidity, lower impact cost. Critical for book scaling. If hit rate matches stock-level v1, this is the production path.

### V5.6 — Hold-horizon sweep

Same Phase C OPPORTUNITY universe. Exit at: 14:30 same-day, T+1 close, T+2 close, T+3 close, T+5 close. Five parallel ledgers.

**Hypothesis:** v1 may have failed because 14:30 is the wrong horizon, not because the signal is wrong. Plot Sharpe vs horizon — if any horizon's CI excludes zero on the upside, that's the right exit.

### V5.7 — Options overlay

For each Phase C OPPORTUNITY: enter via long ATM call (LONG signals) or long ATM put (SHORT signals) using Station 6.5 synthetic pricer. Strike = nearest 50-step. Exit at 14:30 same-day. Vol input: EWMA realized vol from 1-min bars.

**Hypothesis:** Convex payoff helps marginal trades — small directional edge becomes profitable when downside is capped at premium.

## Cost Model

Extends `phase_c_backtest/cost_model.py`:

| Instrument | Slippage (bps) | Brokerage | STT | Stamp |
|---|---|---|---|---|
| Stock futures | 5 | ₹20/leg | 0.0125% sell | 0.002% buy |
| Index futures (NIFTY/BANKNIFTY) | 2 | ₹20/leg | 0.0125% sell | 0.002% buy |
| Sectoral index futures (NIFTY IT etc.) | 8 | ₹20/leg | 0.0125% sell | 0.002% buy |
| Options (long-only) | 15 (mid-spread) | ₹20/leg | 0.0625% sell | 0.003% buy |

Slippage figures are conservative; sectoral indices get a higher slippage haircut to reflect thinner books vs NIFTY/BANKNIFTY.

Options P&L computed via Station 6.5 pricer at entry and exit times — no Greeks-only approximation.

## Statistical Standard

**Per-variant tests** (all on the OOS forward window):
1. Hit rate vs 50% — binomial test
2. Sharpe CI — bootstrap 10,000 IID resamples, fixed seed=7
3. Walk-forward — rolling 2y train / 3mo OOS quarterly refit (in-sample only — forward window is too short for walk-forward)

**Cross-variant comparison:**
- Bonferroni correction across 7 variants (α = 0.01 / 7 = 0.00143 per test)
- Variant passes only if Sharpe CI lower bound > 0 AND hit rate p < 0.00143

This is harder to pass than v1 (which used α/5). That's deliberate — we're testing 7 hypotheses and want to control multiple-comparisons error.

## Output

`docs/research/phase-c-v5-baskets/` — 11 sections:

1. Executive summary (per-variant verdict table)
2. Strategy description (basket framing rationale)
3. Methodology
4. Results — V5.1 sector pair
5. Results — V5.2 stock vs sector index
6. Results — V5.3 NIFTY overlay
7. Results — V5.4 BANKNIFTY dispersion
8. Results — V5.5 leader routing
9. Results — V5.6 horizon sweep
10. Results — V5.7 options overlay
11. Verdict + production recommendation

Each variant section auto-generated from its parquet ledger by `report.py` — same template, same statistics, same plots. Comparable across variants.

## Risks & Open Questions

1. **NSE F&O availability per sectoral** — must verify before assuming tradeability. Mitigation: `tradeable_indices.py` script hits NSE live-quote endpoint per symbol; non-tradeable indices fall back to constituent-basket synthesis.
2. **Beta stability** — V5.2/V5.3 hedge ratios computed on 60-day rolling OLS may be unstable in regime transitions. Mitigation: cap hedge ratio at [0.5, 1.5], log warning when outside.
3. **Options pricing in stress** — Station 6.5 was validated on calm market data (MAPE 0.95%). Vol-spike environments may be misspecified. Mitigation: log per-trade pricing-error confidence interval; flag any trade where bid-ask implied IV > model IV by >5 vol points.
4. **Look-ahead in basket formation** — V5.1 forms pairs from the OPPORTUNITY signal set, which itself uses next-bar return as the label. Ensure basket-side selection uses only signal-time information. Audit in spec-compliance review.
5. **Survivorship in 4-year history** — same constraint as v1 (HDFC delisted 2023). Mitigation: continue using `if bars.empty: continue` guard.

## Terminal Integration

Terminal restructure (commits `dcd6bdb` and predecessors, Apr 20) shipped a 10-tab layout with a discovery-friendly schema split: `tradeable_candidates[]` (Trading) vs `signals[]` (Scanner). Filter chips auto-derive from data, so new signal sources appear without UI changes.

V5 introduces concepts the current schema doesn't model:

| V5 concept | Schema field to add | Component change |
|---|---|---|
| Pair | `legs: [{symbol, side, weight}, ...]` on tradeable_candidate | extend `candidates-table` to render multi-leg rows |
| Index hedge | `hedge_leg: {symbol, side, ratio}` | extend `positions-table` to show composite P&L |
| Options leg | `option_leg: {strike, expiry, premium, type}` | new `options-leg` mini-component |
| Hold horizon | `exit_horizon: "14:30" \| "T+1" \| ...` | add column to candidates-table |
| Variant tag | `variant: "v51" \| "v52" \| ...` | filter chip auto-populates |

**Do not build terminal upfront.** Wait for V5.1's first ledger to land, then design from real fields. Plan task: "Terminal schema extension + 2 components", gated on V5.1 ledger.

## Out of Scope (V6+)

- Iron condor / butterfly when classifier says "lagging mean-reversion"
- Cross-strategy combination (Phase C × News × Trust score)
- Karpathy/Kelly per-spread sizing
- Calendar spread on pinning
- Risk-parity weighting

These are documented in the menu but not validated here. V6 picks up the 2-3 most promising V5 variants and combines them.
