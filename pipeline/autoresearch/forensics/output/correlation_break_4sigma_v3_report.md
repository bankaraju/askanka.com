# Forensic Card v3 — Stratifying the Unexplained 4σ Residual

**Source:** correlation_break_4sigma_v2.csv (1774 events, 2021-05-10 → 2026-04-21)
**Generated:** 2026-04-25T10:46:19.318668+00:00

## Definitions

- **explained_earnings:** earnings within T-3..T+1
- **explained_sector:** |sector_index_z| ≥ 1.5 AND same direction as the break
- **co_occurs_insider:** PIT filing in T-3..T+1 (note: 0.99x lift vs random null — co-occurrence ≠ cause)
- **unexplained:** none of the above

**Overall unexplained: 56.1% (995 of 1774 events)**

Cells below n<min are suppressed; tables sorted by share_unexplained desc.

## 1. By sector (where do the unexplained breaks pile up?)

| sector_index | n | unexplained | earnings | sector | insider |
|---|---:|---:|---:|---:|---:|
| nan | 808 | 65.1% (526) | 29.2% | 0.0% | 7.4% |
| NIFTYENERGY | 161 | 61.5% (99) | 17.4% | 19.3% | 6.2% |
| BANKNIFTY | 208 | 58.7% (122) | 26.4% | 10.1% | 12.5% |
| NIFTYAUTO | 75 | 53.3% (40) | 37.3% | 10.7% | 0.0% |
| NIFTYFMCG | 111 | 51.4% (57) | 37.8% | 19.8% | 1.8% |
| NIFTYMETAL | 103 | 46.6% (48) | 33.0% | 23.3% | 6.8% |
| NIFTYPHARMA | 131 | 38.9% (51) | 44.3% | 19.8% | 11.5% |
| NIFTYIT | 158 | 29.1% (46) | 39.9% | 21.5% | 31.6% |

## 2. By year (is the residual time-concentrated?)

| year | n | unexplained | earnings | sector | insider |
|---|---:|---:|---:|---:|---:|
| 2021.0 | 222 | 53.2% (118) | 27.0% | 9.5% | 18.9% |
| 2022.0 | 329 | 55.0% (181) | 30.4% | 8.5% | 10.6% |
| 2023.0 | 385 | 55.8% (215) | 29.1% | 9.6% | 11.2% |
| 2024.0 | 377 | 57.8% (218) | 32.9% | 9.8% | 7.2% |
| 2025.0 | 326 | 54.9% (179) | 37.1% | 8.3% | 5.8% |
| 2026.0 | 135 | 62.2% (84) | 28.1% | 12.6% | 5.9% |

## 3. By regime (does any regime leak more?)

| regime | n | unexplained | earnings | sector | insider |
|---|---:|---:|---:|---:|---:|
| nan | 75 | 66.7% (50) | 14.7% | 2.7% | 22.7% |
| RISK-ON | 325 | 62.2% (202) | 26.2% | 8.9% | 8.6% |
| RISK-OFF | 308 | 59.4% (183) | 26.0% | 11.7% | 10.4% |
| NEUTRAL | 395 | 55.4% (219) | 32.7% | 11.9% | 7.6% |
| CAUTION | 361 | 51.8% (187) | 36.6% | 8.6% | 9.1% |
| EUPHORIA | 310 | 49.7% (154) | 38.1% | 7.1% | 11.0% |

## 4. By |z| magnitude bucket (do extreme breaks differ?)

| abs_z_bucket | n | unexplained | earnings | sector | insider |
|---|---:|---:|---:|---:|---:|
| [4.0, 4.5) | 593 | 58.0% (344) | 27.3% | 9.3% | 10.1% |
| [4.5, 5.0) | 378 | 58.2% (220) | 30.4% | 9.0% | 9.0% |
| [5.0, 6.0) | 368 | 57.1% (210) | 30.4% | 8.7% | 10.6% |
| [6.0, 8.0) | 302 | 52.3% (158) | 37.1% | 9.3% | 7.0% |
| [8.0, ∞) | 133 | 47.4% (63) | 40.6% | 13.5% | 15.0% |

## 5. By direction (UP vs DOWN asymmetry?)

| direction | n | unexplained | earnings | sector | insider |
|---|---:|---:|---:|---:|---:|
| UP | 1171 | 60.3% (706) | 27.1% | 8.5% | 9.4% |
| DOWN | 603 | 47.9% (289) | 39.5% | 11.1% | 10.6% |

## Observations (auto-generated)

- **Sector spread:** nan has 65.1% unexplained vs NIFTYIT at 29.1% (Δ 36.0 pp)
- **Year spread:** 2026 has 62.2% unexplained vs 2021 at 53.2%
- **Regime spread:** nan 66.7% vs EUPHORIA 49.7%
- **Direction:** UP unexplained 60.3% vs DOWN 47.9% (Δ 12.4 pp)
- **|z| trend:** smallest bucket ([4.0, 4.5)) 58.0% unexplained vs extreme bucket ([8.0, ∞)) 47.4%

## Reading the tables

A high share_unexplained cell means: this slice has many breaks that earnings/sector/insider do NOT explain — so a missing channel (likely news, bulk deals, OFS, or model error) dominates there. Look for cells that are >5 pp above the overall mean and ask: what is unique about that slice that the four observed channels miss?
