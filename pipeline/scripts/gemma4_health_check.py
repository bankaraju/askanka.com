"""Daily 05:30 IST Gemma 4 health check.

Reads:  http://127.0.0.1:11434/v1/chat/completions  (via SSH tunnel from
        laptop -> Contabo, or directly when running on the VPS)
Writes: pipeline/data/research/gemma4_pilot/gemma4_health.json
        (consumed by the data-freshness watchdog as a freshness contract)
Alerts: Telegram ops channel on FAIL or DEGRADED.

Exit codes: 0 on OK or DEGRADED (so cron does not flag soft latency issues
as task failures), 1 on FAIL (so the watchdog escalates).

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 19)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"
LATENCY_BUDGET_S = 60.0


def _ping_ollama() -> dict[str, Any]:
    try:
        t0 = dt.datetime.now()
        r = requests.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "model": "gemma4:26b",
                "messages": [{"role": "user", "content": "Reply: PONG"}],
                "temperature": 0.0,
                "max_tokens": 8,
            },
            timeout=120,
        )
        latency_s = (dt.datetime.now() - t0).total_seconds()
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        text = r.json()["choices"][0]["message"]["content"].strip()
        if "PONG" not in text.upper():
            return {"ok": False, "error": f"bad response: {text!r}"}
        return {"ok": True, "latency_s": latency_s, "text": text}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _send_alert(msg: str) -> None:
    try:
        from pipeline.telegram_client import send_message  # type: ignore

        send_message(msg, channel="ops")
    except Exception:  # noqa: BLE001
        pass


def run_check(out_dir: Path = DEFAULT_OUT) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = _ping_ollama()
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now_iso = dt.datetime.now(ist).isoformat()

    status_record: dict[str, Any] = {"ts": now_iso}
    if p["ok"] and p["latency_s"] < LATENCY_BUDGET_S:
        status_record.update(
            status="OK", latency_s=p["latency_s"], text=p["text"]
        )
        rc = 0
    elif p["ok"]:
        status_record.update(
            status="DEGRADED",
            error=(
                f"latency {p['latency_s']:.1f}s > budget "
                f"{LATENCY_BUDGET_S}s"
            ),
            latency_s=p["latency_s"],
        )
        _send_alert(
            f"⚠️ Gemma 4 health DEGRADED: latency {p['latency_s']:.1f}s"
        )
        rc = 0
    else:
        status_record.update(status="FAIL", error=p.get("error", "unknown"))
        _send_alert(f"🚨 Gemma 4 health FAIL: {p.get('error')}")
        rc = 1

    (out_dir / "gemma4_health.json").write_text(
        json.dumps(status_record, indent=2), encoding="utf-8"
    )
    logging.info(
        "Gemma 4 health %s -- %s", status_record["status"], status_record
    )
    return rc


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="[gemma4_health] %(message)s"
    )
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
