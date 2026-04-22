import json
from pathlib import Path


def test_intraday_tasks_include_today_regime_output():
    """Every AnkaIntraday#### task must claim today_regime.json as an output
    so the watchdog's freshness contract catches a stuck MSI refresh."""
    inv = json.loads(
        (Path(__file__).resolve().parent.parent / "config" / "anka_inventory.json")
        .read_text(encoding="utf-8")
    )
    tasks = inv.get("tasks", inv if isinstance(inv, list) else [])
    intraday = [t for t in tasks if t.get("task_name", "").startswith("AnkaIntraday")]
    assert len(intraday) >= 20, "expected at least 20 AnkaIntraday entries"
    missing = [t["task_name"] for t in intraday
               if "pipeline/data/today_regime.json" not in t.get("outputs", [])]
    assert not missing, f"tasks missing today_regime.json output: {missing}"
