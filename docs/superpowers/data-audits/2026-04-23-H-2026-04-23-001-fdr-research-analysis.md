# FDR Research Analysis — H-2026-04-23-001

**Status:** RESEARCH. This is **NOT** a deployment ruling. Bonferroni
remains the deployment bar; every survivor below stays RESEARCH /
TIER_EXPLORING.

**Source data:** `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/permutations_100k.json` — 100,000 bootstrap shuffles of each (ticker, direction) per-ticker fade test.

**Method:** Benjamini–Hochberg false-discovery-rate procedure at several α levels. Two subsets reported:

1. **All valid hypotheses (m = 254):** every (ticker, direction) with n_events ≥ 10, p-value defined. Signed edge not pre-filtered.
2. **Positive-edge-only subset (m = 90):** same, restricted to hypotheses where `edge_net_pct > 0` (i.e., the fade strategy at least made money after costs before significance testing). This matches a deployable screen.

## Results

| Correction | α | Survivors (all 254) | Survivors (positive-edge 90) |
|---|---:|---:|---:|
| Bonferroni (deployment bar) | 0.05 | **0** | **0** |
| BH-FDR | 0.05 | 0 | **5** |
| BH-FDR | 0.10 | 4 | 6 |
| BH-FDR | 0.20 | 6 | 17 |

### Positive-edge BH-FDR survivors at α = 0.05 (m = 90)

| Ticker | Backtest dir | n_events | hit_rate | edge_net% | p_value |
|---|---|---:|---:|---:|---:|
| TORNTPHARM | UP | 22 | 0.773 | +0.935 | 0.00070 |
| 360ONE | UP | 15 | 0.733 | +1.611 | 0.00080 |
| TORNTPOWER | UP | 16 | 0.625 | +1.384 | 0.00120 |
| SBIN | UP | 14 | 0.714 | +1.244 | 0.00130 |
| IDFCFIRSTB | DOWN | 13 | 0.846 | +1.544 | 0.00210 |

None of these clear Bonferroni (α/m = 1.97e-4 on the positive-edge
subset; 1.17e-4 on the full 426-hypothesis family that the hypothesis
registry pre-declared).

## Interpretation

**Under a softer multiplicity correction (BH-FDR), a small pool of
residual-reversion hypotheses shows evidence of edge in the 5-year
panel.** The effect is concentrated: five (ticker, direction) pairs,
all with positive post-cost mean and ≥62.5% hit rates, and all in the
p ≤ 0.0021 range.

These survive **BH-FDR α=0.05** — which expects a ≤5% false-discovery
rate across declared rejections, **not** the strict ≤5% family-wise
error rate Bonferroni controls. A strategy that only survives FDR is
a research candidate, never a deployment decision.

## Critical caveat: the live engine is not running this strategy

The backtest sets `trade_ret_pct = -sign(z_residual) * next_ret` — it
**fades** the residual. `break_signal_generator.py` (the live engine)
sets direction from `sign(expected_return)` — it **follows** the
peers' expected direction.

These two direction-generators coincide only in some market
geometries. Specifically:

| Scenario | Backtest dir (from residual sign) | Live engine dir (from expected_return sign) | Aligned? |
|---|---|---|---|
| Peers up, stock flat/lagged | DOWN → long stock (fade negative residual) | LONG (expected > 0) | ✅ |
| Peers down, stock flat/outperformed | UP → short stock (fade positive residual) | SHORT (expected < 0) | ✅ |
| Peers up, stock overshoots up | UP → **short stock** (fade) | **LONG** (expected > 0) | ❌ opposite |
| Peers down, stock overshoots down | DOWN → **long stock** (fade) | **SHORT** (expected < 0) | ❌ opposite |

The five FDR survivors above all have backtest direction = UP or DOWN
that reflects the **residual sign**, not the peer direction. Whether
the live engine's FOLLOW thesis has the same edge on the same events
is **untested** — task #107 (Phase C thesis audit) is exactly this
question.

**What this research analysis does NOT claim:**
- That Phase C "passes" anything.
- That the five tickers above justify the live engine's existing
  FOLLOW direction on those tickers.
- That the Bonferroni FAIL verdict on `gate_checklist.json` is
  overturned. It stands.

**What this research analysis DOES claim:**
- There is empirical evidence, at a softer significance bar, for a
  residual-fade edge on ~5 specific tickers in the 5-year panel.
- Those five tickers warrant thesis re-audit (#107) and possibly a
  re-registered hypothesis that tests the **fade** direction
  explicitly (H-2026-04-XX-002 or similar), with a pre-declared
  family size reflecting only those candidates rather than the full
  426.

## Guardrails (user-specified)

1. **Bonferroni stays the deployment bar.** FDR survivors are
   RESEARCH only.
2. **No tier change.** TIER_EXPLORING remains the label for every
   Phase C output. No promotion path from FDR.
3. **Log as research analysis, not "Phase C passes."** This document's
   filename, framing, and distribution reflect that.

## Structured output

Full per-row FDR results at all three α levels and both subsets:
`pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/fdr_research_analysis.json`.
