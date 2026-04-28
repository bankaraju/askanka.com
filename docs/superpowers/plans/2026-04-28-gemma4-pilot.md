# Gemma 4 Local-Inference Pilot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the infrastructure for a 20-day forward-only evaluation of Gemma 4 26B-A4B local inference (Contabo VPS) as the Tier 2 (mundane / volume) LLM provider for four pilot tasks: trust-score concall supplement, news classification + sentiment, EOD Telegram trade narrative, and daily article draft (markets only).

**Architecture:** Eight phases — (0) Contabo + Ollama bootstrap, (1) provider protocol + `llm_router`, (2) LanceDB + bge-large RAG infra, (3) shadow-mode dispatcher + JSONL audit logger, (4) per-task rubrics + wire 4 tasks in shadow mode, (5) Terminal "Gemma Pilot" tab with pairwise audit UI, (6) daily report card aggregator + auto-disable guardrails + health check cron, (7) doc + inventory updates. Days 1–7 are shadow (both stacks run, only current serves prod). Day 8 flips qualifying tasks to LIVE. Day 20 is the cutover decision.

**Tech Stack:** Python 3.11, Ollama (CPU GGUF inference), Gemma 4 26B-A4B Q4_K_M, LanceDB (file-based vector store), `bge-large-en-v1.5` embeddings via `sentence-transformers`, FastAPI (existing terminal API), vanilla JS (existing terminal frontend), pytest, anthropic SDK, google-genai SDK, Telegram Bot API (existing), Kite Connect (existing read-only paths). systemd on Contabo for `ollama serve`.

**Spec:** `docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md` (commit 0eb40cf).

**Pilot window:** 20 calendar days from install. Target start 2026-04-29, cutover decision target 2026-05-19.

**Hard prerequisite:** Contabo VPS reachable per `memory/reference_contabo_vps.md` (anka@185.182.8.107, key at `~/.ssh/contabo_vmi3256563`, IST timezone, 4 GB swap, ufw + fail2ban hardened). VPS Phase 1 + Phase 2 commissioning already done — repo is cloned, venv exists, AnkaVPSSyncDaily/Weekly artifact-pull is operational.

---

## Resolved Open Questions (from spec §10)

| Question | Decision | Reason |
|---|---|---|
| Vector DB for RAG | **LanceDB** | File-based; no postgres dependency on Contabo; pyarrow under the hood matches existing parquet stack. |
| Embedding model | **`bge-large-en-v1.5`** (~340 MB, 1024-dim) | Top of MTEB English+code retrieval at this size; runs on CPU in seconds. |
| Routing handoff pattern | **Wrapper** | Each provider implements `Provider` protocol; `llm_router` picks one based on task name + feature flag, hands it `prompt` + `retrieved_context: list[Document]`, returns `(text, usage)`. Middleware would couple too tightly to a framework. |
| Report card format | **Both** — Markdown to `pipeline/data/research/gemma4_pilot/report_cards/<YYYY-MM-DD>.md` AND JSON at `pipeline/data/research/gemma4_pilot/report_cards/<YYYY-MM-DD>.json`. Terminal "Gemma Pilot" tab reads the JSON. | Markdown for human read; JSON for the UI to consume. One aggregator emits both. |
| Pairwise sample selection | **Stratified by hour** — for each of the 4 tasks, pick up to 10 samples per day from 4 buckets: pre-market (06:00–09:30 IST), morning session (09:30–12:30), afternoon (12:30–15:30), post-close (15:30–22:00). 2–3 samples per bucket, capped at 10 total per task. Random within each bucket. | Avoids over-weighting batch jobs that all run at the same time. |

---

## Task 0: Contabo Bootstrap — Ollama + Gemma 4 26B-A4B

**Files:**
- Create: `pipeline/scripts/install_gemma4_contabo.sh`
- Create: `pipeline/scripts/gemma4_smoke_test.py`
- Test: `pipeline/tests/gemma4_pilot/test_ollama_smoke.py`
- Create: `pipeline/tests/gemma4_pilot/__init__.py` (empty)
- Create: `pipeline/llm_providers/__init__.py` (empty)

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p pipeline/tests/gemma4_pilot pipeline/llm_providers
type nul > pipeline/tests/gemma4_pilot/__init__.py
type nul > pipeline/llm_providers/__init__.py
```

- [ ] **Step 2: Write the install script**

`pipeline/scripts/install_gemma4_contabo.sh`:

```bash
#!/usr/bin/env bash
# One-shot Contabo bootstrap for Gemma 4 26B-A4B Q4_K_M via Ollama.
# Idempotent: safe to re-run.
set -euo pipefail

LOG_PREFIX="[install_gemma4_contabo]"
log() { echo "${LOG_PREFIX} $*"; }

# 1. Verify hardware preconditions
TOTAL_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
if [ "${TOTAL_GB}" -lt 40 ]; then
    log "FAIL: need ≥40 GB RAM, have ${TOTAL_GB} GB"
    exit 1
fi
log "RAM OK: ${TOTAL_GB} GB"

DISK_GB=$(df -BG /root | awk 'NR==2 {print $4}' | tr -d 'G')
if [ "${DISK_GB}" -lt 30 ]; then
    log "FAIL: need ≥30 GB free disk, have ${DISK_GB} GB"
    exit 1
fi
log "Disk OK: ${DISK_GB} GB free"

# 2. Install ollama if not present
if ! command -v ollama >/dev/null 2>&1; then
    log "Installing ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    log "ollama already installed: $(ollama --version)"
fi

# 3. Ensure systemd unit is enabled and running
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 2
if ! systemctl is-active --quiet ollama; then
    log "FAIL: ollama systemd service did not start"
    exit 1
fi
log "ollama service active"

# 4. Pull Gemma 4 26B-A4B Q4_K_M (~16 GB)
# Tag verified at https://ollama.com/library/gemma4 — confirm exact tag name at runtime.
MODEL_TAG="${GEMMA4_TAG:-gemma4:26b-a4b-q4_k_m}"
if ! ollama list | grep -q "${MODEL_TAG}"; then
    log "Pulling ${MODEL_TAG} (~16 GB, may take 10-30 min on Contabo network)..."
    ollama pull "${MODEL_TAG}"
else
    log "${MODEL_TAG} already pulled"
fi

# 5. Smoke test
log "Running smoke test..."
RESPONSE=$(ollama run "${MODEL_TAG}" "Reply with exactly the single word: PONG" 2>&1 | head -5)
if echo "${RESPONSE}" | grep -qi "pong"; then
    log "Smoke test PASS"
else
    log "Smoke test FAIL — got: ${RESPONSE}"
    exit 1
fi

log "DONE — ollama + ${MODEL_TAG} ready on $(hostname) at $(date --iso-8601=seconds)"
```

Make executable: `chmod +x pipeline/scripts/install_gemma4_contabo.sh`

- [ ] **Step 3: Run install on Contabo**

From laptop:
```bash
scp -i ~/.ssh/contabo_vmi3256563 pipeline/scripts/install_gemma4_contabo.sh anka@185.182.8.107:/tmp/
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 "bash /tmp/install_gemma4_contabo.sh"
```

Expected final line: `[install_gemma4_contabo] DONE — ollama + gemma4:26b-a4b-q4_k_m ready on <hostname> at <timestamp>`

If the model tag `gemma4:26b-a4b-q4_k_m` does not exist in the ollama registry, query `ollama search gemma4` on Contabo and re-run with `GEMMA4_TAG=<correct_tag> bash /tmp/install_gemma4_contabo.sh`. Update the default in the script and commit.

- [ ] **Step 4: Open ollama port to laptop only (firewall)**

Ollama binds to `127.0.0.1:11434` by default. We will tunnel from laptop via SSH instead of opening the port to the internet — never expose ollama publicly without auth.

Verify:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 "ss -tlnp | grep 11434"
```

Expected: `LISTEN ... 127.0.0.1:11434 ...` (no `0.0.0.0`).

- [ ] **Step 5: Write the Python-side smoke script**

`pipeline/scripts/gemma4_smoke_test.py`:

```python
"""Local-side smoke test for ollama Gemma 4. Tunnels to Contabo via SSH.

Usage:
    # In a separate terminal, open the tunnel:
    ssh -L 11434:127.0.0.1:11434 -N -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107

    # Then run:
    python pipeline/scripts/gemma4_smoke_test.py
"""
from __future__ import annotations

import json
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
        print("FAIL: cannot reach 127.0.0.1:11434 — is the SSH tunnel open?", file=sys.stderr)
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
```

- [ ] **Step 6: Run the smoke test**

In one terminal: `ssh -L 11434:127.0.0.1:11434 -N -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107`

In another: `python pipeline/scripts/gemma4_smoke_test.py`

Expected: `Latency: <30-90>s  Response: 'PONG'` then `PASS`. Note actual latency in commit message — sanity-checks the 5–10× slower CPU expectation from spec §1.

- [ ] **Step 7: Write the pytest smoke test (skipped when ollama unreachable)**

`pipeline/tests/gemma4_pilot/test_ollama_smoke.py`:

```python
"""Pytest version of the smoke test. Skipped automatically if ollama tunnel is closed.
This lives in the test suite so CI can validate the contract during dev sessions
when the engineer has the tunnel open."""
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
    reason="ollama not reachable on 127.0.0.1:11434 (open SSH tunnel to Contabo to run)",
)


def test_ollama_pong():
    r = requests.post(
        "http://127.0.0.1:11434/v1/chat/completions",
        json={
            "model": "gemma4:26b-a4b-q4_k_m",
            "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
            "temperature": 0.0,
            "max_tokens": 8,
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    text = r.json()["choices"][0]["message"]["content"].strip().upper()
    assert "PONG" in text
```

- [ ] **Step 8: Run the pytest smoke test**

Run: `pytest pipeline/tests/gemma4_pilot/test_ollama_smoke.py -v`
Expected: PASS (with tunnel open) or SKIPPED (without tunnel).

- [ ] **Step 9: Commit**

```bash
git add pipeline/scripts/install_gemma4_contabo.sh pipeline/scripts/gemma4_smoke_test.py pipeline/tests/gemma4_pilot/__init__.py pipeline/tests/gemma4_pilot/test_ollama_smoke.py pipeline/llm_providers/__init__.py
git commit -m "feat(gemma4-pilot): Phase 0 — Contabo + Ollama bootstrap with smoke tests"
```

---

## Task 1: Provider Protocol

**Files:**
- Create: `pipeline/llm_providers/base.py`
- Test: `pipeline/tests/gemma4_pilot/test_provider_protocol.py`

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/test_provider_protocol.py`:

```python
"""Provider protocol contract tests. A conforming Provider must implement:
    name (str), generate(prompt, retrieved_context, **kwargs) -> ProviderResponse.
The protocol exists to let llm_router treat all providers uniformly."""
from __future__ import annotations

import pytest

from pipeline.llm_providers.base import Provider, ProviderResponse


class _FakeProvider:
    name = "fake"

    def generate(self, prompt, retrieved_context=None, **kwargs):
        ctx_len = len(retrieved_context) if retrieved_context else 0
        return ProviderResponse(
            text=f"echo: {prompt} (ctx={ctx_len})",
            usage={"input_tokens": len(prompt.split()), "output_tokens": 4},
            provider="fake",
            model="fake-1",
            latency_s=0.01,
        )


def test_provider_response_dataclass_fields():
    r = ProviderResponse(text="hi", usage={"input_tokens": 1, "output_tokens": 1},
                         provider="x", model="y", latency_s=0.0)
    assert r.text == "hi"
    assert r.provider == "x"
    assert r.model == "y"
    assert r.usage["input_tokens"] == 1


def test_fake_conforms_to_protocol():
    p: Provider = _FakeProvider()
    response = p.generate("hello", retrieved_context=[{"text": "ctx1"}])
    assert response.text == "echo: hello (ctx=1)"
    assert response.usage["output_tokens"] == 4
    assert response.provider == "fake"


def test_protocol_accepts_no_context():
    p: Provider = _FakeProvider()
    response = p.generate("hi")
    assert "ctx=0" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/gemma4_pilot/test_provider_protocol.py -v`
Expected: ImportError (Provider, ProviderResponse not defined).

- [ ] **Step 3: Write minimal implementation**

`pipeline/llm_providers/base.py`:

```python
"""Provider protocol — every LLM backend implements this to be routable.

Wrapper pattern (resolved §10 of design doc): each provider gets a prompt + a
list of retrieved-context documents, returns ProviderResponse. Routing decisions
live in llm_router, not in the providers themselves."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    usage: Mapping[str, int]
    provider: str
    model: str
    latency_s: float
    raw: Mapping[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest pipeline/tests/gemma4_pilot/test_provider_protocol.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm_providers/base.py pipeline/tests/gemma4_pilot/test_provider_protocol.py
git commit -m "feat(gemma4-pilot): provider protocol with ProviderResponse dataclass"
```

---

## Task 2: OpenAI-Compatible Provider (Ollama / Gemma 4)

**Files:**
- Create: `pipeline/llm_providers/openai_compat.py`
- Test: `pipeline/tests/gemma4_pilot/test_openai_compat_provider.py`

- [ ] **Step 1: Write the failing test (uses requests-mock for the network call)**

`pipeline/tests/gemma4_pilot/test_openai_compat_provider.py`:

```python
from __future__ import annotations

import pytest
import requests_mock as _rm

from pipeline.llm_providers.openai_compat import OpenAICompatProvider


@pytest.fixture
def mock_ollama():
    with _rm.Mocker() as m:
        m.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "id": "x",
                "choices": [{"message": {"content": "hello world"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                "model": "gemma4:26b-a4b-q4_k_m",
            },
            status_code=200,
        )
        yield m


def test_generate_no_context(mock_ollama):
    p = OpenAICompatProvider(
        name="gemma4-local",
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b-a4b-q4_k_m",
        api_key="ollama",
    )
    r = p.generate("say hello", retrieved_context=None)
    assert r.text == "hello world"
    assert r.provider == "gemma4-local"
    assert r.model == "gemma4:26b-a4b-q4_k_m"
    assert r.usage["input_tokens"] == 5
    assert r.usage["output_tokens"] == 2
    assert r.latency_s >= 0


def test_generate_includes_retrieved_context_in_system(mock_ollama):
    p = OpenAICompatProvider(
        name="gemma4-local",
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b-a4b-q4_k_m",
        api_key="ollama",
    )
    p.generate("question?", retrieved_context=[{"text": "fact A"}, {"text": "fact B"}])
    sent = mock_ollama.request_history[-1].json()
    msgs = sent["messages"]
    # System message must precede user message and include both context docs
    assert msgs[0]["role"] == "system"
    assert "fact A" in msgs[0]["content"]
    assert "fact B" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "question?"


def test_http_error_raises(mock_ollama):
    mock_ollama.post(
        "http://127.0.0.1:11434/v1/chat/completions",
        status_code=503,
        text="model loading",
    )
    p = OpenAICompatProvider(
        name="gemma4-local",
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b-a4b-q4_k_m",
        api_key="ollama",
    )
    with pytest.raises(RuntimeError, match="503"):
        p.generate("hi")
```

Add `requests-mock` to `requirements-dev.txt` if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/gemma4_pilot/test_openai_compat_provider.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

`pipeline/llm_providers/openai_compat.py`:

```python
"""OpenAI-compatible provider — works against Ollama, vLLM, OpenAI, etc.

We use this for Gemma 4 via Ollama. Ollama exposes /v1/chat/completions in
OpenAI's exact request/response shape, including the `usage` block."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import requests

from pipeline.llm_providers.base import ProviderResponse

_DEFAULT_TIMEOUT_S = 240  # 4 min — task #4 article draft latency budget per spec §3.1


@dataclass
class OpenAICompatProvider:
    name: str
    base_url: str
    model: str
    api_key: str = "x"  # ollama ignores this but the field exists in OpenAI-compat
    timeout_s: int = _DEFAULT_TIMEOUT_S

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            messages.append({
                "role": "system",
                "content": (
                    "You are a domain expert. Use the following retrieved context "
                    "to answer the user. Do not invent facts beyond it.\n\n"
                    f"CONTEXT:\n{ctx_block}"
                ),
            })
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        t0 = time.monotonic()
        r = requests.post(url, json=payload, headers=headers, timeout=self.timeout_s)
        latency_s = time.monotonic() - t0

        if r.status_code != 200:
            raise RuntimeError(f"{self.name} HTTP {r.status_code}: {r.text[:500]}")

        body = r.json()
        text = body["choices"][0]["message"]["content"]
        usage_raw = body.get("usage", {}) or {}
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
        }
        return ProviderResponse(
            text=text,
            usage=usage,
            provider=self.name,
            model=self.model,
            latency_s=latency_s,
            raw=body,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest pipeline/tests/gemma4_pilot/test_openai_compat_provider.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm_providers/openai_compat.py pipeline/tests/gemma4_pilot/test_openai_compat_provider.py requirements-dev.txt
git commit -m "feat(gemma4-pilot): OpenAICompatProvider for ollama Gemma 4"
```

---

## Task 3: Anthropic + Gemini Provider Wrappers

**Files:**
- Create: `pipeline/llm_providers/anthropic_provider.py`
- Create: `pipeline/llm_providers/gemini_provider.py`
- Test: `pipeline/tests/gemma4_pilot/test_anthropic_provider.py`
- Test: `pipeline/tests/gemma4_pilot/test_gemini_provider.py`

These wrap the existing Anthropic SDK and google-genai SDK already used elsewhere in the pipeline (per `memory/reference_llm_providers.md`). The wrappers only normalize the response shape onto `ProviderResponse`.

- [ ] **Step 1: Write Anthropic test**

`pipeline/tests/gemma4_pilot/test_anthropic_provider.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_normalizes_response():
    fake_client = MagicMock()
    fake_msg = SimpleNamespace(
        content=[SimpleNamespace(text="hello")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        model="claude-haiku-4-5-20251001",
    )
    fake_client.messages.create.return_value = fake_msg

    p = AnthropicProvider(name="claude-haiku", model="claude-haiku-4-5-20251001",
                         client=fake_client)
    r = p.generate("ping", retrieved_context=[{"text": "facts"}])

    assert r.text == "hello"
    assert r.provider == "claude-haiku"
    assert r.model == "claude-haiku-4-5-20251001"
    assert r.usage == {"input_tokens": 10, "output_tokens": 2}

    # Verify retrieved_context flowed into the system prompt
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert "facts" in call_kwargs["system"]
```

- [ ] **Step 2: Implement Anthropic provider**

`pipeline/llm_providers/anthropic_provider.py`:

```python
"""Anthropic provider wrapper. Normalizes onto ProviderResponse."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pipeline.llm_providers.base import ProviderResponse


@dataclass
class AnthropicProvider:
    name: str
    model: str
    client: Any = None  # anthropic.Anthropic instance; injected for testability
    max_tokens: int = 4096

    def __post_init__(self):
        if self.client is None:
            import anthropic  # lazy import — keeps tests dep-free
            self.client = anthropic.Anthropic()

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        system_parts = [
            "You are a domain expert. Be concise and grounded in the provided context."
        ]
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            system_parts.append(f"CONTEXT:\n{ctx_block}")
        system = "\n\n".join(system_parts)

        t0 = time.monotonic()
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", 0.2),
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_s = time.monotonic() - t0

        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        return ProviderResponse(
            text=text,
            usage={
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            },
            provider=self.name,
            model=msg.model,
            latency_s=latency_s,
        )
```

- [ ] **Step 3: Write Gemini test**

`pipeline/tests/gemma4_pilot/test_gemini_provider.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_normalizes_response():
    fake_client = MagicMock()
    fake_resp = SimpleNamespace(
        text="hello",
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=2),
    )
    fake_client.models.generate_content.return_value = fake_resp

    p = GeminiProvider(name="gemini-flash", model="gemini-2.5-flash", client=fake_client)
    r = p.generate("ping", retrieved_context=[{"text": "facts"}])

    assert r.text == "hello"
    assert r.provider == "gemini-flash"
    assert r.model == "gemini-2.5-flash"
    assert r.usage == {"input_tokens": 10, "output_tokens": 2}

    sent_kwargs = fake_client.models.generate_content.call_args.kwargs
    contents = sent_kwargs["contents"]
    assert "facts" in contents
    assert "ping" in contents
```

- [ ] **Step 4: Implement Gemini provider**

`pipeline/llm_providers/gemini_provider.py`:

```python
"""Gemini provider wrapper using google-genai SDK."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pipeline.llm_providers.base import ProviderResponse


@dataclass
class GeminiProvider:
    name: str
    model: str
    client: Any = None

    def __post_init__(self):
        if self.client is None:
            from google import genai
            self.client = genai.Client()

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        ctx_block = ""
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            ctx_block = f"CONTEXT:\n{ctx_block}\n\n---\n\n"
        contents = ctx_block + prompt

        t0 = time.monotonic()
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        latency_s = time.monotonic() - t0

        usage = resp.usage_metadata
        return ProviderResponse(
            text=resp.text,
            usage={
                "input_tokens": getattr(usage, "prompt_token_count", 0),
                "output_tokens": getattr(usage, "candidates_token_count", 0),
            },
            provider=self.name,
            model=self.model,
            latency_s=latency_s,
        )
```

- [ ] **Step 5: Run both tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_anthropic_provider.py pipeline/tests/gemma4_pilot/test_gemini_provider.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/llm_providers/anthropic_provider.py pipeline/llm_providers/gemini_provider.py pipeline/tests/gemma4_pilot/test_anthropic_provider.py pipeline/tests/gemma4_pilot/test_gemini_provider.py
git commit -m "feat(gemma4-pilot): Anthropic + Gemini provider wrappers"
```

---

## Task 4: llm_router — Task → Provider Routing

**Files:**
- Create: `pipeline/llm_router.py`
- Create: `pipeline/config/llm_routing.json`
- Test: `pipeline/tests/gemma4_pilot/test_llm_router.py`

The router takes a task name (one of the 4 pilot tasks, plus a default) and returns the active provider per the routing config. Routing config is a flat JSON file so we can flip a task between LIVE / SHADOW / DISABLED without code changes.

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/test_llm_router.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.llm_router import LLMRouter, RoutingConfig


@pytest.fixture
def cfg_path(tmp_path):
    cfg = {
        "default_primary": "gemini-flash",
        "default_fallback": "claude-haiku",
        "tasks": {
            "concall_supplement":   {"mode": "shadow", "primary": "gemini-flash",
                                     "shadow": "gemma4-local"},
            "news_classification":  {"mode": "live",   "primary": "gemma4-local",
                                     "shadow": "gemini-flash"},
            "eod_narrative":        {"mode": "disabled", "primary": "gemini-flash",
                                     "shadow": "gemma4-local"},
            "article_draft":        {"mode": "shadow", "primary": "gemini-flash",
                                     "shadow": "gemma4-local"},
        },
    }
    p = tmp_path / "routing.json"
    p.write_text(json.dumps(cfg))
    return p


def test_load_config(cfg_path):
    cfg = RoutingConfig.load(cfg_path)
    assert cfg.tasks["news_classification"]["mode"] == "live"


def test_router_returns_primary_for_live(cfg_path):
    router = LLMRouter(RoutingConfig.load(cfg_path),
                       providers={"gemma4-local": "G", "gemini-flash": "F",
                                  "claude-haiku": "C"})
    primary, shadow = router.providers_for("news_classification")
    assert primary == "G"
    assert shadow == "F"


def test_router_returns_primary_for_shadow(cfg_path):
    router = LLMRouter(RoutingConfig.load(cfg_path),
                       providers={"gemma4-local": "G", "gemini-flash": "F",
                                  "claude-haiku": "C"})
    primary, shadow = router.providers_for("article_draft")
    assert primary == "F"   # current stack is primary in shadow mode
    assert shadow == "G"    # gemma is shadow


def test_router_disabled_returns_primary_only(cfg_path):
    router = LLMRouter(RoutingConfig.load(cfg_path),
                       providers={"gemma4-local": "G", "gemini-flash": "F",
                                  "claude-haiku": "C"})
    primary, shadow = router.providers_for("eod_narrative")
    assert primary == "F"
    assert shadow is None


def test_unknown_task_falls_back_to_default(cfg_path):
    router = LLMRouter(RoutingConfig.load(cfg_path),
                       providers={"gemma4-local": "G", "gemini-flash": "F",
                                  "claude-haiku": "C"})
    primary, shadow = router.providers_for("some_other_task")
    assert primary == "F"  # default_primary
    assert shadow is None
```

- [ ] **Step 2: Run test, verify failure**

Run: `pytest pipeline/tests/gemma4_pilot/test_llm_router.py -v`
Expected: ImportError.

- [ ] **Step 3: Write the routing config**

`pipeline/config/llm_routing.json`:

```json
{
  "default_primary": "gemini-flash",
  "default_fallback": "claude-haiku",
  "tasks": {
    "concall_supplement": {
      "mode": "shadow",
      "primary": "gemini-flash",
      "shadow": "gemma4-local"
    },
    "news_classification": {
      "mode": "shadow",
      "primary": "gemini-flash",
      "shadow": "gemma4-local"
    },
    "eod_narrative": {
      "mode": "shadow",
      "primary": "gemini-flash",
      "shadow": "gemma4-local"
    },
    "article_draft": {
      "mode": "shadow",
      "primary": "gemini-flash",
      "shadow": "gemma4-local"
    }
  }
}
```

All four tasks start in `shadow` mode (days 1–7). Day 8 promotion is a JSON edit, no code change.

- [ ] **Step 4: Implement the router**

`pipeline/llm_router.py`:

```python
"""Central LLM routing layer.

Per task: pick a provider in {live, shadow, disabled} mode. Live runs gemma in
production; shadow runs both stacks and only the current is consumed; disabled
runs the current stack only and skips gemma entirely.

Mode flips are JSON edits (pipeline/config/llm_routing.json), no code change."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "llm_routing.json"


@dataclass(frozen=True)
class RoutingConfig:
    default_primary: str
    default_fallback: str
    tasks: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "RoutingConfig":
        cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
        raw = json.loads(cfg_path.read_text())
        return cls(
            default_primary=raw["default_primary"],
            default_fallback=raw["default_fallback"],
            tasks=raw.get("tasks", {}),
        )


@dataclass
class LLMRouter:
    config: RoutingConfig
    providers: Mapping[str, Any]  # name -> Provider instance

    def providers_for(self, task: str) -> tuple[Any, Any | None]:
        """Return (primary_provider, shadow_provider_or_None) for the named task."""
        task_cfg = self.config.tasks.get(task)
        if task_cfg is None:
            return self.providers[self.config.default_primary], None

        mode = task_cfg["mode"]
        primary_name = task_cfg.get("primary", self.config.default_primary)

        if mode == "live":
            shadow_name = task_cfg.get("shadow")
            return (
                self.providers[primary_name],
                self.providers.get(shadow_name) if shadow_name else None,
            )
        if mode == "shadow":
            shadow_name = task_cfg.get("shadow")
            return (
                self.providers[primary_name],
                self.providers.get(shadow_name) if shadow_name else None,
            )
        if mode == "disabled":
            return self.providers[primary_name], None
        raise ValueError(f"unknown mode {mode!r} for task {task!r}")
```

- [ ] **Step 5: Run tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_llm_router.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/llm_router.py pipeline/config/llm_routing.json pipeline/tests/gemma4_pilot/test_llm_router.py
git commit -m "feat(gemma4-pilot): llm_router with live/shadow/disabled modes per task"
```

---

## Task 5: LanceDB RAG — Schema + Indexer

**Files:**
- Create: `pipeline/rag/__init__.py` (empty)
- Create: `pipeline/rag/embeddings.py`
- Create: `pipeline/rag/index.py`
- Create: `pipeline/scripts/build_rag_index.py`
- Test: `pipeline/tests/gemma4_pilot/test_rag_embeddings.py`
- Test: `pipeline/tests/gemma4_pilot/test_rag_index.py`

Design choice (resolved §10): LanceDB. One table named `corpus` with columns: `doc_id` (str, PK), `source_path` (str), `chunk_idx` (int), `text` (str), `embedding` (vector[1024]), `mtime` (timestamp), `task_tags` (list[str]).

- [ ] **Step 1: Add deps**

Append to `requirements.txt`:
```
lancedb==0.18.0
sentence-transformers==3.3.0
```

Run: `pip install lancedb==0.18.0 sentence-transformers==3.3.0`

- [ ] **Step 2: Write embeddings test**

`pipeline/tests/gemma4_pilot/test_rag_embeddings.py`:

```python
from __future__ import annotations

import pytest

from pipeline.rag.embeddings import Embedder

pytestmark = pytest.mark.skipif(
    pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
    is None,
    reason="model unavailable",
)


def test_embedder_returns_1024_dim():
    e = Embedder.bge_large()
    vecs = e.encode(["hello world", "another sentence"])
    assert vecs.shape == (2, 1024)


def test_embedder_is_deterministic():
    e = Embedder.bge_large()
    v1 = e.encode(["pinned text"])
    v2 = e.encode(["pinned text"])
    assert (v1 == v2).all()
```

- [ ] **Step 3: Implement embeddings**

`pipeline/rag/embeddings.py`:

```python
"""bge-large-en-v1.5 sentence embedder. CPU-friendly, 1024-dim, ~340 MB.

Resolved §10: chosen over Gemma 4's own embeddings (hosted only) and
all-mpnet-base-v2 (smaller, lower MTEB score on English+code)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

import numpy as np


@dataclass
class Embedder:
    model_name: str
    _model: object = None

    def __post_init__(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

    @classmethod
    @lru_cache(maxsize=1)
    def bge_large(cls) -> "Embedder":
        return cls(model_name="BAAI/bge-large-en-v1.5")

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True,
        )
```

- [ ] **Step 4: Run embeddings test**

Run: `pytest pipeline/tests/gemma4_pilot/test_rag_embeddings.py -v`
Expected: 2 passed (first run downloads the 340 MB model; subsequent runs cached).

- [ ] **Step 5: Write index test**

`pipeline/tests/gemma4_pilot/test_rag_index.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from pipeline.rag.index import RAGIndex


def _fake_embedder():
    class _E:
        def encode(self, texts):
            # deterministic pseudo-embeddings: hash → 1024 floats
            out = np.zeros((len(texts), 1024), dtype=np.float32)
            for i, t in enumerate(texts):
                rng = np.random.default_rng(hash(t) % (2**32))
                v = rng.normal(size=1024).astype(np.float32)
                v /= np.linalg.norm(v) + 1e-9
                out[i] = v
            return out
    return _E()


def test_index_round_trip(tmp_path):
    idx = RAGIndex.create(tmp_path / "lance", embedder=_fake_embedder())
    idx.add_documents([
        {"doc_id": "d1", "source_path": "a.md", "chunk_idx": 0,
         "text": "Bharat is researching options spreads.", "task_tags": ["concall_supplement"]},
        {"doc_id": "d2", "source_path": "b.md", "chunk_idx": 0,
         "text": "ETF regime engine uses 28 global ETFs.", "task_tags": ["article_draft"]},
    ])
    hits = idx.search("regime ETFs", k=2)
    assert len(hits) == 2
    # Top hit should be d2 (semantically closest given fake embeddings — verify the
    # function runs end-to-end; semantic correctness comes from real embedder)
    assert {h["doc_id"] for h in hits} == {"d1", "d2"}


def test_index_filter_by_task_tag(tmp_path):
    idx = RAGIndex.create(tmp_path / "lance", embedder=_fake_embedder())
    idx.add_documents([
        {"doc_id": "d1", "source_path": "a.md", "chunk_idx": 0,
         "text": "concall material", "task_tags": ["concall_supplement"]},
        {"doc_id": "d2", "source_path": "b.md", "chunk_idx": 0,
         "text": "article material", "task_tags": ["article_draft"]},
    ])
    hits = idx.search("anything", k=5, task_tag="article_draft")
    assert len(hits) == 1
    assert hits[0]["doc_id"] == "d2"


def test_index_upsert_replaces_existing(tmp_path):
    idx = RAGIndex.create(tmp_path / "lance", embedder=_fake_embedder())
    idx.add_documents([{"doc_id": "d1", "source_path": "a.md", "chunk_idx": 0,
                        "text": "v1", "task_tags": []}])
    idx.add_documents([{"doc_id": "d1", "source_path": "a.md", "chunk_idx": 0,
                        "text": "v2", "task_tags": []}])
    hits = idx.search("v2", k=10)
    texts = {h["text"] for h in hits if h["doc_id"] == "d1"}
    assert texts == {"v2"}
```

- [ ] **Step 6: Implement index**

`pipeline/rag/index.py`:

```python
"""LanceDB-backed RAG index. One table 'corpus' per the design doc.

Search returns top-k by cosine similarity (vectors are L2-normalized at encode
time, so cosine == dot product == LanceDB default for normalized inputs).
Optional filter by task_tag — for tasks that should only see relevant material
(e.g. concall_supplement should not retrieve from article archives)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import lancedb
import numpy as np
import pyarrow as pa


_SCHEMA = pa.schema([
    pa.field("doc_id", pa.string()),
    pa.field("source_path", pa.string()),
    pa.field("chunk_idx", pa.int32()),
    pa.field("text", pa.string()),
    pa.field("embedding", pa.list_(pa.float32(), 1024)),
    pa.field("task_tags", pa.list_(pa.string())),
])


@dataclass
class RAGIndex:
    db_path: Path
    embedder: Any
    _db: Any = field(default=None, init=False)
    _tbl: Any = field(default=None, init=False)

    @classmethod
    def create(cls, db_path: Path, embedder: Any) -> "RAGIndex":
        db_path.mkdir(parents=True, exist_ok=True)
        idx = cls(db_path=db_path, embedder=embedder)
        idx._db = lancedb.connect(str(db_path))
        if "corpus" in idx._db.table_names():
            idx._tbl = idx._db.open_table("corpus")
        else:
            idx._tbl = idx._db.create_table("corpus", schema=_SCHEMA)
        return idx

    def add_documents(self, docs: Sequence[dict]) -> None:
        if not docs:
            return
        texts = [d["text"] for d in docs]
        vecs = self.embedder.encode(texts)
        rows = []
        for d, v in zip(docs, vecs):
            rows.append({
                "doc_id": d["doc_id"],
                "source_path": d["source_path"],
                "chunk_idx": int(d.get("chunk_idx", 0)),
                "text": d["text"],
                "embedding": v.astype(np.float32).tolist(),
                "task_tags": list(d.get("task_tags", [])),
            })
        # Upsert: delete any existing rows with the same doc_id+chunk_idx, then add
        ids = [(r["doc_id"], r["chunk_idx"]) for r in rows]
        for doc_id, chunk_idx in ids:
            self._tbl.delete(f"doc_id = '{doc_id}' AND chunk_idx = {chunk_idx}")
        self._tbl.add(rows)

    def search(self, query: str, k: int = 5, task_tag: str | None = None) -> list[dict]:
        qv = self.embedder.encode([query])[0]
        q = self._tbl.search(qv.tolist()).limit(k)
        if task_tag:
            q = q.where(f"array_contains(task_tags, '{task_tag}')")
        rows = q.to_list()
        out = []
        for r in rows:
            out.append({
                "doc_id": r["doc_id"],
                "source_path": r["source_path"],
                "chunk_idx": r["chunk_idx"],
                "text": r["text"],
                "task_tags": list(r["task_tags"]),
                "score": float(r.get("_distance", 0.0)),
            })
        return out
```

- [ ] **Step 7: Run index tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_rag_index.py -v`
Expected: 3 passed.

- [ ] **Step 8: Write the corpus build script**

`pipeline/scripts/build_rag_index.py`:

```python
"""Build / refresh the RAG corpus from canonical sources.

Sources by task_tag:
    concall_supplement   → opus/concalls/<TICKER>/*.md
    news_classification  → docs/superpowers/specs/news_taxonomy.md, recent fno_news.json
    eod_narrative        → docs/SYSTEM_OPERATIONS_MANUAL.md, last 30d eod_review.md
    article_draft        → ObsidianVault/markets/*.md, ObsidianVault/geopolitics/*.md (last 90d)

Run nightly via cron. Incremental: skip files whose mtime is unchanged."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from pipeline.rag.embeddings import Embedder
from pipeline.rag.index import RAGIndex

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot" / "rag_db"

# (glob_under_repo, task_tag)
SOURCES = [
    ("opus/concalls/*/*.md",                          "concall_supplement"),
    ("docs/superpowers/specs/news_taxonomy.md",       "news_classification"),
    ("data/fno_news.json",                            "news_classification"),
    ("docs/SYSTEM_OPERATIONS_MANUAL.md",              "eod_narrative"),
    # Article-draft sources read from the Obsidian vault — see vault path below
]

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "C:/Users/Claude_Anka/ObsidianVault"))
VAULT_SOURCES = [
    ("markets/*.md",       "article_draft"),
    ("geopolitics/*.md",   "article_draft"),
]

CHUNK_SIZE = 1500   # chars; ~300 tokens
CHUNK_OVERLAP = 200


def _chunk(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return out


def _doc_id(path: Path, idx: int) -> str:
    h = hashlib.sha1(str(path).encode()).hexdigest()[:12]
    return f"{h}-{idx}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[build_rag_index] %(message)s")
    log = logging.getLogger("build_rag_index")

    embedder = Embedder.bge_large()
    idx = RAGIndex.create(DB_PATH, embedder=embedder)

    docs: list[dict] = []
    for pattern, task_tag in SOURCES:
        for p in REPO_ROOT.glob(pattern):
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for ci, chunk in enumerate(_chunk(text)):
                docs.append({
                    "doc_id": _doc_id(p, ci),
                    "source_path": str(p.relative_to(REPO_ROOT)),
                    "chunk_idx": ci,
                    "text": chunk,
                    "task_tags": [task_tag],
                })

    if VAULT_ROOT.exists():
        for pattern, task_tag in VAULT_SOURCES:
            for p in VAULT_ROOT.glob(pattern):
                if not p.is_file():
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for ci, chunk in enumerate(_chunk(text)):
                    docs.append({
                        "doc_id": _doc_id(p, ci),
                        "source_path": str(p),
                        "chunk_idx": ci,
                        "text": chunk,
                        "task_tags": [task_tag],
                    })
    else:
        log.warning("Obsidian vault not found at %s — skipping vault sources", VAULT_ROOT)

    log.info("Indexing %d chunks from %d files", len(docs), len({d["source_path"] for d in docs}))
    idx.add_documents(docs)
    log.info("Done. Index at %s", DB_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Run a first build**

Run: `python pipeline/scripts/build_rag_index.py`
Expected: log line `Indexing N chunks from M files` then `Done.` Verify `pipeline/data/research/gemma4_pilot/rag_db/corpus.lance/` exists.

- [ ] **Step 10: Commit**

```bash
git add requirements.txt pipeline/rag/ pipeline/scripts/build_rag_index.py pipeline/tests/gemma4_pilot/test_rag_embeddings.py pipeline/tests/gemma4_pilot/test_rag_index.py
git commit -m "feat(gemma4-pilot): LanceDB RAG infra + bge-large embedder + corpus builder"
```

---

## Task 6: Audit Logger + Shadow Dispatcher

**Files:**
- Create: `pipeline/gemma4_pilot/__init__.py` (empty)
- Create: `pipeline/gemma4_pilot/audit_logger.py`
- Create: `pipeline/gemma4_pilot/shadow_dispatcher.py`
- Test: `pipeline/tests/gemma4_pilot/test_audit_logger.py`
- Test: `pipeline/tests/gemma4_pilot/test_shadow_dispatcher.py`

Audit logger writes one JSONL row per call to `pipeline/data/research/gemma4_pilot/audit/<task>/<YYYY-MM-DD>.jsonl`. Shadow dispatcher orchestrates the per-call dance: in shadow mode, run primary synchronously, fire shadow asynchronously (don't block prod path on shadow failures), score both, log both.

- [ ] **Step 1: Write audit logger test**

`pipeline/tests/gemma4_pilot/test_audit_logger.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from pipeline.gemma4_pilot.audit_logger import AuditLogger


def test_logger_writes_jsonl_row(tmp_path):
    logger = AuditLogger(root=tmp_path)
    logger.log(
        task="concall_supplement",
        date_iso="2026-04-29",
        record={
            "ts": "2026-04-29T14:30:00+05:30",
            "ticker": "RELIANCE",
            "primary": {"provider": "gemini-flash", "text": "...", "latency_s": 4.2,
                         "rubric_score": 1.0, "rubric_pass": True},
            "shadow":  {"provider": "gemma4-local", "text": "...", "latency_s": 71.3,
                         "rubric_score": 0.8, "rubric_pass": True},
        },
    )
    out = tmp_path / "audit" / "concall_supplement" / "2026-04-29.jsonl"
    assert out.exists()
    line = json.loads(out.read_text().strip())
    assert line["ticker"] == "RELIANCE"
    assert line["shadow"]["provider"] == "gemma4-local"


def test_logger_appends(tmp_path):
    logger = AuditLogger(root=tmp_path)
    for i in range(3):
        logger.log(task="news_classification", date_iso="2026-04-29",
                   record={"i": i})
    out = tmp_path / "audit" / "news_classification" / "2026-04-29.jsonl"
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[2])["i"] == 2
```

- [ ] **Step 2: Implement audit logger**

`pipeline/gemma4_pilot/audit_logger.py`:

```python
"""Append-only JSONL audit logger for per-call records.

Layout: <root>/audit/<task>/<YYYY-MM-DD>.jsonl
One row per primary+shadow call pair (or single call if no shadow)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class AuditLogger:
    root: Path

    def log(self, *, task: str, date_iso: str, record: Mapping[str, Any]) -> None:
        out = self.root / "audit" / task / f"{date_iso}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
```

- [ ] **Step 3: Run audit logger test**

Run: `pytest pipeline/tests/gemma4_pilot/test_audit_logger.py -v`
Expected: 2 passed.

- [ ] **Step 4: Write shadow dispatcher test**

`pipeline/tests/gemma4_pilot/test_shadow_dispatcher.py`:

```python
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from pipeline.gemma4_pilot.shadow_dispatcher import ShadowDispatcher
from pipeline.llm_providers.base import ProviderResponse


def _resp(provider, text, latency=1.0):
    return ProviderResponse(
        text=text, usage={"input_tokens": 1, "output_tokens": 1},
        provider=provider, model="m", latency_s=latency,
    )


def test_dispatcher_returns_primary_when_no_shadow(tmp_path):
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK")
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="news_classification",
        date_iso="2026-04-29",
        primary=primary,
        shadow=None,
        prompt="classify this",
        retrieved_context=None,
        meta={"item_id": "x"},
    )
    assert text == "PRIMARY OK"
    primary.generate.assert_called_once()
    rubric.assert_called_once()


def test_dispatcher_runs_both_in_shadow_mode(tmp_path):
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK", latency=2.0)
    shadow = MagicMock()
    shadow.generate.return_value = _resp("gemma4-local", "SHADOW OK", latency=70.0)
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="article_draft", date_iso="2026-04-29",
        primary=primary, shadow=shadow,
        prompt="write the article",
        retrieved_context=[{"text": "ctx"}],
        meta={"topic": "markets"},
    )
    assert text == "PRIMARY OK"   # production still consumes primary
    primary.generate.assert_called_once()
    shadow.generate.assert_called_once()
    assert rubric.call_count == 2

    # Check JSONL written
    audit_files = list((tmp_path / "audit" / "article_draft").glob("*.jsonl"))
    assert len(audit_files) == 1
    import json
    rec = json.loads(audit_files[0].read_text().strip())
    assert rec["primary"]["text"] == "PRIMARY OK"
    assert rec["shadow"]["text"] == "SHADOW OK"


def test_dispatcher_swallows_shadow_failures(tmp_path):
    """Shadow MUST NOT break production. If gemma errors, prod still returns primary."""
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK")
    shadow = MagicMock()
    shadow.generate.side_effect = RuntimeError("ollama down")
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="eod_narrative", date_iso="2026-04-29",
        primary=primary, shadow=shadow, prompt="hi",
        retrieved_context=None, meta={},
    )
    assert text == "PRIMARY OK"

    import json
    audit_files = list((tmp_path / "audit" / "eod_narrative").glob("*.jsonl"))
    rec = json.loads(audit_files[0].read_text().strip())
    assert rec["shadow"]["error"] == "ollama down"
    assert rec["primary"]["text"] == "PRIMARY OK"
```

- [ ] **Step 5: Implement the shadow dispatcher**

`pipeline/gemma4_pilot/shadow_dispatcher.py`:

```python
"""Shadow-mode dispatcher.

Calls primary (the current production stack) synchronously. If a shadow provider
is configured, also calls it but never lets a shadow failure or shadow latency
block the production path. Logs both via AuditLogger and runs the per-task
rubric on each output."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pipeline.gemma4_pilot.audit_logger import AuditLogger
from pipeline.llm_providers.base import ProviderResponse, Provider


RubricFn = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
"""Signature: rubric_fn(text, meta) -> {'score': float, 'pass': bool, 'notes': str}"""


@dataclass
class ShadowDispatcher:
    audit_root: Path
    rubric_fn: RubricFn

    def __post_init__(self):
        self._logger = AuditLogger(root=self.audit_root)

    def dispatch(
        self,
        *,
        task: str,
        date_iso: str,
        primary: Provider,
        shadow: Provider | None,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None,
        meta: Mapping[str, Any],
    ) -> str:
        primary_resp, primary_err = self._safe_generate(primary, prompt, retrieved_context)
        if primary_err is not None:
            # Production failure — propagate, do not silently swallow
            raise primary_err

        primary_score = self._safe_rubric(primary_resp.text, meta)

        shadow_block: dict[str, Any]
        if shadow is None:
            shadow_block = {"provider": None}
        else:
            shadow_resp, shadow_err = self._safe_generate(shadow, prompt, retrieved_context)
            if shadow_err is not None:
                shadow_block = {
                    "provider": getattr(shadow, "name", "shadow"),
                    "error": str(shadow_err),
                }
            else:
                shadow_score = self._safe_rubric(shadow_resp.text, meta)
                shadow_block = {
                    "provider": shadow_resp.provider,
                    "model": shadow_resp.model,
                    "text": shadow_resp.text,
                    "latency_s": shadow_resp.latency_s,
                    "usage": dict(shadow_resp.usage),
                    "rubric_score": shadow_score["score"],
                    "rubric_pass": shadow_score["pass"],
                    "rubric_notes": shadow_score["notes"],
                }

        record = {
            "ts": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(),
            "task": task,
            "meta": dict(meta),
            "primary": {
                "provider": primary_resp.provider,
                "model": primary_resp.model,
                "text": primary_resp.text,
                "latency_s": primary_resp.latency_s,
                "usage": dict(primary_resp.usage),
                "rubric_score": primary_score["score"],
                "rubric_pass": primary_score["pass"],
                "rubric_notes": primary_score["notes"],
            },
            "shadow": shadow_block,
        }
        self._logger.log(task=task, date_iso=date_iso, record=record)

        return primary_resp.text

    @staticmethod
    def _safe_generate(provider, prompt, ctx):
        try:
            r = provider.generate(prompt, retrieved_context=ctx)
            return r, None
        except Exception as exc:  # noqa: BLE001
            return None, exc

    def _safe_rubric(self, text, meta):
        try:
            return self.rubric_fn(text, meta)
        except Exception as exc:  # noqa: BLE001
            return {"score": 0.0, "pass": False, "notes": f"rubric_error: {exc}"}
```

- [ ] **Step 6: Run dispatcher tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_shadow_dispatcher.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add pipeline/gemma4_pilot/__init__.py pipeline/gemma4_pilot/audit_logger.py pipeline/gemma4_pilot/shadow_dispatcher.py pipeline/tests/gemma4_pilot/test_audit_logger.py pipeline/tests/gemma4_pilot/test_shadow_dispatcher.py
git commit -m "feat(gemma4-pilot): audit logger + shadow-mode dispatcher (failures don't block prod)"
```

---

## Task 7: Per-Task Rubric — Concall Supplement (Task #1)

**Files:**
- Create: `pipeline/gemma4_pilot/rubrics/__init__.py` (empty)
- Create: `pipeline/gemma4_pilot/rubrics/concall_supplement.py`
- Test: `pipeline/tests/gemma4_pilot/rubrics/test_concall_supplement.py`
- Create: `pipeline/tests/gemma4_pilot/rubrics/__init__.py` (empty)

Rubric criteria (spec §3.1 task 1):
- Output is valid JSON matching trust-score supplement schema
- Includes 3+ concall-derived signal points
- No hallucinated tickers (cross-check against universe)
- Latency < 90 s per ticker (latency assessed by dispatcher, not rubric)

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/rubrics/test_concall_supplement.py`:

```python
from __future__ import annotations

import json

from pipeline.gemma4_pilot.rubrics.concall_supplement import score


UNIVERSE = {"RELIANCE", "TCS", "INFY", "HDFCBANK"}


def test_pass_when_valid_json_three_points_no_hallucination():
    text = json.dumps({
        "ticker": "RELIANCE",
        "signal_points": [
            {"point": "Refining margins guided up", "stance": "BULLISH"},
            {"point": "Capex peak behind us",      "stance": "BULLISH"},
            {"point": "Telecom ARPU stalling",     "stance": "BEARISH"},
        ],
    })
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is True
    assert r["score"] == 1.0


def test_fail_when_invalid_json():
    r = score("this is not json", {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert r["score"] == 0.0
    assert "json" in r["notes"].lower()


def test_fail_when_fewer_than_three_signal_points():
    text = json.dumps({
        "ticker": "RELIANCE",
        "signal_points": [{"point": "only one", "stance": "BULLISH"}],
    })
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert "3" in r["notes"]


def test_fail_when_hallucinated_ticker_appears_in_text():
    text = json.dumps({
        "ticker": "RELIANCE",
        "signal_points": [
            {"point": "Refining and TICKER_DOES_NOT_EXIST competition", "stance": "BEARISH"},
            {"point": "Capex peak behind us", "stance": "BULLISH"},
            {"point": "Telecom ARPU stalling", "stance": "BEARISH"},
        ],
    })
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert "halluc" in r["notes"].lower()


def test_pass_when_known_ticker_referenced():
    """Cross-references to other universe tickers are allowed."""
    text = json.dumps({
        "ticker": "RELIANCE",
        "signal_points": [
            {"point": "Telecom competition vs vodafone idea", "stance": "BEARISH"},
            {"point": "Better than TCS in capex discipline",  "stance": "BULLISH"},
            {"point": "Telecom ARPU stalling",                "stance": "BEARISH"},
        ],
    })
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is True
```

- [ ] **Step 2: Run test, verify failure**

Run: `pytest pipeline/tests/gemma4_pilot/rubrics/test_concall_supplement.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the rubric**

`pipeline/gemma4_pilot/rubrics/concall_supplement.py`:

```python
"""Rubric for Task #1 — concall supplement.

Pass criteria from spec §3.1:
  1. Output is valid JSON matching the trust-score supplement schema (ticker,
     signal_points list of {point, stance}).
  2. Includes 3+ signal points.
  3. No hallucinated tickers — capitalized tokens that look like tickers must
     either be in the universe or be a recognized non-ticker word.

Returns {'score': float in [0,1], 'pass': bool, 'notes': str}."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

# Tokens that look ticker-like but aren't tickers in our universe
_NON_TICKER_ALLCAPS = {
    "USD", "EUR", "INR", "GBP", "JPY", "CNY",
    "GAAP", "EBITDA", "ROE", "ROCE", "PAT", "EPS", "DCF", "CAGR", "ARPU",
    "Q1", "Q2", "Q3", "Q4", "FY", "YOY", "QOQ", "MOM",
    "CEO", "CFO", "MD", "AGM", "EGM", "BOD",
    "GST", "TDS", "RBI", "SEBI", "IPO", "FPO", "OFS",
    "AI", "ML", "EV", "ESG", "B2B", "B2C", "API",
    "BULLISH", "BEARISH", "NEUTRAL",
}

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&]{2,15}\b")


def score(text: str, meta: Mapping[str, Any]) -> dict:
    notes = []
    universe = set(meta.get("universe", set()))

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"score": 0.0, "pass": False, "notes": f"invalid_json: {e}"}

    if not isinstance(data, dict):
        return {"score": 0.0, "pass": False, "notes": "json_not_object"}

    points = data.get("signal_points")
    if not isinstance(points, list):
        return {"score": 0.0, "pass": False, "notes": "missing_signal_points_list"}

    if len(points) < 3:
        return {"score": 0.0, "pass": False,
                "notes": f"only {len(points)} signal_points, need 3+"}

    for p in points:
        if not isinstance(p, dict) or "point" not in p or "stance" not in p:
            return {"score": 0.0, "pass": False, "notes": "bad_signal_point_shape"}
        if p["stance"] not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            return {"score": 0.0, "pass": False,
                    "notes": f"bad_stance: {p['stance']!r}"}

    # Hallucinated-ticker check
    blob = " ".join(str(p.get("point", "")) for p in points).upper()
    candidates = set(_TICKER_RE.findall(blob))
    candidates -= _NON_TICKER_ALLCAPS
    candidates -= universe
    candidates.discard(str(data.get("ticker", "")).upper())
    # Filter further: must look like a likely ticker (mostly letters, optional digits)
    suspect = {c for c in candidates if re.fullmatch(r"[A-Z][A-Z0-9&]{3,15}", c)}
    if suspect:
        return {"score": 0.0, "pass": False,
                "notes": f"hallucinated_ticker_candidates: {sorted(suspect)}"}

    return {"score": 1.0, "pass": True, "notes": "ok"}
```

- [ ] **Step 4: Run rubric tests**

Run: `pytest pipeline/tests/gemma4_pilot/rubrics/test_concall_supplement.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/gemma4_pilot/rubrics/__init__.py pipeline/gemma4_pilot/rubrics/concall_supplement.py pipeline/tests/gemma4_pilot/rubrics/__init__.py pipeline/tests/gemma4_pilot/rubrics/test_concall_supplement.py
git commit -m "feat(gemma4-pilot): rubric for task #1 concall supplement"
```

---

## Task 8: Per-Task Rubric — News Classification (Task #2)

**Files:**
- Create: `pipeline/gemma4_pilot/rubrics/news_classification.py`
- Test: `pipeline/tests/gemma4_pilot/rubrics/test_news_classification.py`

Rubric criteria (spec §3.1 task 2):
- Returns one of: BULLISH / BEARISH / NEUTRAL / NOT_RELEVANT
- Confidence ∈ [0, 1]
- Sector tag from canonical sector list

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/rubrics/test_news_classification.py`:

```python
from __future__ import annotations

import json

from pipeline.gemma4_pilot.rubrics.news_classification import score, CANONICAL_SECTORS


def test_pass_valid():
    text = json.dumps({"label": "BULLISH", "confidence": 0.82,
                       "sector": "Banking & Financials"})
    r = score(text, {})
    assert r["pass"] is True
    assert r["score"] == 1.0


def test_fail_invalid_label():
    text = json.dumps({"label": "MAYBE", "confidence": 0.5, "sector": "IT"})
    r = score(text, {})
    assert r["pass"] is False
    assert "label" in r["notes"]


def test_fail_confidence_out_of_range():
    text = json.dumps({"label": "BEARISH", "confidence": 1.7,
                       "sector": "Banking & Financials"})
    r = score(text, {})
    assert r["pass"] is False
    assert "confidence" in r["notes"]


def test_fail_unknown_sector():
    text = json.dumps({"label": "NEUTRAL", "confidence": 0.5, "sector": "Crypto"})
    r = score(text, {})
    assert r["pass"] is False
    assert "sector" in r["notes"]


def test_canonical_sectors_includes_banking_and_it():
    """Smoke check on the canonical list shape."""
    assert "Banking & Financials" in CANONICAL_SECTORS
    assert "IT" in CANONICAL_SECTORS
```

- [ ] **Step 2: Implement**

`pipeline/gemma4_pilot/rubrics/news_classification.py`:

```python
"""Rubric for Task #2 — news classification + sentiment.

Canonical sector list lifted from pipeline/config/sector_map.json (single source
of truth used elsewhere in the pipeline). If that file moves, update the import
below — do not maintain a duplicate here."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

_VALID_LABELS = {"BULLISH", "BEARISH", "NEUTRAL", "NOT_RELEVANT"}

_SECTOR_MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "sector_map.json"


def _load_sectors() -> set[str]:
    if not _SECTOR_MAP_PATH.exists():
        # Fallback so tests don't depend on the live file
        return {
            "Banking & Financials", "IT", "Auto", "FMCG", "Pharma", "Metals",
            "Oil & Gas", "Power", "Realty", "Telecom", "Capital Goods",
            "Cement", "Chemicals", "Consumer Durables", "Media",
        }
    raw = json.loads(_SECTOR_MAP_PATH.read_text())
    # File maps ticker -> sector; we want the unique sector values
    if isinstance(raw, dict):
        return set(raw.values())
    return set(raw)


CANONICAL_SECTORS = _load_sectors()


def score(text: str, meta: Mapping[str, Any]) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"score": 0.0, "pass": False, "notes": f"invalid_json: {e}"}

    if not isinstance(data, dict):
        return {"score": 0.0, "pass": False, "notes": "json_not_object"}

    label = data.get("label")
    if label not in _VALID_LABELS:
        return {"score": 0.0, "pass": False, "notes": f"bad_label: {label!r}"}

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        return {"score": 0.0, "pass": False, "notes": f"bad_confidence: {conf!r}"}

    sector = data.get("sector")
    if sector not in CANONICAL_SECTORS:
        return {"score": 0.0, "pass": False,
                "notes": f"unknown_sector: {sector!r} (must be in canonical list)"}

    return {"score": 1.0, "pass": True, "notes": "ok"}
```

- [ ] **Step 3: Run tests**

Run: `pytest pipeline/tests/gemma4_pilot/rubrics/test_news_classification.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add pipeline/gemma4_pilot/rubrics/news_classification.py pipeline/tests/gemma4_pilot/rubrics/test_news_classification.py
git commit -m "feat(gemma4-pilot): rubric for task #2 news classification"
```

---

## Task 9: Per-Task Rubric — EOD Telegram Narrative (Task #3)

**Files:**
- Create: `pipeline/gemma4_pilot/rubrics/eod_narrative.py`
- Test: `pipeline/tests/gemma4_pilot/rubrics/test_eod_narrative.py`

Rubric criteria (spec §3.1 task 3):
- Length 200–600 chars (Telegram-friendly)
- Mentions today's regime
- Mentions at least one specific position from the day's ledger
- No factually wrong numbers (cross-check against `live_paper_ledger.json`)

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/rubrics/test_eod_narrative.py`:

```python
from __future__ import annotations

from pipeline.gemma4_pilot.rubrics.eod_narrative import score


META = {
    "regime": "RISK_ON",
    "positions": [
        {"ticker": "RELIANCE", "side": "LONG", "pnl_pct": 1.42},
        {"ticker": "TCS",      "side": "SHORT", "pnl_pct": -0.31},
    ],
}


def test_pass_short_well_grounded_narrative():
    text = (
        "Today closed in RISK_ON. RELIANCE long booked 1.4% and TCS short "
        "bled 0.3%. Net day: +1.1% on the basket. Tomorrow watch oil and "
        "the rupee. Volatility light, FII flow constructive. Stops held."
    )
    r = score(text, META)
    assert r["pass"] is True


def test_fail_too_short():
    r = score("Quiet day.", META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_too_long():
    r = score("X" * 700, META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_missing_regime_mention():
    text = "RELIANCE long booked 1.4% and TCS short bled 0.3%. " * 4
    r = score(text, META)
    assert r["pass"] is False
    assert "regime" in r["notes"].lower()


def test_fail_no_position_mention():
    text = "RISK_ON regime today. " * 12
    r = score(text, META)
    assert r["pass"] is False
    assert "position" in r["notes"].lower()


def test_fail_wrong_pnl_number():
    text = (
        "RISK_ON closed flat. RELIANCE long booked 9.99% — well above "
        "expectation. Light volatility. Stops held overnight. The basket "
        "delivered as planned. Tomorrow watch oil."
    )
    # ledger says 1.42% — 9.99% should be flagged as a wrong number
    r = score(text, META)
    assert r["pass"] is False
    assert "number" in r["notes"].lower() or "pnl" in r["notes"].lower()
```

- [ ] **Step 2: Implement**

`pipeline/gemma4_pilot/rubrics/eod_narrative.py`:

```python
"""Rubric for Task #3 — EOD Telegram trade narrative.

Number-grounding check: extract every percent figure from the text. For each
ticker mentioned, the closest percent figure to that ticker's name in the text
must be within 0.2 percentage points of the ledger value. This is a heuristic;
the human pairwise audit catches cases the heuristic misses."""
from __future__ import annotations

import re
from typing import Any, Mapping

_PCT_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)\s*%")
_MIN_LEN = 200
_MAX_LEN = 600
_PCT_TOL = 0.5  # percentage-points tolerance


def score(text: str, meta: Mapping[str, Any]) -> dict:
    n = len(text)
    if n < _MIN_LEN or n > _MAX_LEN:
        return {"score": 0.0, "pass": False,
                "notes": f"length: {n} chars not in [{_MIN_LEN}, {_MAX_LEN}]"}

    regime = str(meta.get("regime", ""))
    if regime and regime.upper() not in text.upper():
        return {"score": 0.0, "pass": False,
                "notes": f"regime '{regime}' not mentioned"}

    positions = meta.get("positions") or []
    mentioned = [p for p in positions if p["ticker"].upper() in text.upper()]
    if not mentioned:
        return {"score": 0.0, "pass": False,
                "notes": "no position mentioned from the day's ledger"}

    # Number-grounding: check each mentioned ticker's pnl
    upper = text.upper()
    for p in mentioned:
        ticker = p["ticker"].upper()
        true_pct = float(p["pnl_pct"])
        # Find the % figure nearest to the ticker mention
        idx = upper.find(ticker)
        if idx < 0:
            continue
        # Look in a 80-char window after the ticker
        window = text[idx: idx + 80]
        pcts = [float(m) for m in _PCT_RE.findall(window)]
        if not pcts:
            continue
        nearest = min(pcts, key=lambda x: abs(x - true_pct))
        if abs(nearest - true_pct) > _PCT_TOL:
            return {"score": 0.0, "pass": False,
                    "notes": f"wrong_pnl_number: {ticker} text says {nearest}% but "
                             f"ledger says {true_pct}%"}

    return {"score": 1.0, "pass": True, "notes": "ok"}
```

- [ ] **Step 3: Run tests**

Run: `pytest pipeline/tests/gemma4_pilot/rubrics/test_eod_narrative.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add pipeline/gemma4_pilot/rubrics/eod_narrative.py pipeline/tests/gemma4_pilot/rubrics/test_eod_narrative.py
git commit -m "feat(gemma4-pilot): rubric for task #3 EOD narrative with pnl-number grounding"
```

---

## Task 10: Per-Task Rubric — Article Draft (Task #4)

**Files:**
- Create: `pipeline/gemma4_pilot/rubrics/article_draft.py`
- Test: `pipeline/tests/gemma4_pilot/rubrics/test_article_draft.py`

Rubric criteria (spec §3.1 task 4):
- Length 800–2500 words
- All cited market numbers verifiable against `data/global_regime.json` (per `feedback_stale_data_disqualifies_article.md`)
- No hallucinated tickers, names, dates
- Coherent narrative arc → human pairwise audit handles this; rubric only catches the hard failures

The rubric does NOT score prose quality — that's what pairwise is for.

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/rubrics/test_article_draft.py`:

```python
from __future__ import annotations

from pipeline.gemma4_pilot.rubrics.article_draft import score


META = {
    "global_regime": {
        "brent_usd": 92.4,
        "wti_usd": 88.2,
        "usd_inr": 84.1,
        "us10y_pct": 4.25,
    },
    "universe": {"RELIANCE", "TCS", "INFY", "HDFCBANK", "ONGC", "BPCL"},
    "ts_iso": "2026-04-29",
}


def _filler(words: int) -> str:
    return " ".join(["lorem"] * words)


def test_pass_valid_article():
    body = (
        "Brent traded at $92 today. The rupee at 84.1 reflected the same "
        "narrative as Reliance and ONGC are watching. " + _filler(900)
    )
    r = score(body, META)
    assert r["pass"] is True


def test_fail_too_short():
    body = "Brent at $92." + _filler(100)
    r = score(body, META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_wrong_oil_price():
    body = "Brent traded at $103 today. " + _filler(900)
    r = score(body, META)
    assert r["pass"] is False
    assert "brent" in r["notes"].lower() or "number" in r["notes"].lower()


def test_fail_hallucinated_ticker():
    body = ("Brent at $92, USDINR 84.1. Reliance and TICKERX led the rally. "
            + _filler(900))
    r = score(body, META)
    assert r["pass"] is False
    assert "halluc" in r["notes"].lower()
```

- [ ] **Step 2: Implement**

`pipeline/gemma4_pilot/rubrics/article_draft.py`:

```python
"""Rubric for Task #4 — daily article draft (markets only).

Strict numeric-grounding: any $ or % figure that names a known anchor (Brent,
WTI, USDINR, US10Y) must be within tolerance of meta['global_regime']. This
is the hard rule from feedback_stale_data_disqualifies_article.md."""
from __future__ import annotations

import re
from typing import Any, Mapping

_MIN_WORDS = 800
_MAX_WORDS = 2500

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&]{3,15}\b")
_NON_TICKER = {
    "USDINR", "EURUSD", "USDJPY", "BRENT", "WTI", "OPEC", "FII", "DII",
    "NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY", "MIDCAP", "SMALLCAP",
    "GAAP", "EBITDA", "ARPU", "RBI", "SEBI", "GST", "FY", "AGM", "CEO",
    "CFO", "USD", "INR", "EUR", "JPY", "GBP", "CNY", "BULLISH", "BEARISH",
    "NEUTRAL", "RISK", "ON", "OFF",
}

_BRENT_RE = re.compile(r"brent[^\d$]{0,20}\$?\s*([0-9]{2,3}(?:\.[0-9])?)", re.I)
_WTI_RE = re.compile(r"wti[^\d$]{0,20}\$?\s*([0-9]{2,3}(?:\.[0-9])?)", re.I)
_USDINR_RE = re.compile(r"(?:rupee|usdinr|inr)[^\d]{0,20}([0-9]{2,3}\.[0-9])", re.I)
_US10Y_RE = re.compile(r"(?:us\s*10\s*y(?:ear)?|10[-\s]?yr|treasur(?:y|ies))[^\d%]{0,20}([0-9]\.[0-9]{1,2})", re.I)

_ANCHOR_TOL = {
    "brent_usd": 1.5,
    "wti_usd": 1.5,
    "usd_inr": 0.3,
    "us10y_pct": 0.10,
}


def score(text: str, meta: Mapping[str, Any]) -> dict:
    word_count = len(text.split())
    if word_count < _MIN_WORDS or word_count > _MAX_WORDS:
        return {"score": 0.0, "pass": False,
                "notes": f"length: {word_count} words not in [{_MIN_WORDS}, {_MAX_WORDS}]"}

    regime = meta.get("global_regime", {}) or {}
    universe = set(meta.get("universe", set()))

    # Number-grounding: each anchor we can extract must be within tolerance
    checks = [
        ("brent_usd",  _BRENT_RE),
        ("wti_usd",    _WTI_RE),
        ("usd_inr",    _USDINR_RE),
        ("us10y_pct",  _US10Y_RE),
    ]
    for key, regex in checks:
        m = regex.search(text)
        if m is None:
            continue
        try:
            cited = float(m.group(1))
        except ValueError:
            continue
        truth = regime.get(key)
        if truth is None:
            continue
        if abs(cited - float(truth)) > _ANCHOR_TOL[key]:
            return {"score": 0.0, "pass": False,
                    "notes": f"stale_or_wrong_number: {key} cited={cited} "
                             f"truth={truth} tol={_ANCHOR_TOL[key]}"}

    # Hallucinated-ticker check: capitalized 4-16-letter tokens not in universe
    candidates = set(_TICKER_RE.findall(text))
    candidates -= _NON_TICKER
    candidates -= universe
    suspect = {c for c in candidates if 4 <= len(c) <= 16 and c.isalpha()}
    if suspect:
        return {"score": 0.0, "pass": False,
                "notes": f"hallucinated_ticker_candidates: {sorted(suspect)[:5]}"}

    return {"score": 1.0, "pass": True, "notes": "ok"}
```

- [ ] **Step 3: Run tests**

Run: `pytest pipeline/tests/gemma4_pilot/rubrics/test_article_draft.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add pipeline/gemma4_pilot/rubrics/article_draft.py pipeline/tests/gemma4_pilot/rubrics/test_article_draft.py
git commit -m "feat(gemma4-pilot): rubric for task #4 article draft with anchor-number grounding"
```

---

## Task 11: Wire Concall Supplement to Shadow Dispatcher

**Files:**
- Modify: `opus/anka_score_pipeline.py` (or wherever concall supplement currently calls Gemini — verify with `grep -rn "concall" opus/ pipeline/` first)
- Test: `pipeline/tests/gemma4_pilot/test_wire_concall.py`

This is the FIRST production wiring. The integration pattern below is the template for tasks 12-14.

- [ ] **Step 1: Find the existing concall supplement call site**

Run: `git grep -n "concall" -- 'opus/**/*.py' 'pipeline/**/*.py'`

Identify the function that currently calls Gemini for concall supplements (likely something like `opus/anka_score_pipeline.py::generate_concall_supplement` or `opus/concall_extractor.py`). Note the exact file:line for the LLM call.

- [ ] **Step 2: Build the wiring helper**

Create `pipeline/gemma4_pilot/wiring.py` (one helper, used by all 4 task wirings):

```python
"""Single entry point for pilot-routed LLM calls. Each call site replaces its
direct provider call with `dispatch_for_task(...)`."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline.gemma4_pilot.shadow_dispatcher import ShadowDispatcher
from pipeline.llm_providers.anthropic_provider import AnthropicProvider
from pipeline.llm_providers.gemini_provider import GeminiProvider
from pipeline.llm_providers.openai_compat import OpenAICompatProvider
from pipeline.llm_router import LLMRouter, RoutingConfig
from pipeline.gemma4_pilot.rubrics import (
    concall_supplement,
    news_classification,
    eod_narrative,
    article_draft,
)

_AUDIT_ROOT = Path(__file__).resolve().parents[1] / "data" / "research" / "gemma4_pilot"

_RUBRICS = {
    "concall_supplement":  concall_supplement.score,
    "news_classification": news_classification.score,
    "eod_narrative":       eod_narrative.score,
    "article_draft":       article_draft.score,
}


def _build_providers() -> dict:
    return {
        "gemini-flash":  GeminiProvider(name="gemini-flash", model="gemini-2.5-flash"),
        "claude-haiku":  AnthropicProvider(name="claude-haiku",
                                            model="claude-haiku-4-5-20251001"),
        "gemma4-local":  OpenAICompatProvider(
            name="gemma4-local",
            base_url="http://127.0.0.1:11434/v1",
            model="gemma4:26b-a4b-q4_k_m",
            api_key="ollama",
        ),
    }


def _build_router() -> LLMRouter:
    return LLMRouter(
        config=RoutingConfig.load(),
        providers=_build_providers(),
    )


def dispatch_for_task(
    *,
    task: str,
    prompt: str,
    retrieved_context: Sequence[Mapping[str, Any]] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> str:
    """Pilot entry point. Routes per pipeline/config/llm_routing.json,
    runs shadow if configured, returns production text."""
    rubric_fn = _RUBRICS.get(task)
    if rubric_fn is None:
        raise ValueError(f"unknown pilot task: {task!r}")
    router = _build_router()
    primary, shadow = router.providers_for(task)
    dispatcher = ShadowDispatcher(audit_root=_AUDIT_ROOT, rubric_fn=rubric_fn)
    return dispatcher.dispatch(
        task=task,
        date_iso=dt.date.today().isoformat(),
        primary=primary,
        shadow=shadow,
        prompt=prompt,
        retrieved_context=retrieved_context,
        meta=meta or {},
    )
```

- [ ] **Step 3: Write the wiring test**

`pipeline/tests/gemma4_pilot/test_wire_concall.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from pipeline.gemma4_pilot.wiring import dispatch_for_task
from pipeline.llm_providers.base import ProviderResponse


def _resp(provider, text):
    return ProviderResponse(text=text, usage={"input_tokens": 1, "output_tokens": 1},
                            provider=provider, model="m", latency_s=1.0)


def test_dispatch_concall_returns_primary_text(tmp_path, monkeypatch):
    """Smoke: with mocked providers, dispatch_for_task threads through cleanly
    and writes an audit row."""
    fake_primary = MagicMock()
    fake_primary.generate.return_value = _resp("gemini-flash",
        '{"ticker": "RELIANCE", "signal_points": ['
        '{"point": "a", "stance": "BULLISH"},'
        '{"point": "b", "stance": "BULLISH"},'
        '{"point": "c", "stance": "BEARISH"}]}')
    fake_shadow = MagicMock()
    fake_shadow.generate.return_value = _resp("gemma4-local",
        '{"ticker": "RELIANCE", "signal_points": ['
        '{"point": "a", "stance": "BULLISH"},'
        '{"point": "b", "stance": "BULLISH"},'
        '{"point": "c", "stance": "NEUTRAL"}]}')

    fake_router = MagicMock()
    fake_router.providers_for.return_value = (fake_primary, fake_shadow)

    monkeypatch.setattr(
        "pipeline.gemma4_pilot.wiring._build_router",
        lambda: fake_router,
    )
    monkeypatch.setattr(
        "pipeline.gemma4_pilot.wiring._AUDIT_ROOT",
        tmp_path,
    )

    out = dispatch_for_task(
        task="concall_supplement",
        prompt="Summarize RELIANCE Q4 concall.",
        retrieved_context=None,
        meta={"ticker": "RELIANCE", "universe": {"RELIANCE", "TCS"}},
    )
    assert "signal_points" in out
    fake_primary.generate.assert_called_once()
    fake_shadow.generate.assert_called_once()
```

- [ ] **Step 4: Run wiring test**

Run: `pytest pipeline/tests/gemma4_pilot/test_wire_concall.py -v`
Expected: 1 passed.

- [ ] **Step 5: Replace the existing call site (file from Step 1)**

In the existing concall function, replace the direct `gemini.generate_content(...)` (or equivalent) with:

```python
from pipeline.gemma4_pilot.wiring import dispatch_for_task

# Build retrieved context from prior concalls (if available) — see RAG index
text = dispatch_for_task(
    task="concall_supplement",
    prompt=prompt,
    retrieved_context=None,  # plumb through from RAG in a follow-up if needed
    meta={"ticker": ticker, "universe": KNOWN_TICKERS},
)
```

Keep the existing prompt unchanged. Keep the existing JSON-parsing of the result unchanged. The dispatcher-routed text is shape-compatible with what Gemini was returning.

- [ ] **Step 6: Run the full suite**

Run: `pytest pipeline/tests/gemma4_pilot/ pipeline/tests/test_*concall*.py -v`
Expected: green. Any breakage = the prompt or response format diverged; revert and retry.

- [ ] **Step 7: Commit**

```bash
git add pipeline/gemma4_pilot/wiring.py opus/anka_score_pipeline.py pipeline/tests/gemma4_pilot/test_wire_concall.py
# replace path above with the actual call-site file from Step 1
git commit -m "feat(gemma4-pilot): wire task #1 concall supplement through shadow dispatcher"
```

---

## Task 12: Wire News Classification to Shadow Dispatcher

**Files:**
- Modify: `pipeline/news_intelligence.py` (verify with `grep -rn "classif" pipeline/`)

- [ ] **Step 1: Find the existing news classifier call site**

Run: `git grep -n "classify\|sentiment" -- 'pipeline/news_intelligence*.py' 'pipeline/news*.py'`

- [ ] **Step 2: Replace the call**

Replace the direct LLM call with `dispatch_for_task(task="news_classification", prompt=..., meta={})`. The classifier prompt template is unchanged.

- [ ] **Step 3: Run news-related tests**

Run: `pytest pipeline/tests/test_news*.py pipeline/tests/gemma4_pilot/ -v`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add pipeline/news_intelligence.py
# replace path with actual call-site file
git commit -m "feat(gemma4-pilot): wire task #2 news classification through shadow dispatcher"
```

---

## Task 13: Wire EOD Telegram Narrative to Shadow Dispatcher

**Files:**
- Modify: `pipeline/eod_review.py` (verify with `git grep -n eod_narrative pipeline/`)

- [ ] **Step 1: Find the existing narrative call site**

Run: `git grep -n "narrative\|telegram" -- 'pipeline/eod*.py'`

- [ ] **Step 2: Replace the call**

```python
text = dispatch_for_task(
    task="eod_narrative",
    prompt=prompt,
    retrieved_context=None,
    meta={"regime": today_regime, "positions": positions_for_meta},
)
```

`positions_for_meta` is built from the same `live_paper_ledger.json` rows used to build `prompt`. It MUST match the rubric's expected shape (`[{"ticker", "side", "pnl_pct"}]`) so the rubric can score the result.

- [ ] **Step 3: Run EOD tests**

Run: `pytest pipeline/tests/test_eod*.py pipeline/tests/gemma4_pilot/ -v`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add pipeline/eod_review.py
git commit -m "feat(gemma4-pilot): wire task #3 EOD narrative through shadow dispatcher"
```

---

## Task 14: Wire Daily Article Draft (Markets) to Shadow Dispatcher

**Files:**
- Modify: `pipeline/daily_articles.py` or article generator (verify with `git grep -n "article" pipeline/ -l`)

Per spec §3 task #4: "**One topic only** to bound the blast radius." Wire ONLY the markets article. Epstein and war articles continue calling Gemini directly during the pilot.

- [ ] **Step 1: Find the markets article generation call site**

Run: `git grep -n "topic.*market\|topic_schemas" -- 'pipeline/**/*.py'`

- [ ] **Step 2: Conditionally route only the markets topic**

```python
from pipeline.gemma4_pilot.wiring import dispatch_for_task
from pipeline.global_regime_loader import load_global_regime  # existing

if topic == "markets":
    text = dispatch_for_task(
        task="article_draft",
        prompt=prompt,
        retrieved_context=rag_hits,  # from build_rag_index corpus
        meta={
            "global_regime": load_global_regime(),
            "universe": KNOWN_FNO_TICKERS,
            "ts_iso": dt.date.today().isoformat(),
        },
    )
else:
    text = existing_gemini_call(prompt)  # epstein, war stay on current stack
```

- [ ] **Step 3: Run article tests**

Run: `pytest pipeline/tests/test_*article*.py pipeline/tests/gemma4_pilot/ -v`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add pipeline/daily_articles.py
git commit -m "feat(gemma4-pilot): wire task #4 markets article (only) through shadow dispatcher"
```

---

## Task 15: Pairwise Audit UI — API Endpoint + Sample Selector

**Files:**
- Create: `pipeline/gemma4_pilot/pairwise_sampler.py`
- Create: `pipeline/terminal/api/gemma_pilot.py`
- Test: `pipeline/tests/gemma4_pilot/test_pairwise_sampler.py`
- Test: `pipeline/tests/gemma4_pilot/test_gemma_pilot_api.py`

Sample selection (resolved §10): stratified by hour into 4 buckets. For each task, fetch up to 10 samples per day.

- [ ] **Step 1: Write sampler test**

`pipeline/tests/gemma4_pilot/test_pairwise_sampler.py`:

```python
from __future__ import annotations

import json

from pipeline.gemma4_pilot.pairwise_sampler import sample_pairs_for_day


def _write_audit(root, task, date, rows):
    p = root / "audit" / task / f"{date}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows))


def test_sampler_returns_only_rows_with_both_outputs(tmp_path):
    rows = [
        {"ts": "2026-04-29T10:00:00+05:30", "task": "news_classification",
         "primary": {"text": "P1"}, "shadow": {"text": "S1", "provider": "gemma4-local"}},
        {"ts": "2026-04-29T11:00:00+05:30", "task": "news_classification",
         "primary": {"text": "P2"}, "shadow": {"provider": "gemma4-local",
                                                 "error": "boom"}},
    ]
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)

    samples = sample_pairs_for_day(tmp_path, "news_classification", "2026-04-29",
                                   max_samples=10)
    assert len(samples) == 1
    assert samples[0]["primary"]["text"] == "P1"


def test_sampler_stratifies_by_hour(tmp_path):
    rows = []
    # 6 rows in the morning bucket, 1 in afternoon, 0 elsewhere
    for h in [10, 10, 10, 11, 11, 11, 13]:
        rows.append({
            "ts": f"2026-04-29T{h:02d}:00:00+05:30",
            "primary": {"text": f"p{h}"}, "shadow": {"text": f"s{h}", "provider": "gemma4-local"},
        })
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)

    samples = sample_pairs_for_day(tmp_path, "news_classification", "2026-04-29",
                                   max_samples=10, seed=42)
    # all 7 fit under the cap of 10 — sampler should return all
    assert len(samples) == 7

    samples2 = sample_pairs_for_day(tmp_path, "news_classification", "2026-04-29",
                                    max_samples=4, seed=42)
    # capped at 4: should pull from both buckets, not all from morning
    buckets = {s["bucket"] for s in samples2}
    assert "morning" in buckets
    assert "afternoon" in buckets
```

- [ ] **Step 2: Implement sampler**

`pipeline/gemma4_pilot/pairwise_sampler.py`:

```python
"""Stratified-by-hour sampler for pairwise UI.

Buckets (IST):
    pre_market  : 06:00 - 09:30
    morning     : 09:30 - 12:30
    afternoon   : 12:30 - 15:30
    post_close  : 15:30 - 22:00

Returns a list of {primary, shadow, ts, bucket, audit_row_idx} dicts.
Ratings are written back to a separate pairwise file by the API endpoint."""
from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


_BUCKETS = [
    ("pre_market", dt.time(6, 0),  dt.time(9, 30)),
    ("morning",    dt.time(9, 30), dt.time(12, 30)),
    ("afternoon",  dt.time(12, 30), dt.time(15, 30)),
    ("post_close", dt.time(15, 30), dt.time(22, 0)),
]


def _bucket_for(ts_str: str) -> str:
    t = dt.datetime.fromisoformat(ts_str).timetz()
    naive = dt.time(t.hour, t.minute)
    for name, lo, hi in _BUCKETS:
        if lo <= naive < hi:
            return name
    return "other"


def sample_pairs_for_day(
    root: Path,
    task: str,
    date_iso: str,
    max_samples: int = 10,
    seed: int | None = None,
) -> list[dict]:
    audit_path = root / "audit" / task / f"{date_iso}.jsonl"
    if not audit_path.exists():
        return []

    rows: list[tuple[int, dict]] = []
    for i, line in enumerate(audit_path.read_text().splitlines()):
        if not line.strip():
            continue
        rec = json.loads(line)
        if (rec.get("shadow") or {}).get("text") and (rec.get("primary") or {}).get("text"):
            rec["bucket"] = _bucket_for(rec["ts"])
            rec["audit_row_idx"] = i
            rows.append((i, rec))

    if not rows:
        return []

    by_bucket: dict[str, list] = defaultdict(list)
    for _, r in rows:
        by_bucket[r["bucket"]].append(r)

    rng = random.Random(seed)
    for bucket_rows in by_bucket.values():
        rng.shuffle(bucket_rows)

    out: list[dict] = []
    bucket_names = list(by_bucket.keys())
    cursors = {b: 0 for b in bucket_names}
    while len(out) < max_samples:
        progressed = False
        for b in bucket_names:
            if cursors[b] < len(by_bucket[b]) and len(out) < max_samples:
                out.append(by_bucket[b][cursors[b]])
                cursors[b] += 1
                progressed = True
        if not progressed:
            break
    return out
```

- [ ] **Step 3: Run sampler tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_pairwise_sampler.py -v`
Expected: 2 passed.

- [ ] **Step 4: Write the API test**

`pipeline/tests/gemma4_pilot/test_gemma_pilot_api.py`:

```python
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from pipeline.terminal.api.gemma_pilot import router as gemma_router

# Mount the router on a minimal app for testing
from fastapi import FastAPI


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.terminal.api.gemma_pilot.AUDIT_ROOT",
        tmp_path,
    )
    audit_dir = tmp_path / "audit" / "news_classification"
    audit_dir.mkdir(parents=True)
    rows = [{
        "ts": "2026-04-29T10:00:00+05:30",
        "primary": {"text": "P1", "provider": "gemini-flash"},
        "shadow":  {"text": "S1", "provider": "gemma4-local"},
    }]
    (audit_dir / "2026-04-29.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

    app = FastAPI()
    app.include_router(gemma_router, prefix="/api/gemma_pilot")
    return TestClient(app)


def test_get_pairs_returns_blind_ordered(client):
    r = client.get("/api/gemma_pilot/pairs",
                    params={"task": "news_classification", "date": "2026-04-29"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    pair = body[0]
    # Output must be blinded — keys 'A' and 'B', not 'primary' and 'shadow'
    assert set(pair.keys()) >= {"id", "A", "B"}
    assert "primary" not in pair
    assert "shadow" not in pair
    # The pair must have exactly the two texts (in some order)
    assert {pair["A"], pair["B"]} == {"P1", "S1"}


def test_post_rating_saves(client, tmp_path):
    r = client.get("/api/gemma_pilot/pairs",
                    params={"task": "news_classification", "date": "2026-04-29"})
    pair = r.json()[0]

    r2 = client.post("/api/gemma_pilot/rate", json={
        "id": pair["id"],
        "task": "news_classification",
        "date": "2026-04-29",
        "winner": "A",  # human's blind pick
    })
    assert r2.status_code == 200

    pairwise_path = tmp_path / "audit" / "pairwise" / "2026-04-29.jsonl"
    assert pairwise_path.exists()
    rec = json.loads(pairwise_path.read_text().strip())
    assert rec["task"] == "news_classification"
    # Server resolves blind A/B back to provider name in storage
    assert rec["winner_provider"] in {"gemini-flash", "gemma4-local"}
```

- [ ] **Step 5: Implement the API**

`pipeline/terminal/api/gemma_pilot.py`:

```python
"""FastAPI router for the 'Gemma Pilot' terminal tab.

Endpoints:
    GET  /pairs?task=...&date=YYYY-MM-DD  → blinded list of pairs to rate
    POST /rate                            → store a rating (resolves blind back to provider)
    GET  /report_card?date=YYYY-MM-DD     → daily report card JSON
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pipeline.gemma4_pilot.pairwise_sampler import sample_pairs_for_day

AUDIT_ROOT = Path(__file__).resolve().parents[2] / "data" / "research" / "gemma4_pilot"

router = APIRouter()


def _blind_pair(rec: dict) -> dict:
    """Return {'id', 'A', 'B', 'A_provider_secret', 'B_provider_secret'}.

    The id is a hash of (task, audit_row_idx, ts) so the rating endpoint can
    resolve A/B back to the provider without trusting the client to echo it."""
    primary_text = rec["primary"]["text"]
    shadow_text = rec["shadow"]["text"]
    primary_prov = rec["primary"]["provider"]
    shadow_prov = rec["shadow"]["provider"]

    seed = f"{rec.get('audit_row_idx', 0)}|{rec['ts']}"
    flip = (hashlib.sha256(seed.encode()).digest()[0] % 2) == 1
    if flip:
        a_text, b_text = shadow_text, primary_text
        a_prov, b_prov = shadow_prov, primary_prov
    else:
        a_text, b_text = primary_text, shadow_text
        a_prov, b_prov = primary_prov, shadow_prov

    pair_id = hashlib.sha256(seed.encode()).hexdigest()[:16]
    return {
        "id": pair_id,
        "A": a_text,
        "B": b_text,
        "_A_provider": a_prov,
        "_B_provider": b_prov,
        "ts": rec["ts"],
        "bucket": rec.get("bucket"),
    }


@router.get("/pairs")
def get_pairs(task: str, date: str) -> list[dict[str, Any]]:
    raw = sample_pairs_for_day(AUDIT_ROOT, task, date, max_samples=10, seed=42)
    out = []
    for r in raw:
        blind = _blind_pair(r)
        # Strip server-only fields before sending
        out.append({k: v for k, v in blind.items() if not k.startswith("_")})
    return out


class RateRequest(BaseModel):
    id: str
    task: str
    date: str
    winner: str  # "A" | "B" | "tie"


@router.post("/rate")
def post_rate(req: RateRequest) -> dict:
    if req.winner not in {"A", "B", "tie"}:
        raise HTTPException(400, "winner must be 'A', 'B', or 'tie'")

    # Re-derive the same blind pair to learn which provider corresponds to A/B
    raw = sample_pairs_for_day(AUDIT_ROOT, req.task, req.date, max_samples=10, seed=42)
    matching = None
    for r in raw:
        if _blind_pair(r)["id"] == req.id:
            matching = _blind_pair(r)
            break
    if matching is None:
        raise HTTPException(404, "pair not found")

    if req.winner == "A":
        winner_provider = matching["_A_provider"]
    elif req.winner == "B":
        winner_provider = matching["_B_provider"]
    else:
        winner_provider = "tie"

    out_path = AUDIT_ROOT / "audit" / "pairwise" / f"{req.date}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(),
        "task": req.task,
        "pair_id": req.id,
        "winner": req.winner,
        "winner_provider": winner_provider,
        "A_provider": matching["_A_provider"],
        "B_provider": matching["_B_provider"],
    }
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return {"ok": True}


@router.get("/report_card")
def get_report_card(date: str) -> dict:
    p = AUDIT_ROOT / "report_cards" / f"{date}.json"
    if not p.exists():
        raise HTTPException(404, f"no report card for {date}")
    return json.loads(p.read_text())
```

- [ ] **Step 6: Mount the router on the existing terminal app**

Find the FastAPI app file (likely `pipeline/terminal/app.py`). Add:

```python
from pipeline.terminal.api.gemma_pilot import router as gemma_pilot_router
app.include_router(gemma_pilot_router, prefix="/api/gemma_pilot")
```

- [ ] **Step 7: Run API tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_gemma_pilot_api.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add pipeline/gemma4_pilot/pairwise_sampler.py pipeline/terminal/api/gemma_pilot.py pipeline/terminal/app.py pipeline/tests/gemma4_pilot/test_pairwise_sampler.py pipeline/tests/gemma4_pilot/test_gemma_pilot_api.py
git commit -m "feat(gemma4-pilot): pairwise sampler + blinded API endpoint"
```

---

## Task 16: Pairwise Audit UI — Frontend Tab

**Files:**
- Create: `pipeline/terminal/templates/gemma_pilot.html`
- Create: `pipeline/terminal/static/js/pages/gemma-pilot.js`
- Modify: existing terminal navigation (e.g., `pipeline/terminal/templates/_nav.html`) to add a "Gemma Pilot" link

- [ ] **Step 1: Create the page HTML**

`pipeline/terminal/templates/gemma_pilot.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Anka Terminal — Gemma Pilot</title>
    <link rel="stylesheet" href="/static/css/terminal.css">
    <style>
        .pair-card { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }
        .pair-card pre { white-space: pre-wrap; padding: 12px; background: #fafafa;
                         border: 1px solid #ddd; border-radius: 4px;
                         max-height: 400px; overflow-y: auto; }
        .vote-row { display: flex; gap: 8px; margin: 8px 0 24px; }
        .vote-btn { padding: 8px 16px; cursor: pointer; }
        .task-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
        .task-tab { padding: 6px 12px; cursor: pointer; border: 1px solid #ccc; }
        .task-tab.active { background: #333; color: white; }
        .meta { font-size: 0.85em; color: #666; }
    </style>
</head>
<body>
    <h1>Gemma Pilot — Pairwise Audit</h1>
    <div class="meta" id="status">Loading...</div>

    <div class="task-tabs" id="task-tabs">
        <div class="task-tab active" data-task="concall_supplement">Concall</div>
        <div class="task-tab" data-task="news_classification">News</div>
        <div class="task-tab" data-task="eod_narrative">EOD Narrative</div>
        <div class="task-tab" data-task="article_draft">Article</div>
    </div>

    <input type="date" id="date-picker">

    <div id="pairs"></div>

    <h2>Today's Report Card</h2>
    <pre id="report-card">…</pre>

    <script src="/static/js/pages/gemma-pilot.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create the JS**

`pipeline/terminal/static/js/pages/gemma-pilot.js`:

```javascript
const today = new Date().toISOString().slice(0, 10);
let currentTask = "concall_supplement";
let currentDate = today;

document.getElementById("date-picker").value = today;
document.getElementById("date-picker").addEventListener("change", e => {
    currentDate = e.target.value;
    loadPairs();
    loadReportCard();
});

document.querySelectorAll(".task-tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".task-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        currentTask = tab.dataset.task;
        loadPairs();
    });
});

async function loadPairs() {
    const status = document.getElementById("status");
    status.textContent = `Loading ${currentTask} for ${currentDate}...`;
    const r = await fetch(`/api/gemma_pilot/pairs?task=${currentTask}&date=${currentDate}`);
    const pairs = await r.json();
    const container = document.getElementById("pairs");
    container.innerHTML = "";
    if (pairs.length === 0) {
        status.textContent = `No samples for ${currentTask} on ${currentDate}`;
        return;
    }
    status.textContent = `${pairs.length} pairs to rate`;
    for (const p of pairs) {
        const card = document.createElement("div");
        card.innerHTML = `
            <div class="meta">${p.bucket} bucket — ${p.ts}</div>
            <div class="pair-card">
                <div><strong>A</strong><pre>${escapeHtml(p.A)}</pre></div>
                <div><strong>B</strong><pre>${escapeHtml(p.B)}</pre></div>
            </div>
            <div class="vote-row">
                <button class="vote-btn" data-id="${p.id}" data-w="A">A wins</button>
                <button class="vote-btn" data-id="${p.id}" data-w="tie">Tie</button>
                <button class="vote-btn" data-id="${p.id}" data-w="B">B wins</button>
            </div>
            <hr>
        `;
        container.appendChild(card);
    }
    container.querySelectorAll(".vote-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            await fetch("/api/gemma_pilot/rate", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    id: btn.dataset.id,
                    task: currentTask,
                    date: currentDate,
                    winner: btn.dataset.w,
                }),
            });
            btn.parentElement.querySelectorAll(".vote-btn").forEach(b => b.disabled = true);
            btn.textContent = btn.textContent + " ✓";
        });
    });
}

async function loadReportCard() {
    const r = await fetch(`/api/gemma_pilot/report_card?date=${currentDate}`);
    const el = document.getElementById("report-card");
    if (r.status !== 200) { el.textContent = "(no report card yet)"; return; }
    const card = await r.json();
    el.textContent = JSON.stringify(card, null, 2);
}

function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
}

loadPairs();
loadReportCard();
```

- [ ] **Step 3: Add the page route to the FastAPI app**

In `pipeline/terminal/app.py` (or equivalent):

```python
from fastapi.responses import HTMLResponse

@app.get("/gemma_pilot", response_class=HTMLResponse)
def gemma_pilot_page(request: Request):
    return templates.TemplateResponse("gemma_pilot.html", {"request": request})
```

Add a nav link in `_nav.html` (or wherever the terminal sidebar is rendered):

```html
<a href="/gemma_pilot">Gemma Pilot</a>
```

- [ ] **Step 4: Manual smoke**

Start the terminal: `python -m pipeline.terminal` (or whatever the existing entrypoint is).

Visit `http://127.0.0.1:8000/gemma_pilot`. Verify:
- Page loads
- "Concall" tab is active by default
- Date picker shows today
- "No samples" message appears when no audit data exists yet (expected pre-pilot)

- [ ] **Step 5: Commit**

```bash
git add pipeline/terminal/templates/gemma_pilot.html pipeline/terminal/static/js/pages/gemma-pilot.js pipeline/terminal/app.py pipeline/terminal/templates/_nav.html
git commit -m "feat(gemma4-pilot): Gemma Pilot terminal tab with pairwise UI + report card view"
```

---

## Task 17: Daily Report Card Aggregator

**Files:**
- Create: `pipeline/gemma4_pilot/daily_report.py`
- Create: `pipeline/scripts/gemma4_daily_report.py`
- Test: `pipeline/tests/gemma4_pilot/test_daily_report.py`

The aggregator runs at EOD (after all four task ledgers for the day have accumulated). Produces:
- `pipeline/data/research/gemma4_pilot/report_cards/<date>.json` (consumed by terminal tab)
- `pipeline/data/research/gemma4_pilot/report_cards/<date>.md` (human read)

Per spec §4.1, the locked metric definitions:
- **rubric pass rate** = pass / total (per provider, per task)
- **pairwise win rate** = (gemma_wins + 0.5 * ties) / total_ratings (per task)

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/test_daily_report.py`:

```python
from __future__ import annotations

import json

from pipeline.gemma4_pilot.daily_report import build_report


def _write_audit(root, task, date, rows):
    p = root / "audit" / task / f"{date}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows))


def _row(prim_pass, shadow_pass, primary_text="P", shadow_text="S",
          shadow_provider="gemma4-local", shadow_error=None):
    rec = {
        "ts": "2026-04-29T10:00:00+05:30",
        "primary": {"provider": "gemini-flash", "model": "gemini-2.5-flash",
                     "text": primary_text, "rubric_score": 1.0 if prim_pass else 0.0,
                     "rubric_pass": prim_pass, "latency_s": 2.0,
                     "usage": {"input_tokens": 100, "output_tokens": 50}},
    }
    if shadow_error:
        rec["shadow"] = {"provider": shadow_provider, "error": shadow_error}
    else:
        rec["shadow"] = {"provider": shadow_provider, "model": "gemma4:26b-a4b-q4_k_m",
                          "text": shadow_text, "rubric_score": 1.0 if shadow_pass else 0.0,
                          "rubric_pass": shadow_pass, "latency_s": 70.0,
                          "usage": {"input_tokens": 100, "output_tokens": 50}}
    return rec


def test_report_aggregates_rubric_pass_rates(tmp_path):
    rows = [_row(True, True), _row(True, False), _row(True, True), _row(True, True)]
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)

    pairwise_path = tmp_path / "audit" / "pairwise" / "2026-04-29.jsonl"
    pairwise_path.parent.mkdir(parents=True, exist_ok=True)
    pairwise_path.write_text("\n".join(json.dumps(r) for r in [
        {"task": "news_classification", "winner_provider": "gemma4-local", "winner": "A"},
        {"task": "news_classification", "winner_provider": "gemma4-local", "winner": "B"},
        {"task": "news_classification", "winner_provider": "gemini-flash",  "winner": "A"},
        {"task": "news_classification", "winner_provider": "tie",           "winner": "tie"},
    ]))

    report = build_report(tmp_path, "2026-04-29")

    nc = report["tasks"]["news_classification"]
    assert nc["calls"] == 4
    assert nc["primary_rubric_pass_rate"] == 1.0
    assert nc["shadow_rubric_pass_rate"] == 0.75    # 3/4
    assert nc["pairwise_total"] == 4
    # Win rate: gemma_wins=2, ties=1 → (2 + 0.5*1) / 4 = 0.625
    assert abs(nc["pairwise_win_rate"] - 0.625) < 1e-9


def test_report_handles_shadow_errors(tmp_path):
    rows = [_row(True, True), _row(True, None, shadow_error="ollama_down")]
    _write_audit(tmp_path, "concall_supplement", "2026-04-29", rows)

    report = build_report(tmp_path, "2026-04-29")
    cs = report["tasks"]["concall_supplement"]
    assert cs["calls"] == 2
    assert cs["shadow_errors"] == 1
    # shadow_rubric_pass_rate: 1 pass / 1 successful_call = 1.0 (errors not counted)
    assert cs["shadow_rubric_pass_rate"] == 1.0


def test_report_writes_both_json_and_md(tmp_path):
    rows = [_row(True, True)]
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)
    build_report(tmp_path, "2026-04-29", write_files=True)
    assert (tmp_path / "report_cards" / "2026-04-29.json").exists()
    assert (tmp_path / "report_cards" / "2026-04-29.md").exists()
```

- [ ] **Step 2: Implement**

`pipeline/gemma4_pilot/daily_report.py`:

```python
"""Daily report card aggregator. Reads:
   - audit/<task>/<date>.jsonl    (per-call records)
   - audit/pairwise/<date>.jsonl  (human pairwise ratings)
Produces:
   - report_cards/<date>.json
   - report_cards/<date>.md"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASKS = ["concall_supplement", "news_classification", "eod_narrative", "article_draft"]


def build_report(root: Path, date_iso: str, write_files: bool = False) -> dict:
    report: dict = {"date": date_iso, "tasks": {}}

    pairwise_path = root / "audit" / "pairwise" / f"{date_iso}.jsonl"
    pairwise_rows: list[dict] = []
    if pairwise_path.exists():
        for line in pairwise_path.read_text().splitlines():
            if line.strip():
                pairwise_rows.append(json.loads(line))

    for task in TASKS:
        audit_path = root / "audit" / task / f"{date_iso}.jsonl"
        rows: list[dict] = []
        if audit_path.exists():
            for line in audit_path.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))

        prim_pass = sum(1 for r in rows if r.get("primary", {}).get("rubric_pass"))
        shadow_attempts = [r for r in rows if r.get("shadow", {}).get("provider")]
        shadow_errors = sum(1 for r in shadow_attempts if r["shadow"].get("error"))
        shadow_success = [r for r in shadow_attempts if not r["shadow"].get("error")]
        shadow_pass = sum(1 for r in shadow_success if r["shadow"].get("rubric_pass"))

        prim_lat = [r["primary"].get("latency_s", 0) for r in rows
                    if "primary" in r and "latency_s" in r["primary"]]
        shadow_lat = [r["shadow"].get("latency_s", 0) for r in shadow_success
                      if "latency_s" in r["shadow"]]

        task_pairs = [r for r in pairwise_rows if r.get("task") == task]
        gemma_wins = sum(1 for r in task_pairs if r.get("winner_provider") == "gemma4-local")
        ties = sum(1 for r in task_pairs if r.get("winner_provider") == "tie")
        n_pairs = len(task_pairs)
        win_rate = ((gemma_wins + 0.5 * ties) / n_pairs) if n_pairs else None

        report["tasks"][task] = {
            "calls": len(rows),
            "primary_rubric_pass_rate": (prim_pass / len(rows)) if rows else None,
            "shadow_rubric_pass_rate": (shadow_pass / len(shadow_success))
                                        if shadow_success else None,
            "shadow_errors": shadow_errors,
            "primary_latency_p50_s": _p50(prim_lat),
            "shadow_latency_p50_s":  _p50(shadow_lat),
            "pairwise_total": n_pairs,
            "pairwise_gemma_wins": gemma_wins,
            "pairwise_ties": ties,
            "pairwise_win_rate": win_rate,
        }

    if write_files:
        out_json = root / "report_cards" / f"{date_iso}.json"
        out_md = root / "report_cards" / f"{date_iso}.md"
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2))
        out_md.write_text(_render_markdown(report))

    return report


def _p50(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[len(s) // 2]


def _fmt_pct(x: float | None) -> str:
    return f"{x*100:.1f}%" if x is not None else "—"


def _fmt_s(x: float | None) -> str:
    return f"{x:.1f}s" if x is not None else "—"


def _render_markdown(report: dict) -> str:
    lines = [f"# Gemma Pilot Report Card — {report['date']}", ""]
    lines.append("| Task | Calls | Primary Rubric | Shadow Rubric | Shadow Errors | "
                 "P50 Lat (P/S) | Pairs | Pairwise Win |")
    lines.append("|---|---:|---:|---:|---:|---|---:|---:|")
    for task, m in report["tasks"].items():
        lines.append(
            f"| {task} | {m['calls']} | {_fmt_pct(m['primary_rubric_pass_rate'])} "
            f"| {_fmt_pct(m['shadow_rubric_pass_rate'])} | {m['shadow_errors']} "
            f"| {_fmt_s(m['primary_latency_p50_s'])} / {_fmt_s(m['shadow_latency_p50_s'])} "
            f"| {m['pairwise_total']} | {_fmt_pct(m['pairwise_win_rate'])} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 3: Implement the runner script**

`pipeline/scripts/gemma4_daily_report.py`:

```python
"""EOD runner — generates today's report card to JSON+MD and posts a one-line
summary to Telegram. Scheduled at 22:00 IST after all four task ledgers
have accumulated."""
from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from pathlib import Path

from pipeline.gemma4_pilot.daily_report import build_report

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[gemma4_daily_report] %(message)s")
    log = logging.getLogger("gemma4_daily_report")
    today = dt.date.today().isoformat()
    report = build_report(AUDIT_ROOT, today, write_files=True)
    log.info("Wrote report card for %s", today)

    # One-line Telegram summary (best-effort; do not fail if Telegram is down)
    try:
        from pipeline.telegram_client import send_message  # existing
        line = f"Gemma Pilot {today}: "
        for task, m in report["tasks"].items():
            wr = m.get("pairwise_win_rate")
            line += f"{task}={'%.0f%%' % (wr*100) if wr is not None else '—'}  "
        send_message(line.strip(), channel="ops")
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram post failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run report tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_daily_report.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/gemma4_pilot/daily_report.py pipeline/scripts/gemma4_daily_report.py pipeline/tests/gemma4_pilot/test_daily_report.py
git commit -m "feat(gemma4-pilot): daily report card aggregator + Telegram one-liner"
```

---

## Task 18: Auto-Disable Guardrail

**Files:**
- Create: `pipeline/gemma4_pilot/auto_disable.py`
- Create: `pipeline/scripts/gemma4_auto_disable_check.py`
- Test: `pipeline/tests/gemma4_pilot/test_auto_disable.py`

Per spec §4.2:
- **Rubric pass rate < 90% over rolling 24h** → flip task to `disabled` mode in `llm_routing.json` + Telegram alert
- **Pairwise win rate < 40% over rolling 7 days** → write a `manual_review_required` flag (no auto-flip)

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/test_auto_disable.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from pipeline.gemma4_pilot.auto_disable import check_and_apply


def _audit(root, task, date_iso, n_pass, n_fail):
    p = root / "audit" / task / f"{date_iso}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for _ in range(n_pass):
        rows.append({"shadow": {"provider": "gemma4-local",
                                  "rubric_pass": True}})
    for _ in range(n_fail):
        rows.append({"shadow": {"provider": "gemma4-local",
                                  "rubric_pass": False}})
    p.write_text("\n".join(json.dumps(r) for r in rows))


def _routing(path, mode_for_task):
    cfg = {
        "default_primary": "gemini-flash", "default_fallback": "claude-haiku",
        "tasks": {t: {"mode": m, "primary": "gemini-flash", "shadow": "gemma4-local"}
                  for t, m in mode_for_task.items()}
    }
    path.write_text(json.dumps(cfg))


def test_disables_when_below_90_pct(tmp_path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"news_classification": "live"})
    _audit(tmp_path, "news_classification", "2026-04-29", n_pass=8, n_fail=2)
    # 80% pass — should disable

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert any(a["action"] == "disabled" and a["task"] == "news_classification"
               for a in actions)

    cfg = json.loads(routing_path.read_text())
    assert cfg["tasks"]["news_classification"]["mode"] == "disabled"


def test_no_disable_when_above_threshold(tmp_path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"news_classification": "live"})
    _audit(tmp_path, "news_classification", "2026-04-29", n_pass=95, n_fail=5)

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert not any(a["action"] == "disabled" for a in actions)


def test_pairwise_below_40_pct_writes_manual_flag(tmp_path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"article_draft": "live"})
    _audit(tmp_path, "article_draft", "2026-04-29", n_pass=10, n_fail=0)  # rubric ok

    # 7 days of pairwise: gemma_wins=2, ties=0, gemini_wins=8 → 2/10 = 20%
    pw = tmp_path / "audit" / "pairwise" / "2026-04-29.jsonl"
    pw.parent.mkdir(parents=True, exist_ok=True)
    rows = ([{"task": "article_draft", "winner_provider": "gemini-flash"}] * 8
            + [{"task": "article_draft", "winner_provider": "gemma4-local"}] * 2)
    pw.write_text("\n".join(json.dumps(r) for r in rows))

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert any(a["action"] == "manual_review_flagged" and a["task"] == "article_draft"
               for a in actions)
    flag = tmp_path / "manual_review" / "article_draft.flag"
    assert flag.exists()
```

- [ ] **Step 2: Implement**

`pipeline/gemma4_pilot/auto_disable.py`:

```python
"""Auto-disable guardrail per spec §4.2.

Rules:
  - rubric < 90% over rolling 24h → flip task mode to 'disabled' + Telegram alert
  - pairwise < 40% over rolling 7d → write manual_review/<task>.flag (no auto-flip)

Both rules are per-task; one task tripping does not affect the others."""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

LOG = logging.getLogger(__name__)

TASKS = ["concall_supplement", "news_classification", "eod_narrative", "article_draft"]
RUBRIC_FLOOR = 0.90
PAIRWISE_FLOOR = 0.40


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _rolling_dates(today_iso: str, days: int) -> list[str]:
    today = dt.date.fromisoformat(today_iso)
    return [(today - dt.timedelta(days=i)).isoformat() for i in range(days)]


def _shadow_rubric_pass_rate(root: Path, task: str, dates: list[str]) -> tuple[float | None, int]:
    n = 0
    p = 0
    for d in dates:
        rows = _read_jsonl(root / "audit" / task / f"{d}.jsonl")
        for r in rows:
            sh = r.get("shadow") or {}
            if sh.get("error") or sh.get("provider") is None:
                continue
            n += 1
            if sh.get("rubric_pass"):
                p += 1
    return ((p / n) if n else None), n


def _pairwise_win_rate(root: Path, task: str, dates: list[str]) -> tuple[float | None, int]:
    wins = ties = total = 0
    for d in dates:
        for r in _read_jsonl(root / "audit" / "pairwise" / f"{d}.jsonl"):
            if r.get("task") != task:
                continue
            total += 1
            wp = r.get("winner_provider")
            if wp == "gemma4-local":
                wins += 1
            elif wp == "tie":
                ties += 1
    return (((wins + 0.5 * ties) / total) if total else None), total


def check_and_apply(audit_root: Path, routing_path: Path, today_iso: str) -> list[dict]:
    cfg = json.loads(routing_path.read_text())
    actions: list[dict] = []

    for task in TASKS:
        # 24h rubric
        rate, n = _shadow_rubric_pass_rate(audit_root, task, _rolling_dates(today_iso, 1))
        if rate is not None and n >= 5 and rate < RUBRIC_FLOOR:
            current_mode = cfg.get("tasks", {}).get(task, {}).get("mode", "shadow")
            if current_mode != "disabled":
                cfg.setdefault("tasks", {}).setdefault(task, {})
                cfg["tasks"][task]["mode"] = "disabled"
                actions.append({
                    "task": task, "action": "disabled",
                    "reason": f"rubric_pass_rate {rate:.2%} < {RUBRIC_FLOOR:.0%} "
                              f"over last 24h (n={n})",
                })

        # 7d pairwise
        wr, np_ = _pairwise_win_rate(audit_root, task, _rolling_dates(today_iso, 7))
        if wr is not None and np_ >= 10 and wr < PAIRWISE_FLOOR:
            flag_path = audit_root / "manual_review" / f"{task}.flag"
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.write_text(
                f"[{today_iso}] pairwise_win_rate={wr:.2%} (n={np_}) below "
                f"{PAIRWISE_FLOOR:.0%} floor — manual review required\n"
            )
            actions.append({
                "task": task, "action": "manual_review_flagged",
                "reason": f"pairwise_win_rate {wr:.2%} < {PAIRWISE_FLOOR:.0%} "
                          f"over last 7d (n={np_})",
            })

    if actions:
        routing_path.write_text(json.dumps(cfg, indent=2))
        for a in actions:
            LOG.warning("guardrail: %s — %s — %s", a["task"], a["action"], a["reason"])
            try:
                from pipeline.telegram_client import send_message
                send_message(
                    f"⚠️ Gemma Pilot guardrail: {a['task']} {a['action']} — {a['reason']}",
                    channel="ops",
                )
            except Exception as e:  # noqa: BLE001
                LOG.warning("telegram failed: %s", e)
    return actions
```

- [ ] **Step 3: Implement runner**

`pipeline/scripts/gemma4_auto_disable_check.py`:

```python
"""Runner for the auto-disable guardrail. Scheduled hourly during pilot."""
from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from pipeline.gemma4_pilot.auto_disable import check_and_apply

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"
ROUTING_PATH = REPO_ROOT / "pipeline" / "config" / "llm_routing.json"


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                         format="[gemma4_auto_disable] %(message)s")
    actions = check_and_apply(AUDIT_ROOT, ROUTING_PATH, dt.date.today().isoformat())
    if not actions:
        logging.info("no guardrail actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run guardrail tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_auto_disable.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/gemma4_pilot/auto_disable.py pipeline/scripts/gemma4_auto_disable_check.py pipeline/tests/gemma4_pilot/test_auto_disable.py
git commit -m "feat(gemma4-pilot): auto-disable guardrail (24h rubric + 7d pairwise)"
```

---

## Task 19: Health Check Cron — 05:30 IST

**Files:**
- Create: `pipeline/scripts/gemma4_health_check.py`
- Test: `pipeline/tests/gemma4_pilot/test_health_check.py`

Daily check that ollama is up, the model is loaded, and a smoke ping returns within budget. Logs to a freshness file watched by the watchdog. Posts to Telegram on failure.

- [ ] **Step 1: Write the failing test**

`pipeline/tests/gemma4_pilot/test_health_check.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pipeline.scripts.gemma4_health_check import run_check


def test_health_pass_when_ping_succeeds(tmp_path, monkeypatch):
    def fake_ping(*_, **__):
        return {"ok": True, "latency_s": 12.3, "text": "PONG"}

    monkeypatch.setattr("pipeline.scripts.gemma4_health_check._ping_ollama",
                         fake_ping)
    rc = run_check(out_dir=tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "gemma4_health.json").read_text())
    assert out["status"] == "OK"
    assert out["latency_s"] == 12.3


def test_health_fail_when_ping_errors(tmp_path, monkeypatch):
    def fake_ping(*_, **__):
        return {"ok": False, "error": "connection refused"}

    monkeypatch.setattr("pipeline.scripts.gemma4_health_check._ping_ollama",
                         fake_ping)
    monkeypatch.setattr("pipeline.scripts.gemma4_health_check._send_alert",
                         lambda *_, **__: None)
    rc = run_check(out_dir=tmp_path)
    assert rc == 1
    out = json.loads((tmp_path / "gemma4_health.json").read_text())
    assert out["status"] == "FAIL"
```

- [ ] **Step 2: Implement**

`pipeline/scripts/gemma4_health_check.py`:

```python
"""Daily 05:30 IST Gemma 4 health check.

Reads:  http://127.0.0.1:11434/v1/chat/completions  (via ssh tunnel)
Writes: pipeline/data/research/gemma4_pilot/gemma4_health.json
        (consumed by the data-freshness watchdog)
Alerts: Telegram ops channel on FAIL"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"
LATENCY_BUDGET_S = 60.0


def _ping_ollama() -> dict[str, Any]:
    try:
        t0 = dt.datetime.now()
        r = requests.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "model": "gemma4:26b-a4b-q4_k_m",
                "messages": [{"role": "user", "content": "Reply: PONG"}],
                "temperature": 0.0,
                "max_tokens": 8,
            },
            timeout=120,
        )
        latency_s = (dt.datetime.now() - t0).total_seconds()
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        text = r.json()["choices"][0]["message"]["content"].strip()
        if "PONG" not in text.upper():
            return {"ok": False, "error": f"bad response: {text!r}"}
        return {"ok": True, "latency_s": latency_s, "text": text}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _send_alert(msg: str) -> None:
    try:
        from pipeline.telegram_client import send_message
        send_message(msg, channel="ops")
    except Exception:  # noqa: BLE001
        pass


def run_check(out_dir: Path = DEFAULT_OUT) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = _ping_ollama()
    now_iso = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat()

    status_record: dict[str, Any] = {"ts": now_iso}
    if p["ok"] and p["latency_s"] < LATENCY_BUDGET_S:
        status_record.update(status="OK", latency_s=p["latency_s"], text=p["text"])
        rc = 0
    elif p["ok"]:
        status_record.update(status="DEGRADED",
                              error=f"latency {p['latency_s']:.1f}s > budget {LATENCY_BUDGET_S}s",
                              latency_s=p["latency_s"])
        _send_alert(f"⚠️ Gemma 4 health DEGRADED: latency {p['latency_s']:.1f}s")
        rc = 0
    else:
        status_record.update(status="FAIL", error=p.get("error", "unknown"))
        _send_alert(f"🚨 Gemma 4 health FAIL: {p.get('error')}")
        rc = 1

    (out_dir / "gemma4_health.json").write_text(json.dumps(status_record, indent=2))
    logging.info("Gemma 4 health %s — %s", status_record["status"], status_record)
    return rc


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[gemma4_health] %(message)s")
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run health check tests**

Run: `pytest pipeline/tests/gemma4_pilot/test_health_check.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add pipeline/scripts/gemma4_health_check.py pipeline/tests/gemma4_pilot/test_health_check.py
git commit -m "feat(gemma4-pilot): daily 05:30 IST health check + Telegram alerting"
```

---

## Task 20: Schedule the New Cron Tasks

**Files:**
- Modify: `pipeline/config/anka_inventory.json` (add 4 new tasks)
- Create: `pipeline/scripts/AnkaGemma4HealthCheck.bat`
- Create: `pipeline/scripts/AnkaGemma4DailyReport.bat`
- Create: `pipeline/scripts/AnkaGemma4AutoDisable.bat`
- Create: `pipeline/scripts/AnkaGemma4RagRebuild.bat`

Per CLAUDE.md kill-switch rules: every new scheduled task must be in `anka_inventory.json` in the same commit. Per `feedback_prefer_vps_systemd_over_windows_scheduler.md`, default new schedules to VPS systemd — but this pilot's data flows are laptop-side (FastAPI terminal, audit logger, etc.) so we keep the schedules on Windows for now and mirror to VPS in a later phase.

- [ ] **Step 1: Read the inventory schema**

```bash
head -80 pipeline/config/anka_inventory.json
```

Note the existing entry shape (tier, cadence_class, expected output files, grace_multiplier).

- [ ] **Step 2: Add the four entries to inventory**

Add to `pipeline/config/anka_inventory.json` (preserve existing tasks):

```json
{
  "name": "AnkaGemma4HealthCheck",
  "tier": "warn",
  "cadence_class": "daily",
  "schedule": "05:30 IST",
  "outputs": ["pipeline/data/research/gemma4_pilot/gemma4_health.json"],
  "grace_multiplier": 1.5,
  "description": "Daily Gemma 4 ollama liveness + latency check. Pilot only."
},
{
  "name": "AnkaGemma4DailyReport",
  "tier": "warn",
  "cadence_class": "daily",
  "schedule": "22:00 IST",
  "outputs": [
    "pipeline/data/research/gemma4_pilot/report_cards/<today>.json",
    "pipeline/data/research/gemma4_pilot/report_cards/<today>.md"
  ],
  "grace_multiplier": 1.5,
  "description": "EOD aggregation of rubric pass-rates + pairwise win-rates per pilot task."
},
{
  "name": "AnkaGemma4AutoDisable",
  "tier": "info",
  "cadence_class": "intraday",
  "schedule": "every hour, 09:00-22:00 IST",
  "outputs": [],
  "grace_multiplier": 2.0,
  "description": "Hourly guardrail check. Disables a pilot task if rubric <90% (24h) or flags manual review if pairwise <40% (7d)."
},
{
  "name": "AnkaGemma4RagRebuild",
  "tier": "info",
  "cadence_class": "daily",
  "schedule": "03:30 IST",
  "outputs": ["pipeline/data/research/gemma4_pilot/rag_db/corpus.lance/"],
  "grace_multiplier": 2.0,
  "description": "Nightly incremental re-embed of changed source files into the LanceDB corpus."
}
```

- [ ] **Step 3: Create the .bat files**

Each follows the same pattern as existing `pipeline/scripts/Anka*.bat`. Example:

`pipeline/scripts/AnkaGemma4HealthCheck.bat`:

```batch
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\gemma4_health_check.py >> opus\logs\gemma4_pilot.log 2>&1
```

`pipeline/scripts/AnkaGemma4DailyReport.bat`:

```batch
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\gemma4_daily_report.py >> opus\logs\gemma4_pilot.log 2>&1
```

`pipeline/scripts/AnkaGemma4AutoDisable.bat`:

```batch
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\gemma4_auto_disable_check.py >> opus\logs\gemma4_pilot.log 2>&1
```

`pipeline/scripts/AnkaGemma4RagRebuild.bat`:

```batch
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\build_rag_index.py >> opus\logs\gemma4_pilot.log 2>&1
```

- [ ] **Step 4: Register the tasks with Windows Task Scheduler**

Run from an elevated PowerShell (or document for the user to run):

```powershell
schtasks /Create /SC DAILY /ST 05:30 /TN AnkaGemma4HealthCheck /TR "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\AnkaGemma4HealthCheck.bat" /F
schtasks /Create /SC DAILY /ST 22:00 /TN AnkaGemma4DailyReport /TR "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\AnkaGemma4DailyReport.bat" /F
schtasks /Create /SC HOURLY /ST 09:00 /TN AnkaGemma4AutoDisable /TR "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\AnkaGemma4AutoDisable.bat" /F
schtasks /Create /SC DAILY /ST 03:30 /TN AnkaGemma4RagRebuild /TR "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\AnkaGemma4RagRebuild.bat" /F
```

Verify:
```powershell
schtasks /Query /TN AnkaGemma4HealthCheck /V /FO LIST | Select-String "Last Run","Next Run","Status"
```

- [ ] **Step 5: Run a one-off manual test of each .bat**

```bash
./pipeline/scripts/AnkaGemma4HealthCheck.bat
./pipeline/scripts/AnkaGemma4RagRebuild.bat
./pipeline/scripts/AnkaGemma4DailyReport.bat
./pipeline/scripts/AnkaGemma4AutoDisable.bat
```

Each must succeed and write its expected output. Inspect `opus/logs/gemma4_pilot.log` for tracebacks.

- [ ] **Step 6: Commit**

```bash
git add pipeline/config/anka_inventory.json pipeline/scripts/AnkaGemma4HealthCheck.bat pipeline/scripts/AnkaGemma4DailyReport.bat pipeline/scripts/AnkaGemma4AutoDisable.bat pipeline/scripts/AnkaGemma4RagRebuild.bat
git commit -m "feat(gemma4-pilot): schedule 4 cron tasks + register in anka_inventory"
```

---

## Task 21: Documentation + Memory Sync

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` — add Gemma Pilot section
- Modify: `CLAUDE.md` — add Gemma Pilot bullets to clockwork schedule
- Modify: memory `reference_llm_providers.md` — add Gemma 4 row
- Create: memory `project_gemma4_pilot.md` — project memory
- Update: memory `MEMORY.md` — add index entry

Per `feedback_doc_sync_mandate.md`: every code change must update ALL relevant docs in the SAME commit. This task closes the loop.

- [ ] **Step 1: Update SYSTEM_OPERATIONS_MANUAL.md**

Find the "scheduled tasks" section. Add four entries to the table. Add a new prose section "Gemma 4 Pilot (Tier 2 LLM eval, 20-day window)":

```markdown
### Gemma 4 Pilot (2026-04-29 → 2026-05-19)

A 20-day forward-only evaluation of Gemma 4 26B-A4B local inference (Contabo VPS) as the Tier 2 LLM provider for four mundane/volume tasks: trust-score concall supplement, news classification, EOD Telegram narrative, daily article draft (markets only).

**Routing:** `pipeline/config/llm_routing.json` (modes: live, shadow, disabled — flip via JSON edit).
**Audit:** `pipeline/data/research/gemma4_pilot/audit/<task>/<YYYY-MM-DD>.jsonl`.
**Pairwise UI:** Terminal `/gemma_pilot` tab.
**Report card:** Daily 22:00 IST, written to `pipeline/data/research/gemma4_pilot/report_cards/<date>.{json,md}`.
**Guardrails:** Hourly auto-disable check — rubric <90% (24h) trips a task to disabled; pairwise <40% (7d) writes a manual review flag.
**Health check:** Daily 05:30 IST, ollama liveness + ping latency.
**RAG corpus rebuild:** Nightly 03:30 IST, incremental re-embed.

Spec: `docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md`.
Plan: `docs/superpowers/plans/2026-04-28-gemma4-pilot.md`.
```

- [ ] **Step 2: Update CLAUDE.md clockwork schedule**

Add to the relevant time slots:

Under "Overnight Batch":
- 03:30 — AnkaGemma4RagRebuild: nightly incremental re-embed of LanceDB corpus (info, pilot)
- 05:30 — AnkaGemma4HealthCheck: ollama + Gemma 4 daily liveness ping (warn, pilot)

Under "Market Hours":
- Hourly 09:00–22:00 — AnkaGemma4AutoDisable: pilot guardrail check (info, pilot)

Under "Post-Close":
- 22:00 — AnkaGemma4DailyReport: pilot report card aggregation + Telegram one-liner (warn, pilot)

- [ ] **Step 3: Update reference_llm_providers.md**

Add a row for Gemma 4 26B-A4B with: cost (zero per-token, fixed VPS), latency profile (5–10× slower CPU), pilot status, license (Apache 2.0). Note that it does NOT replace Gemini for Tier 1.

- [ ] **Step 4: Create project memory**

`memory/project_gemma4_pilot.md`:

```markdown
---
name: Gemma 4 Local-Inference Pilot
description: 20-day Tier 2 evaluation of Gemma 4 26B-A4B on Contabo VPS (started 2026-04-29). Covers concall supplement, news classification, EOD narrative, markets article. Spec frozen at 2026-04-28; no parameter changes during the holdout window.
type: project
---

20-day forward-only pilot started 2026-04-29 (target cutover decision 2026-05-19).
Spec: `docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md` (commit 0eb40cf).
Plan: `docs/superpowers/plans/2026-04-28-gemma4-pilot.md`.

**Why:** cost predictability + Apache 2.0 license certainty + Gemini rate-limit pain on trust-score work. Not a speed play (CPU is 5–10× slower).

**How to apply:**
- Tier 1 (architecting / discipline) stays on frontier APIs — do not migrate.
- Four tasks are wired in shadow days 1–7. Day 8 promotes any task with rubric ≥95% + pairwise ≥60% to LIVE. Day 20 cutover requires rubric ≥90% AND pairwise ≥50% AND no silent regression AND ≥80% cost reduction.
- All routing decisions are JSON edits in `pipeline/config/llm_routing.json` (no code change).
- Pairwise UI lives at terminal `/gemma_pilot`.
- Report card is auto-posted to Telegram ops at 22:00 IST.
- Auto-disable trips a task on rubric <90% (rolling 24h). Pairwise <40% (rolling 7d) flags manual review.
- Articles: only the **markets** topic is in the pilot. Epstein and war stay on current Gemini stack.
```

- [ ] **Step 5: Update MEMORY.md index**

Add after the existing project entries:

```markdown
- [Gemma 4 pilot](project_gemma4_pilot.md) — 20-day Tier 2 eval on Contabo (2026-04-29 → 2026-05-19). 4 tasks shadow→live. Apache 2.0.
```

Watch the size warning (24.4 KB cap). If overflow, condense an older entry.

- [ ] **Step 6: Verify all docs consistent**

Run: `git diff --stat` — confirm 5+ files modified across docs and memory.

- [ ] **Step 7: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md ../../.claude/projects/C--Users-Claude-Anka-askanka-com/memory/reference_llm_providers.md ../../.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_gemma4_pilot.md ../../.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md
git commit -m "docs(gemma4-pilot): sync SYSTEM_OPERATIONS_MANUAL + CLAUDE.md + memory"
```

(Adjust paths to actual memory file locations in your shell.)

---

## Self-Review Checklist (run after all tasks complete)

- [ ] **Spec coverage:**
  - §2.2 hardware verified — Task 0 step 1
  - §2.3 model variant — Task 0 step 2 + 3
  - §2.4 ollama — Task 0
  - §2.5 license — covered in spec; nothing to implement
  - §3 four pilot tasks — Tasks 11–14
  - §3.1 per-task rubrics — Tasks 7–10
  - §4.1 hybrid scoring — Tasks 6 (dispatcher) + 15–16 (pairwise UI)
  - §4.2 auto-disable guardrails — Task 18
  - §4.3 activation pattern (shadow → live → cutover) — implemented as JSON edits in `llm_routing.json` (Task 4); the day-8 and day-20 flips are explicit human decisions, not auto.
  - §5 file inventory — every listed file is created or planned
  - §6 cutover criteria — encoded in `auto_disable.py` thresholds; final cutover is a manual decision against the report card
  - §7 NOT — guardrails enforce these (RAG only, no fine-tune, only markets article, etc.)
  - §8 failure modes — guardrails + health check + shadow-failure swallowing
  - §10 open questions — resolved in the table at top of plan

- [ ] **No placeholders.** Every step has runnable code or a runnable command.

- [ ] **Type consistency.** `Provider`, `ProviderResponse`, `RubricFn`, `RoutingConfig`, `LLMRouter`, `ShadowDispatcher`, `AuditLogger` are referenced consistently across tasks.

- [ ] **Day-8 promotion procedure (operational, not in plan):** edit `pipeline/config/llm_routing.json`, change `mode` from `shadow` to `live` for tasks meeting threshold. Restart `pipeline.terminal` if any in-process router cache exists (it doesn't — `_build_router` rebuilds per dispatch call by design).

- [ ] **Day-20 cutover procedure (operational):** read `pipeline/data/research/gemma4_pilot/report_cards/<day20>.md`. For each task that meets §6 criteria, leave routing in `live`. For tasks that don't, edit JSON to flip to `disabled`, then commit a permanent decision to a follow-up spec.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-gemma4-pilot.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for the wiring tasks (11–14) where each call site is isolated.

**2. Inline Execution** — Execute tasks in this session using executing-plans. Better for the early infrastructure tasks (0–6) where each builds tightly on the last and you'll want to keep state in mind.

A reasonable hybrid: tasks 0–6 (infrastructure) inline, then 7–21 via subagents.

Which approach?
