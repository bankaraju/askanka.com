# Phase C Intraday Shape Audit — SP1 Report

**Window:** 2026-02-24 → 2026-04-25
**N total roster:** 87  
**N valid (after BARS_INSUFFICIENT/MISMATCH):** 71
**Verdict:** **INSUFFICIENT_N**

## Table A — Shape × side × source distribution

| shape          | trade_rec   |   actual |   missed |
|:---------------|:------------|---------:|---------:|
| CHOPPY         | SHORT       |        2 |        0 |
| CHOPPY         | nan         |        1 |       27 |
| ONE_WAY_DOWN   | SHORT       |        0 |        2 |
| ONE_WAY_DOWN   | nan         |        0 |       13 |
| ONE_WAY_UP     | nan         |        0 |        4 |
| REVERSE_V_HIGH | SHORT       |        1 |        1 |
| REVERSE_V_HIGH | nan         |        1 |       17 |
| V_LOW_RECOVERY | nan         |        0 |        2 |

## Table B-actual — Win rate × shape × side (actual P&L)

| shape          | trade_rec   |   n |   win_rate |   avg_pnl_pct |
|:---------------|:------------|----:|-----------:|--------------:|
| CHOPPY         | SHORT       |   2 |          0 |        -1.195 |
| CHOPPY         | nan         |   1 |          1 |         5.32  |
| REVERSE_V_HIGH | SHORT       |   1 |          1 |         4.05  |
| REVERSE_V_HIGH | nan         |   1 |          1 |         4.05  |

## Table B-cf — Win rate × shape × side (counterfactual grid avg)

| shape          | trade_rec   |   n |   win_rate |   avg_pnl_pct |
|:---------------|:------------|----:|-----------:|--------------:|
| ONE_WAY_DOWN   | SHORT       |   2 |          1 |      0.506765 |
| REVERSE_V_HIGH | SHORT       |   1 |          1 |      1.62173  |

## Table B-best — Win rate × shape × side (counterfactual best grid)

| shape          | trade_rec   |   n |   win_rate |   avg_pnl_pct |
|:---------------|:------------|----:|-----------:|--------------:|
| ONE_WAY_DOWN   | SHORT       |   2 |          1 |      0.814974 |
| REVERSE_V_HIGH | SHORT       |   1 |          1 |      2.26322  |

## Table F — Regime × shape × side cube

| regime   | shape          | trade_rec   |   n |   win_rate |   avg_pnl_pct |
|:---------|:---------------|:------------|----:|-----------:|--------------:|
| CAUTION  | ONE_WAY_DOWN   | SHORT       |   2 |          1 |      0.506765 |
| CAUTION  | REVERSE_V_HIGH | SHORT       |   1 |          1 |      1.62173  |
