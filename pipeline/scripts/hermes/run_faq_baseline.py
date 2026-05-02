#!/usr/bin/env python3
"""Run all 30 baseline FAQ questions through Hermes on Contabo.

Reads:  ~/askanka.com/docs/faq/baseline_questions.json
Writes: ~/.hermes/data/faq_runs/<YYYY-MM-DD>/<question_id>.json
        + ~/.hermes/data/faq_runs/<YYYY-MM-DD>/_summary.json

Each per-question JSON has: id, tier, topic, q, answer_text, citations,
quotes, latency_seconds, hermes_exit_code, started_at, ended_at.
"""
from __future__ import annotations
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "askanka.com"
QUESTIONS = REPO / "docs" / "faq" / "baseline_questions.json"
HERMES = Path.home() / ".local" / "bin" / "hermes"
OUT_BASE = Path.home() / ".hermes" / "data" / "faq_runs"

sys.path.insert(0, str(REPO / "pipeline" / "scripts" / "hermes"))
from parse_citations import extract_citations, extract_quotes  # noqa: E402


def run_one(question: dict, out_dir: Path) -> dict:
    qid = question["id"]
    out_path = out_dir / f"{qid}.json"
    if out_path.exists():
        print(f"[{qid}] already done — skipping")
        return json.loads(out_path.read_text())

    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()
    print(f"[{qid}] tier={question['tier']} starting at {started_iso}")

    try:
        proc = subprocess.run(
            [str(HERMES), "-z", question["q"], "--skills", "system-faq"],
            capture_output=True, text=True, timeout=900,
        )
        exit_code = proc.returncode
        answer = (proc.stdout or "") + (proc.stderr if proc.returncode != 0 else "")
    except subprocess.TimeoutExpired:
        exit_code = -1
        answer = "TIMEOUT after 900s"

    latency = time.time() - started
    cites = extract_citations(answer)
    quotes = extract_quotes(answer)

    record = {
        "id": qid,
        "tier": question["tier"],
        "topic": question["topic"],
        "q": question["q"],
        "answer_text": answer,
        "citations": cites,
        "quotes": quotes,
        "n_quotes": len(quotes),
        "latency_seconds": round(latency, 1),
        "hermes_exit_code": exit_code,
        "started_at": started_iso,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(record, indent=2))
    print(f"[{qid}] done in {latency:.0f}s, {len(cites)} citations, {len(quotes)} quotes")
    return record


def main() -> int:
    data = json.loads(QUESTIONS.read_text())
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = OUT_BASE / today
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {"date": today, "results": []}
    for q in data["questions"]:
        rec = run_one(q, out_dir)
        summary["results"].append({
            "id": rec["id"], "tier": rec["tier"],
            "latency_seconds": rec["latency_seconds"],
            "n_citations": len(rec["citations"]),
            "n_quotes": rec["n_quotes"],
            "exit_code": rec["hermes_exit_code"],
        })

    (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"DONE: 30 questions written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
