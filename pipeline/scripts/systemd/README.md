# VPS systemd unit files (canonical copies)

Source of truth for systemd timers running on the Contabo VPS
(`anka@185.182.8.107`). Each unit is also installed at
`/etc/systemd/system/<name>` on the VPS.

When you change a unit file:

1. Edit the version here
2. Commit
3. SSH to VPS, pull, copy into `/etc/systemd/system/`, run
   `sudo systemctl daemon-reload`
4. If the timer was added or its OnCalendar changed:
   `sudo systemctl enable --now <name>.timer`

## H-2026-04-29-ta-karpathy-v1 (added 2026-04-28)

Three new units for the per-stock TA Lasso pilot. Holdout window
2026-04-29 -> 2026-05-28; the OPEN/CLOSE python modules guard the
window themselves so the timers can stay enabled year-round and noop
out-of-window.

| Unit | Cadence | Module |
|---|---|---|
| `anka-ta-karpathy-predict` | Daily 04:30 IST | `python -m pipeline.ta_scorer.karpathy_predict` |
| `anka-ta-karpathy-open`    | Mon-Fri 09:15 IST | `python -m pipeline.ta_scorer.karpathy_holdout open` |
| `anka-ta-karpathy-close`   | Mon-Fri 15:25 IST | `python -m pipeline.ta_scorer.karpathy_holdout close` |

## Install commands (one-time, after `git pull` on VPS)

```bash
sudo cp ~/askanka.com/pipeline/scripts/systemd/anka-ta-karpathy-*.service /etc/systemd/system/
sudo cp ~/askanka.com/pipeline/scripts/systemd/anka-ta-karpathy-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now anka-ta-karpathy-predict.timer
sudo systemctl enable --now anka-ta-karpathy-open.timer
sudo systemctl enable --now anka-ta-karpathy-close.timer
sudo systemctl list-timers | grep ta-karpathy
```

The timers do NOT need to be disabled when the holdout window closes
on 2026-05-28; the OPEN module returns early when today is outside
the window. Disable manually only if the verdict declares FAIL_*
terminal state.
