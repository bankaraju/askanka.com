# H-2026-04-25-001 backtest verdict: FAIL

Generated: 2026-04-25T08:05:45.535621+00:00

## Permutation null (label permutation, ≥100k)
- p_value: 0.3361
- 95% bootstrap CI on mean trade return (%): [-0.6637, 1.0662]

## Naive comparator suite
- random_direction: mean=0.5689%  sharpe=4.0215  hit=0.5769  n=26
- equal_weight_basket: mean=-0.1001%  sharpe=-0.6856  hit=0.5000  n=26
- fade_inverse: mean=-0.1924%  sharpe=-1.3216  hit=0.4615  n=26

## §15.1 gate ladder
- §1/3: FAIL — S0 pass (Sharpe>=1, hit>=55%, DD<=20%)  (note: )
- §1/3: FAIL — S1 pass (Sharpe>=0.8, DD<=25%, cum P&L>0)  (note: )
- §2: PASS — Risk metrics computed per bucket per level  (note: )
- §5A: PASS — Data audit classification != AUTO-FAIL  (note: impaired_pct=0.77)
- §6: PASS — Universe disclosed (or under waiver)  (note: waiver=None)
- §7: PASS — Execution mode declared = MODE_A (EOD)  (note: )
- §8: PASS — Direction audit emitted  (note: conflicts=0)
- §9: FAIL — n>=30 per regime OR flagged exploratory  (note: underpowered_count=1)
- §9A: PASS — Fragility verdict != PARAMETER-FRAGILE  (note: )
- §9B.1: FAIL — Beats strongest naive comparator at S0  (note: )
- §9B.2: PASS — Permutations >= required floor  (note: )
- §10: PARTIAL — Holdout >= 20% of history  (note: target=0.2; current holdout 6% -- waiver required for promotion)
- §11B: FAIL — Residual Sharpe >= 70% of gross Sharpe  (note: )