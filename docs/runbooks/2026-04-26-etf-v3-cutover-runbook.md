# ETF v3 Production Cutover Runbook

**Date:** 2026-04-26
**Trigger:** Cycle-3 verdict (`pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md`)
identifies v3 CURATED-30 as the only configuration with positive pooled
edge under honest rolling refit (53.55% / +1.83pp / P>base 78.7%).
**Goal:** Replace v2 ETF reoptimize + daily-signal jobs with v3-curated
equivalents, BEFORE tomorrow morning's 04:45 IST signal window.

---

## Prerequisites

- [x] `etf_v3_curated_reoptimize.py` written (commit `4cfb9bd`)
- [x] `etf_v3_curated_signal.py` written (commit `4cfb9bd`)
- [x] `etf_v3_curated_reoptimize.bat` written
- [x] `etf_v3_curated_signal.bat` written
- [x] Cadence sweep verdict (3/5/7/10/15 days) — DONE (#52). Production cadence locked at 5 days. See `pipeline/data/research/etf_v3/2026-04-26-cadence-sweep-verdict.md`.
- [x] 60-day forward stocks-comparison (cadence=5 + cadence=1) — DONE. Verdict: v3 picks 5% as often as v2, strict subset (zero v3-only picks), daily refit picks fewer days and loses money on its 1 active day. See `pipeline/data/research/etf_v3/2026-04-26-60d-forward-verdict.md`.
- [ ] User approval to flip scheduler (production change)

**60-day forward verdict summary (added 19:50 IST):**
| Engine | trade-eligible days / 27 | trades | cluster mean bps | hit rate |
|---|---|---|---|---|
| v2 production | 22 | 627 | +7.9 ± 14.0 | 56.6% |
| v3 cadence=5 (production) | 2 | 35 | +29.3 ± 6.6 | 71.4% |
| v3 cadence=1 (overfit) | 1 | 23 | -19.8 ± 0.0 | 56.5% |
| neither (both NEUTRAL) | 4 | 55 | -17.5 ± 15.2 | 47.3% |

**The forward shows v3 is a strict pruning of v2 (no new ideas), so cutover risk profile is:**
- Hard cutover: trade frequency drops ~95%, no new trade ideas surface, P&L exposure on n_clusters=2
- Sidecar parallel: zero downside, accumulates evidence for ~30 trade-eligible days before commit
- Recommendation: **SIDECAR**. The data does not yet justify the irreversible step.

**Today's v3-curated dry-run (sanity check before any cutover):**
- `today_zone`: NEUTRAL
- `today_signal`: 527.6
- `zone_center`: 322.23
- `zone_band`: 265.83
- `direction`: UP
- `in-fit accuracy`: 56.88%
- `in-fit sharpe`: 1.907

**v2 currently says:** RISK-ON (signal=4.35). The two engines AGREE on
direction (UP) but DISAGREE on intensity. v3 stays inside the NEUTRAL
band, v2 has crossed +1 std into RISK-ON. This divergence is exactly
the symptom user-intuition has flagged: "we were better off not doing
anything during RISK-ON." If v3 is the right model, today is a stand-down
day, not a load-up day.

---

## Cutover sequence (estimated 30 min total)

### Step 1: Seed v3 weights on production laptop (5 min)

```bat
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_v3_curated_reoptimize
```

**Expected outputs:**
- `pipeline/autoresearch/etf_v3_curated_optimal_weights.json` (new)
- `pipeline/autoresearch/regime_trade_map.json` (updated, `signal_source: "etf_v3_curated"`)
- `pipeline/logs/etf_v3_curated_reoptimize.log`

**Verification:**
```bat
python -X utf8 -c "import json; d=json.load(open(r'pipeline/autoresearch/etf_v3_curated_optimal_weights.json')); print('features:', d['n_features']); print('zone:', d['today_zone']); print('signal:', round(d['today_signal'],2)); print('center:', round(d['zone_thresholds']['center'],2)); print('band:', round(d['zone_thresholds']['band'],2))"
```

Should print: `features: 37, zone: NEUTRAL, signal: ~527, center: ~322, band: ~266`
(values match the Contabo dry-run; small drift from a few hours of intra-day
data shouldn't shift zone unless we're sitting near a band boundary).

### Step 2: Smoke-test the daily signal module (2 min)

```bat
python -X utf8 -m pipeline.autoresearch.etf_v3_curated_signal --dry-run
```

**Expected:** prints `today_zone`, `today_signal` matching Step 1.

If they differ — investigate before flipping the scheduler. The two should
produce IDENTICAL outputs on the same panel snapshot.

### Step 3: Update inventory + .bat registration (10 min)

3a. **Add v3 entries to `pipeline/config/anka_inventory.json`:**

```json
{
  "task_name": "AnkaETFv3CuratedReoptimize",
  "tier": "critical",
  "cadence_class": "weekly",
  "outputs": [
    "pipeline/autoresearch/etf_v3_curated_optimal_weights.json",
    "pipeline/autoresearch/regime_trade_map.json"
  ],
  "grace_multiplier": 1.5,
  "notes": "Saturday 22:00 IST. etf_v3_curated_reoptimize.py — Karpathy random search on curated 30 ETFs + 7 engineered Indian features. Cycle-3 verdict winner."
},
{
  "task_name": "AnkaETFv3CuratedSignal",
  "tier": "critical",
  "cadence_class": "daily",
  "outputs": [
    "pipeline/autoresearch/regime_trade_map.json"
  ],
  "grace_multiplier": 1.5,
  "notes": "04:45 IST daily. etf_v3_curated_signal.py — read stored weights, compute today_zone via canonical loader (no yfinance, no silent feature drop)."
}
```

3b. **Mark v2 entries DEPRECATED but keep them for 14 days:**

Edit `AnkaETFReoptimize` and `AnkaETFSignal` notes to prepend
`[DEPRECATED 2026-04-26 — sidecar mode, will remove 2026-05-10] `.

3c. **Register new scheduled tasks (Windows Task Scheduler):**

```bat
schtasks /create /tn "AnkaETFv3CuratedReoptimize" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_v3_curated_reoptimize.bat" /sc weekly /d SAT /st 22:00 /f
schtasks /create /tn "AnkaETFv3CuratedSignal" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_v3_curated_signal.bat" /sc daily /st 04:45 /f
```

3d. **Reroute v2 to sidecar mode (no longer canonical):**

Edit `pipeline/scripts/etf_daily_signal.bat` to set
`--trade-map pipeline/autoresearch/regime_trade_map_v2_legacy.json` so
the v2 path keeps writing for parallel monitoring but no longer overwrites
the canonical regime_trade_map.json that downstream consumers read.

### Step 4: First-run smoke (live, not dry-run) (3 min)

```bat
C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_v3_curated_signal.bat
```

Verify:
- `regime_trade_map.json` has `signal_source: "etf_v3_curated"`
- `today_regime.json` updated by regime_scanner.py
- Website JSONs updated by website_exporter.py
- Telegram dashboard reflects new zone (manually trigger morning brief if needed)

### Step 5: Watchdog + documentation (10 min)

5a. Run watchdog to confirm new tasks are recognized:

```bat
python -X utf8 -m pipeline.watchdog
```

Should NOT report `ORPHAN_TASK` for the v3 entries (they're now in
inventory). Should NOT report `MISSING_TASK` for v2 (v2 still scheduled
in sidecar mode).

5b. Update docs in same commit:
- `CLAUDE.md` — clockwork schedule section (add new tasks, mark v2 deprecated)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — ETF Regime Engine section
- `pipeline/config/anka_inventory.json` — entries from 3a
- This runbook — fill in actual cadence chosen by sweep (#52)

5c. Commit + push.

---

## Rollback plan

If anything goes wrong on day 1:

```bat
schtasks /delete /tn "AnkaETFv3CuratedSignal" /f
schtasks /delete /tn "AnkaETFv3CuratedReoptimize" /f
```

Then revert `etf_daily_signal.bat` to write to `regime_trade_map.json`
again, and run the v2 daily-signal bat to repopulate the canonical map.
The git commit can be reverted in full — no schema migrations needed.

The rollback restores production v2 in <2 minutes.

---

## Forward-shadow comparison (1-2 weeks of parallel data)

Even after cutover, keep v2 running in sidecar mode (writes to
`regime_trade_map_v2_legacy.json`). Compare daily:
- v3 zone vs v2 zone
- v3 signal vs v2 signal
- Direction agreement rate
- Zone-disagreement-conditioned next-day NIFTY return

After 14 days (≈10 trading days), if v3 has not produced any unexpected
behaviour AND v2 sidecar continues to perform within its established
distribution, retire v2 entries entirely (delete schtasks, remove .bat
files, archive `etf_reoptimize.py` and `etf_daily_signal.py` to
`pipeline/_archive/`).

If v3 misfires (extreme zone, outlier signal, missed window), pause the
v3 task and revert to v2 immediately while we debug.
