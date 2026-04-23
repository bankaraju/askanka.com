# Phase C Direction — What's Tested vs What's Traded

**Scope:** Correlation-breaks strategy only. Phase A (ranker) and Phase B (spread
composer) use different direction logic and are not governed by this note.

## The two directions

| | Defined as | Set by |
|---|---|---|
| **Backtest direction (FADE)** | `-sign(residual)` where `residual = actual_return - expected_return` | `pipeline/autoresearch/overshoot_reversion_backtest.py` |
| **Live engine direction (FOLLOW)** | `sign(expected_return)` — LONG if peers predict up, SHORT if peers predict down | `pipeline/break_signal_generator.py` |

The two directions agree on **LAG** geometry (peers moved, stock lagged — `sign(expected_return) != sign(residual)`) and disagree on **OVERSHOOT** geometry (peers moved, stock moved further on the same side — `sign(expected_return) == sign(residual)`).

## How mismatch is flagged

Every Phase C event carries four new fields (spec §3):

- `event_geometry`: `LAG` | `OVERSHOOT` | `DEGENERATE`
- `direction_intended`: the thesis the live engine is *running* (`FOLLOW` for LAG, `NEUTRAL` for OVERSHOOT)
- `direction_tested`: what the backtest *validated* (always `FADE` for correlation-breaks v1)
- `direction_consistent`: `true` iff `event_geometry == LAG` (FADE and FOLLOW agree on that slice)

These are set by `pipeline/autoresearch/reverse_regime_breaks.py::enrich_break_with_direction` at scan time and flow through the `correlation_breaks.json` artifact into every downstream consumer.

## How trades are gated

`pipeline/break_signal_generator.py` routes only `classification == "OPPORTUNITY_LAG"` to actionable signals. `OPPORTUNITY_OVERSHOOT` becomes a research-only alert and does not reach the shadow ledger.

This is a hard routing rule — not a config flag — until `H-2026-04-23-003` (OVERSHOOT FADE hypothesis) passes compliance. See `docs/superpowers/hypothesis-registry.jsonl`.

## Where verdicts live

The `pipeline/autoresearch/overshoot_compliance/direction_suspect.py` module compares the LAG compliance run (`H-2026-04-23-002`) against the OVERSHOOT compliance run (`H-2026-04-23-003`) and writes per-cell verdicts to `pipeline/autoresearch/results/direction_suspect_verdicts_<date>.json`. Verdicts:

- `CLEAN` — LAG cleared Bonferroni; live FOLLOW is supported. (Also emitted when neither slice clears anything — no alpha on either side.)
- `DIRECTION_SUSPECT` — OVERSHOOT FADE cleared but LAG FOLLOW did not; live engine is trading the wrong side.
- `PARAMETER_FRAGILE_DIRECTION` — Both slices cleared; edge exists under multiple theses.
- `INSUFFICIENT_POWER` — Fewer than 10 events in at least one slice.

## Promotion gate (spec §7)

Phase C stays `TIER_EXPLORING` until:

1. Every deployable cell is `CLEAN` (or carries an explicit waiver).
2. No `DIRECTION_SUSPECT` cell touches the deployable path.
3. Any "Phase C deployable" claim uses a Bonferroni-corrected bar — FDR-only survivors stay research-tier.

See `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` for the full gate ladder and `docs/superpowers/plans/2026-04-23-phase-c-follow-vs-fade-audit.md` for the implementation history.
