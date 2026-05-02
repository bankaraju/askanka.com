#!/usr/bin/env python3
"""Run all 30 baseline FAQ questions through Ollama directly (bypasses Hermes).

Hermes Agent's 64K-minimum overhead made even single-pass calls take 15+ min/Q
with no output on Contabo CPU. Calling Ollama /api/generate directly with the
INDEX inlined avoids that overhead entirely; KV cache stays small, decode runs
at the model's intrinsic ~1.1 tok/sec speed.

Reads:  ~/askanka.com/docs/faq/INDEX.md
        ~/askanka.com/docs/faq/baseline_questions.json
Writes: ~/.hermes/data/faq_runs/<YYYY-MM-DD>/<question_id>.json
        + ~/.hermes/data/faq_runs/<YYYY-MM-DD>/_summary.json

Each per-question JSON has: id, tier, topic, q, answer_text, citations,
quotes, latency_seconds, ollama_status, started_at, ended_at.
"""
from __future__ import annotations
import json
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
MODEL = "gemma4-8k"

sys.path.insert(0, str(REPO / "pipeline" / "scripts" / "hermes"))
from parse_citations import extract_citations, extract_quotes  # noqa: E402

SYSTEM = """You answer ONLY from the askanka.com FAQ INDEX shown below. Strict rules:

1. Quote at least one verbatim phrase from the matching INDEX entry. Format each quote as:
   > "exact phrase from INDEX"
   — docs/path/to/source.md   (use a path from that INDEX entry's Sources)
2. End EVERY answer with a 'Sources:' line followed by bullet points listing each cited path:
   Sources:
   - docs/path/one.md
   - docs/path/two.md
3. Do NOT invent facts, model names, p-values, dates, or numbers not present in INDEX.
4. Do NOT use LaTeX, markdown headers, or bold/italics — plain prose + quote blocks + Sources only.
5. If the question's topic is not in INDEX, reply 'NOT_IN_INDEX' and stop.
"""


def build_prompt(index_text: str, question: str) -> str:
    return (
        f"{SYSTEM}\n\n"
        f"INDEX:\n{index_text}\n\n"
        f"QUESTION: {question}\n\n"
        f"Answer:"
    )


def call_ollama(prompt: str, num_predict: int = 1000, timeout_s: int = 1800) -> dict:
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps({
            "model": MODEL,
            "prompt": prompt,
            "think": False,
            "stream": False,
            "options": {"num_predict": num_predict, "temperature": 0.0},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())


def run_one(question: dict, index_text: str, out_dir: Path) -> dict:
    qid = question["id"]
    out_path = out_dir / f"{qid}.json"
    if out_path.exists():
        print(f"[{qid}] already done — skipping")
        return json.loads(out_path.read_text())

    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()
    print(f"[{qid}] tier={question['tier']} starting at {started_iso}", flush=True)

    prompt = build_prompt(index_text, question["q"])
    try:
        resp = call_ollama(prompt)
        answer = resp.get("response", "")
        status = "ok"
    except Exception as e:
        answer = f"ERROR: {e}"
        resp = {}
        status = "error"

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
        "ollama_status": status,
        "prompt_eval_count": resp.get("prompt_eval_count"),
        "eval_count": resp.get("eval_count"),
        "prompt_eval_duration_s": round((resp.get("prompt_eval_duration") or 0) / 1e9, 2),
        "eval_duration_s": round((resp.get("eval_duration") or 0) / 1e9, 2),
        "started_at": started_iso,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(record, indent=2))
    print(
        f"[{qid}] done in {latency:.0f}s, "
        f"{len(cites)} citations, {len(quotes)} quotes, "
        f"in={record['prompt_eval_count']}tok out={record['eval_count']}tok",
        flush=True,
    )
    return record


def main() -> int:
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    data = json.loads(QUESTIONS.read_text())
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = OUT_BASE / today
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {"date": today, "model": MODEL, "results": []}
    for q in data["questions"]:
        rec = run_one(q, index_text, out_dir)
        summary["results"].append({
            "id": rec["id"], "tier": rec["tier"],
            "latency_seconds": rec["latency_seconds"],
            "n_citations": len(rec["citations"]),
            "n_quotes": rec["n_quotes"],
            "status": rec["ollama_status"],
        })

    (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"DONE: {len(summary['results'])} questions written to {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
