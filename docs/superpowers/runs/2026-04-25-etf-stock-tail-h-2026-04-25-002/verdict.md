# H-2026-04-25-002 backtest verdict: FAIL

Generated: 2026-04-25T19:44:29.848961+00:00  |  run_id: `5cdb2ffe7f69249922c73a5fd1a6c758`

## Held-out cross-entropy
- Model CE: **0.4838** nats/prediction
- B0_always_prior: 0.4748
- B1_regime_logistic: 0.4778
- B2_interactions_logistic: 0.5175

- Strongest baseline: **B0_always_prior**
- Permutation p-value (100k label perms): **0.0000**
- Fragility verdict: **FRAGILE**

## §15.1 gate ladder
- §5A: **PASS** — all input datasets Approved-for-research per data validation policy
- §6: **PASS** — F&O 211, point-in-time via fno_universe_history.json
- §7: **PASS** — MODE_NONE_FORECAST_ONLY (path D)
- §8: **PASS** — model outputs probabilities only — no direction conflict possible
- §9: **PASS** — n_holdout=32,580
- §9A: **FAIL** — fragility verdict = FRAGILE
- §9B.1: **FAIL** — strongest baseline = B0_always_prior (ce=0.4748); model_ce=0.4838; margin=-0.0090 nats; required ≥0.0050
- §9B.2: **PASS** — p=0.0000, floor 0.01
- §10: **PASS** — holdout_pct=0.21 (target 0.20)
- §11B: **FAIL** — calibration-residualized margin=-0.0028 nats, required ≥0.005
