"""Content-level audits that mtime-based freshness can't catch.

Each audit returns a list of dicts: ``{"kind": str, "detail": str,
"output_path": str | None, "self_heal": str | None}``. The watchdog
shell wraps these into Issue objects.

Audits live here because they all share the same shape (read a known
file or set of files, decide if content is internally consistent or
agrees with an external source-of-truth) and because keeping them in
one module makes it cheap to add the next one — every reactive
"oh yeah let me see" debug session should end with a new function in
this file.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

log = logging.getLogger("anka.watchdog.content")

REPO_ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))

# Paired/shadow ledgers swept for "OPEN row from prior trading day" drift.
# Add new ledgers here as new paired-shadow surfaces ship — every paired
# shadow should be in this list so the close-no-op bug pattern can never
# silently recur.
STALE_OPEN_LEDGERS: tuple[Path, ...] = (
    REPO_ROOT / "pipeline/data/research/phase_c/live_paper_options_ledger.json",
    REPO_ROOT / "pipeline/data/research/phase_c/live_paper_ledger.json",
    REPO_ROOT / "pipeline/data/research/scanner/live_paper_scanner_options_ledger.json",
    REPO_ROOT / "pipeline/data/research/scanner/live_paper_scanner_futures_ledger.json",
)

# Provenance sidecars whose mtime must track their data file within tolerance.
# Drift means the provenance writer didn't fire when the data was last
# updated — the badge on the dashboard then lies about what produced today's
# regime/score/etc.
PROVENANCE_PAIRS: tuple[tuple[Path, Path, int], ...] = (
    # (data_file, provenance_file, max_lag_seconds)
    (
        REPO_ROOT / "pipeline/data/today_regime.json",
        REPO_ROOT / "pipeline/data/today_regime.json.provenance.json",
        6 * 3600,  # 6h tolerance — both should be written by AnkaETFSignal at 04:45 IST
    ),
)

# VPS files whose content must agree with laptop equivalents. The laptop
# is the source-of-truth for these; VPS-side drift means a downstream
# task there is acting on stale information and the watchdog should
# self-heal by pushing the laptop copy.
CROSS_HOST_FILES: tuple[tuple[str, str, str], ...] = (
    # (laptop_path, vps_path, comparison_field)
    (
        "pipeline/data/today_regime.json",
        "/home/anka/askanka.com/pipeline/data/today_regime.json",
        "regime",
    ),
)

VPS_SSH_KEY = Path("C:/Users/Claude_Anka/.ssh/contabo_vmi3256563")
VPS_SSH_HOST = "anka@185.182.8.107"


def _rel(p: Path) -> str:
    """Render ``p`` relative to REPO_ROOT when possible, else absolute.

    Tests can monkeypatch ``REPO_ROOT`` to a tmp dir, but the
    ``STALE_OPEN_LEDGERS`` constants point at real paths — the safe
    rendering is "relative if under root, else absolute as-is."
    """
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# Audit 1 — stale OPEN rows in paired-shadow ledgers
# ---------------------------------------------------------------------------

def _today_ist_iso() -> str:
    return datetime.now(IST).date().isoformat()


def _row_open_date(row: dict) -> str | None:
    """Best-effort extract of the trading-day date from a ledger row.

    Different ledgers use slightly different field names — try the most
    specific (``open_date``) first, fall back to truncating ``entry_time``
    or ``open_dt`` to date. Returns ``None`` if no date can be derived,
    which the caller treats as "can't audit, skip" not "definitely stale."
    """
    for key in ("open_date", "entry_date"):
        v = row.get(key)
        if v:
            return str(v)[:10]
    for key in ("open_dt", "entry_time"):
        v = row.get(key)
        if v:
            return str(v)[:10]
    return None


def audit_stale_open_rows(today_iso: str | None = None) -> list[dict]:
    """Sweep every paired/shadow ledger for OPEN rows from prior days.

    Caught the 2026-04-30 phase_c options sidecar no-op bug *after the
    fact* — this audit ensures the next instance fires immediately.

    Returns one issue per ledger that has stale OPEN rows. The
    ``self_heal`` field names a registered self-heal action the watchdog
    can dispatch automatically.
    """
    today = today_iso or _today_ist_iso()
    issues: list[dict] = []
    for ledger_path in STALE_OPEN_LEDGERS:
        if not ledger_path.exists():
            continue  # ledger may not yet exist (new shadow surface)
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append({
                "kind": "LEDGER_UNREADABLE",
                "detail": f"{ledger_path.name}: {type(exc).__name__}: {exc}",
                "output_path": _rel(ledger_path),
                "self_heal": None,
            })
            continue
        rows = data if isinstance(data, list) else data.get("rows", [])
        stale = [
            r for r in rows
            if r.get("status") == "OPEN"
            and (_row_open_date(r) or today) < today
        ]
        if stale:
            sample = ", ".join(str(r.get("signal_id", "?"))[:30] for r in stale[:3])
            extra = f" (+{len(stale) - 3} more)" if len(stale) > 3 else ""
            self_heal = None
            if "options_ledger" in ledger_path.name:
                self_heal = "phase_c_options_sidecar_close"
            issues.append({
                "kind": "STALE_OPEN_ROWS",
                "detail": f"{len(stale)} OPEN row(s) older than {today}: {sample}{extra}",
                "output_path": _rel(ledger_path),
                "self_heal": self_heal,
            })
    return issues


# ---------------------------------------------------------------------------
# Audit 2 — provenance sidecar drift
# ---------------------------------------------------------------------------

def audit_provenance_drift() -> list[dict]:
    """Verify each provenance sidecar's mtime is within tolerance of its data file.

    Caught 2026-04-30: today_regime.json was 09:25:12 today but its
    provenance sidecar was dated 04-27. The provenance writer wasn't
    firing on every regime refresh, so the dashboard's "what engine
    produced this" badge was lying.
    """
    issues: list[dict] = []
    for data_file, prov_file, max_lag in PROVENANCE_PAIRS:
        if not data_file.exists():
            continue  # OUTPUT_MISSING already handles this
        if not prov_file.exists():
            issues.append({
                "kind": "PROVENANCE_MISSING",
                "detail": f"{data_file.name} exists but its .provenance.json sidecar does not",
                "output_path": _rel(prov_file),
                "self_heal": None,
            })
            continue
        data_mtime = data_file.stat().st_mtime
        prov_mtime = prov_file.stat().st_mtime
        lag = data_mtime - prov_mtime
        if lag > max_lag:
            data_dt = datetime.fromtimestamp(data_mtime, tz=IST)
            prov_dt = datetime.fromtimestamp(prov_mtime, tz=IST)
            issues.append({
                "kind": "PROVENANCE_DRIFT",
                "detail": (
                    f"data {data_dt:%Y-%m-%d %H:%M} but provenance {prov_dt:%Y-%m-%d %H:%M} "
                    f"({lag/3600:.1f}h lag, max {max_lag/3600:.1f}h)"
                ),
                "output_path": _rel(prov_file),
                "self_heal": None,
            })
    return issues


# ---------------------------------------------------------------------------
# Audit 3 — cross-host (laptop vs VPS) file content drift
# ---------------------------------------------------------------------------

def _ssh_read(remote_path: str, timeout: int = 10) -> str | None:
    """Read a remote file via SSH. Returns text on success, None on any failure.

    Failure modes (network, key, permission, missing file) all collapse
    to ``None`` — the watchdog treats unreachable VPS as "cannot audit"
    rather than firing false-positive drift alerts.
    """
    if not VPS_SSH_KEY.exists():
        return None
    try:
        result = subprocess.run(
            ["ssh", "-i", str(VPS_SSH_KEY), "-o", "StrictHostKeyChecking=no",
             "-o", f"ConnectTimeout={timeout}",
             "-o", "BatchMode=yes",  # non-interactive: never prompt for password
             VPS_SSH_HOST, f"cat {remote_path}"],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            log.info("ssh cat %s failed rc=%d: %s",
                     remote_path, result.returncode, result.stderr.strip()[:120])
            return None
        return result.stdout
    except Exception as exc:
        log.warning("ssh read %s raised: %s", remote_path, exc)
        return None


def audit_cross_host_regime() -> list[dict]:
    """Compare laptop's authoritative file against VPS copy for content drift.

    Caught 2026-04-30: VPS today_regime.json was 5 days stale, saying
    RISK-ON, while the laptop (correctly) computed NEUTRAL. SECRSI on
    VPS read the stale file and tagged every basket leg with the wrong
    regime label.

    Self-heal: ``push_regime_to_vps`` action — scp the laptop file over.
    Idempotent and safe (laptop is authoritative by design).
    """
    issues: list[dict] = []
    for laptop_rel, vps_path, field in CROSS_HOST_FILES:
        laptop_path = REPO_ROOT / laptop_rel
        if not laptop_path.exists():
            continue  # OUTPUT_MISSING handles this
        try:
            laptop_data = json.loads(laptop_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        vps_text = _ssh_read(vps_path)
        if vps_text is None:
            issues.append({
                "kind": "VPS_UNREACHABLE",
                "detail": f"could not read {vps_path}",
                "output_path": laptop_rel,
                "self_heal": None,
            })
            continue
        try:
            vps_data = json.loads(vps_text)
        except Exception as exc:
            issues.append({
                "kind": "VPS_FILE_CORRUPT",
                "detail": f"{vps_path}: {type(exc).__name__}: {exc}",
                "output_path": laptop_rel,
                "self_heal": "push_to_vps",
            })
            continue
        laptop_val = laptop_data.get(field)
        vps_val = vps_data.get(field)
        if laptop_val != vps_val:
            issues.append({
                "kind": "HOST_DRIFT",
                "detail": (
                    f"{laptop_rel} field={field}: laptop={laptop_val!r} vps={vps_val!r} — "
                    f"VPS-side tasks are reading wrong value"
                ),
                "output_path": laptop_rel,
                "self_heal": "push_to_vps",
            })
            continue
        # Even when content matches, check VPS-side timestamp staleness —
        # a clock-skewed agree could mask a frozen file.
        laptop_ts = laptop_data.get("timestamp")
        vps_ts = vps_data.get("timestamp")
        if laptop_ts and vps_ts:
            try:
                laptop_dt = datetime.fromisoformat(laptop_ts)
                vps_dt = datetime.fromisoformat(vps_ts)
                lag = (laptop_dt - vps_dt).total_seconds()
                if lag > 12 * 3600:
                    issues.append({
                        "kind": "HOST_TIMESTAMP_LAG",
                        "detail": (
                            f"{laptop_rel} laptop {laptop_dt:%Y-%m-%d %H:%M} vs vps "
                            f"{vps_dt:%Y-%m-%d %H:%M} ({lag/3600:.1f}h lag, max 12h)"
                        ),
                        "output_path": laptop_rel,
                        "self_heal": "push_to_vps",
                    })
            except (TypeError, ValueError):
                pass
    return issues


def run_all_audits() -> list[dict]:
    """Run every content audit; merge results."""
    issues: list[dict] = []
    issues.extend(audit_stale_open_rows())
    issues.extend(audit_provenance_drift())
    issues.extend(audit_cross_host_regime())
    return issues
