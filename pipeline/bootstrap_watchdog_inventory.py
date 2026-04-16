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
    "AnkaRefreshKite": {
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
