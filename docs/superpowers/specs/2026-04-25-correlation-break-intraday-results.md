# Intraday Correlation-Break Replay — v0 Results (FAIL)

**Date:** 2026-04-25
**Pre-registration anchor:** commit `9cab5d4` (`docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis.md`)
**Artefact:** `pipeline/autoresearch/data/intraday_break_replay_60d.parquet`
**Code:** `pipeline/autoresearch/intraday_break_replay.py`

---

## Verdict

**FAIL** by the §8 pre-registered rule.

```
avg net P&L ≤ 20 bps OR p > 0.10 → FAIL
```

Observed: avg net P&L = **-25 bps**, p (vs 40 bps H₁ bar) ≈ 0.0005 one-sided, direction wrong.

## Primary result

| Metric | Value |
|---|---|
| N trades | 35 |
| Avg net P&L | **-25 bps** |
| Median net P&L | -10.4 bps |
| Hit rate | 37% (13 W / 22 L) |
| Per-trade std | 99 bps |
| t vs 0 | -1.50 |
| t vs 20 bps | -2.70 |
| t vs 40 bps | **-3.90** |
| Cost assumption | 20 bps round-trip |

Sample ran over CAUTION regime (the only regime active across the 60-day
window). All trades classified OPPORTUNITY_LAG as specified.

## Exit path distribution

| Exit | Count | % |
|---|---|---|
| Z_CROSS | 23 | 66% |
| TIME_STOP (14:30) | 8 | 23% |
| STOP (1.5σ) | 4 | 11% |

## Why the strategy fails (forensic finding)

66% of trades closed via Z_CROSS — the predicted mean-reversion event. But
most Z_CROSS closures were losers. Interpretation: the gap *did* close (as
the thesis predicted), but it closed **symmetrically** — sometimes the stock
moved toward the peers (favourable), sometimes the peers moved back toward
the stock (flat to slightly unfavourable after costs). Average outcome
after 20 bps round-trip:

- Favourable closure: stock catches up ≈ 30 bps net positive
- Unfavourable closure: peers retreat, stock flat ≈ -20 bps (pure cost)
- Close to 50/50 split + cost asymmetry → -25 bps expectation

The live engine's thesis assumes the first case dominates. The data says
the two cases are nearly symmetric. Without a directional edge on *which
side* closes the gap, the strategy pays costs and loses.

## Sub-findings (pre-specified secondaries)

### H₁ₐ: σ bucket monotonicity

| σ bucket | N | Avg net P&L |
|---|---|---|
| mild [1.5, 2) | 27 | -34 bps |
| rare [2, 3) | 6 | **+19 bps** |
| extreme [3, ∞) | 2 | -41 bps |

Weak support for H₁ₐ in the rare bucket only — σ ∈ [2, 3) was mildly
positive on 6 observations. Extreme bucket (2 obs) is not informative.
**This does not rescue the main verdict**, but is worth logging as a
candidate for a separate future test (pre-registered at σ > 2 threshold,
longer sample).

### H₁ᵦ: same-day Z_CROSS hit rate

66% of trades closed via Z_CROSS, exceeding the 60% sub-hypothesis
threshold. But the Z_CROSS closures were mostly losing — see forensic
above. This sub-hypothesis is structurally confirmed but doesn't imply
edge.

### H₁ᶜ: direction symmetry

LONG avg: -40 bps (12 trades)
SHORT avg: -17 bps (23 trades)

SHORT less bad than LONG, consistent with a mildly downtrending CAUTION
period. Difference 23 bps is within the 30 bps tolerance. No clear
asymmetry rules violated.

## Power / sample caveat (disclosed, does not change verdict)

Thesis §5.3 estimated N ∈ [300, 600] for 60 days; observed N = 35. The
shortfall is ~10×. Two plausible causes:

1. The full engine filter (σ > 1.5 AND LAG AND PCR-agrees AND no OI
   anomaly AND profile has transition-to-CAUTION stats) is much stricter
   than assumed — PCR/OI gating alone may eliminate most triggers since
   positioning data coverage is incomplete.
2. Only CAUTION regime was active; most transitions in the profile are
   not "X→CAUTION" but "X→NEUTRAL" or "X→RISK-OFF" — eligible ticker
   pool for any given day is smaller than the full 210.

At N=35, MDE rises from 30 bps to ~63 bps, so a formal one-sided test
cannot *reject* a true 40 bps edge by power alone. However:

- Point estimate is **-25 bps**, not weakly positive
- Hit rate is **37%**, not ≥50%
- Both directional signals argue against edge

Under the pre-registered rule, FAIL stands. A re-run on a larger sample
(via forward-accumulating scan archives over the coming months) could
revisit, but we must not retrofit the verdict criteria.

## Implications (from thesis §10)

1. **Live 3-day streak attributed to luck + open-snap look-ahead bug.**
   The negative replay P&L under honest-execution rules confirms the
   shadow ledger has been over-crediting the strategy. Expected
   under-report on real fills: 20–50 bps per trade.
2. **Pause live entries** on correlation-break LAG until a re-designed
   thesis exists. Existing open positions run to their natural exits
   (Z_CROSS, STOP, 14:30) but no new ADD signals.
3. **Workstream B still proceeds** — execution rule hardening (kill
   open-snap, deterministic exit ladder, intraday expected-return
   refresh) is thesis-independent and benefits any future strategy.
4. **Workstream C (public narrative) shelved.** No trader-language
   playbook for this strategy.
5. **Archive forward.** Persist every `correlation_breaks.json`
   snapshot and post-2026-04-24 live trade; retest in 90 days with a
   larger sample. Separately pre-register a σ > 2 variant given the
   H₁ₐ signal.

## What PASS would have looked like

For reference, a PASS outcome would have needed:

- Avg net P&L > 40 bps
- t vs 40 bps bar > 1.645 (one-sided α = 0.05)
- Hit rate > 50%
- Z_CROSS closures skewed to winners (not losers)

Observed results missed all four criteria. The failure is
unambiguous, not a near-miss.

## Pre-registration integrity

Thesis committed at `9cab5d4` before results were read. Verdict rule
was frozen by that commit. This results document interprets observed
data against the frozen rule. No post-hoc modifications to the
verdict criteria were made.

The only post-hoc decision is whether to pursue the σ > 2 sub-finding
in a future pre-registered test, which is explicitly permitted by the
thesis §9 (sub-hypotheses inform interpretation, cannot be gating
criteria in this test but may justify *separate* future tests).

---

**Author:** Anka Research (Bharat) + Claude Opus 4.7 assistance
**Signed off:** results document committed alongside the artefact
parquet and v0 backtest code.
