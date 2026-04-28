"""Real PCR snapshot producer for intraday_v1 framework.

Reads ONLY persisted EOD archives at ``pipeline/data/oi_history_stocks/<YYYY-MM-DD>.json``
and emits per-symbol ``{sym}_today.json`` + ``{sym}_2d_ago.json`` files containing
``put_oi_total_next_month`` and ``call_oi_total_next_month`` from the ``next``
expiry chain.

Hard contract (per ``feedback_no_hallucination_mandate.md``):
- If today's archive is missing for the resolved date, no files written.
- If 2-days-ago archive is missing, no files written.
- If a symbol is missing from EITHER archive, no file written for that symbol.
- No synthetic zeros, no yesterday-as-substitute. Real data or no data.

"Today" snapshot resolves to the most recent archive file with
``archive_date <= eval_date``. "2 days ago" resolves to 2 *trading days*
before that — counted by archive files actually present on disk, so weekends
and holidays are skipped naturally.

Wired into ``runner.loader_refresh()`` so the 04:30 IST nightly job
populates fresh PCR snapshots after refreshing the 1-min cache.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
OI_ARCHIVE_DIR = PIPELINE_ROOT / "data" / "oi_history_stocks"
DEFAULT_OUTPUT_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "pcr"
)

log = logging.getLogger("intraday_v1.pcr_producer")


def _list_archive_dates(archive_dir: Path) -> List[date]:
    """Return sorted list of archive dates parseable from filenames in ``archive_dir``."""
    if not archive_dir.exists():
        return []
    dates: List[date] = []
    for p in archive_dir.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        dates.append(d)
    return sorted(dates)


def _resolve_snapshot_dates(
    eval_date: date, archive_dir: Path
) -> Optional[Dict[str, date]]:
    """Resolve the ``today`` and ``2_days_ago`` archive dates for ``eval_date``.

    Returns ``None`` if either anchor cannot be resolved from the archive files
    actually present on disk.
    """
    available = _list_archive_dates(archive_dir)
    today_candidates = [d for d in available if d <= eval_date]
    if not today_candidates:
        return None
    today_d = today_candidates[-1]
    older = [d for d in available if d < today_d]
    if len(older) < 2:
        return None
    two_d_ago_d = older[-2]
    return {"today": today_d, "two_d_ago": two_d_ago_d}


def _load_archive(archive_dir: Path, d: date) -> Optional[Dict]:
    """Load one archive JSON; return None if file missing or unreadable."""
    p = archive_dir / f"{d.isoformat()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"failed to load archive {p}: {e}")
        return None


def _extract_next_oi(symbol_blob: Dict) -> Optional[Dict[str, int]]:
    """Pull put/call OI from the .next chain; return None if shape unexpected."""
    nxt = symbol_blob.get("next")
    if not isinstance(nxt, dict):
        return None
    put_oi = nxt.get("put_oi")
    call_oi = nxt.get("call_oi")
    if put_oi is None or call_oi is None:
        return None
    try:
        return {
            "put_oi_total_next_month": int(put_oi),
            "call_oi_total_next_month": int(call_oi),
        }
    except (TypeError, ValueError):
        return None


def produce_pcr_snapshots(
    eval_date: date,
    output_dir: Path,
    archive_dir: Path = OI_ARCHIVE_DIR,
) -> Dict:
    """Emit ``{sym}_today.json`` + ``{sym}_2d_ago.json`` for symbols in both archives.

    Parameters
    ----------
    eval_date
        The runtime date for which snapshots are being produced. The "today"
        archive is the most recent archive file ``<= eval_date``.
    output_dir
        Where to write the per-symbol JSON files. Created if absent.
    archive_dir
        Where the EOD archives live (defaults to ``OI_ARCHIVE_DIR``).

    Returns
    -------
    dict
        ``{"today_date", "two_d_ago_date", "symbols_written", "skipped"}``.
        Empty/missing anchors return zero ``symbols_written`` and a single
        ``skipped`` row explaining why.
    """
    summary: Dict = {
        "today_date": None,
        "two_d_ago_date": None,
        "symbols_written": 0,
        "skipped": [],
    }

    anchors = _resolve_snapshot_dates(eval_date, archive_dir)
    if anchors is None:
        summary["skipped"].append(
            {"reason": "INSUFFICIENT_ARCHIVES", "eval_date": eval_date.isoformat()}
        )
        log.warning(
            f"PCR producer: cannot resolve anchors for eval_date={eval_date} "
            f"(need >=2 archive files <= eval_date)"
        )
        return summary

    today_d = anchors["today"]
    two_d_ago_d = anchors["two_d_ago"]
    summary["today_date"] = today_d.isoformat()
    summary["two_d_ago_date"] = two_d_ago_d.isoformat()

    today_blob = _load_archive(archive_dir, today_d)
    two_d_blob = _load_archive(archive_dir, two_d_ago_d)
    if today_blob is None or two_d_blob is None:
        summary["skipped"].append({
            "reason": "ARCHIVE_LOAD_FAILED",
            "today_loaded": today_blob is not None,
            "two_d_ago_loaded": two_d_blob is not None,
        })
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)

    common_syms = sorted(set(today_blob.keys()) & set(two_d_blob.keys()))
    today_only = sorted(set(today_blob.keys()) - set(two_d_blob.keys()))
    two_d_only = sorted(set(two_d_blob.keys()) - set(today_blob.keys()))

    for sym in today_only:
        summary["skipped"].append({"symbol": sym, "reason": "MISSING_FROM_2D_AGO"})
    for sym in two_d_only:
        summary["skipped"].append({"symbol": sym, "reason": "MISSING_FROM_TODAY"})

    written = 0
    for sym in common_syms:
        today_oi = _extract_next_oi(today_blob[sym])
        two_d_oi = _extract_next_oi(two_d_blob[sym])
        if today_oi is None or two_d_oi is None:
            summary["skipped"].append({
                "symbol": sym,
                "reason": "MISSING_NEXT_CHAIN_OI",
                "today_ok": today_oi is not None,
                "two_d_ago_ok": two_d_oi is not None,
            })
            continue
        (output_dir / f"{sym}_today.json").write_text(
            json.dumps(today_oi), encoding="utf-8"
        )
        (output_dir / f"{sym}_2d_ago.json").write_text(
            json.dumps(two_d_oi), encoding="utf-8"
        )
        written += 1

    summary["symbols_written"] = written
    log.info(
        f"PCR producer: wrote {written} symbol pairs "
        f"(today={today_d}, 2d_ago={two_d_ago_d}, skipped={len(summary['skipped'])})"
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = produce_pcr_snapshots(date.today(), DEFAULT_OUTPUT_DIR)
    print(json.dumps(result, indent=2, default=str))
