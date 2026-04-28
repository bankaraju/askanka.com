"""Pytest version of the smoke test. Skipped automatically when the
ollama tunnel is not open.

Lives in the test suite so CI can validate the contract during dev
sessions when the engineer has the tunnel open. CI without the tunnel
sees these as SKIPPED, which is correct -- the test asserts a remote
service is up, not local code correctness.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 0)
"""
from __future__ import annotations

import socket

import pytest
import requests


def _tunnel_open() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 11434))
        return True
    except OSError:
        return False
    finally:
        s.close()


pytestmark = pytest.mark.skipif(
    not _tunnel_open(),
    reason=(
        "ollama not reachable on 127.0.0.1:11434 "
        "(open SSH tunnel to Contabo to run)"
    ),
)


def test_ollama_pong():
    r = requests.post(
        "http://127.0.0.1:11434/v1/chat/completions",
        json={
            "model": "gemma4:26b-a4b-q4_k_m",
            "messages": [
                {"role": "user", "content": "Reply with exactly: PONG"},
            ],
            "temperature": 0.0,
            "max_tokens": 8,
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    text = r.json()["choices"][0]["message"]["content"].strip().upper()
    assert "PONG" in text
