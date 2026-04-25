# Forensic v3 + Wave C — §5A.5 Raw-Bar-Canonicity Audit

**Source:** correlation_break_4sigma_v2.csv (1774 events, 2021-05-10 → 2026-04-21)
**Generated:** 2026-04-25T10:55:14.806555+00:00

## Why this audit exists

The compliance run that produced events.json (`compliance_H-2026-04-23-001_20260423-150125`) scored **impaired_pct = 10.349 % — classification AUTO-FAIL** under §5A.3 of `docs/superpowers/specs/backtesting-specs.txt` (auto-fail threshold 3.0 %). Per §5A.5, any bar flagged by the §5A.1 audit inside a trade's execution window invalidates that trade — no substitution, no imputation, no silent pass-through. The forensic v1/v2/v3 cards are descriptive (no edge claim, no §6 dataset registration), but they ALL drew from the same AUTO-FAIL events.json. This audit quantifies how many of the 'unexplained 56 %' residual events are actually §5A.5 violations vs real idiosyncratic moves.

## Method

Calendar = union of dates across every fno_historical/*.csv ticker with ≥1000 bars (same construction as `overshoot_compliance/runner.py:158`). Per-ticker flagged_dates computed by `overshoot_compliance.execution_window.build_flagged_dates` (missing | duplicate | stale_run | zero_price | zero_volume). Each event tagged on T and T-1 (T-1 is the persistence anchor in the v1 |z|≥3 filter).

## §5A status breakdown

| status | n | share |
|---|---:|---:|
| 5A_CLEAN | 1756 | 99.0% |
| 5A_FLAGGED_T | 0 | 0.0% |
| 5A_FLAGGED_T_MINUS_1 | 18 | 1.0% |
| 5A_FLAGGED_BOTH | 0 | 0.0% |

## Decomposition: full vs §5A-clean vs §5A-flagged

| segment | n | earnings | sector | insider co-occurs | **unexplained** |
|---|---:|---:|---:|---:|---:|
| full event set | 1774 | 31.3% | 9.4% | 9.8% | **56.1%** |
| §5A-clean only | 1756 | 31.2% | 9.2% | 9.9% | **56.2%** |
| §5A-flagged only | 18 | 44.4% | 27.8% | 5.6% | **44.4%** |

**Reading:** if the §5A-clean unexplained share is materially below the full-set share, then the v3 'unexplained 56 %' was inflated by §5A.5 violations. Δ = -0.1 pp.

## Where the §5A flags concentrate

### by direction

| value | n | n_flagged | share_flagged |
|---|---:|---:|---:|
| UP | 1171 | 12 | 1.0% |
| DOWN | 603 | 6 | 1.0% |

### by sector

| value | n | n_flagged | share_flagged |
|---|---:|---:|---:|
| NIFTYIT | 158 | 7 | 4.4% |
| NIFTYAUTO | 75 | 1 | 1.3% |
| nan | 808 | 8 | 1.0% |
| NIFTYMETAL | 103 | 1 | 1.0% |
| BANKNIFTY | 208 | 1 | 0.5% |
| NIFTYFMCG | 111 | 0 | 0.0% |
| NIFTYENERGY | 161 | 0 | 0.0% |
| NIFTYPHARMA | 131 | 0 | 0.0% |
| NIFTYREALTY | 19 | 0 | 0.0% |

### by year

| value | n | n_flagged | share_flagged |
|---|---:|---:|---:|
| 2026.0 | 135 | 7 | 5.2% |
| 2024.0 | 377 | 5 | 1.3% |
| 2025.0 | 326 | 3 | 0.9% |
| 2021.0 | 222 | 1 | 0.5% |
| 2022.0 | 329 | 1 | 0.3% |
| 2023.0 | 385 | 1 | 0.3% |

### by |z| bucket

| value | n | n_flagged | share_flagged |
|---|---:|---:|---:|
| [8.0,∞) | 133 | 3 | 2.3% |
| [4.0,4.5) | 593 | 8 | 1.3% |
| [5.0,6.0) | 368 | 4 | 1.1% |
| [4.5,5.0) | 378 | 2 | 0.5% |
| [6.0,8.0) | 302 | 1 | 0.3% |

## §5A blind spot discovered during this audit

Empirical inspection of `pipeline/data/fno_historical/*.csv` shows that **204/213 tickers carry rows on 2024-01-01**, **211/213 on 2025-01-01**, **212/213 on 2026-01-01**, **194/213 on 2022-01-14** — all NSE-closed dates (New Year's Day, Pongal/Makar Sankranti). These rows carry the prior session's OHLC unchanged, but the canonical §5A audit flags **zero** of them. Two reasons:

1. The §5A calendar is built as the union of dates across long-history tickers (`runner.py:158`). When 200+ tickers carry the same stale holiday row, that date *is* the canonical calendar — there's no expected-but-missing bar to flag.
2. The `stale_run` detector only fires when a single (open|high|low|close) tuple repeats for ≥3 consecutive bars. A holiday-bar that copies the PRIOR-day close is one row, not a run — it escapes `stale_run` and only shows up as `zero_volume` if the source preserved zero volume (which the FNO source does not).

**Recommended remediation (separate ticket, not part of this audit):**
- Source an independent NSE holiday master list (2021-2026) and intersect-trim every fno_historical/*.csv to drop holiday rows.
- Add a §5A.1 sub-check `holiday_carryover`: row exists on a published-NSE-holiday date AND OHLC equals prior-trading-day OHLC.
- Re-run `compliance_H-2026-04-23-001` after remediation. The current `impaired_pct = 10.349` baseline already AUTO-FAILs even without this extra check; the post-remediation number will tell us whether the true value is dominated by listing-effect or by holiday carryover.

This blind spot does not change the §5A status counts above, but it means the v3 'unexplained 56 %' headline is robust against the *currently-implemented* §5A — not against the §5A as the policy intends. A future audit that uses a published holiday calendar may shift the headline materially.

## Policy implication

- **§5A.3 auto-fail:** the source events.json was AUTO-FAIL (10.35 % impaired) and may not be cited in a deployment review under any waiver.
- **§5A.5 raw-bar canonicity:** §5A-flagged events should be removed from the forensic event set, not reattributed.
- **Consequence for v1/v2/v3:** the 'unexplained 56 %' headline must be reported against the §5A-clean subset only. The §5A-flagged events were never valid evidence of anything.
- **Upstream fix:** before re-running compliance, the fno_historical CSVs need a holiday-row purge (rows on NSE-closed dates that carry the prior session's OHLC). 204/213 tickers carry a 2024-01-01 row (NSE was closed for New Year's Day); 211/213 carry 2025-01-01; 212/213 carry 2026-01-01. These are all stale_run violations on the immediate post-holiday session.
