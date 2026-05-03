"""Auto-grade FAQ baseline runs using Gemini 2.5 Flash.

Reads:   ~/.hermes/data/faq_runs/<date>/*.json (per-question records)
         ~/askanka.com/<source files referenced by citations>
Writes:  docs/research/hermes_pilot/report_cards/<date>-week-1.md
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "askanka.com"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
RUNS_BASE = Path.home() / ".hermes" / "data" / "faq_runs"
REPORT_DIR = REPO / "docs" / "research" / "hermes_pilot" / "report_cards"

GRADER_TEMPLATE = """You are grading an answer from a Hermes/Gemma-4 system-FAQ agent
that must answer ONLY from cited source files in the askanka.com repo.

Score on these 4 dimensions and return ONLY a JSON object with these keys:
  citation: 0 or 1 (1 if at least one source file from INDEX is cited; 0 otherwise)
  faithfulness: 0, 1, or 2 (0=contradicts source, 1=mostly aligned but one wrong claim, 2=every claim traceable to cited source)
  completeness: 0, 1, or 2 (0=doesn't address question, 1=partial, 2=addresses fully and at appropriate depth)
  no_hallucination: 0 or 1 (1=clean, only source-grounded claims; 0=invented at least one fact)
  notes: 1-2 sentences justifying the scores

QUESTION (Tier {tier}):
{q}

HERMES ANSWER:
---
{answer_text}
---

CITED SOURCE FILES (verbatim content):
---
{sources_content}
---

Return JSON ONLY. No prose, no markdown fences, no commentary."""


def load_source_content(citations: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in citations:
        full = REPO / path
        if full.exists():
            try:
                out[path] = full.read_text(encoding="utf-8", errors="replace")[:24000]
            except Exception as e:
                out[path] = f"<read-error: {e}>"
        else:
            out[path] = "<missing-file>"
    return out


def build_grader_prompt(record: dict, sources_content: dict[str, str]) -> str:
    sources_block = "\n\n".join(
        f"### {path}\n{content}" for path, content in sources_content.items()
    ) or "(no sources cited)"
    return GRADER_TEMPLATE.format(
        tier=record["tier"], q=record["q"],
        answer_text=record["answer_text"][:6000],
        sources_content=sources_block,
    )


def parse_grader_response(raw: str) -> dict:
    """Extract the LAST JSON object from grader output."""
    matches = list(re.finditer(r"\{[^{}]*\}", raw, re.DOTALL))
    if not matches:
        raise ValueError(f"No JSON object found in grader response: {raw[:200]}")
    return json.loads(matches[-1].group(0))


def score_record(record: dict, scored: dict) -> dict:
    cite = int(scored["citation"])
    faith = int(scored["faithfulness"])
    comp = int(scored["completeness"])
    halluc = int(scored["no_hallucination"])
    citation_override = None

    n_quotes_loose = record.get("n_quotes_loose")
    if n_quotes_loose is None:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from parse_citations import extract_quotes_loose
        n_quotes_loose = len(extract_quotes_loose(record.get("answer_text", "")))

    if record["tier"] == 1 and n_quotes_loose < 2:
        citation_override = 0
        cite = 0

    score = cite + faith + comp + halluc
    return {
        "id": record["id"], "tier": record["tier"],
        "citation": cite, "faithfulness": faith,
        "completeness": comp, "no_hallucination": halluc,
        "score": score, "max": 6,
        "pass": score >= 5 and halluc == 1,
        "citation_override": citation_override,
        "notes": scored.get("notes", ""),
    }


def call_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash via the existing pipeline GeminiProvider."""
    from pipeline.llm_providers.gemini_provider import GeminiProvider

    provider = GeminiProvider(name="gemini", model="gemini-2.5-flash")
    resp = provider.generate(prompt)
    return resp.text


def main(date_str: str | None = None) -> int:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    runs_dir = RUNS_BASE / date_str
    if not runs_dir.exists():
        print(f"FAIL: no runs at {runs_dir}", file=sys.stderr)
        return 1

    scored_records: list[dict] = []
    for path in sorted(runs_dir.glob("T*Q*.json")):
        record = json.loads(path.read_text())
        sources = load_source_content(record["citations"])
        prompt = build_grader_prompt(record, sources)
        try:
            raw = call_gemini(prompt)
            scored = parse_grader_response(raw)
        except Exception as e:
            scored = {"citation": 0, "faithfulness": 0, "completeness": 0,
                      "no_hallucination": 0, "notes": f"GRADER ERROR: {e}"}
        scored_records.append(score_record(record, scored))

    write_report_card(date_str, scored_records, runs_dir)
    return 0


def write_report_card(date_str: str, records: list[dict], runs_dir: Path) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{date_str}-week-1.md"
    by_tier = {t: [r for r in records if r["tier"] == t] for t in (1, 2, 3, 4, 5)}

    total = sum(r["score"] for r in records)
    max_total = 6 * len(records)
    pct = round(100 * total / max_total, 1) if max_total else 0
    halluc_clean = sum(1 for r in records if r["no_hallucination"] == 1)
    halluc_pct = round(100 * halluc_clean / len(records), 1) if records else 0
    cite_pct = round(100 * sum(1 for r in records if r["citation"] == 1) / len(records), 1) if records else 0

    summary_path = runs_dir / "_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        latencies = [r["latency_seconds"] for r in summary["results"]]
        avg_latency_min = round(sum(latencies) / len(latencies) / 60, 1) if latencies else 0
    else:
        avg_latency_min = 0

    pass_overall = pct >= 85 and halluc_pct == 100 and cite_pct >= 80 and avg_latency_min <= 5
    if pass_overall:
        verdict = "PASS"
    elif halluc_pct < 100:
        verdict = "FAIL"
    else:
        verdict = "DWELL"

    lines = [
        f"# Hermes Pilot — Week 1 Report Card",
        "",
        f"**Date run:** {date_str}",
        "**Skills under test:** system-faq",
        f"**Total questions:** {len(records)}",
        f"**Aggregate score:** {total} / {max_total} ({pct}%)",
        "",
        "**Per-tier:**",
    ]
    for t in (1, 2, 3, 4, 5):
        rs = by_tier[t]
        if not rs:
            continue
        ts = sum(r["score"] for r in rs)
        tm = 6 * len(rs)
        lines.append(f"- Tier {t}: {ts}/{tm} ({round(100 * ts/tm, 1)}%)")

    lines += [
        "",
        "**Per-criterion:**",
        f"- Citation (a): {cite_pct}%",
        f"- Faithfulness (b): {sum(r['faithfulness'] for r in records)}/{2 * len(records)}",
        f"- Completeness (c): {sum(r['completeness'] for r in records)}/{2 * len(records)}",
        f"- Hallucination (d): {halluc_pct}% **(must be 100%)**",
        f"- Avg latency: {avg_latency_min} min/q (budget ≤ 5)",
        "",
        f"**Verdict:** {verdict}",
        "",
        "**Per-question:**",
        "| ID | Tier | Cite | Faith | Compl | NoHall | Score | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['id']} | {r['tier']} | {r['citation']} | {r['faithfulness']} | "
            f"{r['completeness']} | {r['no_hallucination']} | {r['score']}/6 | "
            f"{r['notes'][:80].replace('|', ' ')} |"
        )
    lines += [
        "",
        "**Bharat spot-check:** [TODO — review 5 random questions, note any disagreements with grader]",
        "",
        "**Triggered action:** [TODO — fill per acceleration table once spot-check complete]",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    sidecar = REPORT_DIR / f"{date_str}-week-1.json"
    sidecar.write_text(json.dumps({
        "date": date_str,
        "n_questions": len(records),
        "aggregate_pct": pct,
        "halluc_clean_pct": halluc_pct,
        "citation_pct": cite_pct,
        "avg_latency_min": avg_latency_min,
        "verdict": verdict,
        "per_tier_pct": {
            t: round(100 * sum(r["score"] for r in by_tier[t]) / (6 * len(by_tier[t])), 1)
            for t in (1, 2, 3, 4, 5) if by_tier[t]
        },
        "tiers_present": sorted({r["tier"] for r in records}),
        "records": records,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {sidecar}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
