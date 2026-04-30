"""EODHD intraday backfill orchestrator (5m + 1m).

Pulls per-ticker intraday bars from EODHD /api/intraday for a configurable
date range, writes per-ticker CSVs to pipeline/data/fno_intraday_<interval>/.
Monthly chunking for 5m/1h, weekly chunking for 1m.

Quota math (verified by capabilities probe 2026-04-30)
------------------------------------------------------
- Each /api/intraday call costs 5 quota units (per EODHD docs).
- 5m × 5y × 100 tickers ≈ 60 monthly chunks × 100 = 6,000 calls × 5 = 30K quota.
- 1m × 2y × 100 tickers ≈ 252×2 daily chunks × 100 = 50,400 calls × 5 = 252K quota
  → split across 3 days at 100K/day cap.
- Daily quota: 100K. Used today already: ~1K. Plenty of headroom for 5m run.

Output schema (per-ticker CSV)
------------------------------
datetime,open,high,low,close,volume
2024-04-23 09:15:00,2456.10,2459.85,2456.10,2459.10,12450
...
- datetime: NSE local time (IST), 09:15-15:29 trading window
- volume: may be NULL on 5m bars (only 1m has 100% volume completeness)

CLI
---
  # Top-100 by ADV, 5m, 5y
  python -m pipeline.intraday_backfill_eodhd --interval 5m --top-n 100 --years 5

  # Specific tickers
  python -m pipeline.intraday_backfill_eodhd --tickers RELIANCE TCS HDFCBANK \
         --interval 1m --years 1

  # Dry-run to estimate quota cost
  python -m pipeline.intraday_backfill_eodhd --interval 5m --top-n 100 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / "pipeline" / "logs"

INTRADAY_DEPTH = {
    "1m": date(2024, 4, 1),    # ~2y back per probe
    "5m": date(2021, 4, 1),    # ~5y back per probe
    "1h": date(2021, 4, 1),    # same as 5m
}

CHUNK_DAYS = {
    "1m": 7,    # weekly chunks (~2,625 bars per chunk → safe)
    "5m": 30,   # monthly chunks (~2,250 bars)
    "1h": 90,   # quarterly chunks (~600 bars)
}

DAILY_QUOTA = 100_000
INTRADAY_CALL_COST = 5
DEFAULT_SLEEP_BETWEEN_CALLS = 0.3
DEFAULT_PARALLEL_WORKERS = 5

_PRINT_LOCK = threading.Lock()


@dataclass(frozen=True)
class ChunkResult:
    ticker: str
    interval: str
    chunk_from: str
    chunk_to: str
    n_bars: int
    status: str
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
    raise SystemExit("EODHD_API_KEY missing")


def _epoch(d: date) -> int:
    return int(time.mktime(d.timetuple()))


def _eodhd_intraday_call(symbol: str, interval: str, from_d: date, to_d: date,
                         api_key: str) -> tuple[int, list[dict] | None, str | None]:
    qs = urlencode({
        "interval": interval,
        "from": _epoch(from_d),
        "to": _epoch(to_d + timedelta(days=1)),  # +1 to include to_d
        "api_token": api_key, "fmt": "json",
    })
    url = f"https://eodhd.com/api/intraday/{symbol}?{qs}"
    req = Request(url, headers={"User-Agent": "askanka-intraday-backfill/1.0"})
    try:
        with urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        if not isinstance(data, list):
            return r.status, None, f"non-list response: {str(data)[:120]}"
        return r.status, data, None
    except HTTPError as e:
        return e.code, None, f"HTTP {e.code} {e.reason}"
    except (URLError, json.JSONDecodeError) as e:
        return 0, None, f"{type(e).__name__}: {e}"


def _bars_to_csv_rows(bars: list[dict]) -> list[list]:
    """Convert EODHD intraday response items to CSV rows.

    EODHD intraday returns: timestamp (epoch UTC), gmtoffset, datetime
    (UTC string), open, high, low, close, volume (or null). NSE bars are
    timestamped UTC; we convert to IST (+5:30).
    """
    rows = []
    for b in bars:
        ts = b.get("timestamp")
        if ts is None:
            continue
        # NSE 09:15 IST = 03:45 UTC. We display IST in the CSV.
        dt_utc = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        dt_ist = dt_utc + timedelta(hours=5, minutes=30)
        # Filter to NSE trading window (09:15-15:30 IST inclusive)
        h, m = dt_ist.hour, dt_ist.minute
        if not (9 <= h <= 15):
            continue
        if h == 9 and m < 15:
            continue
        if h == 15 and m > 30:
            continue
        rows.append([
            dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
            b.get("open"), b.get("high"), b.get("low"), b.get("close"),
            b.get("volume") if b.get("volume") is not None else "",
        ])
    return rows


def _write_csv(path: Path, rows: list[list], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.is_file() else "w"
    with path.open(mode, encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        if mode == "w":
            w.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow(r)


def _existing_dt_set(path: Path) -> set[str]:
    """Read existing CSV and return set of datetime strings for dedup."""
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            dt = row.get("datetime")
            if dt:
                out.add(dt)
    return out


def _chunk_dates(start: date, end: date, days_per_chunk: int) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days_per_chunk - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def backfill_ticker(
    ticker: str, interval: str,
    *, from_d: date, to_d: date, api_key: str,
    out_dir: Path, dry_run: bool, sleep_between: float,
) -> list[ChunkResult]:
    symbol = ticker if "." in ticker else f"{ticker}.NSE"
    out_path = out_dir / f"{ticker.upper()}.csv"
    existing = _existing_dt_set(out_path)
    chunks = _chunk_dates(from_d, to_d, CHUNK_DAYS[interval])
    results: list[ChunkResult] = []
    new_rows: list[list] = []

    for c_from, c_to in chunks:
        if dry_run:
            results.append(ChunkResult(
                ticker=ticker, interval=interval,
                chunk_from=c_from.isoformat(), chunk_to=c_to.isoformat(),
                n_bars=0, status="DRY_RUN",
            ))
            continue

        status, bars, err = _eodhd_intraday_call(
            symbol, interval, c_from, c_to, api_key)
        if bars is None:
            results.append(ChunkResult(
                ticker=ticker, interval=interval,
                chunk_from=c_from.isoformat(), chunk_to=c_to.isoformat(),
                n_bars=0, status=f"ERROR_HTTP_{status}", error=err,
            ))
            time.sleep(sleep_between)
            continue

        rows = _bars_to_csv_rows(bars)
        # dedup against existing
        rows = [r for r in rows if r[0] not in existing]
        for r in rows:
            existing.add(r[0])
        new_rows.extend(rows)

        results.append(ChunkResult(
            ticker=ticker, interval=interval,
            chunk_from=c_from.isoformat(), chunk_to=c_to.isoformat(),
            n_bars=len(rows), status="OK",
        ))
        time.sleep(sleep_between)

    if new_rows and not dry_run:
        # Re-read existing to defeat concurrent-writer races (multiple
        # orchestrator processes hitting same file). Bit us 2026-04-30
        # when 3 backfills ran in parallel and dedup-against-stale-set
        # produced 3x rows.
        fresh_existing = _existing_dt_set(out_path)
        new_rows = [r for r in new_rows if r[0] not in fresh_existing]
        if new_rows:
            new_rows.sort(key=lambda r: r[0])
            _write_csv(out_path, new_rows, append=True)
            _resort_csv(out_path)

    return results


def _resort_csv(path: Path) -> None:
    """Read CSV, sort by datetime ascending, rewrite. Idempotent."""
    if not path.is_file():
        return
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        rows = list(reader)
        fields = reader.fieldnames or ["datetime", "open", "high", "low", "close", "volume"]
    rows.sort(key=lambda r: r["datetime"])
    with path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return [t.upper() for t in args.tickers]
    canonical = REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
    if not canonical.is_file():
        raise SystemExit(f"canonical FNO file missing: {canonical}")
    doc = json.loads(canonical.read_text(encoding="utf-8"))
    valid_from = doc.get("per_ticker_valid_from", {})
    tickers = list(valid_from.keys())

    # Sort by 60d ADV (highest first)
    try:
        from pipeline.research.auto_spread_discovery.liquidity import _cached_universe_adv
        adv = _cached_universe_adv()
        tickers.sort(key=lambda t: -adv.get(t.upper(), 0.0))
    except Exception as e:
        print(f"  warn: ADV-based sort failed ({e}); using alphabetical")
        tickers.sort()

    if args.top_n:
        return tickers[:args.top_n]
    return tickers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", choices=["1m", "5m", "1h"], required=True)
    ap.add_argument("--tickers", nargs="+")
    ap.add_argument("--top-n", type=int, help="first N tickers by ADV from FNO universe")
    ap.add_argument("--from", dest="from_d")
    ap.add_argument("--to", dest="to_d")
    ap.add_argument("--years", type=int, default=5,
                    help="walk back N years from today (default 5)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_BETWEEN_CALLS)
    ap.add_argument("--workers", type=int, default=DEFAULT_PARALLEL_WORKERS,
                    help="parallel ticker workers (default 5)")
    ap.add_argument("--out-dir", help="override default output dir")
    args = ap.parse_args(argv)

    api_key = _read_api_key()
    today = date.today()
    interval = args.interval
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO / "pipeline" / "data" / f"fno_intraday_{interval}")

    # Clamp from_d to interval depth
    requested_from = (date.fromisoformat(args.from_d)
                      if args.from_d else today - timedelta(days=365 * args.years))
    from_d = max(requested_from, INTRADAY_DEPTH[interval])
    to_d = date.fromisoformat(args.to_d) if args.to_d else today

    tickers = _resolve_tickers(args)

    chunks_per_ticker = len(_chunk_dates(from_d, to_d, CHUNK_DAYS[interval]))
    est_calls = chunks_per_ticker * len(tickers)
    est_quota = est_calls * INTRADAY_CALL_COST

    print(f"interval:    {interval}")
    print(f"window:      {from_d} -> {to_d}")
    print(f"chunk-size:  {CHUNK_DAYS[interval]} days")
    print(f"chunks/tkr:  {chunks_per_ticker}")
    print(f"tickers:     {len(tickers)} ({', '.join(tickers[:5])}...)")
    print(f"out-dir:     {out_dir}")
    print(f"est calls:   {est_calls}")
    print(f"est quota:   {est_quota} (of {DAILY_QUOTA}/day)")
    print(f"mode:        {'DRY_RUN' if args.dry_run else 'COMMIT'}")
    print()

    if est_quota > DAILY_QUOTA * 0.8 and not args.dry_run:
        print(f"WARN: est quota {est_quota} > 80% of daily limit — consider chunking by ticker")
        print("  Continue? (Ctrl-C to abort, 5s grace)")
        time.sleep(5)

    n_total = 0
    n_total_bars = 0
    started = datetime.now(timezone.utc)
    completed = [0]  # mutable counter for thread-safe progress

    def _run_one(idx: int, t: str) -> tuple[int, str, int, int, int]:
        per_ticker = backfill_ticker(
            t, interval, from_d=from_d, to_d=to_d, api_key=api_key,
            out_dir=out_dir, dry_run=args.dry_run, sleep_between=args.sleep,
        )
        n_chunks = len(per_ticker)
        n_bars = sum(r.n_bars for r in per_ticker)
        n_errors = sum(1 for r in per_ticker if r.status.startswith("ERROR"))
        with _PRINT_LOCK:
            completed[0] += 1
            done = completed[0]
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            eta_min = (elapsed / done) * (len(tickers) - done) / 60.0
            print(f"  [{done:3d}/{len(tickers)}] {t:14s} chunks={n_chunks} "
                  f"bars={n_bars:6d} errors={n_errors} eta={eta_min:.0f}min", flush=True)
        return idx, t, n_chunks, n_bars, n_errors

    if args.workers <= 1:
        for i, t in enumerate(tickers):
            _, _, nc, nb, _ = _run_one(i, t)
            n_total += nc
            n_total_bars += nb
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(_run_one, i, t) for i, t in enumerate(tickers)]
            for fut in as_completed(futures):
                _, _, nc, nb, _ = fut.result()
                n_total += nc
                n_total_bars += nb

    print()
    print(f"total chunks: {n_total}")
    print(f"total bars:   {n_total_bars}")
    print(f"elapsed:      {(datetime.now(timezone.utc) - started).total_seconds() / 60.0:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
