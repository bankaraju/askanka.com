"""EODHD news API probe — Indian-equity coverage depth check.

Pulls EODHD /api/news for 5 representative tickers across a 60-day window
and a 5-year reach-back probe, then compares against the existing
pipeline/data/news_events_history.json by URL-hash and headline-prefix.

Outputs:
  pipeline/data/research/eodhd_probe/<date>/
    raw_<ticker>.json          per-ticker raw EODHD response
    summary.json               counts, overlap, unique-to-EODHD
    findings.md                human-readable verdict

Run:
    python pipeline/scripts/one_off/eodhd_news_probe.py

Cost: each ticker = 1 HTTPS GET. EODHD All-In-One plan covers /api/news
within quota. Total = 5 tickers × 2 windows = 10 requests.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parents[3]
HIST_PATH = REPO / "pipeline" / "data" / "news_events_history.json"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "eodhd_probe" / date.today().isoformat()

TICKERS = ["RELIANCE.NSE", "HAL.NSE", "TCS.NSE", "HDFCBANK.NSE", "TATAMOTORS.NSE"]
LIMIT = 1000  # EODHD max per request


def _read_env_key() -> str | None:
    # 1) explicit env var
    k = os.environ.get("EODHD_API_KEY")
    if k:
        return k
    # 2) .env file at repo root or pipeline/
    for envp in (REPO / ".env", REPO / "pipeline" / ".env"):
        if envp.is_file():
            for line in envp.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("EODHD_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return None


def _eodhd_news(symbol: str, from_iso: str, to_iso: str, api_key: str) -> list[dict]:
    """Hit EODHD /api/news. Returns the raw list (max LIMIT items per call)."""
    import urllib.request
    qs = urlencode({
        "s": symbol,
        "from": from_iso,
        "to": to_iso,
        "limit": LIMIT,
        "offset": 0,
        "api_token": api_key,
        "fmt": "json",
    })
    url = f"https://eodhd.com/api/news?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "askanka-eodhd-probe/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return json.loads(body)


def _hash_url(u: str) -> str:
    return hashlib.sha256((u or "").encode("utf-8")).hexdigest()[:16]


def _load_history() -> dict[str, list[dict]]:
    """Map ticker -> list of {url, headline, published_at} from news_events_history.json."""
    if not HIST_PATH.is_file():
        return {}
    try:
        doc = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    by_ticker: dict[str, list[dict]] = {}
    # The schema is a list of events with `tickers_affected` plus url+headline+date
    if isinstance(doc, list):
        for ev in doc:
            tickers = ev.get("tickers_affected") or ev.get("tickers") or []
            if not isinstance(tickers, list):
                continue
            url = (ev.get("url") or "").strip()
            head = (ev.get("headline") or "").strip()
            pub = ev.get("published_at") or ev.get("date") or ""
            for t in tickers:
                tag = str(t).upper().split(".")[0]
                by_ticker.setdefault(tag, []).append({
                    "url": url, "headline": head, "published_at": pub,
                    "url_hash": _hash_url(url),
                })
    elif isinstance(doc, dict):
        # alternate schema: keyed by date or category — best-effort flat scan
        def _walk(node):
            if isinstance(node, list):
                for it in node:
                    yield from _walk(it)
            elif isinstance(node, dict):
                if "url" in node and "headline" in node:
                    yield node
                else:
                    for v in node.values():
                        yield from _walk(v)
        for ev in _walk(doc):
            tickers = ev.get("tickers_affected") or ev.get("tickers") or []
            if not isinstance(tickers, list):
                continue
            url = (ev.get("url") or "").strip()
            head = (ev.get("headline") or "").strip()
            pub = ev.get("published_at") or ev.get("date") or ""
            for t in tickers:
                tag = str(t).upper().split(".")[0]
                by_ticker.setdefault(tag, []).append({
                    "url": url, "headline": head, "published_at": pub,
                    "url_hash": _hash_url(url),
                })
    return by_ticker


def _overlap_metrics(eodhd_hits: list[dict], hist_hits: list[dict]) -> dict:
    eodhd_url_hashes = {_hash_url(h.get("link") or h.get("url") or "") for h in eodhd_hits}
    eodhd_url_hashes.discard("")
    hist_url_hashes = {h["url_hash"] for h in hist_hits if h.get("url_hash")}
    common = eodhd_url_hashes & hist_url_hashes
    eodhd_only = eodhd_url_hashes - hist_url_hashes
    hist_only = hist_url_hashes - eodhd_url_hashes
    return {
        "eodhd_total": len(eodhd_url_hashes),
        "hist_total": len(hist_url_hashes),
        "common_urls": len(common),
        "eodhd_unique": len(eodhd_only),
        "hist_unique": len(hist_only),
        "pct_eodhd_overlap": (100.0 * len(common) / max(1, len(eodhd_url_hashes))),
    }


def _windows() -> list[tuple[str, str, str]]:
    """Return [(label, from_iso, to_iso)] — 60-day recent + 5-year-ago slice."""
    today = date.today()
    sixty_ago = (today - timedelta(days=60)).isoformat()
    five_y_ago = (today - timedelta(days=365 * 5))
    five_y_plus_60 = (five_y_ago + timedelta(days=60)).isoformat()
    return [
        ("recent_60d", sixty_ago, today.isoformat()),
        ("five_y_ago_60d", five_y_ago.isoformat(), five_y_plus_60),
    ]


def main() -> int:
    api_key = _read_env_key()
    if not api_key:
        print("ERROR: EODHD_API_KEY not found in env or .env", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    history = _load_history()
    print(f"history loaded: {len(history)} tickers, "
          f"e.g. RELIANCE has {len(history.get('RELIANCE', []))} entries")

    summary = {
        "probed_at": datetime.now(tz=timezone.utc).isoformat(),
        "tickers": TICKERS,
        "windows": [],
        "per_ticker": {},
    }

    for label, from_iso, to_iso in _windows():
        print(f"\n=== window {label}: {from_iso} -> {to_iso} ===")
        win_summary: dict = {"label": label, "from": from_iso, "to": to_iso, "tickers": {}}
        for sym in TICKERS:
            tag = sym.split(".")[0]
            try:
                hits = _eodhd_news(sym, from_iso, to_iso, api_key)
            except Exception as exc:
                print(f"  {sym}: FAIL {exc}")
                win_summary["tickers"][tag] = {"error": str(exc)}
                continue

            if not isinstance(hits, list):
                # API returned an error envelope
                print(f"  {sym}: non-list response: {hits!r}")
                win_summary["tickers"][tag] = {"error": str(hits)}
                continue

            raw_path = OUT_DIR / f"{label}_{tag}.json"
            raw_path.write_text(json.dumps(hits, indent=2)[:500_000], encoding="utf-8")

            sources = sorted({h.get("source", "?") for h in hits})
            dates = sorted({(h.get("date") or "")[:10] for h in hits if h.get("date")})
            cov_first = dates[0] if dates else None
            cov_last = dates[-1] if dates else None

            hist_hits = history.get(tag, [])
            metrics = _overlap_metrics(hits, hist_hits)
            metrics.update({
                "n_eodhd_raw": len(hits),
                "sources": sources,
                "coverage_first": cov_first,
                "coverage_last": cov_last,
            })
            win_summary["tickers"][tag] = metrics
            print(f"  {tag}: eodhd={metrics['eodhd_total']:4d} "
                  f"hist={metrics['hist_total']:4d} "
                  f"common={metrics['common_urls']:4d} "
                  f"unique-to-eodhd={metrics['eodhd_unique']:4d} "
                  f"({metrics['pct_eodhd_overlap']:.1f}% overlap)")

        summary["windows"].append(win_summary)

    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary -> {summary_path}")

    # Aggregate verdict
    findings = ["# EODHD news probe — findings",
                f"Probed at {summary['probed_at']}",
                ""]
    for w in summary["windows"]:
        findings.append(f"## Window: {w['label']}  ({w['from']} -> {w['to']})\n")
        findings.append("| Ticker | EODHD | History | Common | EODHD-unique | Overlap% | First | Last | Sources |")
        findings.append("|---|---|---|---|---|---|---|---|---|")
        for tag, m in w["tickers"].items():
            if "error" in m:
                findings.append(f"| {tag} | ERROR: {m['error']} |||||||| ")
                continue
            findings.append(
                f"| {tag} | {m['eodhd_total']} | {m['hist_total']} | "
                f"{m['common_urls']} | {m['eodhd_unique']} | "
                f"{m['pct_eodhd_overlap']:.1f}% | "
                f"{m.get('coverage_first','?')} | {m.get('coverage_last','?')} | "
                f"{', '.join(m.get('sources', [])[:5])} |"
            )
        findings.append("")
    findings.append("## Verdict heuristics")
    findings.append("- recent_60d EODHD-unique fraction > 30% AND five_y_ago_60d returns >0 results: register EODHD, plan 5y backfill")
    findings.append("- recent_60d overlap >= 80% AND five_y_ago_60d empty: redundant, keep current scrapers")
    findings.append("- intermediate: log + revisit with broader ticker probe")
    (OUT_DIR / "findings.md").write_text("\n".join(findings), encoding="utf-8")
    print(f"findings -> {OUT_DIR / 'findings.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
