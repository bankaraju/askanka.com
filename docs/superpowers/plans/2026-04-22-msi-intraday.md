# MSI Intraday Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recompute the Macro Sentiment Index (MSI) every 15 minutes during market hours so the terminal banner shows a live number with an honest `msi_updated_at` timestamp, instead of the once-per-day morning snapshot that currently lies.

**Architecture:**
Morning `regime_scanner.py` (09:25) writes the first MSI + caches the raw FII/DII flow into `data/today_regime.json`. Each 15-min `intraday_scan.bat` cycle invokes a new standalone `pipeline/msi_refresh.py` which reads the cached FII from that file, re-fetches the 4 intraday-available inputs (India VIX, USD/INR, Nifty 30d return, crude), recomputes MSI, and atomically rewrites **only** the MSI-related fields (`msi_score`, `msi_regime`, `msi_updated_at`) of `today_regime.json`. On any fetch or compute failure, the script exits without touching the file — morning MSI is held, mtime does not advance, and the watchdog's existing file-freshness check flags it amber.

**Tech Stack:** Python 3.11, requests, yfinance, pytest, vanilla JS (ES modules), FastAPI.

---

## File Structure

- **Modify** `pipeline/macro_stress.py` — add `cached_fii` kwarg to `compute_msi()` so the caller can bypass the FII HTTP fetch.
- **Modify** `pipeline/regime_scanner.py` — persist raw FII flow + `msi_updated_at` into `today_regime.json` so intraday refresh has a cache to read from.
- **Create** `pipeline/msi_refresh.py` — standalone 15-min script that reads the cached FII, recomputes MSI, atomically writes back. Logs to `logs/intraday_scan.log`. Exits 0 on success, 2 on soft failure (hold morning MSI).
- **Modify** `pipeline/scripts/intraday_scan.bat` — insert `python -X utf8 msi_refresh.py` line between existing scanners.
- **Modify** `pipeline/config/anka_inventory.json` — add `pipeline/data/today_regime.json` to every `AnkaIntraday####` entry's `outputs[]` so the watchdog treats stale MSI as an intraday freshness miss.
- **Modify** `pipeline/terminal/api/regime.py` — expose `msi_updated_at` as its own field in the `/api/regime` response (distinct from the global-regime `updated_at`).
- **Modify** `pipeline/terminal/static/js/components/regime-banner.js` — render a small stale dot next to MSI when `msi_updated_at` is > 30 min old during market hours.
- **Create** `pipeline/tests/test_msi_refresh.py` — unit tests for `msi_refresh.py` behaviour.
- **Modify** `pipeline/tests/test_macro_stress.py` — add test for `compute_msi(cached_fii=...)` bypassing the HTTP path. (If file doesn't exist, create it; scope the addition to the new kwarg only.)
- **Modify** `pipeline/terminal/tests/test_regime_api.py` — assert `msi_updated_at` appears in the response.
- **Modify** `docs/SYSTEM_OPERATIONS_MANUAL.md` — document the new MSI refresh cadence under the ETF/MSI and Intraday sections.

---

## Task 1: Persist cached FII + MSI timestamp at morning scan

**Files:**
- Modify: `pipeline/regime_scanner.py:217-235` (today_regime dict construction and write)

Morning already computes MSI via `compute_msi()` — the returned dict contains `fii_net`, `dii_net`, `combined_flow`, and `timestamp`. Currently only `msi_score` + `msi_regime` are persisted (lines 223-224). Add the raw FII fields and `msi_updated_at` so the intraday refresh has a cache and the banner has an honest timestamp.

- [ ] **Step 1: Find an existing test that asserts today_regime.json structure, or add a new inline unit test**

Run: `rg -n "today_regime" pipeline/tests/`
Expected: some existing coverage — read it first to understand patterns. If none is suitable, create a minimal new test in a new file `pipeline/tests/test_regime_scanner_persistence.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

def test_morning_scan_persists_cached_fii_and_msi_timestamp(tmp_path, monkeypatch):
    # Arrange: redirect regime_scanner to a tmp data dir
    import pipeline.regime_scanner as rs
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(rs, "_DATA", data_dir)
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", data_dir / "today_regime.json")
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", data_dir / "prev_regime.json")
    # Fake trade map so the scanner doesn't try to read autoresearch files
    trade_map = tmp_path / "trade_map.json"
    trade_map.write_text(json.dumps({"RISK-OFF": {}, "NEUTRAL": {}, "today_zone": "NEUTRAL"}))
    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map)
    # Fake MSI so no HTTP calls happen
    fake_msi = {
        "msi_score": 42.4, "regime": "MACRO_NEUTRAL",
        "fii_net": -1234.5, "dii_net": 890.1, "combined_flow": -344.4,
        "timestamp": "2026-04-22T09:25:00+05:30",
    }
    with patch("macro_stress.compute_msi", return_value=fake_msi):
        rs.main()

    written = json.loads((data_dir / "today_regime.json").read_text())
    assert written["msi_score"] == 42.4
    assert written["msi_updated_at"] == "2026-04-22T09:25:00+05:30"
    # Cached FII fields: raw numbers, not nested
    assert written["msi_cached_inputs"]["fii_net"] == -1234.5
    assert written["msi_cached_inputs"]["dii_net"] == 890.1
    assert written["msi_cached_inputs"]["combined_flow"] == -344.4
```

- [ ] **Step 2: Run the test — verify it fails**

Run: `pytest pipeline/tests/test_regime_scanner_persistence.py -v`
Expected: FAIL — `KeyError: 'msi_updated_at'` or similar.

- [ ] **Step 3: Modify `pipeline/regime_scanner.py` to add the new fields**

Locate the `today_regime` dict literal around line 219-230. Extend it:

```python
    today_regime = {
        "timestamp": timestamp,
        "regime": current_regime,
        "regime_source": "etf_engine",
        "msi_score": msi_score,
        "msi_regime": msi_regime,
        "msi_updated_at": msi.get("timestamp") if msi else None,
        "msi_cached_inputs": {
            "fii_net":       msi.get("fii_net") if msi else None,
            "dii_net":       msi.get("dii_net") if msi else None,
            "combined_flow": msi.get("combined_flow") if msi else None,
        } if msi else None,
        "regime_stable": regime_stable,
        "consecutive_days": consecutive_days,
        "trade_map_key": trade_map_key,
        ...  # leave everything below untouched
    }
```

Do **not** change any field names that already exist. `msi` is the variable holding the `compute_msi()` result (declared around line 194-198). If MSI computation failed (the existing try/except at line 202-203 catches this), `msi` is `{}` and `msi.get(...)` returns `None`, so `msi_updated_at` and `msi_cached_inputs` become `None`. That's the signal to downstream intraday refresh: "no cache, skip today."

- [ ] **Step 4: Run the test — verify it passes**

Run: `pytest pipeline/tests/test_regime_scanner_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/regime_scanner.py pipeline/tests/test_regime_scanner_persistence.py
git commit -m "feat(regime): persist msi_updated_at + cached FII flow at morning scan"
```

---

## Task 2: Add `cached_fii` kwarg to compute_msi()

**Files:**
- Modify: `pipeline/macro_stress.py:410-466` (compute_msi function)
- Modify: `pipeline/tests/test_macro_stress.py` (add new test — create file if missing)

The intraday refresh needs a way to skip the FII HTTP fetch and use the morning-cached value instead. Parameterize `compute_msi` with an optional `cached_fii` dict.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_macro_stress.py` (create file if it doesn't exist, otherwise append):

```python
from unittest.mock import patch, MagicMock
from macro_stress import compute_msi


def test_compute_msi_uses_cached_fii_when_provided():
    """When cached_fii is provided, _fetch_institutional_flow must NOT be called
    and the cached values flow through to the inst_flow component."""
    cached = {"fii_net": -2000.0, "dii_net": 1500.0, "combined_flow": -500.0}
    with patch("macro_stress._fetch_institutional_flow") as mock_fetch, \
         patch("macro_stress._fetch_india_vix", return_value=14.5), \
         patch("macro_stress._fetch_india_vix_90d_avg", return_value=13.0), \
         patch("macro_stress._fetch_usdinr_change_5d", return_value=0.3), \
         patch("macro_stress._fetch_nifty_30d_return", return_value=-1.5), \
         patch("macro_stress._fetch_crude_change_5d", return_value=1.0):
        result = compute_msi(cached_fii=cached)

    mock_fetch.assert_not_called()
    assert result["fii_net"] == -2000.0
    assert result["dii_net"] == 1500.0
    assert result["combined_flow"] == -500.0


def test_compute_msi_without_cached_fii_calls_fetch():
    """Baseline: without cached_fii, the existing HTTP fetch path runs."""
    fake_inst = {"fii_net": -100.0, "dii_net": 50.0, "combined_flow": -50.0}
    with patch("macro_stress._fetch_institutional_flow", return_value=fake_inst) as mock_fetch, \
         patch("macro_stress._fetch_india_vix", return_value=14.5), \
         patch("macro_stress._fetch_india_vix_90d_avg", return_value=13.0), \
         patch("macro_stress._fetch_usdinr_change_5d", return_value=0.3), \
         patch("macro_stress._fetch_nifty_30d_return", return_value=-1.5), \
         patch("macro_stress._fetch_crude_change_5d", return_value=1.0):
        result = compute_msi()

    mock_fetch.assert_called_once()
    assert result["fii_net"] == -100.0
```

- [ ] **Step 2: Run the tests — verify they fail**

Run: `pytest pipeline/tests/test_macro_stress.py::test_compute_msi_uses_cached_fii_when_provided -v`
Expected: FAIL — `TypeError: compute_msi() got an unexpected keyword argument 'cached_fii'`.

- [ ] **Step 3: Modify `pipeline/macro_stress.py` compute_msi signature**

Change the signature and the first two lines of the body. Do not change anything else in the function:

```python
def compute_msi(*, cached_fii: dict | None = None) -> dict:
    """Compute today's Macro Sentiment Index.

    Args:
        cached_fii: Optional dict with keys {fii_net, dii_net, combined_flow}.
            If provided, skip the NSE HTTP fetch and use these values. Used by
            the intraday refresh because NSE publishes FII flows EOD only.

    Returns dict:
      msi_score: float 0-100
      regime: MACRO_STRESS | MACRO_NEUTRAL | MACRO_EASY
      components: {input: {raw_value, normalised, weight, contribution}}
      timestamp: ISO string (IST)
    """
    inst      = cached_fii if cached_fii is not None else _fetch_institutional_flow()
    fii_net   = inst.get("fii_net")
    dii_net   = inst.get("dii_net", 0.0)
    combined  = inst.get("combined_flow") if cached_fii is not None else inst.get("combined")
    # ... rest of the function unchanged
```

Note: the cached dict uses key `combined_flow` (matching how it's persisted in Task 1) while the live fetch returns `combined`. The `combined` path here preserves existing behaviour.

- [ ] **Step 4: Run both tests — verify they pass**

Run: `pytest pipeline/tests/test_macro_stress.py -v -k compute_msi`
Expected: PASS on both. Also run the full existing macro_stress test suite if present to confirm no regression:
`pytest pipeline/tests/test_macro_stress.py -v`

- [ ] **Step 5: Commit**

```bash
git add pipeline/macro_stress.py pipeline/tests/test_macro_stress.py
git commit -m "feat(macro_stress): accept cached_fii kwarg to skip HTTP fetch on intraday runs"
```

---

## Task 3: Create `msi_refresh.py` standalone script

**Files:**
- Create: `pipeline/msi_refresh.py`
- Create: `pipeline/tests/test_msi_refresh.py`

This is the intraday worker. It reads cached FII from `today_regime.json`, recomputes MSI, atomically rewrites only the MSI fields. Any exception or missing cache → log warning, exit 2, do not touch file (morning MSI held).

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_msi_refresh.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _write_morning_regime(path: Path, **overrides):
    data = {
        "timestamp": "2026-04-22T09:25:00+05:30",
        "regime": "RISK-OFF",
        "regime_source": "etf_engine",
        "msi_score": 42.4,
        "msi_regime": "MACRO_NEUTRAL",
        "msi_updated_at": "2026-04-22T09:25:00+05:30",
        "msi_cached_inputs": {
            "fii_net": -1200.0, "dii_net": 800.0, "combined_flow": -400.0,
        },
        "regime_stable": True,
        "consecutive_days": 2,
        "trade_map_key": "RISK-OFF",
        "eligible_spreads": {"Defence vs IT": {"1d_win": 45}},
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_happy_path_updates_msi_fields_only(tmp_path, monkeypatch):
    """On success, only msi_score / msi_regime / msi_updated_at change;
    every other field (including eligible_spreads) is preserved byte-for-byte."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file)
    monkeypatch.setattr("pipeline.msi_refresh.REGIME_FILE", regime_file)

    fake_msi = {
        "msi_score": 48.2, "regime": "MACRO_NEUTRAL",
        "fii_net": -1200.0, "dii_net": 800.0, "combined_flow": -400.0,
        "timestamp": "2026-04-22T11:30:00+05:30",
    }
    with patch("pipeline.msi_refresh.compute_msi", return_value=fake_msi) as mock_compute:
        from pipeline.msi_refresh import main
        rc = main()

    # compute_msi must have been called with the cached FII
    call_kwargs = mock_compute.call_args.kwargs
    assert call_kwargs["cached_fii"]["fii_net"] == -1200.0
    assert rc == 0

    after = json.loads(regime_file.read_text())
    assert after["msi_score"] == 48.2
    assert after["msi_regime"] == "MACRO_NEUTRAL"
    assert after["msi_updated_at"] == "2026-04-22T11:30:00+05:30"
    # Non-MSI fields unchanged
    assert after["regime_stable"] is True
    assert after["consecutive_days"] == 2
    assert after["eligible_spreads"] == {"Defence vs IT": {"1d_win": 45}}


def test_missing_cached_fii_holds_morning(tmp_path, monkeypatch):
    """If msi_cached_inputs is None (morning MSI compute failed), do nothing."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file, msi_cached_inputs=None)
    monkeypatch.setattr("pipeline.msi_refresh.REGIME_FILE", regime_file)

    # compute_msi must NOT be called when there's no cache
    with patch("pipeline.msi_refresh.compute_msi") as mock_compute:
        from pipeline.msi_refresh import main
        rc = main()

    mock_compute.assert_not_called()
    assert rc == 2
    # File untouched
    assert json.loads(regime_file.read_text())["msi_score"] == 42.4


def test_compute_exception_holds_morning(tmp_path, monkeypatch):
    """If compute_msi raises, leave the file alone and exit 2."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file)
    monkeypatch.setattr("pipeline.msi_refresh.REGIME_FILE", regime_file)

    before = regime_file.read_text()
    with patch("pipeline.msi_refresh.compute_msi", side_effect=RuntimeError("vix fetch 502")):
        from pipeline.msi_refresh import main
        rc = main()

    assert rc == 2
    assert regime_file.read_text() == before  # byte-identical


def test_missing_regime_file_exits_quietly(tmp_path, monkeypatch):
    """No file → exit 2, no exception to scheduler."""
    regime_file = tmp_path / "today_regime.json"  # does not exist
    monkeypatch.setattr("pipeline.msi_refresh.REGIME_FILE", regime_file)
    from pipeline.msi_refresh import main
    assert main() == 2
```

- [ ] **Step 2: Run the tests — verify they fail**

Run: `pytest pipeline/tests/test_msi_refresh.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.msi_refresh'`.

- [ ] **Step 3: Create `pipeline/msi_refresh.py`**

```python
"""MSI intraday refresh — runs every 15 min during market hours.

Reads cached FII flow from data/today_regime.json (persisted by the
09:25 morning scan), recomputes MSI with live VIX / USD-INR / Nifty /
crude, and atomically rewrites ONLY the MSI-related fields of
today_regime.json. On any failure, the file is left untouched —
morning MSI is held, the file's mtime does not advance, and the
watchdog's existing freshness check will flag it amber.

Exit codes:
    0 — success, file updated
    2 — soft failure (cache missing, compute raised, file absent);
        morning MSI held, scheduler should not treat this as fatal.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from macro_stress import compute_msi  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
REGIME_FILE = _HERE / "data" / "today_regime.json"

log = logging.getLogger("anka.msi_refresh")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON to a sibling .tmp file then os.replace — atomic on NTFS."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    if not REGIME_FILE.exists():
        log.warning("today_regime.json not found — nothing to refresh")
        return 2

    try:
        current = json.loads(REGIME_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to read today_regime.json: %s", exc)
        return 2

    cached = current.get("msi_cached_inputs")
    if not cached or cached.get("fii_net") is None:
        log.warning("no cached FII flow in today_regime.json — holding morning MSI")
        return 2

    try:
        msi = compute_msi(cached_fii=cached)
    except Exception as exc:
        log.warning("compute_msi failed: %s — holding morning MSI", exc)
        return 2

    # Mutate only the MSI fields. Everything else — regime, eligible_spreads,
    # hysteresis — is morning's snapshot and must be preserved byte-for-byte.
    current["msi_score"] = msi["msi_score"]
    current["msi_regime"] = msi["regime"]
    current["msi_updated_at"] = msi["timestamp"]

    try:
        _atomic_write(REGIME_FILE, current)
    except Exception as exc:
        log.error("atomic write failed: %s", exc)
        return 2

    log.info(
        "MSI refreshed: %.1f (%s) at %s",
        msi["msi_score"], msi["regime"], msi["timestamp"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests — verify they pass**

Run: `pytest pipeline/tests/test_msi_refresh.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pipeline/msi_refresh.py pipeline/tests/test_msi_refresh.py
git commit -m "feat(msi): intraday refresh script — holds morning MSI on any failure"
```

---

## Task 4: Wire into `intraday_scan.bat` and watchdog inventory

**Files:**
- Modify: `pipeline/scripts/intraday_scan.bat`
- Modify: `pipeline/config/anka_inventory.json` (26 `AnkaIntraday####` entries)

- [ ] **Step 1: Write the failing test for the inventory change**

Create or append to `pipeline/tests/test_anka_inventory.py`:

```python
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
```

- [ ] **Step 2: Run the test — verify it fails**

Run: `pytest pipeline/tests/test_anka_inventory.py::test_intraday_tasks_include_today_regime_output -v`
Expected: FAIL — all 26 tasks listed as missing.

- [ ] **Step 3: Add the output entry to all 26 AnkaIntraday tasks**

Edit `pipeline/config/anka_inventory.json`. For each `AnkaIntraday0930` through `AnkaIntraday1530` entry, append `"pipeline/data/today_regime.json"` to its `outputs[]` list. Do this in one pass; do not change any other field. A small helper is acceptable:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path("pipeline/config/anka_inventory.json")
inv = json.loads(p.read_text(encoding="utf-8"))
tasks = inv["tasks"] if isinstance(inv, dict) else inv
changed = 0
for t in tasks:
    if t.get("task_name", "").startswith("AnkaIntraday"):
        outs = t.setdefault("outputs", [])
        if "pipeline/data/today_regime.json" not in outs:
            outs.append("pipeline/data/today_regime.json")
            changed += 1
p.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"updated {changed} intraday tasks")
PY
```

Expected: `updated 26 intraday tasks` (or whatever the real count is).

- [ ] **Step 4: Run the inventory test — verify it passes**

Run: `pytest pipeline/tests/test_anka_inventory.py -v`
Expected: PASS.

- [ ] **Step 5: Modify `pipeline/scripts/intraday_scan.bat`**

Insert a single new line between `spread_intelligence.py` and the Phase C correlation-break block:

```bat
python -X utf8 spread_intelligence.py >> logs\intraday_scan.log 2>&1
python -X utf8 msi_refresh.py >> logs\intraday_scan.log 2>&1
REM Phase C: Correlation break scanner (runs after OI scanner so positioning.json is fresh)
```

Do not touch any other line. The `msi_refresh.py` exit code 2 on soft failure is intentionally **not** wired to `goto error` — a stale MSI is a banner-dot concern, not a scheduler failure.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/intraday_scan.bat pipeline/config/anka_inventory.json pipeline/tests/test_anka_inventory.py
git commit -m "chore(intraday): wire msi_refresh.py + watch today_regime.json freshness"
```

---

## Task 5: Expose `msi_updated_at` in `/api/regime` and render banner stale dot

**Files:**
- Modify: `pipeline/terminal/api/regime.py:44-56` (response dict)
- Modify: `pipeline/terminal/tests/test_regime_api.py` (assert new field)
- Modify: `pipeline/terminal/static/js/components/regime-banner.js` (render stale dot)

- [ ] **Step 1: Add a failing API test**

Append to `pipeline/terminal/tests/test_regime_api.py`:

```python
def test_regime_endpoint_returns_msi_updated_at(tmp_path, monkeypatch):
    """/api/regime must expose msi_updated_at distinct from updated_at,
    so the banner can show when MSI was last recomputed (not when ETF
    regime was last refreshed)."""
    import pipeline.terminal.api.regime as mod
    from fastapi.testclient import TestClient
    from pipeline.terminal.app import app

    today = tmp_path / "today_regime.json"
    today.write_text(json.dumps({
        "regime": "RISK-OFF",
        "msi_score": 48.2,
        "msi_regime": "MACRO_NEUTRAL",
        "msi_updated_at": "2026-04-22T11:30:00+05:30",
        "regime_stable": True,
        "consecutive_days": 2,
        "eligible_spreads": {},
        "timestamp": "2026-04-22T09:25:00+05:30",
    }))
    monkeypatch.setattr(mod, "_TODAY_REGIME_FILE", today)
    # Blank out the global file so the endpoint falls back to today_regime fields
    monkeypatch.setattr(mod, "_GLOBAL_REGIME_FILE", tmp_path / "missing_global.json")
    monkeypatch.setattr(mod, "_RECOMMENDATIONS_FILE", tmp_path / "missing_recs.json")

    body = TestClient(app).get("/api/regime").json()
    assert body["msi_updated_at"] == "2026-04-22T11:30:00+05:30"
    # updated_at is still the global regime timestamp, here fallen back to today's
    assert body["updated_at"] == "2026-04-22T09:25:00+05:30"
```

(The test file already imports `json`; reuse it. If not, add the import at the top.)

- [ ] **Step 2: Run the test — verify it fails**

Run: `pytest pipeline/terminal/tests/test_regime_api.py::test_regime_endpoint_returns_msi_updated_at -v`
Expected: FAIL — `KeyError: 'msi_updated_at'`.

- [ ] **Step 3: Add the field to the regime API response**

Edit `pipeline/terminal/api/regime.py`. In the return dict around line 44-55, add one line:

```python
        "msi_score": today_data.get("msi_score", 0.0),
        "msi_regime": today_data.get("msi_regime", "UNAVAILABLE"),
        "msi_updated_at": today_data.get("msi_updated_at"),
        "trade_map_key": today_data.get("trade_map_key"),
```

- [ ] **Step 4: Run the API test — verify it passes**

Run: `pytest pipeline/terminal/tests/test_regime_api.py -v`
Expected: all existing tests still pass + the new one passes.

- [ ] **Step 5: Render the stale dot in the banner**

Edit `pipeline/terminal/static/js/components/regime-banner.js`. Replace the block that renders the "Updated:" line (currently lines 26-35) with a version that (a) uses `msi_updated_at` for the MSI line specifically, and (b) shows a small amber dot when the MSI timestamp is older than 30 min during market hours (09:15–15:30 IST):

```javascript
function _msiStaleDot(msiUpdatedAt) {
  if (!msiUpdatedAt) return '';
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata', hour12: false,
    hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date());
  const hh = Number(parts.find(p => p.type === 'hour').value);
  const mm = Number(parts.find(p => p.type === 'minute').value);
  const totalMin = hh * 60 + mm;
  const inMarket = totalMin >= 555 && totalMin < 930;  // 09:15–15:30
  if (!inMarket) return '';
  const ageMin = (Date.now() - new Date(msiUpdatedAt)) / 60000;
  if (ageMin < 30) return '';
  return ' <span title="MSI not refreshed in 30+ min" style="color: var(--colour-amber); font-size: 0.8em;">●</span>';
}
```

And in the template (within the existing `container.innerHTML = ...` block), replace:

```html
<span class="text-muted" style="font-size: 0.75rem;">
  MSI: <span class="mono">${(data.msi_score || 0).toFixed(1)}</span>
  (${data.msi_regime || 'N/A'})
</span>
<br>
<span class="text-muted" style="font-size: 0.6875rem;">
  Updated: ${data.updated_at ? new Date(data.updated_at).toLocaleTimeString('en-IN') : '--'}
</span>
```

with:

```html
<span class="text-muted" style="font-size: 0.75rem;">
  MSI: <span class="mono">${(data.msi_score || 0).toFixed(1)}</span>
  (${data.msi_regime || 'N/A'})${_msiStaleDot(data.msi_updated_at)}
</span>
<br>
<span class="text-muted" style="font-size: 0.6875rem;">
  MSI: ${data.msi_updated_at ? new Date(data.msi_updated_at).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit'}) : '--'}
  · Regime: ${data.updated_at ? new Date(data.updated_at).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit'}) : '--'}
</span>
```

This splits the single lying timestamp into two honest ones: MSI freshness and ETF regime freshness.

- [ ] **Step 6: Manual browser verification**

Start the terminal (`python -m pipeline.terminal.app` or the existing launch command), load the dashboard, confirm:
(a) The MSI row shows a timestamp near "now" once `msi_refresh.py` has run once, and
(b) If you temporarily break `msi_refresh.py` (e.g. `raise RuntimeError` at the top of `main()`), the amber dot appears within 30 min.

Report what you saw in the commit message — per CLAUDE.md "type checking and test suites verify code correctness, not feature correctness."

- [ ] **Step 7: Commit**

```bash
git add pipeline/terminal/api/regime.py pipeline/terminal/tests/test_regime_api.py pipeline/terminal/static/js/components/regime-banner.js
git commit -m "feat(banner): split MSI vs regime timestamps; amber dot when MSI stale"
```

---

## Task 6: Docs + memory sync (CLAUDE.md mandate)

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Create: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_msi_intraday.md`
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\MEMORY.md` (add one pointer line)

Per CLAUDE.md: **"Any change to the system — new task, new script, new data flow, changed schedule — MUST update ALL of these in the SAME commit."** This task exists to enforce that.

- [ ] **Step 1: Update `docs/SYSTEM_OPERATIONS_MANUAL.md`**

Find the ETF/MSI section (likely under "Station 2" or similar) and the Intraday section. Add a short paragraph (2–4 sentences) to each:

At the MSI/ETF section:
> **MSI intraday refresh (added 2026-04-22)** — Morning `regime_scanner.py` persists raw FII flow into `today_regime.json.msi_cached_inputs`. Each 15-min intraday cycle calls `pipeline/msi_refresh.py`, which reuses the cached FII and re-fetches live VIX, USD/INR, Nifty 30d return, and crude to recompute MSI. On any failure the script exits 2 and leaves `today_regime.json` untouched — morning MSI is held and the watchdog flags today_regime.json as stale after `grace_multiplier × 15 min`.

At the Intraday section (where intraday_scan.bat is described):
> The sequence inside `intraday_scan.bat` is: technicals → OI → news → fno_news → news_intel → spread_intel → **msi_refresh** → correlation_breaks → website_exporter. MSI refresh is soft: its failure does not stop downstream scanners.

- [ ] **Step 2: Create the memory file**

Write `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_msi_intraday.md`:

```markdown
---
name: MSI intraday refresh
description: MSI recomputes every 15 min via pipeline/msi_refresh.py (2026-04-22) — FII cached from morning, other inputs live
type: project
---
MSI used to be a once-per-day (09:25) value. As of 2026-04-22 it refreshes each
intraday cycle via `pipeline/msi_refresh.py`, which reads `msi_cached_inputs.fii_net`
from `today_regime.json` (NSE publishes FII EOD only) and re-fetches India VIX,
USD/INR, Nifty 30d return, and crude. On any fetch failure the script exits 2 and
leaves the file alone — morning MSI is held, today_regime.json mtime stops
advancing, watchdog flags it amber.

**Why:** The terminal banner was showing `MSI: 42.4 · Updated: 11:18` where 42.4
was the 09:25 morning snapshot but 11:18 was the ETF regime refresh time — two
different data sources under one label. Fix restored "honest numbers".

**How to apply:** If adding new MSI inputs, check which are intraday-available.
If an input isn't intraday-live (like FII), cache it from morning into
`msi_cached_inputs` and pass via the `compute_msi(cached_fii=...)` kwarg. Never
overwrite morning MSI with a partial result — soft-fail and let the banner dot
+ watchdog flag it.
```

- [ ] **Step 3: Add pointer to `MEMORY.md`**

Open `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\MEMORY.md` and add one line in the project section (alphabetical-ish is fine):

```markdown
- [MSI intraday refresh](project_msi_intraday.md) — Recomputes every 15 min via msi_refresh.py, FII cached from morning, soft-fail holds morning MSI
```

- [ ] **Step 4: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs: MSI intraday refresh — operations manual section"
```

The memory files live under the `.claude` directory and aren't part of this repo, so they commit separately (or are saved outside version control per convention).

---

## Self-review checklist (run after plan execution)

- All 6 tasks committed?
- `pytest pipeline/tests/` + `pytest pipeline/terminal/tests/` — no new failures beyond the pre-existing 1 deferred item from the prior plan?
- Browser check: `MSI: …(MACRO_NEUTRAL)` shows a sub-11:18-style timestamp that advances every 15 min?
- Kill switch test: temporarily raise in `msi_refresh.main()` — amber dot appears within 30 min and morning MSI value is preserved?
- SYSTEM_OPERATIONS_MANUAL.md mentions `msi_refresh.py` by name?
- `anka_inventory.json` has `today_regime.json` in every intraday task's outputs?

If any answer is no, loop back to the relevant task, don't paper over.
