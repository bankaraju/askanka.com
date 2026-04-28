"""Local-side smoke test for Ollama Gemma 4. Tunnels to Contabo via SSH.

Usage:
    # In a separate terminal, open the tunnel:
    ssh -L 11434:127.0.0.1:11434 -N -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107

    # Then run:
    python pipeline/scripts/gemma4_smoke_test.py

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 0)
"""
from __future__ import annotations

import sys
import time

import requests

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "gemma4:26b-a4b-q4_k_m"


def main() -> int:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Reply with exactly the single word: PONG"},
        ],
        "temperature": 0.0,
        "max_tokens": 8,
    }
    t0 = time.time()
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    except requests.exceptions.ConnectionError:
        print(
            "FAIL: cannot reach 127.0.0.1:11434 -- is the SSH tunnel open?",
            file=sys.stderr,
        )
        return 2
    elapsed = time.time() - t0
    if r.status_code != 200:
        print(f"FAIL: HTTP {r.status_code}: {r.text[:500]}", file=sys.stderr)
        return 3
    body = r.json()
    text = body["choices"][0]["message"]["content"].strip()
    print(f"Latency: {elapsed:.1f}s  Response: {text!r}")
    if "PONG" not in text.upper():
        print("FAIL: did not contain PONG", file=sys.stderr)
        return 4
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
