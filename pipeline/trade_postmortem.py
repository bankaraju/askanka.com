"""Per-closed-trade post-mortem markdown emitter.

Backlog #30 (C14). Closed trades flow into closed_signals.json without a
human-readable narrative; peak→final gaps and lessons go uncaptured. This
module renders a markdown post-mortem per close, writes it under
`articles/postmortem-<date>-<slug>.md`, and appends a `segment="postmortem"`
entry to `data/articles_index.json` so the website can publish "what the
book actually did" alongside editorial.

The renderer accepts both shapes:
- closed_signals.json native (peak_spread_pnl_pct, final_pnl.spread_pnl_pct,
  _data_levels.daily_stop, status, close_timestamp)
- the test/plan flat shape (peak_pnl, final_pnl, daily_stop_pct, exit_reason)

so it works as a library and from the live EOD path with no shape coupling.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.trade_postmortem")

# Match the trail-arm threshold used by signal_tracker / mechanical replay
# (TRAIL_ARM_PCT = 2.0). Peaks at or above this should have armed the trail
# stop — when they then close negative, that's the trail-didn't-arm lesson.
TRAIL_ARM_PCT = 2.0

# Default paths used by the live EOD invocation. Overridable for tests.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTICLES_DIR = _REPO_ROOT / "articles"
DEFAULT_INDEX_PATH = _REPO_ROOT / "data" / "articles_index.json"


# ---------------------------------------------------------------------------
# Field extractors — accept either shape
# ---------------------------------------------------------------------------

def _peak_pnl(trade: dict) -> Optional[float]:
    if "peak_pnl" in trade:
        return _to_float(trade.get("peak_pnl"))
    return _to_float(trade.get("peak_spread_pnl_pct"))


def _final_pnl(trade: dict) -> Optional[float]:
    if isinstance(trade.get("final_pnl"), dict):
        return _to_float(trade["final_pnl"].get("spread_pnl_pct"))
    if "final_pnl" in trade:
        return _to_float(trade.get("final_pnl"))
    levels = trade.get("_data_levels") or {}
    return _to_float(levels.get("cumulative"))


def _daily_stop_pct(trade: dict) -> Optional[float]:
    if "daily_stop_pct" in trade:
        return _to_float(trade["daily_stop_pct"])
    levels = trade.get("_data_levels") or {}
    return _to_float(levels.get("daily_stop"))


def _exit_reason(trade: dict) -> str:
    if trade.get("exit_reason"):
        return str(trade["exit_reason"])
    return str(trade.get("status") or "CLOSED")


def _close_date(trade: dict) -> str:
    ts = trade.get("close_timestamp") or trade.get("close_time")
    if ts:
        try:
            return datetime.fromisoformat(str(ts).split(".")[0]).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return datetime.now().strftime("%Y-%m-%d")


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # Reject NaN — float("nan") parses but is not a sensible report value.
    if f != f:
        return None
    return f


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, dash-separate, strip leading/trailing dashes."""
    s = _NON_ALNUM.sub("-", str(name).lower()).strip("-")
    return s or "trade"


# ---------------------------------------------------------------------------
# extract_lesson — rule-based one-liner
# ---------------------------------------------------------------------------

def extract_lesson(
    peak: Optional[float],
    final: Optional[float],
    daily_stop: Optional[float],
    status: str,
) -> str:
    """One-line lesson extracted from the closed-trade arc.

    Order matters — first matching rule wins.
    """
    s = (status or "").upper()

    # Trail-arm check: peak crossed the arm threshold but final ended
    # negative. The trail should have ratcheted the stop forward; that it
    # didn't is the lesson worth flagging.
    if peak is not None and final is not None and peak >= TRAIL_ARM_PCT and final < 0:
        return (
            f"trail did not arm — peak {peak:+.2f}% gave back to {final:+.2f}%; "
            f"review trail arm threshold ({TRAIL_ARM_PCT:.1f}%) and ratchet logic"
        )

    # Daily stop killed a winner: status is a stop-out but final is still
    # positive. The hard-stop policy clipped a real edge.
    if "STOP" in s and final is not None and final > 0:
        return (
            f"daily stop on a winner — closed at {final:+.2f}%; "
            "review hard-stop policy on positive-P&L closes"
        )

    # Clean target hit — status is a target tag and final is well into
    # positive territory.
    if "TARGET" in s and final is not None and final > 0:
        return f"clean target hit at {final:+.2f}%"

    # Default: name what happened without a moral.
    final_str = f"{final:+.2f}%" if final is not None else "—"
    return f"{status or 'closed'} at {final_str}"


# ---------------------------------------------------------------------------
# render_postmortem — markdown body
# ---------------------------------------------------------------------------

def render_postmortem(trade: dict) -> str:
    """Render markdown for a single closed-trade record."""
    name = trade.get("spread_name") or trade.get("signal_id") or "Unknown trade"
    status = _exit_reason(trade)
    peak = _peak_pnl(trade)
    final = _final_pnl(trade)
    daily_stop = _daily_stop_pct(trade)
    days = trade.get("days_open")
    close_date = _close_date(trade)

    lesson = extract_lesson(peak=peak, final=final, daily_stop=daily_stop, status=status)

    lines = [
        f"# Post-mortem — {name}",
        "",
        f"**Closed:** {close_date}",
        f"**Exit reason:** {status}",
    ]
    if days is not None:
        lines.append(f"**Days held:** {days}")

    lines += ["", "## Trade arc"]
    if peak is not None:
        lines.append(f"- **Peak P&L:** {peak:+.2f}%")
    else:
        lines.append("- **Peak P&L:** —")
    if final is not None:
        lines.append(f"- **Final P&L:** {final:+.2f}%")
    else:
        lines.append("- **Final P&L:** —")
    if peak is not None and final is not None:
        gap = peak - final
        if gap > 0:
            lines.append(f"- **Gave back:** {gap:.2f}% from peak")
    if daily_stop is not None:
        lines.append(f"- **Daily stop level:** {daily_stop:+.2f}%")

    # If trade gave back from peak, surface "surrendered" word so search
    # tools and the editorial layer can quote it.
    if peak is not None and final is not None and peak > 0 and final < peak:
        lines += ["", f"Trade surrendered {peak - final:.2f}% from its peak."]

    lines += ["", "## Lesson", lesson, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# write_postmortem_for_trade — files + index
# ---------------------------------------------------------------------------

def _trade_filename(trade: dict) -> str:
    date = _close_date(trade)
    slug = slugify(trade.get("spread_name") or trade.get("signal_id") or "trade")
    return f"postmortem-{date}-{slug}.md"


def _trade_headline(trade: dict) -> str:
    name = trade.get("spread_name") or trade.get("signal_id") or "Trade"
    final = _final_pnl(trade)
    if final is not None:
        return f"{name}: post-mortem ({final:+.2f}%)"
    return f"{name}: post-mortem"


def write_postmortem_for_trade(
    trade: dict,
    *,
    articles_dir: Path = None,
    index_path: Path = None,
) -> Path:
    """Write the post-mortem markdown and append the articles_index entry.

    Idempotent: re-running on the same trade returns the same path and
    will not duplicate the articles_index entry.
    """
    articles_dir = Path(articles_dir) if articles_dir else DEFAULT_ARTICLES_DIR
    index_path = Path(index_path) if index_path else DEFAULT_INDEX_PATH

    articles_dir.mkdir(parents=True, exist_ok=True)
    fname = _trade_filename(trade)
    md_path = articles_dir / fname
    md_path.write_text(render_postmortem(trade), encoding="utf-8")

    # Append to articles_index, but only if not already present.
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("articles_index.json unreadable — initialising empty list")
            idx = {"articles": []}
    else:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        idx = {"articles": []}

    articles = idx.setdefault("articles", [])
    if not any(a.get("filename") == fname for a in articles):
        date = _close_date(trade)
        # Format published_at the same way as the existing entries
        # ("April 28, 2026"). On parse failure, fall back to the ISO date.
        try:
            published_at = datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
        except ValueError:
            published_at = date
        articles.insert(0, {
            "date": date,
            "segment": "postmortem",
            "filename": fname,
            "headline": _trade_headline(trade),
            "category": "TRADE POST-MORTEM",
            "color": "#6b7280",
            "published_at": published_at,
        })
        index_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")

    return md_path


# ---------------------------------------------------------------------------
# Convenience: render post-mortems for today's closes
# ---------------------------------------------------------------------------

def render_today_closes(closed_signals: list, today_iso: str) -> list:
    """Filter closed_signals to today's closes and render one post-mortem
    per close. Returns list of (Path, trade) tuples written.

    Used by run_signals.run_eod after run_eod_review() has settled the
    closed_signals.json file for today.
    """
    out = []
    for trade in closed_signals or []:
        ts = str(trade.get("close_timestamp") or "")
        if ts.startswith(today_iso):
            try:
                p = write_postmortem_for_trade(trade)
                out.append((p, trade))
            except Exception as e:  # don't fail EOD on one bad row
                log.warning(
                    "post-mortem render failed for %s: %s",
                    trade.get("signal_id") or trade.get("spread_name"), e,
                )
    return out
