# H-2026-04-26-001 — sections 9 (net slippage) + 11B (hit-rate base rate)

_generated_: 2026-04-26T05:18:52+00:00

## Specification anchor

From `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md` §8 verdict ladder:

> **§9** — no execution drag killing alpha — Mean P&L net of 0.05% per-side slippage ≥ +0.4%
>
> **§11B** — calibration-residualised margin — Hit-rate margin holds after deflating for hit-rate base rate

Both gates are computable in-sample without consuming the holdout.

## Section 9 — net-of-slippage

- n trades                = **42**
- gross mean P&L          = +1.6626%
- slippage assumed         = -0.1% (≈ 0.05% per side × 2)
- **net mean P&L**         = **+1.5626%**
- net hit-rate             = 92.86%
- net Sharpe / trade       = 0.977
- net t-stat               = 6.331
- threshold                = +0.4%
- margin                   = **+1.1626 pp**
- **verdict: §9 PASS**

**Reading:** the rule has ~2.6× headroom over the threshold even after a slippage assumption that is twice typical institutional Indian intraday for the universe (5 bp per side is a defensive estimate; actual usually ~2-3 bp on liquid F&O names). The net t-stat of 6.331 indicates the slippage-adjusted edge is highly significant in-sample.

## Section 11B — hit-rate base-rate residualization

- H-001 observed hit-rate                = 92.86%
- Base rate (B3 NIFTY intraday +day rate) = 51.43%
- Base rate (B3 matched signal-days)      = 54.55%
- Base rate (random direction floor)      = 50.0%

| Margin framing | Value (pp) |
|---|---:|
| H-001 hit − B3 unconditional base | **+41.43 pp** |
| H-001 hit − B3 matched-signal-days base | +38.31 pp |
| H-001 hit − random-direction floor | +42.86 pp |

**Verdict: §11B PASS**

**Reading:** the hit-rate edge is not a base-rate artifact. NIFTY's natural intraday (09:30→14:30 proxy) hit rate in the in-sample window is essentially coin-flip (51.43%); H-001 delivers a 41.43-pp lift on top of that. Even against the matched-day base (54.55%, a tougher comparator that conditions on the same trade-firing days), the lift is 38.31pp.

## Combined in-sample gate status after this commit

| Gate | Status |
|---|---|
| §7 B0 always-prior | CLEARED via T1 perm null |
| §7 B1 random-direction | CLEARED via Tier A.2 |
| §7 B2 trend-follow opposite | CLEARED via Tier A.1 (correct sign) |
| §7 B3 passive long intraday | CLEARED via baseline_b3 |
| §7 B4 random-day same direction | CLEARED via baseline_b4 |
| §8 direction integrity | CLEARED via Tier A.1 |
| §9 execution drag (net slippage) | **CLEARED this commit** |
| §9A per-week fragility | CLEARED via Tier A.3 + Tier C |
| §9B.1 comparator margin | CLEARED via baseline_b3 |
| §9B.2 perm null Bonferroni | CLEARED via T1 |
| §10 single-touch hygiene | INTACT (holdout open 2026-04-27 → 2026-05-26) |
| §11B calibration-residualised | **CLEARED this commit** |
| §5A holdout sample size | not testable yet (holdout-only) |
| §6 pre-registered claim | not testable yet (holdout-only) |

**All in-sample gates that can be tested in-sample are now CLEARED.** Remaining gates require the holdout window 2026-04-27 → 2026-05-26 to materialize.

**Note:** the §10.4 single-touch discipline forbids any parameter change after 2026-04-27 09:30 IST. The current spec (|Z|≥2.0, ATR(14)×2, +0.6%/+1.2% trail, 14:30 TIME_STOP) is locked.
