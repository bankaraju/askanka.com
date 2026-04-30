"""Safe, idempotent self-heal actions the watchdog dispatches automatically.

Each action MUST be:
  - Idempotent — safe to re-run if a prior run already healed
  - Read-only of the source-of-truth (the laptop, in cross-host cases)
  - Logged with before/after state so a human can audit what self-heal did

Anything that *might* cause harm (e.g. clearing a stuck OPEN row by
fabricating a price) goes through the alert path instead — self-heal is
for the cases where the right thing to do is mechanical and obvious.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import date as _date
from pathlib import Path

log = logging.getLogger("anka.watchdog.self_heal")

REPO_ROOT = Path(__file__).resolve().parent.parent
VPS_SSH_KEY = Path("C:/Users/Claude_Anka/.ssh/contabo_vmi3256563")
VPS_SSH_HOST = "anka@185.182.8.107"


def push_to_vps(laptop_rel: str) -> dict:
    """scp a laptop file to its known VPS location. Idempotent."""
    laptop_path = REPO_ROOT / laptop_rel
    if not laptop_path.exists():
        return {"ok": False, "action": "push_to_vps", "detail": f"laptop file missing: {laptop_rel}"}
    vps_path = f"/home/anka/askanka.com/{laptop_rel.replace(chr(92), '/')}"
    try:
        result = subprocess.run(
            ["scp", "-B", "-i", str(VPS_SSH_KEY),
             "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=15",
             str(laptop_path),
             f"{VPS_SSH_HOST}:{vps_path}"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log.info("self-heal push_to_vps: copied %s -> %s", laptop_rel, vps_path)
            return {"ok": True, "action": "push_to_vps", "detail": f"scp {laptop_rel} -> vps:{vps_path}"}
        return {"ok": False, "action": "push_to_vps",
                "detail": f"scp rc={result.returncode}: {result.stderr.strip()[:120]}"}
    except Exception as exc:
        return {"ok": False, "action": "push_to_vps",
                "detail": f"{type(exc).__name__}: {exc}"}


def phase_c_options_sidecar_close() -> dict:
    """Re-run the options sidecar close to sweep stuck OPEN rows.

    Calls the same close path that fires at 14:30 IST. If the rows are
    truly stale (i.e., should have closed at 14:30), this brings them
    to a terminal state at live LTP. If Kite is unavailable, the close
    path stamps TIME_STOP_FAIL_FETCH — also better than silent OPEN.
    """
    try:
        from pipeline.phase_c_shadow import _close_options_sidecar
        today = _date.today().isoformat()
        _close_options_sidecar(today)
        log.info("self-heal phase_c_options_sidecar_close: invoked for %s", today)
        return {"ok": True, "action": "phase_c_options_sidecar_close",
                "detail": f"sidecar swept for {today}"}
    except Exception as exc:
        return {"ok": False, "action": "phase_c_options_sidecar_close",
                "detail": f"{type(exc).__name__}: {exc}"}


def rerun_fno_news_scanner() -> dict:
    """Re-run pipeline.fno_news_scanner to repopulate today's headlines.

    Idempotent: scanner overwrites data/fno_news.json with current
    Google-News pull. Only ~10s wall-clock; safe to invoke whenever the
    file is empty/stale. The morning scheduled task fires at 09:26 IST,
    so this is mostly relevant when something else (e.g. EOD exporter
    with empty filter result) has clobbered it.
    """
    try:
        from pipeline import fno_news_scanner
        fno_news_scanner.main()
        log.info("self-heal rerun_fno_news_scanner: completed")
        return {"ok": True, "action": "rerun_fno_news_scanner",
                "detail": "scanner re-run; fno_news.json refreshed"}
    except Exception as exc:
        return {"ok": False, "action": "rerun_fno_news_scanner",
                "detail": f"{type(exc).__name__}: {exc}"}


def dispatch(action_name: str, output_path: str | None = None) -> dict:
    """Look up and run a registered self-heal action by name."""
    if action_name == "push_to_vps":
        if not output_path:
            return {"ok": False, "action": action_name, "detail": "no output_path supplied"}
        return push_to_vps(output_path)
    if action_name == "phase_c_options_sidecar_close":
        return phase_c_options_sidecar_close()
    if action_name == "rerun_fno_news_scanner":
        return rerun_fno_news_scanner()
    return {"ok": False, "action": action_name, "detail": "unknown self-heal action"}


def write_audit_log(actions: list[dict], log_path: Path) -> None:
    """Append a JSONL line per self-heal action so humans can audit."""
    if not actions:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    ts = datetime.now(ist).isoformat()
    with log_path.open("a", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps({"ts": ts, **a}) + "\n")
