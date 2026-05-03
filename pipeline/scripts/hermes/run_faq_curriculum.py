#!/usr/bin/env python3
"""Curriculum-mode FAQ runner — pre-loads source bytes into the prompt.

Fixes the Week-1 FAIL root cause: the baseline runner sent only INDEX.md
(paths + descriptions, not source bytes) to Gemma, so the model fabricated
verbatim quotes from training memory while citing real paths. This runner
resolves each question's INDEX topic to its source files, reads the actual
bytes, and inlines them in a SOURCE_CONTENT block. Quotes can now be
extracted by the model rather than hallucinated.

Curriculum order (worst-first by Week-1 score):
  Stage 1 = Tier 5 only (6 Qs, was 27.8%)
  Stage 2 = Tier 5 + Tier 2 (12 Qs)
  Stage 3 = + Tier 1 (18 Qs)
  Stage 4 = + Tier 4 (24 Qs)
  Stage 5 = + Tier 3 (30 Qs — full baseline, gates verdict)

Usage:
    python run_faq_curriculum.py --stage 1
    python run_faq_curriculum.py --tiers 5
    python run_faq_curriculum.py --tiers 5,2 --date 2026-05-04

Reads:  ~/askanka.com/docs/faq/INDEX.md
        ~/askanka.com/docs/faq/baseline_questions.json
        + every source file referenced by the matched topic
Writes: ~/.hermes/data/faq_runs/<date>/<question_id>.json
        + ~/.hermes/data/faq_runs/<date>/_summary.json
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "askanka.com"
INDEX_PATH = REPO / "docs" / "faq" / "INDEX.md"
QUESTIONS = REPO / "docs" / "faq" / "baseline_questions.json"
OUT_BASE = Path.home() / ".hermes" / "data" / "faq_runs"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_DEFAULT = "gemma4-32k"
MAX_BYTES_PER_SOURCE = 24000
TIER_CURRICULUM = {1: [5], 2: [5, 2], 3: [5, 2, 1], 4: [5, 2, 1, 4], 5: [5, 2, 1, 4, 3]}

sys.path.insert(0, str(REPO / "pipeline" / "scripts" / "hermes"))
from parse_citations import extract_citations, extract_quotes, extract_quotes_loose  # noqa: E402

BASELINE_TO_INDEX = {
    "Karpathy random search": "Karpathy random search",
    "Lasso L1": "Lasso L1 regularization",
    "BH-FDR": "BH-FDR multiple-testing correction",
    "Deflated Sharpe": "Deflated Sharpe",
    "Walk-forward CV": "Walk-forward cross-validation",
    "Permutation null": "Permutation null",
    "Golden Goose": "8-layer Golden Goose pipeline",
    "ETF regime v3-CURATED-30": "ETF regime engine (v3-CURATED-30)",
    "OPUS ANKA Trust Scores": "OPUS ANKA Trust Scores",
    "Spread Intelligence": "Spread Intelligence Engine",
    "Reverse Regime A/B/C": "Reverse Regime Phase A/B/C",
    "Theme Detector v1": "Theme Detector v1",
    "Clockwork": "80+ scheduled tasks (clockwork)",
    "Watchdog": "Data-freshness watchdog",
    "14:30 cutoff": "14:30 IST new-signal cutoff",
    "Kill-switch": "Kill-switch (strategy-pattern gate)",
    "anka_inventory.json": "anka_inventory.json",
    "VPS execution foundation": "VPS execution foundation",
    "H-2026-04-25-002": "H-2026-04-25-002 (etf-stock-tail-classifier)",
    "H-2026-04-29-ta-karpathy-v1": "H-2026-04-29-ta-karpathy-v1 (per-stock TA Lasso, top-10 NIFTY)",
    "H-2026-04-29-intraday-data-driven-v1": "H-2026-04-29-intraday-data-driven-v1 (twin: stocks + indices)",
    "H-2026-04-27-003 SECRSI": "H-2026-04-27-003 SECRSI (sector RS intraday pair)",
    "H-2026-05-01-EARNINGS-DRIFT-LONG-v1": "H-2026-05-01-EARNINGS-DRIFT-LONG-v1",
    "H-2026-05-01-phase-c-mr-karpathy-v1": "H-2026-05-01-phase-c-mr-karpathy-v1",
    "backtesting-specs §0": "backtesting-specs.txt",
    "Single-touch holdout §10.4": "Single-touch holdout (§10.4 strict)",
    "Data-validation §21": "anka_data_validation_policy_global_standard.md",
    "Doc-sync mandate": "Doc-sync mandate",
    "No-hallucination mandate": "No-hallucination mandate",
    "Subscriber language": "Subscriber language (plain English)",
}

SYSTEM = """You are the askanka.com system-FAQ agent. You answer ONLY from
the SOURCE_CONTENT block. Strict rules:

1. Every factual claim must be traceable to a phrase physically present in
   the SOURCE_CONTENT block. Do NOT use general training-data knowledge.
   The INDEX_ENTRY block is for orientation ONLY — its 'One-line:'
   description is a paraphrased FAQ summary, NOT a source. Do NOT quote
   from INDEX_ENTRY. Quote ONLY from SOURCE_CONTENT.
   If SOURCE_CONTENT does not contain the answer, reply with the single
   line 'INSUFFICIENT_SOURCE' and stop.
2. Use at least one verbatim quote. Format each quote as:
       > "exact substring copied from SOURCE_CONTENT"
       — <source path from a SOURCE_CONTENT header above>
   The quoted text MUST be a copy-paste from a SOURCE_CONTENT block — no
   paraphrase, no completion, no improvement, no underscore-for-space
   substitutions. If you cannot find an exact substring that answers the
   point, write 'no exact quote available' on that point.
3. End every answer with a 'Sources:' line followed by bullet points listing
   each cited path:
       Sources:
       - docs/path/one.md
       - docs/path/two.md
4. No LaTeX, headers, bold, or italics. Plain prose + quote blocks + Sources.
5. Tier 1 (ML methods) requires AT LEAST TWO verbatim quotes from different
   sources. If you cannot find two, say so and quote what you can.

Reasoning, planning, and self-correction must NOT appear in the output —
final answer only."""


def parse_index_topics(index_text: str) -> dict[str, list[str]]:
    """Map INDEX heading text → ordered list of source paths under it."""
    topics: dict[str, list[str]] = {}
    current = None
    in_sources = False
    src_re = re.compile(r"^\s+-\s+([\w./_ -]+\.(?:md|txt|json|jsonl|py))")
    for line in index_text.splitlines():
        h = re.match(r"^###\s+(.+?)\s*$", line)
        if h:
            current = h.group(1).strip()
            topics[current] = []
            in_sources = False
            continue
        if current and line.strip().lower().startswith("- sources:"):
            in_sources = True
            continue
        if current and (line.startswith("## ") or line.startswith("### ")):
            in_sources = False
            current = None
            continue
        if in_sources:
            sm = src_re.match(line)
            if sm:
                topics[current].append(sm.group(1).strip())
    return topics


def get_index_block(index_text: str, heading: str) -> str:
    """Return the INDEX section (one-line description + Sources list) for a heading."""
    lines = index_text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == f"### {heading}":
            j = i + 1
            while j < len(lines) and not (lines[j].startswith("### ") or lines[j].startswith("## ")):
                j += 1
            return "\n".join(lines[i:j]).rstrip()
    return f"### {heading}\n(NOT FOUND)"


def load_sources(paths: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        full = REPO / p
        if not full.exists():
            out[p] = "<missing-file>"
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
            out[p] = text[:MAX_BYTES_PER_SOURCE]
            if len(text) > MAX_BYTES_PER_SOURCE:
                out[p] += f"\n\n... [truncated at {MAX_BYTES_PER_SOURCE} chars]"
        except Exception as e:
            out[p] = f"<read-error: {e}>"
    return out


def build_prompt(question: dict, index_block: str, sources: dict[str, str]) -> str:
    sources_block = "\n\n".join(f"### SOURCE: {p}\n{c}" for p, c in sources.items())
    return (
        f"{SYSTEM}\n\n"
        f"INDEX_ENTRY:\n{index_block}\n\n"
        f"SOURCE_CONTENT:\n{sources_block}\n\n"
        f"QUESTION (Tier {question['tier']}): {question['q']}\n\n"
        f"Answer:"
    )


def call_ollama(model: str, prompt: str, num_predict: int = 1000, timeout_s: int = 3600) -> dict:
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps({
            "model": model,
            "prompt": prompt,
            "think": False,
            "stream": False,
            "options": {"num_predict": num_predict, "temperature": 0.0},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())


def run_one(question: dict, topic_to_sources: dict[str, list[str]],
            index_text: str, model: str, out_dir: Path, force: bool = False) -> dict:
    qid = question["id"]
    out_path = out_dir / f"{qid}.json"
    if out_path.exists() and not force:
        print(f"[{qid}] already done — skipping (use --force to overwrite)", flush=True)
        return json.loads(out_path.read_text())

    index_heading = BASELINE_TO_INDEX.get(question["topic"])
    if not index_heading:
        print(f"[{qid}] FATAL: topic '{question['topic']}' not in BASELINE_TO_INDEX map", flush=True)
        sys.exit(2)
    source_paths = topic_to_sources.get(index_heading, [])
    if not source_paths:
        print(f"[{qid}] FATAL: no sources for INDEX heading '{index_heading}'", flush=True)
        sys.exit(2)

    sources = load_sources(source_paths)
    index_block = get_index_block(index_text, index_heading)
    prompt = build_prompt(question, index_block, sources)
    prompt_chars = len(prompt)

    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()
    print(f"[{qid}] tier={question['tier']} topic='{question['topic']}' "
          f"sources={len(source_paths)} prompt_chars={prompt_chars} "
          f"starting at {started_iso}", flush=True)

    try:
        resp = call_ollama(model, prompt)
        answer = resp.get("response", "")
        status = "ok"
    except Exception as e:
        answer = f"ERROR: {e}"
        resp = {}
        status = "error"

    latency = time.time() - started
    cites = extract_citations(answer)
    quotes = extract_quotes(answer)
    n_quotes_loose = len(extract_quotes_loose(answer))

    record = {
        "id": qid, "tier": question["tier"], "topic": question["topic"],
        "index_heading": index_heading, "source_paths": source_paths,
        "q": question["q"], "answer_text": answer,
        "citations": cites, "quotes": quotes,
        "n_quotes": len(quotes), "n_quotes_loose": n_quotes_loose,
        "latency_seconds": round(latency, 1),
        "ollama_status": status,
        "prompt_chars": prompt_chars,
        "prompt_eval_count": resp.get("prompt_eval_count"),
        "eval_count": resp.get("eval_count"),
        "prompt_eval_duration_s": round((resp.get("prompt_eval_duration") or 0) / 1e9, 2),
        "eval_duration_s": round((resp.get("eval_duration") or 0) / 1e9, 2),
        "started_at": started_iso,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
    }
    out_path.write_text(json.dumps(record, indent=2))
    print(f"[{qid}] done in {latency:.0f}s, "
          f"{len(cites)} citations, {len(quotes)} strict / {n_quotes_loose} loose quotes, "
          f"in={record['prompt_eval_count']}tok out={record['eval_count']}tok", flush=True)
    return record


def filter_questions(questions: list[dict], tiers: list[int]) -> list[dict]:
    return [q for q in questions if q["tier"] in tiers]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--stage", type=int, choices=range(1, 6), help="Curriculum stage 1-5")
    g.add_argument("--tiers", type=str, help="Comma-separated tier numbers, e.g. '5' or '5,2'")
    p.add_argument("--date", type=str, default=None, help="Run date YYYY-MM-DD (default: today)")
    p.add_argument("--model", type=str, default=MODEL_DEFAULT)
    p.add_argument("--force", action="store_true", help="Re-run questions even if output exists")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    tiers = TIER_CURRICULUM[args.stage] if args.stage else [int(x) for x in args.tiers.split(",")]

    index_text = INDEX_PATH.read_text(encoding="utf-8")
    topic_to_sources = parse_index_topics(index_text)
    data = json.loads(QUESTIONS.read_text())

    missing = [q["topic"] for q in data["questions"]
               if q["topic"] not in BASELINE_TO_INDEX
               or BASELINE_TO_INDEX[q["topic"]] not in topic_to_sources]
    if missing:
        print(f"FATAL: topics not resolvable to INDEX: {sorted(set(missing))}", file=sys.stderr)
        return 2

    today = args.date or datetime.now().strftime("%Y-%m-%d")
    out_dir = OUT_BASE / today
    out_dir.mkdir(parents=True, exist_ok=True)

    questions = filter_questions(data["questions"], tiers)
    print(f"Curriculum: tiers={tiers} | {len(questions)} questions | model={args.model} | date={today}",
          flush=True)

    summary_path = out_dir / "_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
    else:
        summary = {"date": today, "model": args.model, "tiers": tiers, "results": []}

    seen_ids = {r["id"] for r in summary.get("results", [])}
    for q in questions:
        rec = run_one(q, topic_to_sources, index_text, args.model, out_dir, force=args.force)
        if rec["id"] not in seen_ids:
            summary["results"].append({
                "id": rec["id"], "tier": rec["tier"],
                "latency_seconds": rec["latency_seconds"],
                "n_citations": len(rec["citations"]),
                "n_quotes": rec["n_quotes"],
                "n_quotes_loose": rec["n_quotes_loose"],
                "status": rec["ollama_status"],
            })

    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"DONE: tiers={tiers} written to {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
