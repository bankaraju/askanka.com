# Baseline B3 — passive long NIFTY intraday (in-sample comparator)

_generated_: 2026-04-26T05:12:51+00:00

## Specification anchor

From `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md` §7:

> **B3** — passive long index intraday | Long NIFTY at 09:30, close at 14:30 every day | Margin ≥ +0.5% over passive intraday beta

In-sample window: **2026-02-24 → 2026-04-24** (35 trading days).
≥2σ signal days inside window: **11**.

## Intraday proxy calibration

- empirical resolve_pct = **0.925** (n_samples=121, n_valid=113)
- ratio_median = 0.8927, ratio_std = 0.6412
- proxy: `intraday_pct ≈ resolve_pct × (close − open) / open`

## H-2026-04-26-001 in-sample (unchanged)

| n | hit % | mean P&L % | std % | Sharpe (ann) | t |
|---:|---:|---:|---:|---:|---:|
| 42 | 92.86 | 1.6626 | 1.5996 | 16.5 | 6.736 |

## B3 baseline (three framings)

### B3-unconditional — long NIFTY every trading day in window

| n days | mean % | hit % | Sharpe (ann) | t | cum % |
|---:|---:|---:|---:|---:|---:|
| 35 | -0.0096 | 51.43 | -0.186 | -0.069 | -0.45 |

### B3-matched-days — long NIFTY only on signal-fire dates

| n days | mean % | hit % | Sharpe (ann) | t | cum % |
|---:|---:|---:|---:|---:|---:|
| 11 | -0.0461 | 54.55 | -0.923 | -0.193 | -0.54 |

### B3-matched-trades-paired — one NIFTY-day return per σ-break trade (73.81% coverage)

| n trades | mean % | hit % | Sharpe (ann) | t | cum % |
|---:|---:|---:|---:|---:|---:|
| 31 | 0.1635 | 70.97 | 3.777 | 1.325 | 5.12 |

## Comparator margin (H-001 mean − B3 mean)

| Framing | Margin (pp) | ≥ +0.5pp? |
|---|---:|:---:|
| Paired per-trade | 1.4991 | PASS |
| Unconditional window | 1.6722 | PASS |
| Matched signal-days | 1.7087 | — |

## Verdict

**§7 B3 in-sample status: PASS**

H-2026-04-26-001 in-sample mean P&L of **1.6626%** per ≥2σ trade beats the passive long-NIFTY 09:30→14:30 intraday baseline by **1.4991 pp** (paired per-trade) and **1.6722 pp** (unconditional window). Both clear the §7 +0.5pp threshold.

**Caveat**: this is an in-sample comparator — the holdout (2026-04-27 → 2026-05-26) is the dispositive test. The proxy `resolve_pct=0.925` was empirically fit on a 38-day sample; if real-window 09:30→14:30 NIFTY returns deviate systematically from the daily-scaled proxy, the B3 numbers shift accordingly. Holdout B3 should be measured on actual 09:30 vs 14:30 LTP snapshots once available.
