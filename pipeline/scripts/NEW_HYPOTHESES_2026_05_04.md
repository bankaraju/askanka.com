# Scheduler additions — Mon 2026-05-04 (next trading day)

Four new hypothesis engines need Windows Scheduled Tasks pointing at these
.bat files. Holdout windows have already begun; the engines no-op gracefully
on regime mismatch / holdout-window mismatch / idempotent re-runs.

Test mode for each task on first add: run as the task's owning user in a
cmd window first to verify environment + Kite session work. Then enable
the schedule.

## H-2026-04-30-RELOMC-EUPHORIA (Reliance vs OMCs)

Trigger: T-1 close V3 CURATED-30 = EUPHORIA. Fires <10 days/year.

| Task | bat | Cron |
|---|---|---|
| AnkaRELOMCBasketOpen   | relomc_basket_open.bat    | Daily 09:25 IST |
| AnkaRELOMCBasketMonitor | relomc_basket_monitor.bat | Every 15 min 09:30-14:25 IST |
| AnkaRELOMCBasketClose   | relomc_basket_close.bat   | Daily 14:25 IST |

Holdout: 2026-05-01 → 2027-04-30. Min n=10. Single-touch.

## H-2026-04-30-DEFENCE-IT-NEUTRAL

Trigger: T-1 close V3 CURATED-30 = NEUTRAL. Fires ~70% of days.

| Task | bat | Cron |
|---|---|---|
| AnkaDEFITBasketOpen    | defence_it_neutral_basket_open.bat    | Daily 09:25 IST |
| AnkaDEFITBasketMonitor | defence_it_neutral_basket_monitor.bat | Every 15 min 09:30-14:25 IST |
| AnkaDEFITBasketClose   | defence_it_neutral_basket_close.bat   | Daily 14:25 IST |

Holdout: 2026-05-01 → 2027-04-30. Min n=30. Single-touch.

## H-2026-04-30-DEFENCE-AUTO-RISKON

Trigger: T-1 close V3 CURATED-30 = RISK-ON. Fires ~13% of days.

| Task | bat | Cron |
|---|---|---|
| AnkaDEFAUBasketOpen    | defence_auto_riskon_basket_open.bat    | Daily 09:25 IST |
| AnkaDEFAUBasketMonitor | defence_auto_riskon_basket_monitor.bat | Every 15 min 09:30-14:25 IST |
| AnkaDEFAUBasketClose   | defence_auto_riskon_basket_close.bat   | Daily 14:25 IST |

Holdout: 2026-05-01 → 2027-04-30. Min n=15. Single-touch.

## H-2026-04-30-PDR-BNK-NBFC

Mean-reversion intraday pair (Banks vs NBFC_HFC). Fires only when |Z|≥1.0σ
at 11:00 IST.

| Task | bat | Cron |
|---|---|---|
| AnkaPDRBNKNBFCCaptureOpens | pdr_bnk_nbfc_capture_opens.bat | Daily 09:16 IST |
| AnkaPDRBNKNBFCBasketOpen   | pdr_bnk_nbfc_basket_open.bat   | Daily 11:00 IST |
| AnkaPDRBNKNBFCBasketClose  | pdr_bnk_nbfc_basket_close.bat  | Daily 14:25 IST |

Holdout: 2026-05-01 → 2026-08-31, auto-extend to 2026-12-31 if n<40. Single-touch.

## Notes

- All engines write to `pipeline/data/research/<hypothesis>/recommendations.csv`.
- Defence bundle uses a single package (`h_2026_04_30_defence_momentum`)
  with `--hypothesis DEFIT/DEFAU` flag; ledgers split into `defit/` vs `defau/`
  subdirectories.
- Each engine logs to `pipeline/logs/<short_id>.log`.
- Don't add to scheduler tonight per the user's "scheduler from next week"
  directive — these are ready, holding for Mon 2026-05-04.
