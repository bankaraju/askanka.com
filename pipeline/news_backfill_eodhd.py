"""EODHD news backfill orchestrator.

Pulls per-ticker news from EODHD /api/news for a configurable date range,
dedups against existing news_events_history.json by event_id hash, writes
incrementally so partial runs are recoverable. Designed to fill the 5y
Mode A backtest window (2020-12-01 -> present) as the foundation for
ASDE v2's news-conditional alpha discovery.

Constraints
-----------
- EODHD news depth for Indian tickers: ~Dec 2020 (verified by capabilities
  probe 2026-04-30). Requests for earlier ranges return n=0 cleanly.
- BSE (.BSE / .BO suffix): NOT supported by EODHD. NSE-only.
- Each /api/news call costs 5 API units against the 100K/day quota.

Schema additions to news_events_history.json
--------------------------------------------
Existing schema already has: title, url, source, published, detected_at,
matched_stocks, categories, tier, confidence, impact, policy_matches.

Backfill adds these provenance fields per event:
  event_id        sha256(url + published + title)[:16] — dedup key
  fetched_at      ISO timestamp when WE pulled it
  fetcher         "eodhd_backfill_v1"
  source_id       EODHD's internal id when present, else null

CLI
---
  python -m pipeline.news_backfill_eodhd --tickers RELIANCE TCS HDFCBANK \
         --from 2024-01-01 --to 2024-12-31 --dry-run

  python -m pipeline.news_backfill_eodhd --top-n 50 --years 2 --commit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO = Path(__file__).resolve().parents[1]
HIST_PATH = REPO / "pipeline" / "data" / "news_events_history.json"
CHECKPOINT_PATH = REPO / "pipeline" / "data" / "news_backfill_eodhd_checkpoint.json"
LOG_DIR = REPO / "pipeline" / "logs"

EODHD_NEWS_DEPTH_START = date(2020, 12, 1)  # empirically observed
DEFAULT_LIMIT_PER_CALL = 1000
DEFAULT_SLEEP_BETWEEN_CALLS = 0.5  # seconds; well under 1k/min limit
DAILY_QUOTA = 100_000
NEWS_CALL_COST = 5  # per EODHD docs


@dataclass(frozen=True)
class BackfillResult:
    ticker: str
    window_from: str
    window_to: str
    n_pulled: int
    n_new: int
    n_dup: int
    status: str  # "OK" | "ERROR_HTTP_<code>" | "ERROR_NETWORK" | "EMPTY"
    error: str | None = None


def _read_api_key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if k:
        return k
    for p in (REPO / ".env", REPO / "pipeline" / ".env"):
        if p.is_file():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.strip().startswith("EODHD_API_KEY="):
                    return ln.split("=", 1)[1].strip()
    raise SystemExit("EODHD_API_KEY missing from env and .env files")


def _event_id(url: str, published: str, title: str) -> str:
    """Stable dedup key — url+published+title sha256 truncated to 16."""
    payload = (url or "") + "|" + (published or "") + "|" + (title or "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _load_history() -> tuple[list[dict], set[str]]:
    """Load existing history + index of (event_id) for dedup.

    Falls back to (url+published) hash for events written before backfill
    schema was introduced.
    """
    if not HIST_PATH.is_file():
        return [], set()
    try:
        events = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], set()
    if not isinstance(events, list):
        return [], set()
    seen: set[str] = set()
    for ev in events:
        eid = ev.get("event_id")
        if eid:
            seen.add(eid)
            continue
        # legacy event without event_id — synthesize from url+published+title
        eid = _event_id(ev.get("url", ""), ev.get("published", ""), ev.get("title", ""))
        seen.add(eid)
    return events, seen


def _atomic_write(path: Path, events: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(events, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def _checkpoint_load() -> dict:
    if not CHECKPOINT_PATH.is_file():
        return {"runs": []}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"runs": []}


def _checkpoint_save(state: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, CHECKPOINT_PATH)


def _eodhd_news_call(symbol: str, from_iso: str, to_iso: str,
                     api_key: str, *, limit: int = DEFAULT_LIMIT_PER_CALL,
                     offset: int = 0) -> tuple[int, list[dict] | None, str | None]:
    """One /api/news call. Returns (status, events_list, error_msg)."""
    qs = urlencode({
        "s": symbol, "from": from_iso, "to": to_iso,
        "limit": limit, "offset": offset,
        "api_token": api_key, "fmt": "json",
    })
    url = f"https://eodhd.com/api/news?{qs}"
    req = Request(url, headers={"User-Agent": "askanka-news-backfill/1.0"})
    try:
        with urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
        events = json.loads(body)
        if not isinstance(events, list):
            return r.status, None, f"non-list response: {str(events)[:120]}"
        return r.status, events, None
    except HTTPError as e:
        return e.code, None, f"HTTP {e.code} {e.reason}"
    except (URLError, json.JSONDecodeError) as e:
        return 0, None, f"{type(e).__name__}: {e}"


def _normalize_event(raw: dict, ticker: str, fetched_at_iso: str) -> dict:
    """Map EODHD news response item to history schema with provenance."""
    title = raw.get("title", "") or ""
    url = raw.get("link") or raw.get("url") or ""
    published = raw.get("date") or ""
    eid = _event_id(url, published, title)
    return {
        "title": title,
        "url": url,
        "source": "EODHD",
        "published": published,
        "detected_at": fetched_at_iso,
        "matched_stocks": [ticker.split(".")[0].upper()],
        "categories": list(raw.get("tags") or []),
        "tier": "EODHD",
        "confidence": "HIGH",  # direct ticker query, not inferred
        "impact": "MEDIUM",     # backfill doesn't classify; default
        "policy_matches": [],
        # provenance fields:
        "event_id": eid,
        "fetched_at": fetched_at_iso,
        "fetcher": "eodhd_backfill_v1",
        "source_id": raw.get("id"),
    }


def _yearly_chunks(start: date, end: date) -> list[tuple[str, str]]:
    """Split [start, end] into yearly windows for EODHD's 1000-event limit."""
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = date(cursor.year, 12, 31)
        if chunk_end > end:
            chunk_end = end
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = date(cursor.year + 1, 1, 1)
    return chunks


def backfill_ticker(
    ticker: str,
    *,
    from_d: date,
    to_d: date,
    api_key: str,
    existing_events: list[dict],
    seen_ids: set[str],
    dry_run: bool = False,
    sleep_between: float = DEFAULT_SLEEP_BETWEEN_CALLS,
) -> list[BackfillResult]:
    """Pull news for one ticker across yearly windows; mutate
    existing_events + seen_ids in place. Returns per-window results."""
    symbol = ticker if "." in ticker else f"{ticker}.NSE"
    results: list[BackfillResult] = []
    fetched_at_iso = _now_iso()

    # Clamp from_d to EODHD news depth start
    effective_from = max(from_d, EODHD_NEWS_DEPTH_START)
    if effective_from > to_d:
        results.append(BackfillResult(
            ticker=ticker, window_from=from_d.isoformat(),
            window_to=to_d.isoformat(),
            n_pulled=0, n_new=0, n_dup=0,
            status="EMPTY", error="window before EODHD depth start (Dec 2020)",
        ))
        return results

    for f_iso, t_iso in _yearly_chunks(effective_from, to_d):
        if dry_run:
            results.append(BackfillResult(
                ticker=ticker, window_from=f_iso, window_to=t_iso,
                n_pulled=0, n_new=0, n_dup=0, status="DRY_RUN",
            ))
            continue

        status, events, err = _eodhd_news_call(symbol, f_iso, t_iso, api_key)
        if events is None:
            results.append(BackfillResult(
                ticker=ticker, window_from=f_iso, window_to=t_iso,
                n_pulled=0, n_new=0, n_dup=0,
                status=f"ERROR_HTTP_{status}", error=err,
            ))
            time.sleep(sleep_between)
            continue

        n_pulled = len(events)
        n_new = 0
        n_dup = 0
        for raw in events:
            normalized = _normalize_event(raw, ticker, fetched_at_iso)
            if normalized["event_id"] in seen_ids:
                n_dup += 1
                continue
            seen_ids.add(normalized["event_id"])
            existing_events.append(normalized)
            n_new += 1

        results.append(BackfillResult(
            ticker=ticker, window_from=f_iso, window_to=t_iso,
            n_pulled=n_pulled, n_new=n_new, n_dup=n_dup, status="OK",
        ))
        time.sleep(sleep_between)

    return results


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return [t.upper() for t in args.tickers]
    # default: read F&O universe from canonical
    canonical = REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
    if not canonical.is_file():
        raise SystemExit(f"canonical FNO file missing: {canonical}")
    doc = json.loads(canonical.read_text(encoding="utf-8"))
    valid_from = doc.get("per_ticker_valid_from", {})
    tickers = sorted(valid_from.keys())
    if args.top_n:
        return tickers[:args.top_n]
    return tickers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", help="explicit ticker list (without .NSE)")
    ap.add_argument("--top-n", type=int, help="first N tickers from canonical FNO list")
    ap.add_argument("--from", dest="from_d", help="ISO date YYYY-MM-DD")
    ap.add_argument("--to", dest="to_d", help="ISO date YYYY-MM-DD")
    ap.add_argument("--years", type=int, default=5,
                    help="if --from not given, walk back N years from today")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate calls without making them")
    ap.add_argument("--commit", action="store_true",
                    help="actually write to history file (default off; reports only)")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_BETWEEN_CALLS,
                    help="seconds between calls (default 0.5)")
    args = ap.parse_args(argv)

    api_key = _read_api_key()
    today = date.today()
    from_d = (date.fromisoformat(args.from_d)
              if args.from_d else today - timedelta(days=365 * args.years))
    to_d = date.fromisoformat(args.to_d) if args.to_d else today
    tickers = _resolve_tickers(args)

    existing_events, seen_ids = _load_history()
    initial_n = len(existing_events)
    print(f"history: {initial_n} existing events")
    print(f"window:  {from_d} -> {to_d}")
    print(f"tickers: {len(tickers)} ({', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''})")
    print(f"mode:    {'DRY_RUN' if args.dry_run else ('COMMIT' if args.commit else 'PREVIEW')}")
    print()

    state = _checkpoint_load()
    run_started = _now_iso()
    run_results: list[dict] = []
    n_total_pulled = 0
    n_total_new = 0

    for i, t in enumerate(tickers):
        per_ticker = backfill_ticker(
            t, from_d=from_d, to_d=to_d, api_key=api_key,
            existing_events=existing_events, seen_ids=seen_ids,
            dry_run=args.dry_run, sleep_between=args.sleep,
        )
        for r in per_ticker:
            n_total_pulled += r.n_pulled
            n_total_new += r.n_new
            run_results.append(asdict(r))
            print(f"  {r.ticker:14s} {r.window_from}->{r.window_to[-2:]}  "
                  f"pulled={r.n_pulled:4d} new={r.n_new:4d} dup={r.n_dup:4d}  {r.status}"
                  + (f" ({r.error})" if r.error else ""))

        if args.commit and not args.dry_run and (i + 1) % 5 == 0:
            _atomic_write(HIST_PATH, existing_events)

    if args.commit and not args.dry_run:
        _atomic_write(HIST_PATH, existing_events)

    state["runs"].append({
        "started_at": run_started,
        "ended_at": _now_iso(),
        "tickers_count": len(tickers),
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
        "n_total_pulled": n_total_pulled,
        "n_total_new": n_total_new,
        "committed": args.commit and not args.dry_run,
        "results": run_results,
    })
    _checkpoint_save(state)

    print()
    print(f"final history: {len(existing_events)} events "
          f"(was {initial_n}, +{len(existing_events) - initial_n})")
    print(f"calls cost ~{n_total_pulled and len(run_results) * NEWS_CALL_COST or 0} of "
          f"{DAILY_QUOTA} daily quota units")
    print(f"checkpoint -> {CHECKPOINT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
