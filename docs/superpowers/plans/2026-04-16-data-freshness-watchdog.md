# Data-Freshness Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the scheduled-task + output-file freshness watchdog specified in `docs/superpowers/specs/2026-04-16-data-freshness-watchdog-design.md`. Ship it live in shadow mode with the canary drift test passing.

**Architecture:** Single Python entry point (`pipeline/watchdog.py`) composed of 4 focused helper modules (inventory, freshness, scheduler, alerts). Two Windows scheduled tasks (`AnkaWatchdogIntraday` every 15 min during market hours, `AnkaWatchdogGate` daily 09:20 + 16:45 IST) invoke the same script with different `--tier` / `--all` filter args. Canonical inventory at `pipeline/config/anka_inventory.json` joins task names to expected outputs and cadence class. Runtime state in `pipeline/data/watchdog_state.json` (gitignored). Alerts reuse existing `pipeline/telegram_bot.send_alert`.

**Tech Stack:** Python 3.11 (existing pipeline), `pytest` for tests, PowerShell for scheduler queries via `subprocess.run`, JSON for inventory + state, Windows Task Scheduler for triggers.

**Spec:** `docs/superpowers/specs/2026-04-16-data-freshness-watchdog-design.md`

---

## File Structure

**Create:**
- `pipeline/watchdog.py` — CLI entry point, orchestration
- `pipeline/watchdog_inventory.py` — inventory load + validate
- `pipeline/watchdog_freshness.py` — cadence formulas, market-hours gate, `check_file_freshness()`
- `pipeline/watchdog_scheduler.py` — PowerShell bridge, task-liveness check, drift detection
- `pipeline/watchdog_alerts.py` — stable-key dedup, state I/O, digest formatter, Telegram + fallback
- `pipeline/config/anka_inventory.json` — canonical inventory, seeded from live scheduler
- `pipeline/scripts/watchdog_intraday.bat` — wrapper for `AnkaWatchdogIntraday`
- `pipeline/scripts/watchdog_gate.bat` — wrapper for `AnkaWatchdogGate`
- `pipeline/tests/test_watchdog_freshness.py`
- `pipeline/tests/test_watchdog_drift.py`
- `pipeline/tests/test_watchdog_dedup.py`
- `pipeline/tests/test_watchdog_errors.py`
- `pipeline/tests/test_watchdog_telegram_fallback.py`
- `pipeline/tests/fixtures/inventory_staged.json` — dry-run smoke fixture
- `pipeline/tests/fixtures/inventory_valid_minimal.json` — unit-test fixture
- `pipeline/bootstrap_watchdog_inventory.py` — one-time bootstrap helper (enumerates live scheduler, classifies known tasks, writes `anka_inventory.json`)
- `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md` — deployment log

**Modify:**
- `.gitignore` — add `pipeline/data/watchdog_state.json`
- `CLAUDE.md` — add one paragraph referencing `anka_inventory.json` as the canonical registry

**Register (PowerShell, not source):**
- `AnkaWatchdogIntraday` scheduled task
- `AnkaWatchdogGate` scheduled task

---

## Context for the executor

- **Platform:** Windows 10. Shell is Git Bash. PowerShell invoked via `powershell.exe -ExecutionPolicy Bypass -File <ps1>`. Never use inline `-Command` with bash-quoted strings — bash mangles `$_`, `$t`, etc. Always write a `.ps1` file first under `C:/Users/Claude_Anka/AppData/Local/Temp/`.
- **Paths:** forward-slash in bash commands; backslash in `.bat` files and PowerShell `Execute` fields.
- **Python venv:** system Python 3.11, not a venv. Direct `python` on the PATH.
- **Timezone:** IST (UTC+5:30). The project has `pipeline/kite_client.py` using `datetime(..., tzinfo=timezone(timedelta(hours=5, minutes=30)))`. Reuse this pattern.
- **Existing Telegram alerter:** `pipeline/telegram_bot.py` exposes `send_alert(**kwargs)`. Reuse — don't reimplement HTTP.
- **Branch:** all work on `feat/data-freshness-watchdog` (created in Task 1). Merge-to-master at end via `superpowers:finishing-a-development-branch`.
- **Rollback anchor:** branch isolation. Nothing destructive before Task 15 (scheduler registration).

---

## Task 1: Branch setup + transcript scaffold

**Files:**
- Create: `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md`

- [ ] **Step 1: Create and switch to feature branch**

```bash
cd /c/Users/Claude_Anka/askanka.com
git checkout master
git status
git checkout -b feat/data-freshness-watchdog
```

Expected: clean working tree on new branch `feat/data-freshness-watchdog`.

- [ ] **Step 2: Write transcript scaffold**

Create `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md`:

```markdown
# Watchdog Bootstrap Transcript — 2026-04-16

**Spec:** `docs/superpowers/specs/2026-04-16-data-freshness-watchdog-design.md`
**Plan:** `docs/superpowers/plans/2026-04-16-data-freshness-watchdog.md`
**Branch:** `feat/data-freshness-watchdog`

## Bootstrap inventory

<populated by Task 2>

## Unit test suite

<populated by Task 14>

## Dry-run smoke test

<populated by Task 14>

## Scheduler registration

<populated by Task 15>

## Shadow-mode first run

<populated by Task 16>

## Canary drift acceptance test (spec §Acceptance #7)

<populated by Task 17>
```

- [ ] **Step 3: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "chore(watchdog): branch + transcript scaffold

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Bootstrap inventory (data artifact)

**Files:**
- Create: `pipeline/bootstrap_watchdog_inventory.py`
- Create: `pipeline/config/anka_inventory.json`

- [ ] **Step 1: Write the bootstrap script**

Create `pipeline/bootstrap_watchdog_inventory.py`:

```python
"""
One-time bootstrap: enumerate live Anka* scheduled tasks, apply a known
classification table, default unknowns to tier=info/cadence=daily, and
write pipeline/config/anka_inventory.json.

Run once. Re-runs merge new tasks non-destructively (preserve existing
classifications for task_names already present in the inventory).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_PATH = REPO_ROOT / "pipeline" / "config" / "anka_inventory.json"

# Known classifications. Every Anka* task we have confident classification
# for gets a row here. Unknown tasks inherit the default below.
KNOWN_TASKS = {
    # --- CRITICAL tier: decision backbone ---
    "AnkaReverseRegimeProfile": {
        "tier": "critical",
        "cadence_class": "daily",
        "outputs": ["pipeline/autoresearch/reverse_regime_profile.json"],
        "grace_multiplier": 1.5,
        "notes": "Phase A overnight profile @ 04:45 IST. Backbone of Phase B ranker.",
    },
    "AnkaMorningScan": {
        "tier": "critical",
        "cadence_class": "daily",
        "outputs": ["data/global_regime.json", "data/live_status.json"],
        "grace_multiplier": 1.5,
        "notes": "09:25 IST. Regime + technicals + OI + news + spread + Phase B ranker.",
    },
    "AnkaEODReview": {
        "tier": "critical",
        "cadence_class": "daily",
        "outputs": ["data/track_record.json"],
        "grace_multiplier": 1.5,
        "notes": "16:00 IST. EOD P&L + track record.",
    },
    "AnkaCorrelationBreaks": {
        "tier": "critical",
        "cadence_class": "intraday",
        "outputs": ["pipeline/data/correlation_breaks.json"],
        "grace_multiplier": 2.0,
        "notes": "Phase C every 15 min during market hours. Restored 2026-04-16 C1.",
    },

    # --- WARN tier: operational but not decision-critical ---
    "AnkaEODTrackRecord": {
        "tier": "warn",
        "cadence_class": "daily",
        "outputs": ["data/track_record.json"],
        "grace_multiplier": 1.5,
        "notes": "16:15 IST. Generates EOD report + website export.",
    },
    "AnkaKiteRefresh": {
        "tier": "warn",
        "cadence_class": "daily",
        "outputs": [],
        "grace_multiplier": 1.5,
        "notes": "09:00 IST. Zerodha API session refresh. No file output; freshness judged on task-last-run only.",
    },
    "AnkaWeeklyStats": {
        "tier": "warn",
        "cadence_class": "weekly",
        "outputs": ["data/spread_stats.json"],
        "grace_multiplier": 1.25,
        "notes": "Sunday 22:00 IST. Backtest refresh for spread library.",
    },
    "AnkaWeeklyReport": {
        "tier": "warn",
        "cadence_class": "weekly",
        "outputs": [],
        "grace_multiplier": 1.25,
        "notes": "Friday 10:00 IST. Weekly rollup summary.",
    },
}

DEFAULT_CLASSIFICATION = {
    "tier": "info",
    "cadence_class": "daily",
    "outputs": [],
    "grace_multiplier": 1.5,
    "notes": "UNCLASSIFIED — bootstrap default. Review and update tier/cadence/outputs.",
}


def enumerate_anka_tasks() -> list[str]:
    """Call PowerShell Get-ScheduledTask -TaskName Anka* and return task names."""
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-ScheduledTask -TaskName 'Anka*' | Select-Object -ExpandProperty TaskName",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"PowerShell failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return sorted(names)


def load_existing_inventory() -> dict:
    """Load existing inventory if present, else return empty shell."""
    if INVENTORY_PATH.exists():
        with INVENTORY_PATH.open() as f:
            return json.load(f)
    return {"version": 1, "updated": "", "tasks": []}


def main() -> None:
    live_tasks = enumerate_anka_tasks()
    if not live_tasks:
        print("No Anka* tasks found in scheduler.", file=sys.stderr)
        sys.exit(1)

    existing = load_existing_inventory()
    existing_by_name = {t["task_name"]: t for t in existing.get("tasks", [])}

    merged = []
    for name in live_tasks:
        if name in existing_by_name:
            # Preserve existing classification (human may have refined it).
            merged.append(existing_by_name[name])
        elif name in KNOWN_TASKS:
            entry = {"task_name": name, **KNOWN_TASKS[name]}
            merged.append(entry)
        else:
            entry = {"task_name": name, **DEFAULT_CLASSIFICATION}
            merged.append(entry)

    from datetime import date

    inventory = {
        "version": 1,
        "updated": date.today().isoformat(),
        "tasks": merged,
    }

    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INVENTORY_PATH.open("w") as f:
        json.dump(inventory, f, indent=2, sort_keys=False)
        f.write("\n")

    unclassified = sum(1 for t in merged if t["tier"] == "info" and "UNCLASSIFIED" in t["notes"])
    classified = len(merged) - unclassified
    print(f"Wrote {INVENTORY_PATH}")
    print(f"  {len(merged)} tasks total")
    print(f"  {classified} classified")
    print(f"  {unclassified} defaulted to info/daily (needs human review)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the bootstrap**

```bash
cd /c/Users/Claude_Anka/askanka.com
python pipeline/bootstrap_watchdog_inventory.py
```

Expected output ending in something like:
```
Wrote C:\Users\Claude_Anka\askanka.com\pipeline\config\anka_inventory.json
  69 tasks total
  8 classified
  61 defaulted to info/daily (needs human review)
```

- [ ] **Step 3: Verify the inventory is valid JSON and has expected structure**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import json
from pathlib import Path
inv = json.load(open('pipeline/config/anka_inventory.json'))
assert inv['version'] == 1, inv
assert 'tasks' in inv, inv
assert len(inv['tasks']) > 0, inv
assert all('task_name' in t for t in inv['tasks']), inv
assert all('tier' in t and t['tier'] in ('critical','warn','info') for t in inv['tasks']), inv
assert all('cadence_class' in t and t['cadence_class'] in ('intraday','daily','weekly') for t in inv['tasks']), inv
print('OK:', len(inv['tasks']), 'tasks valid')
"
```

Expected: `OK: N tasks valid` where N >= 8.

- [ ] **Step 4: Append bootstrap output to transcript + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Bootstrap output"
  echo '```'
  python pipeline/bootstrap_watchdog_inventory.py 2>&1 | tail -10
  echo '```'
  echo ""
  echo "### Inventory size"
  python -c "import json; d=json.load(open('pipeline/config/anka_inventory.json')); print('tasks:', len(d['tasks']))"
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md

git add pipeline/bootstrap_watchdog_inventory.py pipeline/config/anka_inventory.json docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "feat(watchdog): bootstrap script + initial inventory

Enumerate live Anka* tasks, apply 8 known classifications, default the
rest to tier=info/cadence=daily for later human review.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Cadence formulas + market-hours gate (TDD)

**Files:**
- Create: `pipeline/watchdog_freshness.py`
- Create: `pipeline/tests/test_watchdog_freshness.py`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_watchdog_freshness.py`:

```python
"""Tests for cadence formulas and market-hours awareness."""

from datetime import datetime, timezone, timedelta

import pytest

from pipeline.watchdog_freshness import (
    IST,
    compute_window_seconds,
    is_market_hours,
)


class TestComputeWindow:
    def test_intraday_default_multiplier(self):
        # base 15 min + 30 min grace * 1.5 = 60 min = 3600s
        assert compute_window_seconds("intraday", 1.5) == 3600

    def test_intraday_grace_2x(self):
        # 15 min + 30 min * 2.0 = 75 min = 4500s
        assert compute_window_seconds("intraday", 2.0) == 4500

    def test_daily_default(self):
        # 24h + 4h * 1.5 = 30h = 108000s
        assert compute_window_seconds("daily", 1.5) == 108000

    def test_weekly_default(self):
        # 7d + 1d * 1.5 = 8.5d = 734400s
        assert compute_window_seconds("weekly", 1.5) == 734400

    def test_unknown_cadence_raises(self):
        with pytest.raises(ValueError, match="unknown cadence_class"):
            compute_window_seconds("hourly", 1.5)

    def test_negative_multiplier_raises(self):
        with pytest.raises(ValueError, match="grace_multiplier"):
            compute_window_seconds("daily", -0.5)


class TestMarketHours:
    def test_tuesday_10am_is_market_hours(self):
        # 2026-04-14 was a Tuesday
        t = datetime(2026, 4, 14, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_0914_before_open(self):
        t = datetime(2026, 4, 14, 9, 14, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_tuesday_0915_at_open(self):
        t = datetime(2026, 4, 14, 9, 15, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_1530_at_close(self):
        t = datetime(2026, 4, 14, 15, 30, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_1531_after_close(self):
        t = datetime(2026, 4, 14, 15, 31, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_saturday_is_not_market_hours(self):
        # 2026-04-18 is a Saturday
        t = datetime(2026, 4, 18, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_sunday_is_not_market_hours(self):
        t = datetime(2026, 4, 19, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_utc_timestamp_converted_correctly(self):
        # 04:30 UTC on Tuesday = 10:00 IST — market hours
        t = datetime(2026, 4, 14, 4, 30, tzinfo=timezone.utc)
        assert is_market_hours(t) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_freshness.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'pipeline.watchdog_freshness'` or similar.

- [ ] **Step 3: Write the minimal module**

Create `pipeline/watchdog_freshness.py`:

```python
"""Cadence formulas and market-hours gate for the watchdog.

The watchdog asks two orthogonal questions per file:
  1. Are we currently in a window where this file is expected to be fresh?
     (market-hours awareness for intraday cadence)
  2. If so, is the file older than its grace-adjusted window?
"""

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# (base_interval_seconds, base_grace_seconds) per cadence class.
_CADENCE_BASE = {
    "intraday": (15 * 60, 30 * 60),       # 15 min expected, 30 min base grace
    "daily":    (24 * 3600, 4 * 3600),    # 24 h, 4 h base grace
    "weekly":   (7 * 86400, 1 * 86400),   # 7 d, 1 d base grace
}

_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def compute_window_seconds(cadence_class: str, grace_multiplier: float) -> int:
    """Return window = base_interval + base_grace * grace_multiplier (seconds)."""
    if cadence_class not in _CADENCE_BASE:
        raise ValueError(f"unknown cadence_class: {cadence_class!r}")
    if grace_multiplier < 0:
        raise ValueError(f"grace_multiplier must be >= 0, got {grace_multiplier}")
    base_interval, base_grace = _CADENCE_BASE[cadence_class]
    return int(base_interval + base_grace * grace_multiplier)


def is_market_hours(now: datetime) -> bool:
    """True if `now` is within Mon-Fri 09:15-15:30 IST.

    Accepts any timezone-aware datetime; converts to IST internally.
    """
    now_ist = now.astimezone(IST)
    if now_ist.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return _MARKET_OPEN <= now_ist.time() <= _MARKET_CLOSE
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_freshness.py -v 2>&1 | tail -20
```

Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_freshness.py pipeline/tests/test_watchdog_freshness.py
git commit -m "feat(watchdog): cadence formulas + market-hours gate (TDD)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: File-freshness check (TDD)

**Files:**
- Modify: `pipeline/watchdog_freshness.py` (add `check_file_freshness()`)
- Modify: `pipeline/tests/test_watchdog_freshness.py` (add file-freshness tests)

- [ ] **Step 1: Write the failing tests (append to existing file)**

Append to `pipeline/tests/test_watchdog_freshness.py`:

```python
from pathlib import Path

from pipeline.watchdog_freshness import (
    FreshnessResult,
    check_file_freshness,
)


class TestCheckFileFreshness:
    def test_missing_file_returns_missing(self, tmp_path):
        missing = tmp_path / "nope.json"
        result = check_file_freshness(
            missing, cadence_class="daily", grace_multiplier=1.5,
            now=datetime(2026, 4, 16, 10, 0, tzinfo=IST),
        )
        assert result == FreshnessResult.OUTPUT_MISSING

    def test_fresh_daily_file(self, tmp_path):
        f = tmp_path / "fresh.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)
        # Set mtime 1 hour ago
        one_hour_ago = (now - timedelta(hours=1)).timestamp()
        import os
        os.utime(f, (one_hour_ago, one_hour_ago))

        result = check_file_freshness(
            f, cadence_class="daily", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.FRESH

    def test_stale_daily_file(self, tmp_path):
        f = tmp_path / "stale.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)
        # Set mtime 31 hours ago (window for daily/1.5 is 30h)
        import os
        old = (now - timedelta(hours=31)).timestamp()
        os.utime(f, (old, old))

        result = check_file_freshness(
            f, cadence_class="daily", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.OUTPUT_STALE

    def test_intraday_outside_market_hours_is_fresh(self, tmp_path):
        f = tmp_path / "live_status.json"
        f.write_text("{}")
        # Saturday 10:00 IST — outside market hours, always fresh
        now = datetime(2026, 4, 18, 10, 0, tzinfo=IST)
        import os
        very_old = (now - timedelta(days=5)).timestamp()
        os.utime(f, (very_old, very_old))

        result = check_file_freshness(
            f, cadence_class="intraday", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.FRESH

    def test_intraday_during_market_hours_stale(self, tmp_path):
        f = tmp_path / "live_status.json"
        f.write_text("{}")
        # Tuesday 10:00 IST, file is 2 hours old — window is 60 min → stale
        now = datetime(2026, 4, 14, 10, 0, tzinfo=IST)
        import os
        old = (now - timedelta(minutes=120)).timestamp()
        os.utime(f, (old, old))

        result = check_file_freshness(
            f, cadence_class="intraday", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.OUTPUT_STALE
```

- [ ] **Step 2: Run tests, watch them fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_freshness.py::TestCheckFileFreshness -v 2>&1 | tail -15
```

Expected: `ImportError: cannot import name 'FreshnessResult'`.

- [ ] **Step 3: Add `FreshnessResult` + `check_file_freshness()` to watchdog_freshness.py**

Append to `pipeline/watchdog_freshness.py`:

```python
import enum
import os
from pathlib import Path


class FreshnessResult(enum.Enum):
    FRESH = "FRESH"
    OUTPUT_STALE = "OUTPUT_STALE"
    OUTPUT_MISSING = "OUTPUT_MISSING"


def check_file_freshness(
    output_path: Path,
    cadence_class: str,
    grace_multiplier: float,
    now: datetime,
) -> FreshnessResult:
    """Classify one file's freshness per the spec's stale-detection logic.

    1. If file missing → OUTPUT_MISSING.
    2. If intraday AND not market hours → FRESH (always fresh outside market hours).
    3. If file age > window → OUTPUT_STALE.
    4. Else → FRESH.
    """
    path = Path(output_path)
    if not path.exists():
        return FreshnessResult.OUTPUT_MISSING

    if cadence_class == "intraday" and not is_market_hours(now):
        return FreshnessResult.FRESH

    window = compute_window_seconds(cadence_class, grace_multiplier)
    age = now.timestamp() - os.stat(path).st_mtime
    if age > window:
        return FreshnessResult.OUTPUT_STALE
    return FreshnessResult.FRESH
```

- [ ] **Step 4: Run tests, watch them pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_freshness.py -v 2>&1 | tail -20
```

Expected: all 17 tests pass (12 from Task 3 + 5 new).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_freshness.py pipeline/tests/test_watchdog_freshness.py
git commit -m "feat(watchdog): check_file_freshness with missing/stale classification

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Inventory loader + validator (TDD)

**Files:**
- Create: `pipeline/watchdog_inventory.py`
- Create: `pipeline/tests/test_watchdog_errors.py`
- Create: `pipeline/tests/fixtures/inventory_valid_minimal.json`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/fixtures/inventory_valid_minimal.json`:

```json
{
  "version": 1,
  "updated": "2026-04-16",
  "tasks": [
    {
      "task_name": "AnkaMorningScan",
      "tier": "critical",
      "cadence_class": "daily",
      "outputs": ["data/global_regime.json"],
      "grace_multiplier": 1.5,
      "notes": "morning scan"
    }
  ]
}
```

Create `pipeline/tests/test_watchdog_errors.py`:

```python
"""Tests for inventory loading and error-handling invariants."""

import json
from pathlib import Path

import pytest

from pipeline.watchdog_inventory import (
    InventoryError,
    load_inventory,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadInventory:
    def test_valid_minimal(self):
        inv = load_inventory(FIXTURES / "inventory_valid_minimal.json")
        assert inv["version"] == 1
        assert len(inv["tasks"]) == 1
        assert inv["tasks"][0]["task_name"] == "AnkaMorningScan"

    def test_missing_file_raises_InventoryError(self, tmp_path):
        with pytest.raises(InventoryError, match="not found"):
            load_inventory(tmp_path / "does_not_exist.json")

    def test_malformed_json_raises_InventoryError(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{this is: not valid json")
        with pytest.raises(InventoryError, match="malformed JSON"):
            load_inventory(f)

    def test_missing_version_raises(self, tmp_path):
        f = tmp_path / "no_version.json"
        f.write_text(json.dumps({"tasks": []}))
        with pytest.raises(InventoryError, match="version"):
            load_inventory(f)

    def test_invalid_tier_raises(self, tmp_path):
        f = tmp_path / "bad_tier.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "X", "tier": "bogus", "cadence_class": "daily",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        with pytest.raises(InventoryError, match="tier"):
            load_inventory(f)

    def test_invalid_cadence_raises(self, tmp_path):
        f = tmp_path / "bad_cadence.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "X", "tier": "info", "cadence_class": "hourly",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        with pytest.raises(InventoryError, match="cadence_class"):
            load_inventory(f)

    def test_missing_task_field_raises(self, tmp_path):
        f = tmp_path / "missing_field.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{"task_name": "X"}],  # missing everything else
        }))
        with pytest.raises(InventoryError, match="missing"):
            load_inventory(f)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_errors.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'pipeline.watchdog_inventory'`.

- [ ] **Step 3: Write the module**

Create `pipeline/watchdog_inventory.py`:

```python
"""Inventory file loader and schema validator.

The inventory is the canonical source-of-truth for what tasks should exist
and what their output-file contracts are. A missing or malformed inventory
is a FATAL condition — the watchdog must never silently fall back to
enumerating the live scheduler, because silent drift is the bug we're fixing.
"""

import json
from pathlib import Path
from typing import Any

VALID_TIERS = {"critical", "warn", "info"}
VALID_CADENCES = {"intraday", "daily", "weekly"}
REQUIRED_TASK_FIELDS = {
    "task_name", "tier", "cadence_class", "outputs", "grace_multiplier", "notes",
}


class InventoryError(Exception):
    """Raised on any inventory load/validate failure. Always fatal."""


def load_inventory(path: Path) -> dict[str, Any]:
    """Load and validate the inventory JSON. Raise InventoryError on any issue."""
    path = Path(path)
    if not path.exists():
        raise InventoryError(f"inventory file not found: {path}")
    try:
        with path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise InventoryError(f"malformed JSON in {path}: {e}") from e

    if not isinstance(data, dict):
        raise InventoryError(f"inventory root must be an object, got {type(data).__name__}")
    if "version" not in data:
        raise InventoryError("inventory missing required top-level field: version")
    if data.get("version") != 1:
        raise InventoryError(f"unsupported inventory version: {data.get('version')}")
    if "tasks" not in data or not isinstance(data["tasks"], list):
        raise InventoryError("inventory missing or non-list 'tasks' field")

    for i, task in enumerate(data["tasks"]):
        if not isinstance(task, dict):
            raise InventoryError(f"tasks[{i}] is not an object")
        missing = REQUIRED_TASK_FIELDS - set(task.keys())
        if missing:
            raise InventoryError(f"tasks[{i}] ({task.get('task_name', '?')}) missing fields: {sorted(missing)}")
        if task["tier"] not in VALID_TIERS:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) invalid tier: {task['tier']!r}")
        if task["cadence_class"] not in VALID_CADENCES:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) invalid cadence_class: {task['cadence_class']!r}")
        if not isinstance(task["outputs"], list):
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) outputs must be a list")
        if not isinstance(task["grace_multiplier"], (int, float)) or task["grace_multiplier"] < 0:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) grace_multiplier must be non-negative number")

    return data
```

- [ ] **Step 4: Run tests, watch them pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_errors.py -v 2>&1 | tail -15
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_inventory.py pipeline/tests/test_watchdog_errors.py pipeline/tests/fixtures/inventory_valid_minimal.json
git commit -m "feat(watchdog): inventory loader + validator (TDD)

Missing inventory = fatal InventoryError. Malformed JSON = fatal.
Field-level validation rejects unknown tier/cadence and missing fields.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Scheduler query bridge (TDD with mocked subprocess)

**Files:**
- Create: `pipeline/watchdog_scheduler.py`
- Create: `pipeline/tests/test_watchdog_drift.py`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_watchdog_drift.py`:

```python
"""Tests for scheduler query bridge and drift detection."""

from unittest.mock import patch, MagicMock

import pytest

from pipeline.watchdog_scheduler import (
    SchedulerQueryError,
    TaskLivenessResult,
    query_anka_tasks,
    check_task_liveness,
    check_drift,
)


class TestQueryAnkaTasks:
    def test_parses_powershell_json_output(self):
        fake_stdout = """[
            {"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"},
            {"TaskName": "AnkaEODReview", "LastTaskResult": 0, "LastRunTime": "2026-04-15T16:00:00"}
        ]"""
        mock_result = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert len(tasks) == 2
        assert tasks[0]["TaskName"] == "AnkaMorningScan"
        assert tasks[0]["LastTaskResult"] == 0

    def test_single_task_object_wrapped_to_list(self):
        # PowerShell returns a single object (not array) for one-task result
        fake_stdout = """{"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"}"""
        mock_result = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert len(tasks) == 1

    def test_empty_output_returns_empty_list(self):
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert tasks == []

    def test_powershell_nonzero_raises_SchedulerQueryError(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="Access denied")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            with pytest.raises(SchedulerQueryError, match="Access denied"):
                query_anka_tasks()


class TestDriftDetection:
    def _inventory(self, task_names):
        return {"version": 1, "updated": "2026-04-16", "tasks": [
            {"task_name": n, "tier": "info", "cadence_class": "daily",
             "outputs": [], "grace_multiplier": 1.5, "notes": ""}
            for n in task_names
        ]}

    def _live(self, task_names):
        return [{"TaskName": n, "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:00:00"} for n in task_names]

    def test_exact_agreement_zero_drift(self):
        inv = self._inventory(["A", "B", "C"])
        live = self._live(["A", "B", "C"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == []
        assert ghosts == []

    def test_scheduler_has_extra_tasks_yields_orphans(self):
        inv = self._inventory(["A", "B"])
        live = self._live(["A", "B", "C", "D"])
        orphans, ghosts = check_drift(inv, live)
        assert sorted(orphans) == ["C", "D"]
        assert ghosts == []

    def test_inventory_has_extra_tasks_yields_ghosts(self):
        inv = self._inventory(["A", "B", "C", "D"])
        live = self._live(["A", "B"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == []
        assert sorted(ghosts) == ["C", "D"]

    def test_both_drifts_simultaneously(self):
        inv = self._inventory(["A", "B", "X"])
        live = self._live(["A", "B", "Y"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == ["Y"]
        assert ghosts == ["X"]


class TestCheckTaskLiveness:
    def test_result_0_recent_run_is_alive(self):
        task = {"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"}
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.ALIVE

    def test_never_ran_sentinel(self):
        task = {"TaskName": "AnkaGapPredictor", "LastTaskResult": 267011,
                "LastRunTime": "1999-12-30T00:00:00"}
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_NEVER_RAN

    def test_nonzero_result(self):
        task = {"TaskName": "AnkaWeeklyReport", "LastTaskResult": 1,
                "LastRunTime": "2026-04-11T10:00:00"}
        result = check_task_liveness(task, cadence_class="weekly", grace_multiplier=1.25,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_STALE_RESULT

    def test_stale_run_time(self):
        task = {"TaskName": "AnkaMorningScan", "LastTaskResult": 0,
                "LastRunTime": "2026-04-14T09:25:00"}
        # 48h later, daily cadence + 1.5 multiplier = 30h window → stale run
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_STALE_RUN
```

- [ ] **Step 2: Run tests, watch them fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_drift.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'pipeline.watchdog_scheduler'`.

- [ ] **Step 3: Write the module**

Create `pipeline/watchdog_scheduler.py`:

```python
"""PowerShell bridge to Windows Task Scheduler + drift + task-liveness checks.

Query format: one `Get-ScheduledTask -TaskName Anka* | Get-ScheduledTaskInfo`
invocation piped to ConvertTo-Json. Single call; watchdog does NOT iterate per
task (that would multiply latency by ~70x on a slow laptop).
"""

import enum
import json
import subprocess
from datetime import datetime

from pipeline.watchdog_freshness import IST, compute_window_seconds

# PowerShell one-liner: enumerate Anka*, join with TaskInfo, emit JSON array.
_PS_QUERY = (
    "Get-ScheduledTask -TaskName 'Anka*' | "
    "ForEach-Object { "
    "  $i = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath; "
    "  [PSCustomObject]@{ "
    "    TaskName = $_.TaskName; "
    "    LastTaskResult = $i.LastTaskResult; "
    "    LastRunTime = $i.LastRunTime.ToString('o'); "
    "    NextRunTime = $i.NextRunTime.ToString('o') "
    "  } "
    "} | ConvertTo-Json -Compress"
)


class SchedulerQueryError(Exception):
    """Raised when the PowerShell Get-ScheduledTask call fails."""


class TaskLivenessResult(enum.Enum):
    ALIVE = "ALIVE"
    TASK_NEVER_RAN = "TASK_NEVER_RAN"
    TASK_STALE_RESULT = "TASK_STALE_RESULT"
    TASK_STALE_RUN = "TASK_STALE_RUN"


def query_anka_tasks() -> list[dict]:
    """Invoke PowerShell, return list of {TaskName, LastTaskResult, LastRunTime, NextRunTime}."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", _PS_QUERY],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise SchedulerQueryError(f"Get-ScheduledTask failed: {result.stderr.strip()}")
    out = result.stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    # PowerShell returns a single object (not array) when only one result
    if isinstance(data, dict):
        return [data]
    return data


def check_drift(inventory: dict, live_tasks: list[dict]) -> tuple[list[str], list[str]]:
    """Return (orphans, ghosts).

    orphans = Anka* tasks in scheduler but not in inventory.
    ghosts  = inventory entries whose task_name is not in scheduler.
    """
    inv_names = {t["task_name"] for t in inventory["tasks"]}
    live_names = {t["TaskName"] for t in live_tasks}
    orphans = sorted(live_names - inv_names)
    ghosts = sorted(inv_names - live_names)
    return orphans, ghosts


def check_task_liveness(
    task: dict,
    cadence_class: str,
    grace_multiplier: float,
    now_iso: str,
) -> TaskLivenessResult:
    """Classify one live-scheduler task entry against its expected cadence."""
    # 1999 sentinel = never ran
    last_run_raw = task.get("LastRunTime", "")
    if last_run_raw.startswith("1999-") or last_run_raw.startswith("0001-"):
        return TaskLivenessResult.TASK_NEVER_RAN

    # Non-zero result = crashed or failed
    if task.get("LastTaskResult", 0) != 0:
        return TaskLivenessResult.TASK_STALE_RESULT

    # Parse last-run timestamp and compute age
    try:
        last_run = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
    except (ValueError, AttributeError):
        return TaskLivenessResult.TASK_STALE_RUN

    age = (now - last_run).total_seconds()
    window = compute_window_seconds(cadence_class, grace_multiplier)
    if age > window:
        return TaskLivenessResult.TASK_STALE_RUN
    return TaskLivenessResult.ALIVE
```

- [ ] **Step 4: Run tests, watch them pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_drift.py -v 2>&1 | tail -20
```

Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_scheduler.py pipeline/tests/test_watchdog_drift.py
git commit -m "feat(watchdog): PowerShell scheduler bridge + drift + task-liveness

Single PS invocation enumerates Anka* with joined TaskInfo. Drift compares
inventory to live tasks (returns orphans + ghosts). Liveness classifies
per task against cadence + grace.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Dedup state + alert digest (TDD)

**Files:**
- Create: `pipeline/watchdog_alerts.py`
- Create: `pipeline/tests/test_watchdog_dedup.py`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_watchdog_dedup.py`:

```python
"""Tests for dedup state, stable keys, and digest formatting."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from pipeline.watchdog_alerts import (
    Issue,
    IssueKind,
    State,
    build_digest,
    load_state,
    save_state,
    stable_key,
    update_state,
)

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class TestStableKey:
    def test_key_joins_three_parts_with_pipe(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaMorningScan",
            output_path="data/global_regime.json", detail="",
        )
        assert stable_key(i) == "AnkaMorningScan|data/global_regime.json|OUTPUT_STALE"

    def test_key_with_no_output_path(self):
        i = Issue(
            kind=IssueKind.TASK_NEVER_RAN, task_name="AnkaGapPredictor",
            output_path=None, detail="",
        )
        assert stable_key(i) == "AnkaGapPredictor||TASK_NEVER_RAN"


class TestStateIO:
    def test_load_missing_state_returns_empty(self, tmp_path):
        state = load_state(tmp_path / "nope.json")
        assert state.active_issues == {}

    def test_load_malformed_state_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        state = load_state(f)
        assert state.active_issues == {}

    def test_save_and_reload_roundtrip(self, tmp_path):
        state = State(
            last_run="2026-04-16T09:20:00+05:30",
            active_issues={
                "A|path|OUTPUT_STALE": {
                    "first_seen": "2026-04-16T09:20:00+05:30",
                    "last_seen": "2026-04-16T09:20:00+05:30",
                    "alert_count": 1,
                }
            },
        )
        f = tmp_path / "state.json"
        save_state(state, f)
        loaded = load_state(f)
        assert loaded.active_issues == state.active_issues


class TestUpdateState:
    def _now(self):
        return datetime(2026, 4, 16, 9, 20, tzinfo=IST).isoformat()

    def test_new_issue_gets_alert_count_1(self):
        state = State(last_run="", active_issues={})
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new = update_state(state, [issue], self._now())
        key = stable_key(issue)
        assert is_new[key] is True
        assert new_state.active_issues[key]["alert_count"] == 1

    def test_persistent_issue_increments_count(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new = update_state(state, [issue], self._now())
        assert is_new[key] is False
        assert new_state.active_issues[key]["alert_count"] == 3

    def test_resolved_issue_returns_resolved_list(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        # No current issues
        new_state, is_new = update_state(state, [], self._now())
        assert key not in new_state.active_issues


class TestBuildDigest:
    def test_clean_digest_has_all_section_headers(self):
        state = State(last_run="", active_issues={})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[], resolved_keys=[], state=state, is_new={},
        )
        assert "CRITICAL (0)" in digest
        assert "WARN (0)" in digest
        assert "DRIFT (0)" in digest

    def test_new_critical_renders_loud_block(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaReverseRegimeProfile",
            output_path="pipeline/autoresearch/reverse_regime_profile.json",
            detail="mtime 2026-04-14 15:38 (42h old, max 30h)",
            tier="critical",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 1,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: True},
        )
        assert "AnkaReverseRegimeProfile" in digest
        assert "42h old" in digest

    def test_persistent_issue_renders_compact_reminder(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaMorningScan",
            output_path="data/global_regime.json", detail="",
            tier="critical",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 3,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: False},
        )
        assert "still stale" in digest.lower() or "3rd run" in digest or "run 3" in digest.lower()

    def test_escalation_at_count_6(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaWeeklyStats",
            output_path="data/spread_stats.json", detail="",
            tier="warn",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 6,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: False},
        )
        assert "STILL BROKEN" in digest

    def test_resolved_tail_shows_recovered_keys(self):
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[], resolved_keys=["AnkaEODReview|data/track_record.json|OUTPUT_STALE"],
            state=State(last_run="", active_issues={}), is_new={},
        )
        assert "RESOLVED" in digest
        assert "AnkaEODReview" in digest
```

- [ ] **Step 2: Run tests, watch them fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_dedup.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the alerts module (without Telegram yet — comes in Task 8)**

Create `pipeline/watchdog_alerts.py`:

```python
"""Dedup state, issue keys, digest formatting. Telegram send is in Task 8."""

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class IssueKind(enum.Enum):
    OUTPUT_STALE = "OUTPUT_STALE"
    OUTPUT_MISSING = "OUTPUT_MISSING"
    TASK_NEVER_RAN = "TASK_NEVER_RAN"
    TASK_STALE_RESULT = "TASK_STALE_RESULT"
    TASK_STALE_RUN = "TASK_STALE_RUN"
    ORPHAN_TASK = "ORPHAN_TASK"
    INVENTORY_GHOST = "INVENTORY_GHOST"


@dataclass
class Issue:
    kind: IssueKind
    task_name: str
    output_path: Optional[str] = None
    detail: str = ""
    tier: str = "info"


@dataclass
class State:
    last_run: str
    active_issues: dict = field(default_factory=dict)


ESCALATION_COUNT = 6


def stable_key(issue: Issue) -> str:
    return f"{issue.task_name}|{issue.output_path or ''}|{issue.kind.value}"


def load_state(path: Path) -> State:
    path = Path(path)
    if not path.exists():
        return State(last_run="", active_issues={})
    try:
        with path.open() as f:
            data = json.load(f)
        return State(
            last_run=data.get("last_run", ""),
            active_issues=data.get("active_issues", {}),
        )
    except (json.JSONDecodeError, OSError):
        return State(last_run="", active_issues={})


def save_state(state: State, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump({"last_run": state.last_run, "active_issues": state.active_issues},
                  f, indent=2)
        f.write("\n")


def update_state(
    prior: State,
    current_issues: list[Issue],
    now_iso: str,
) -> tuple[State, dict[str, bool]]:
    """Return (new_state, is_new_map). is_new_map[key] = True if first time seen."""
    is_new: dict[str, bool] = {}
    new_active: dict[str, dict] = {}
    for issue in current_issues:
        key = stable_key(issue)
        if key in prior.active_issues:
            prev = prior.active_issues[key]
            new_active[key] = {
                "first_seen": prev["first_seen"],
                "last_seen": now_iso,
                "alert_count": prev["alert_count"] + 1,
            }
            is_new[key] = False
        else:
            new_active[key] = {
                "first_seen": now_iso,
                "last_seen": now_iso,
                "alert_count": 1,
            }
            is_new[key] = True
    return State(last_run=now_iso, active_issues=new_active), is_new


def _format_issue_loud(issue: Issue) -> str:
    lines = [f"  • {issue.task_name} — {issue.kind.value.lower().replace('_', ' ')}"]
    if issue.output_path:
        lines.append(f"    {issue.output_path}  {issue.detail}")
    elif issue.detail:
        lines.append(f"    {issue.detail}")
    return "\n".join(lines)


def _format_issue_compact(issue: Issue, alert_count: int) -> str:
    return f"  • {issue.task_name} still {issue.kind.value.lower().replace('_', ' ')} (run {alert_count})"


def build_digest(
    run_label: str,
    now_iso: str,
    current_issues: list[Issue],
    resolved_keys: list[str],
    state: State,
    is_new: dict[str, bool],
) -> str:
    """Assemble the Telegram-ready digest message."""
    by_bucket: dict[str, list[Issue]] = {"CRITICAL": [], "WARN": [], "INFO": [], "DRIFT": []}
    for issue in current_issues:
        if issue.kind in (IssueKind.ORPHAN_TASK, IssueKind.INVENTORY_GHOST):
            by_bucket["DRIFT"].append(issue)
        else:
            by_bucket[issue.tier.upper()].append(issue)

    total = sum(len(v) for v in by_bucket.values())
    header = f"🚨 Anka Watchdog — {now_iso[:16].replace('T', ' ')} IST\n{run_label} • {total} issue{'s' if total != 1 else ''}"

    sections = [header, ""]
    for bucket in ("CRITICAL", "WARN", "DRIFT"):
        items = by_bucket[bucket]
        sections.append(f"{bucket} ({len(items)}):")
        for issue in items:
            key = stable_key(issue)
            count = state.active_issues.get(key, {}).get("alert_count", 1)
            if is_new.get(key, True):
                sections.append(_format_issue_loud(issue))
            elif count == ESCALATION_COUNT:
                sections.append(f"  ⚠️ STILL BROKEN AFTER {count // 2} DAYS")
                sections.append(_format_issue_loud(issue))
            else:
                sections.append(_format_issue_compact(issue, count))
        sections.append("")

    if resolved_keys:
        sections.append(f"RESOLVED ({len(resolved_keys)}):")
        for key in resolved_keys:
            task_name = key.split("|")[0]
            sections.append(f"  ✅ {task_name} — fresh again")

    return "\n".join(sections).rstrip() + "\n"
```

- [ ] **Step 4: Run tests, watch them pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_dedup.py -v 2>&1 | tail -20
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_alerts.py pipeline/tests/test_watchdog_dedup.py
git commit -m "feat(watchdog): dedup state + stable-key issues + digest formatter

Issue dataclass with IssueKind enum. State persisted as JSON. update_state
computes first-seen/persistent/escalation transitions. build_digest renders
Telegram-ready message with CRITICAL/WARN/DRIFT sections + RESOLVED tail.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Telegram send + fallback-to-log (TDD)

**Files:**
- Modify: `pipeline/watchdog_alerts.py` (add `send_or_log_digest()`)
- Create: `pipeline/tests/test_watchdog_telegram_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_watchdog_telegram_fallback.py`:

```python
"""Tests for Telegram send + log fallback."""

from unittest.mock import patch, MagicMock

import pytest

from pipeline.watchdog_alerts import send_or_log_digest


class TestSendOrLogDigest:
    def test_happy_path_calls_send_alert(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock(return_value=True)
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=False)
        assert ok is True
        mock_send.assert_called_once()
        assert not fallback_log.exists()  # no fallback needed

    def test_telegram_failure_writes_fallback_log(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock(side_effect=RuntimeError("token revoked"))
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=False)
        assert ok is False
        assert fallback_log.exists()
        content = fallback_log.read_text()
        assert "TELEGRAM_FAILED" in content
        assert "test digest" in content
        assert "token revoked" in content

    def test_dry_run_skips_telegram(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock()
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=True)
        assert ok is True
        mock_send.assert_not_called()
        assert not fallback_log.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_telegram_fallback.py -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'send_or_log_digest'`.

- [ ] **Step 3: Append to `pipeline/watchdog_alerts.py`**

Add to the bottom of `pipeline/watchdog_alerts.py`:

```python
from datetime import datetime


def _send_alert(digest: str) -> bool:
    """Thin shim around pipeline.telegram_bot.send_alert. Isolated for mocking.

    send_alert's signature takes **kwargs of alert fields. Watchdog sends one
    plain-text message with the 'message' key, which the telegram_bot formatter
    renders as the body of the Telegram message.
    """
    from pipeline.telegram_bot import send_alert
    return send_alert(kind="WATCHDOG", message=digest)


def send_or_log_digest(digest: str, fallback_log: Path, dry_run: bool = False) -> bool:
    """Send digest to Telegram, fall back to log on failure.

    Returns True iff Telegram delivery succeeded (or dry_run). Log-fallback
    returns False but does not raise.
    """
    if dry_run:
        return True
    try:
        return bool(_send_alert(digest))
    except Exception as e:
        fallback_log.parent.mkdir(parents=True, exist_ok=True)
        with Path(fallback_log).open("a", encoding="utf-8") as f:
            f.write(f"\n---\nTELEGRAM_FAILED {datetime.now().isoformat()}\nerror: {type(e).__name__}: {e}\n{digest}\n")
        return False
```

- [ ] **Step 4: Run tests, watch them pass**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_telegram_fallback.py -v 2>&1 | tail -15
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog_alerts.py pipeline/tests/test_watchdog_telegram_fallback.py
git commit -m "feat(watchdog): send_or_log_digest with Telegram fallback

On success: send_alert returns True.
On Telegram exception: fallback log entry with TELEGRAM_FAILED prefix + traceback note, return False.
On dry_run: no-op, return True.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Main orchestrator + CLI (`watchdog.py`)

**Files:**
- Create: `pipeline/watchdog.py`

- [ ] **Step 1: Write the main entry module**

Create `pipeline/watchdog.py`:

```python
"""Watchdog CLI entry point — orchestrates inventory → scheduler → freshness → drift → alerts.

Usage:
    python pipeline/watchdog.py --all                  # gate-run: every task + drift
    python pipeline/watchdog.py --tier critical        # intraday: critical tier only
    python pipeline/watchdog.py --all --dry-run        # shadow-mode: digest to stdout instead of Telegram
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from pipeline.watchdog_alerts import (
    Issue,
    IssueKind,
    build_digest,
    load_state,
    save_state,
    send_or_log_digest,
    update_state,
)
from pipeline.watchdog_freshness import (
    IST,
    FreshnessResult,
    check_file_freshness,
)
from pipeline.watchdog_inventory import (
    InventoryError,
    load_inventory,
)
from pipeline.watchdog_scheduler import (
    SchedulerQueryError,
    TaskLivenessResult,
    check_drift,
    check_task_liveness,
    query_anka_tasks,
)

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_PATH = REPO_ROOT / "pipeline" / "config" / "anka_inventory.json"
STATE_PATH = REPO_ROOT / "pipeline" / "data" / "watchdog_state.json"
LOG_PATH = REPO_ROOT / "pipeline" / "logs" / "watchdog.log"
ALERT_FALLBACK_PATH = REPO_ROOT / "pipeline" / "logs" / "watchdog_alerts.log"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("anka.watchdog")


def _fail_inventory(reason: str, now_iso: str, dry_run: bool) -> None:
    """Inventory missing/malformed → emergency alert + exit 1."""
    emergency = f"🚨 Anka Watchdog EMERGENCY {now_iso[:16]}\ninventory problem: {reason}\nskipping this run"
    log.error("INVENTORY FAIL: %s", reason)
    send_or_log_digest(emergency, ALERT_FALLBACK_PATH, dry_run=dry_run)
    sys.exit(1)


def _filter_tasks_by_tier(inventory: dict, tier_filter: str | None) -> list[dict]:
    if tier_filter is None:
        return inventory["tasks"]
    return [t for t in inventory["tasks"] if t["tier"] == tier_filter]


def _eval_task(task: dict, live_by_name: dict, now: datetime) -> list[Issue]:
    """Evaluate one inventory task — return a list of issues (may be empty)."""
    issues: list[Issue] = []
    task_name = task["task_name"]
    tier = task["tier"]
    cadence = task["cadence_class"]
    grace = task["grace_multiplier"]

    # File checks
    for output_path_str in task["outputs"]:
        path = REPO_ROOT / output_path_str
        result = check_file_freshness(path, cadence, grace, now)
        if result == FreshnessResult.OUTPUT_MISSING:
            issues.append(Issue(
                kind=IssueKind.OUTPUT_MISSING, task_name=task_name,
                output_path=output_path_str, detail="file does not exist",
                tier=tier,
            ))
        elif result == FreshnessResult.OUTPUT_STALE:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
            age_hours = (now - mtime).total_seconds() / 3600
            issues.append(Issue(
                kind=IssueKind.OUTPUT_STALE, task_name=task_name,
                output_path=output_path_str,
                detail=f"mtime {mtime:%Y-%m-%d %H:%M} ({age_hours:.1f}h old)",
                tier=tier,
            ))

    # Task liveness (only if task is in live scheduler)
    if task_name in live_by_name:
        result = check_task_liveness(
            live_by_name[task_name], cadence, grace,
            now.isoformat(),
        )
        kind_map = {
            TaskLivenessResult.TASK_NEVER_RAN: IssueKind.TASK_NEVER_RAN,
            TaskLivenessResult.TASK_STALE_RESULT: IssueKind.TASK_STALE_RESULT,
            TaskLivenessResult.TASK_STALE_RUN: IssueKind.TASK_STALE_RUN,
        }
        if result in kind_map:
            last = live_by_name[task_name]
            issues.append(Issue(
                kind=kind_map[result], task_name=task_name,
                output_path=None,
                detail=f"LastTaskResult=0x{last.get('LastTaskResult', 0):x} LastRunTime={last.get('LastRunTime', '?')}",
                tier=tier,
            ))
    return issues


def run(args: argparse.Namespace) -> int:
    now = datetime.now(IST)
    now_iso = now.isoformat()
    run_label = "Intraday check" if args.tier else "Gate run"

    # 1. Load inventory (fatal on failure)
    try:
        inventory = load_inventory(INVENTORY_PATH)
    except InventoryError as e:
        _fail_inventory(str(e), now_iso, args.dry_run)
        return 1  # unreachable

    # 2. Query live scheduler (warn + skip drift on failure, continue file checks)
    drift_skipped = False
    live_tasks: list[dict] = []
    try:
        live_tasks = query_anka_tasks()
    except SchedulerQueryError as e:
        log.warning("scheduler query failed: %s (drift check will be skipped)", e)
        drift_skipped = True

    live_by_name = {t["TaskName"]: t for t in live_tasks}

    # 3. Evaluate each inventory task (filtered by tier if requested)
    selected = _filter_tasks_by_tier(inventory, args.tier)
    current_issues: list[Issue] = []
    for task in selected:
        current_issues.extend(_eval_task(task, live_by_name, now))

    # 4. Drift checks — only on --all (gate) runs, and only if scheduler query worked
    if not args.tier and not drift_skipped:
        orphans, ghosts = check_drift(inventory, live_tasks)
        for name in orphans:
            current_issues.append(Issue(
                kind=IssueKind.ORPHAN_TASK, task_name=name,
                detail="registered in scheduler but not in inventory", tier="warn",
            ))
        for name in ghosts:
            current_issues.append(Issue(
                kind=IssueKind.INVENTORY_GHOST, task_name=name,
                detail="in inventory but missing from scheduler", tier="warn",
            ))

    # 5. Dedup + digest
    prior_state = load_state(STATE_PATH)
    new_state, is_new = update_state(prior_state, current_issues, now_iso)
    resolved_keys = [k for k in prior_state.active_issues if k not in new_state.active_issues]

    # 6. Emit or log
    if not current_issues and not resolved_keys:
        log.info("OK %d tasks, 0 issues", len(selected))
        save_state(new_state, STATE_PATH)
        return 0

    digest = build_digest(
        run_label=run_label + (" (DRIFT skipped)" if drift_skipped else ""),
        now_iso=now_iso,
        current_issues=current_issues,
        resolved_keys=resolved_keys,
        state=new_state,
        is_new=is_new,
    )

    if args.dry_run:
        print(digest)
        log.info("[DRY-RUN] digest written to stdout (%d issues, %d resolved)",
                 len(current_issues), len(resolved_keys))
    else:
        ok = send_or_log_digest(digest, ALERT_FALLBACK_PATH, dry_run=False)
        log.info("digest sent: telegram_ok=%s (%d issues, %d resolved)",
                 ok, len(current_issues), len(resolved_keys))

    save_state(new_state, STATE_PATH)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Anka data-freshness watchdog")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="check every task + drift (gate run)")
    group.add_argument("--tier", choices=["critical", "warn", "info"], help="check only this tier")
    parser.add_argument("--dry-run", action="store_true", help="print digest to stdout instead of Telegram")
    parser.add_argument("--inventory", type=Path, help="override inventory path (for tests)")
    args = parser.parse_args()

    # Allow --inventory override for fixtures
    if args.inventory:
        global INVENTORY_PATH
        INVENTORY_PATH = args.inventory

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the CLI parses args**

```bash
cd /c/Users/Claude_Anka/askanka.com
python pipeline/watchdog.py --help
```

Expected: help text with `--all`, `--tier`, `--dry-run`, `--inventory` options.

- [ ] **Step 3: Smoke-test a dry-run against the real inventory**

```bash
cd /c/Users/Claude_Anka/askanka.com
mkdir -p pipeline/logs
python pipeline/watchdog.py --all --dry-run 2>&1 | head -50
```

Expected: either prints "OK N tasks, 0 issues" (clean) or prints a digest to stdout. Exit 0. No Telegram delivery.

- [ ] **Step 4: Verify state file is written**

```bash
cd /c/Users/Claude_Anka/askanka.com
test -f pipeline/data/watchdog_state.json && echo "state file exists" || echo "MISSING"
cat pipeline/data/watchdog_state.json | python -c "import json, sys; print('valid JSON:', bool(json.load(sys.stdin)))"
```

Expected: "state file exists" and "valid JSON: True".

- [ ] **Step 5: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/watchdog.py
git commit -m "feat(watchdog): main orchestrator + CLI

Wires inventory → scheduler → per-task eval → drift → dedup → digest.
--all for gate runs (drift + all tiers), --tier critical for intraday,
--dry-run to print digest instead of Telegram.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: End-to-end error-handling tests

**Files:**
- Modify: `pipeline/tests/test_watchdog_errors.py` (add end-to-end cases)

- [ ] **Step 1: Append integration-level error-handling tests**

Append to `pipeline/tests/test_watchdog_errors.py`:

```python
from unittest.mock import patch, MagicMock
import subprocess


class TestEndToEndErrorPaths:
    def test_missing_inventory_exits_1_with_emergency_alert(self, tmp_path, capsys):
        """Calling watchdog with missing inventory path → exit 1, emergency alert."""
        import importlib
        import pipeline.watchdog as wd

        # Redirect inventory to nonexistent file
        args = MagicMock(all=True, tier=None, dry_run=True, inventory=tmp_path / "absent.json")
        wd.INVENTORY_PATH = args.inventory

        with patch("pipeline.watchdog.send_or_log_digest") as mock_send:
            with pytest.raises(SystemExit) as exc:
                wd.run(args)
            assert exc.value.code == 1
            mock_send.assert_called_once()
            # First positional arg is the emergency digest string
            emergency_msg = mock_send.call_args[0][0]
            assert "EMERGENCY" in emergency_msg
            assert "inventory" in emergency_msg.lower()

    def test_scheduler_query_failure_skips_drift_continues_file_checks(self, tmp_path, monkeypatch):
        """If PowerShell fails, drift is skipped but file checks still run."""
        # Minimal valid inventory
        inv = tmp_path / "inv.json"
        inv.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "AnkaTest", "tier": "info", "cadence_class": "daily",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        # State in tmp
        state = tmp_path / "state.json"
        import pipeline.watchdog as wd
        monkeypatch.setattr(wd, "INVENTORY_PATH", inv)
        monkeypatch.setattr(wd, "STATE_PATH", state)
        monkeypatch.setattr(wd, "ALERT_FALLBACK_PATH", tmp_path / "alerts.log")
        monkeypatch.setattr(wd, "LOG_PATH", tmp_path / "wd.log")

        from pipeline.watchdog_scheduler import SchedulerQueryError
        with patch("pipeline.watchdog.query_anka_tasks", side_effect=SchedulerQueryError("ps fail")):
            with patch("pipeline.watchdog.send_or_log_digest") as mock_send:
                args = MagicMock(all=True, tier=None, dry_run=True, inventory=inv)
                exit_code = wd.run(args)
        assert exit_code == 0  # ran cleanly despite drift-skip
```

- [ ] **Step 2: Run the new tests**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_errors.py -v 2>&1 | tail -15
```

Expected: 9 tests pass (7 from Task 5 + 2 new).

- [ ] **Step 3: Run the entire watchdog test suite as a final check**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_*.py -v 2>&1 | tail -30
```

Expected: 40+ tests pass (17 freshness + 7 errors + 12 drift + 11 dedup + 3 telegram + 2 new = ~52). Zero failures.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/tests/test_watchdog_errors.py
git commit -m "test(watchdog): end-to-end error paths (missing inventory, scheduler fail)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Dry-run smoke fixture + integration test

**Files:**
- Create: `pipeline/tests/fixtures/inventory_staged.json`

- [ ] **Step 1: Create a fixture that deliberately stales one file**

Create `pipeline/tests/fixtures/inventory_staged.json`:

```json
{
  "version": 1,
  "updated": "2026-04-16",
  "tasks": [
    {
      "task_name": "AnkaReverseRegimeProfile",
      "tier": "critical",
      "cadence_class": "daily",
      "outputs": ["pipeline/tests/fixtures/does_not_exist_on_purpose.json"],
      "grace_multiplier": 1.5,
      "notes": "fixture — expected to fire OUTPUT_MISSING"
    },
    {
      "task_name": "AnkaFixtureOK",
      "tier": "warn",
      "cadence_class": "daily",
      "outputs": ["pipeline/tests/fixtures/inventory_valid_minimal.json"],
      "grace_multiplier": 1000.0,
      "notes": "fixture — huge grace means never stale, for RESOLVED testing"
    }
  ]
}
```

- [ ] **Step 2: Run dry-run against the fixture**

```bash
cd /c/Users/Claude_Anka/askanka.com
python pipeline/watchdog.py --all --dry-run --inventory pipeline/tests/fixtures/inventory_staged.json 2>&1 | tee /tmp/dryrun_out.txt
```

Expected output contains:
- `🚨 Anka Watchdog`
- `CRITICAL (1):`
- `AnkaReverseRegimeProfile — output missing`
- `does_not_exist_on_purpose.json`

Exit code 0.

- [ ] **Step 3: Append dry-run output to transcript**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Dry-run smoke test"
  echo '```'
  head -40 /tmp/dryrun_out.txt
  echo '```'
  echo ""
  echo "### Full watchdog test suite"
  python -m pytest pipeline/tests/test_watchdog_*.py -v 2>&1 | tail -10
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
```

- [ ] **Step 4: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/tests/fixtures/inventory_staged.json docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "test(watchdog): staged fixture + dry-run smoke

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Batch wrappers

**Files:**
- Create: `pipeline/scripts/watchdog_intraday.bat`
- Create: `pipeline/scripts/watchdog_gate.bat`

- [ ] **Step 1: Write the intraday wrapper**

Create `pipeline/scripts/watchdog_intraday.bat`:

```batch
@echo off
REM ANKA Watchdog — intraday cadence (every 15 min, market hours only)
REM Only checks tier=critical files. Drift check only runs in --all mode.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 pipeline\watchdog.py --tier critical >> pipeline\logs\watchdog.log 2>&1
```

- [ ] **Step 2: Write the gate wrapper**

Create `pipeline/scripts/watchdog_gate.bat`:

```batch
@echo off
REM ANKA Watchdog — twice-daily gate (09:20 + 16:45 IST)
REM Checks every task, every tier, plus drift.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 pipeline\watchdog.py --all >> pipeline\logs\watchdog.log 2>&1
```

- [ ] **Step 3: Manual smoke — gate wrapper produces log output**

```bash
cd /c/Users/Claude_Anka/askanka.com
# The wrapper will run with NO --dry-run, meaning if there are any real
# stale items and Telegram is configured, a message WILL go out. For first
# smoke, edit both .bats to include --dry-run temporarily, run, verify.
cp pipeline/scripts/watchdog_gate.bat /tmp/watchdog_gate_real.bat
sed -i 's/ --all / --all --dry-run /' pipeline/scripts/watchdog_gate.bat
cmd //c "pipeline\\scripts\\watchdog_gate.bat"
echo "exit=$?"
tail -10 pipeline/logs/watchdog.log
# Restore real version
cp /tmp/watchdog_gate_real.bat pipeline/scripts/watchdog_gate.bat
rm /tmp/watchdog_gate_real.bat
```

Expected: exit 0, `watchdog.log` has recent entry showing the dry-run digest or "OK N tasks, 0 issues".

- [ ] **Step 4: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/scripts/watchdog_intraday.bat pipeline/scripts/watchdog_gate.bat
git commit -m "feat(watchdog): .bat wrappers for intraday + gate scheduled tasks

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Gitignore + CLAUDE.md update

**Files:**
- Modify: `.gitignore`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Check current .gitignore for the watchdog_state.json pattern**

```bash
cd /c/Users/Claude_Anka/askanka.com
grep -n "watchdog\|^pipeline/data/" .gitignore || echo "pattern not present"
```

- [ ] **Step 2: Add `watchdog_state.json` to .gitignore**

Read the existing `.gitignore`, then append (using Edit tool to keep existing content):

Append this block at the end of `.gitignore`:

```
# Watchdog runtime state (regenerates each run)
pipeline/data/watchdog_state.json

# Watchdog fallback alerts log (generated when Telegram fails)
pipeline/logs/watchdog_alerts.log
```

- [ ] **Step 3: Append CLAUDE.md reference paragraph**

Append to `CLAUDE.md` (under the existing "Clockwork Schedule (IST)" section or at the end):

```markdown

## Scheduler Inventory (Canonical)

Every `Anka*` scheduled task MUST appear in `pipeline/config/anka_inventory.json` with its tier (critical/warn/info), cadence_class (intraday/daily/weekly), expected output files, and grace_multiplier. The data-freshness watchdog (`pipeline/watchdog.py`) uses this inventory as the source-of-truth for what should exist in the scheduler and what their output-file freshness contracts are. Adding a new scheduled task without updating the inventory will trigger an `ORPHAN_TASK` alert on the next watchdog run — this is by design.
```

- [ ] **Step 4: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add .gitignore CLAUDE.md
git commit -m "chore(watchdog): gitignore runtime state + CLAUDE.md inventory reference

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Final unit-suite sign-off + transcript update

**Files:**
- Modify: `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md`

- [ ] **Step 1: Run the entire test suite one more time**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_watchdog_*.py -v 2>&1 | tee /tmp/watchdog_suite.txt | tail -20
echo "---"
grep -E "passed|failed|error" /tmp/watchdog_suite.txt | tail -5
```

Expected: 50+ tests all passing, zero failures.

- [ ] **Step 2: Append suite output to transcript**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Final unit-suite run (pre-registration)"
  echo '```'
  tail -20 /tmp/watchdog_suite.txt
  echo '```'
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
```

- [ ] **Step 3: Commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "docs(watchdog): unit-suite sign-off captured in transcript

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Register scheduled tasks (Stage 1 shadow mode — `--dry-run` ON)

**Files:**
- No source changes. Writes PS script to `%TEMP%` and invokes.

- [ ] **Step 1: Write the registration PowerShell script**

Write to `C:/Users/Claude_Anka/AppData/Local/Temp/register_watchdog.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

# --- AnkaWatchdogIntraday ---
$nameI = 'AnkaWatchdogIntraday'
$batI = 'C:\Users\Claude_Anka\askanka.com\pipeline\scripts\watchdog_intraday.bat'

$existing = Get-ScheduledTask -TaskName $nameI -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $nameI -Confirm:$false
    Write-Output "unregistered existing $nameI"
}

$actionI = New-ScheduledTaskAction -Execute $batI -WorkingDirectory (Split-Path $batI -Parent)

# Trigger: every 15 min between 09:30 and 15:30, Mon-Fri
$triggerI = New-ScheduledTaskTrigger -Once -At (Get-Date '09:30:00') `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Hours 6)
$triggerI.DaysOfWeek = 62  # bitmask: Mon(2)+Tue(4)+Wed(8)+Thu(16)+Fri(32) = 62

$settingsI = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $nameI `
    -Action $actionI -Trigger $triggerI -Settings $settingsI `
    -User $env:USERNAME -RunLevel Limited `
    -Description 'STAGE 1 SHADOW — Data-freshness watchdog, critical-tier only. Every 15 min 09:30-15:30 Mon-Fri. Currently --dry-run via .bat.' | Out-Null

Write-Output "registered $nameI"

# --- AnkaWatchdogGate ---
$nameG = 'AnkaWatchdogGate'
$batG = 'C:\Users\Claude_Anka\askanka.com\pipeline\scripts\watchdog_gate.bat'

$existing = Get-ScheduledTask -TaskName $nameG -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $nameG -Confirm:$false
    Write-Output "unregistered existing $nameG"
}

$actionG = New-ScheduledTaskAction -Execute $batG -WorkingDirectory (Split-Path $batG -Parent)
$triggerG1 = New-ScheduledTaskTrigger -Daily -At 9:20AM
$triggerG2 = New-ScheduledTaskTrigger -Daily -At 4:45PM

$settingsG = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $nameG `
    -Action $actionG -Trigger @($triggerG1, $triggerG2) -Settings $settingsG `
    -User $env:USERNAME -RunLevel Limited `
    -Description 'STAGE 1 SHADOW — Data-freshness watchdog gate run (all tiers + drift). 09:20 + 16:45 IST daily. Currently --dry-run via .bat.' | Out-Null

Write-Output "registered $nameG"

# Sanity check
Get-ScheduledTask -TaskName 'AnkaWatchdog*' | Format-Table TaskName, State
```

- [ ] **Step 2: Edit `.bat` wrappers to add `--dry-run` (shadow mode)**

Modify `pipeline/scripts/watchdog_intraday.bat` to include `--dry-run`:

```batch
@echo off
REM ANKA Watchdog — intraday cadence (STAGE 1 SHADOW: --dry-run ON)
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 pipeline\watchdog.py --tier critical --dry-run >> pipeline\logs\watchdog.log 2>&1
```

Modify `pipeline/scripts/watchdog_gate.bat` similarly:

```batch
@echo off
REM ANKA Watchdog — twice-daily gate (STAGE 1 SHADOW: --dry-run ON)
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 pipeline\watchdog.py --all --dry-run >> pipeline\logs\watchdog.log 2>&1
```

- [ ] **Step 3: Invoke the registration script**

```bash
cd /c/Users/Claude_Anka/askanka.com
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/register_watchdog.ps1" 2>&1 | tee /tmp/register_out.txt
```

Expected output ends with:
```
TaskName                    State
--------                    -----
AnkaWatchdogGate            Ready
AnkaWatchdogIntraday        Ready
```

- [ ] **Step 4: Manually fire the gate task and confirm exit 0**

```bash
powershell.exe -Command "Start-ScheduledTask -TaskName AnkaWatchdogGate; Start-Sleep -Seconds 20; Get-ScheduledTaskInfo -TaskName AnkaWatchdogGate | Format-List LastTaskResult,LastRunTime,NextRunTime"
```

Expected: `LastTaskResult : 0`, `LastRunTime` within the last minute.

- [ ] **Step 5: Commit the .bat shadow-mode edits + append transcript**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Scheduler registration"
  echo '```'
  cat /tmp/register_out.txt
  echo '```'
  echo ""
  echo "### AnkaWatchdogGate first manual fire"
  powershell.exe -Command "Get-ScheduledTaskInfo -TaskName AnkaWatchdogGate | Format-List LastTaskResult,LastRunTime,NextRunTime" 2>&1
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md

git add pipeline/scripts/watchdog_intraday.bat pipeline/scripts/watchdog_gate.bat docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "feat(watchdog): Stage 1 shadow mode — scheduled tasks registered with --dry-run

AnkaWatchdogIntraday every 15 min Mon-Fri 09:30-15:30.
AnkaWatchdogGate daily 09:20 + 16:45 IST.
Both .bats pass --dry-run so digests go to watchdog.log only, no Telegram.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Shadow-mode first-run verification

**Files:**
- Modify: `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md`

- [ ] **Step 1: Confirm watchdog.log has today's dry-run entry**

```bash
cd /c/Users/Claude_Anka/askanka.com
echo "=== watchdog.log tail ==="
tail -60 pipeline/logs/watchdog.log
echo ""
echo "=== most recent [DRY-RUN] marker ==="
grep -n "DRY-RUN\|OK.*tasks" pipeline/logs/watchdog.log | tail -5
```

Expected: log shows `[DRY-RUN] digest written to stdout (N issues, M resolved)` or `OK N tasks, 0 issues` — either is a success indicator for shadow mode.

- [ ] **Step 2: Inspect a stale-detection result if any**

```bash
cd /c/Users/Claude_Anka/askanka.com
# If any issues surfaced, the .bat's stdout redirect captured the full digest
grep -B1 -A80 "🚨 Anka Watchdog" pipeline/logs/watchdog.log 2>/dev/null | tail -100
```

Expected: either nothing (0 issues — pipeline is clean) or one or more digest blocks showing stale items. Either outcome is acceptable — the watchdog is doing its job.

- [ ] **Step 3: Append shadow-run observation to transcript**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Shadow-mode first-run evidence"
  echo '```'
  tail -30 pipeline/logs/watchdog.log
  echo '```'
  echo ""
  echo "### Issues surfaced on first gate run (if any)"
  echo '```'
  grep -B1 -A30 "🚨 Anka Watchdog" pipeline/logs/watchdog.log 2>/dev/null | tail -50 || echo "(no digest blocks — watchdog says clean)"
  echo '```'
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md

git add docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "docs(watchdog): shadow-mode first-run captured in transcript

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Canary drift acceptance test (spec §Acceptance #7)

**Files:**
- Modify: `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md`
- Temporary: register + unregister `AnkaWatchdogDriftCanary`.

The purpose: verify the drift check works end-to-end against a real task, per spec §Acceptance #7's 4-step canary sequence.

- [ ] **Step 1: Register the canary task (scheduler only, NOT inventory)**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/canary_register.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$name = 'AnkaWatchdogDriftCanary'

$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }

# Trivial action that always exits 0
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c echo canary && exit 0'
$trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM  # never fires during today's session
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -User $env:USERNAME -RunLevel Limited `
    -Description 'CANARY - temporary drift-check fixture, delete after acceptance test' | Out-Null

Write-Output "registered $name"
```

```bash
cd /c/Users/Claude_Anka/askanka.com
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/canary_register.ps1"
```

Expected: `registered AnkaWatchdogDriftCanary`.

- [ ] **Step 2: Observation (a) — run watchdog gate, verify `ORPHAN_TASK` alert**

```bash
cd /c/Users/Claude_Anka/askanka.com
# Clear state so this appears as new
rm -f pipeline/data/watchdog_state.json
powershell.exe -Command "Start-ScheduledTask -TaskName AnkaWatchdogGate; Start-Sleep -Seconds 15"
tail -60 pipeline/logs/watchdog.log > /tmp/canary_a.txt
cat /tmp/canary_a.txt
```

Expected: digest block contains `ORPHAN_TASK` and `AnkaWatchdogDriftCanary`.

- [ ] **Step 3: Observation (b) — add canary to inventory, verify `RESOLVED`**

Append this row to `pipeline/config/anka_inventory.json` inside the `tasks` array:

```json
{
  "task_name": "AnkaWatchdogDriftCanary",
  "tier": "info",
  "cadence_class": "daily",
  "outputs": [],
  "grace_multiplier": 1.5,
  "notes": "CANARY — temporary drift-check fixture"
}
```

Then:

```bash
cd /c/Users/Claude_Anka/askanka.com
powershell.exe -Command "Start-ScheduledTask -TaskName AnkaWatchdogGate; Start-Sleep -Seconds 15"
tail -30 pipeline/logs/watchdog.log > /tmp/canary_b.txt
cat /tmp/canary_b.txt
```

Expected: digest contains `RESOLVED` line mentioning `AnkaWatchdogDriftCanary`.

- [ ] **Step 4: Observation (c) — unregister canary, verify `INVENTORY_GHOST`**

```bash
cd /c/Users/Claude_Anka/askanka.com
powershell.exe -Command "Unregister-ScheduledTask -TaskName AnkaWatchdogDriftCanary -Confirm:`$false"
powershell.exe -Command "Start-ScheduledTask -TaskName AnkaWatchdogGate; Start-Sleep -Seconds 15"
tail -30 pipeline/logs/watchdog.log > /tmp/canary_c.txt
cat /tmp/canary_c.txt
```

Expected: digest contains `INVENTORY_GHOST` and `AnkaWatchdogDriftCanary`.

- [ ] **Step 5: Observation (d) — remove canary from inventory, verify clean**

Delete the canary row from `pipeline/config/anka_inventory.json`.

```bash
cd /c/Users/Claude_Anka/askanka.com
powershell.exe -Command "Start-ScheduledTask -TaskName AnkaWatchdogGate; Start-Sleep -Seconds 15"
tail -30 pipeline/logs/watchdog.log > /tmp/canary_d.txt
cat /tmp/canary_d.txt
```

Expected: digest contains `RESOLVED` line for `INVENTORY_GHOST`, no mention of canary in CRITICAL/WARN/DRIFT sections.

- [ ] **Step 6: Append all 4 observations to transcript + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
  echo ""
  echo "### Canary drift acceptance test (spec §Acceptance #7)"
  echo ""
  echo "#### (a) scheduler has canary, inventory does not → ORPHAN_TASK expected"
  echo '```'
  cat /tmp/canary_a.txt
  echo '```'
  echo ""
  echo "#### (b) canary added to inventory → ORPHAN_TASK resolves"
  echo '```'
  cat /tmp/canary_b.txt
  echo '```'
  echo ""
  echo "#### (c) canary removed from scheduler → INVENTORY_GHOST expected"
  echo '```'
  cat /tmp/canary_c.txt
  echo '```'
  echo ""
  echo "#### (d) canary removed from inventory → clean"
  echo '```'
  cat /tmp/canary_d.txt
  echo '```'
} >> docs/operations/2026-04-16-watchdog-bootstrap-transcript.md

git add pipeline/config/anka_inventory.json docs/operations/2026-04-16-watchdog-bootstrap-transcript.md
git commit -m "test(watchdog): canary drift acceptance test passed

4-step sequence validated: (a) orphan, (b) resolve, (c) ghost, (d) clean.
All observations appear in the canonical log + transcript.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Batch exit gate

Plan complete when:

1. All 17 tasks checked off.
2. Unit suite green: `python -m pytest pipeline/tests/test_watchdog_*.py -v` → 0 failures.
3. Both scheduled tasks registered + first manual fire `LastTaskResult=0`.
4. Shadow mode (Stage 1) runs for a min of 5 weekday cycles with logs reviewed. **Note:** Stage 1 observation period is not blocking for this plan — the plan ends at "Stage 1 live." Stages 2 and 3 are separate one-commit flag-flips done ~1-2 weeks later.
5. Canary acceptance test passed (all 4 observations logged in transcript).

Following completion, invoke `superpowers:finishing-a-development-branch` to merge `feat/data-freshness-watchdog` into master.

---

## Out of scope (explicit — do NOT add to this plan)

- Stage 2 flag flip (remove `--dry-run` for `critical`-tier alerts). ~1 week after Stage 1 lands; separate commit.
- Stage 3 flag flip (remove `--dry-run` for `warn`-tier too). ~2 weeks after Stage 1; separate commit.
- Pre-commit hook enforcing inventory updates. Separate plumbing project.
- Auto-remediation (watchdog attempts to re-run failed tasks). Out of scope — watchdog alerts; humans fix.
- Gap 2 (continuous article re-grounding), Gap 3 (terminal/website age badges), Gap 4 (reasoning-chain persistence). Separate brainstorms.

---

## Self-review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §Architecture (3-file diagram) | Tasks 3, 5, 6, 7, 8, 9 |
| §Inventory schema | Tasks 2, 5 (load+validate) |
| §Stale-detection logic — file freshness | Tasks 3, 4 |
| §Stale-detection logic — task liveness | Task 6 |
| §Drift check | Task 6 |
| §Alert payload + dedup (stable key, state, escalation, RESOLVED) | Tasks 7 |
| §Error handling (missing inventory = fatal; scheduler fail = skip drift; Telegram fail = log) | Tasks 5, 8, 9, 10 |
| §Testing (5 test files) | Tasks 3, 4, 5, 6, 7, 8, 10 |
| §Integration dry-run | Task 11 |
| §Rollout Stage 1 | Task 15 |
| §File structure | all tasks |
| §Bootstrap | Task 2 |
| §CLAUDE.md reference | Task 13 |
| §Scheduled-task registration | Task 15 |
| §AC #7 canary test | Task 17 |

**Placeholder scan:** no "TBD" / "add error handling" / "similar to Task N" markers. Every step has complete code or complete commands with expected output.

**Type / name consistency:**
- `IssueKind` enum members used identically across `watchdog_alerts.py`, test files, and `watchdog.py` orchestrator.
- `FreshnessResult` enum used identically in freshness module and orchestrator.
- `TaskLivenessResult` enum used identically in scheduler module and orchestrator.
- `stable_key()` signature matches across dedup tests and production code.
- `check_file_freshness(path, cadence_class, grace_multiplier, now)` signature matches freshness tests and orchestrator.
- `.bat` files reference `pipeline\watchdog.py` via absolute `cd /d` — consistent with existing pipeline `.bat` pattern.
- Branch name `feat/data-freshness-watchdog` consistent across Task 1 creation, commit messages, and the out-of-scope references.
- Inventory path `pipeline/config/anka_inventory.json` consistent across Task 2 bootstrap, Task 5 fixture tests, Task 15 shadow-mode registration.
