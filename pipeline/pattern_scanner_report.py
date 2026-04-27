"""One-pager Markdown report after each scanner paired-shadow close.

Per spec §13. Stratified tables, no edge claim.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _stratify(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[str(r.get(key, "UNKNOWN"))].append(r)
    return dict(out)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def build_report(ledger_path: Path, out_path: Path) -> None:
    rows = json.loads(Path(ledger_path).read_text())
    closed = [r for r in rows if r.get("status") == "CLOSED"]

    lines: list[str] = []
    lines.append("# Pattern Scanner Paired-Shadow Report\n")
    lines.append(f"**Total closed:** {len(closed)}\n")

    # Table A — headline paired diff, stratified by is_expiry_day
    lines.append("\n## Table A — Headline paired diff (options − futures)\n")
    lines.append("| is_expiry_day | N | mean(opt − fut) | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "is_expiry_day").items():
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        diff = (opt - fut) if (opt is not None and fut is not None) else None
        lines.append(f"| {k} | {len(cohort)} | {_fmt_pct(diff)} | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Table B — Win rate by pattern_id
    lines.append("\n## Table B — Win rate by pattern_id\n")
    lines.append("| pattern_id | N | win-rate | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "pattern_id").items():
        wins = sum(1 for r in cohort if (r.get("pnl_net_pct") or 0) > 0)
        wr = wins / len(cohort) if cohort else 0
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        lines.append(f"| {k} | {len(cohort)} | {wr*100:.1f}% | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Table C — by direction
    lines.append("\n## Table C — Win rate by direction\n")
    lines.append("| side | N | win-rate | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "side").items():
        wins = sum(1 for r in cohort if (r.get("pnl_net_pct") or 0) > 0)
        wr = wins / len(cohort) if cohort else 0
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        lines.append(f"| {k} | {len(cohort)} | {wr*100:.1f}% | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Skip rate
    skipped = [r for r in rows if r.get("status") == "SKIPPED_LIQUIDITY"]
    err = [r for r in rows if r.get("status") == "ERROR"]
    lines.append(f"\n## Skip-rate summary\n")
    lines.append(f"- SKIPPED_LIQUIDITY: {len(skipped)} rows ({len(skipped)/max(1,len(rows))*100:.1f}% of total)")
    lines.append(f"- ERROR: {len(err)} rows ({len(err)/max(1,len(rows))*100:.1f}% of total)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
