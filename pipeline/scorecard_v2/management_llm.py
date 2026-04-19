"""
management_llm.py — Layer 2B of Scorecard V2

Qualitative management scoring via Sonnet LLM.
Sends structured, sector-specific prompts and parses JSON responses.

Blended 50/50 with management_quant.py by the orchestrator (__init__.py).

Key design principle: the LLM MUST score against the sector-specific KPIs
provided in the prompt — not freeform qualitative impressions. This prevents
the old Gemini behaviour of ignoring KPI anchors and freelancing on criteria.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_FALLBACK_SCORE = 50
_AR_YEARS = ["2024-2025", "2023-2024", "2022-2023"]
_AR_MAX_CHARS = 4000
_CONCALL_MAX_CHARS = 4000
_SCREENER_MAX_CHARS = 2000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_text(artifacts_dir: Path, symbol: str, filename: str, max_chars: int = 5000) -> str:
    """Read a text artifact, truncated to max_chars. Returns empty string on miss."""
    path = artifacts_dir / symbol / filename
    if not path.exists():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return raw[:max_chars] if len(raw) > max_chars else raw
    except Exception as exc:  # pragma: no cover
        log.warning("_load_text(%s/%s): %s", symbol, filename, exc)
        return ""


def _build_prompt(
    symbol: str,
    sector: str,
    kpis: list[str],
    ar_texts: list[str],
    concall_text: str,
    screener_about: str,
) -> str:
    """Build the structured Sonnet prompt for one stock."""

    kpi_lines = "\n".join(f"  - {k}" for k in kpis) if kpis else "  - (no sector KPIs defined)"

    ar_block = ""
    for year, text in zip(_AR_YEARS, ar_texts):
        if text.strip():
            ar_block += f"\n### Annual Report {year}\n{text.strip()}\n"
    if not ar_block:
        ar_block = "(No annual report text available)"

    concall_block = concall_text.strip() if concall_text.strip() else "(No concall transcript available)"
    screener_block = screener_about.strip() if screener_about.strip() else "(No screener snapshot available)"

    return f"""You are a rigorous equity analyst scoring management quality for **{symbol}** (sector: {sector}).

## Your task
Score this management team against the SECTOR-SPECIFIC KPIs listed below.
Do NOT substitute your own criteria. Score ONLY what the KPIs ask for.

## Sector KPIs to score against
{kpi_lines}

## Source material

### Screener snapshot (ROE, ROCE, P/E, business description)
{screener_block}

### Annual Reports (excerpts)
{ar_block}

### Concall transcript (most recent, excerpt)
{concall_block}

## Output format
Return ONLY valid JSON — no markdown fences, no commentary outside the JSON.

{{
  "execution_delivery": {{
    "<kpi_name>": {{
      "score": <integer 0-100>,
      "evidence": "<one sentence citing specific data from the source material>"
    }}
  }},
  "strategic_coherence": <integer 0-100>,
  "capital_allocation": <integer 0-100>,
  "disclosure_quality": <integer 0-100>,
  "management_llm_score": <integer 0-100>,
  "biggest_strength": "<one sentence>",
  "biggest_red_flag": "<one sentence, or 'None identified' if clean>",
  "what_street_misses": "<one sentence on what consensus underweights>"
}}

Scoring rules:
- execution_delivery: score each sector KPI independently on 0-100
- management_llm_score: weighted average of execution_delivery scores (equal weights),
  then adjusted ±10 for strategic_coherence and capital_allocation quality
- If source material is absent or too thin for a KPI, score it 50 (neutral, not penalised)
- Be specific: cite numbers, years, or quotes in evidence fields
- Do NOT hallucinate data not present in the source material
"""


# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------

def score_stock_llm(
    symbol: str,
    sector: str,
    kpis: list[str],
    artifacts_dir: Path,
    client: Any = None,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Score one stock using LLM. Returns parsed JSON response.

    Args:
        symbol:        NSE ticker symbol (e.g. "RELIANCE")
        sector:        Sector key from taxonomy (e.g. "Energy")
        kpis:          List of sector-specific KPI strings to score against
        artifacts_dir: Path to opus/artifacts/ root
        client:        anthropic.Anthropic() instance (created if None)
        model:         Sonnet model ID

    Returns:
        dict with keys: execution_delivery, strategic_coherence, capital_allocation,
        disclosure_quality, management_llm_score, biggest_strength, biggest_red_flag,
        what_street_misses. Falls back to {"management_llm_score": 50} on errors.
    """
    # Lazy import so the module is importable without anthropic installed
    try:
        import anthropic as _anthropic
    except ImportError:
        log.error("anthropic package not installed — cannot run LLM scoring")
        return {"management_llm_score": _FALLBACK_SCORE}

    if client is None:
        client = _anthropic.Anthropic()

    # Load source material
    ar_texts = [
        _load_text(artifacts_dir, symbol, f"ar_text_{year}.txt", _AR_MAX_CHARS)
        for year in _AR_YEARS
    ]
    concall_text = _load_text(artifacts_dir, symbol, "concall_text.txt", _CONCALL_MAX_CHARS)

    # Screener about: try screener JSON first, fall back to plain text
    screener_about = ""
    screener_json_path = artifacts_dir / symbol / "screener_stock.json"
    if screener_json_path.exists():
        try:
            sc = json.loads(screener_json_path.read_text(encoding="utf-8"))
            # Pull relevant snapshot fields
            snapshot_fields = ["about", "roe", "roce", "pe", "eps", "sales_growth_5yr",
                                "profit_growth_5yr", "debt_to_equity"]
            lines = []
            for k in snapshot_fields:
                v = sc.get(k)
                if v is not None:
                    lines.append(f"{k}: {v}")
            screener_about = "\n".join(lines)[:_SCREENER_MAX_CHARS]
        except Exception as exc:
            log.debug("screener JSON parse error for %s: %s", symbol, exc)

    if not screener_about:
        screener_about = _load_text(artifacts_dir, symbol, "screener_about.txt", _SCREENER_MAX_CHARS)

    prompt = _build_prompt(symbol, sector, kpis, ar_texts, concall_text, screener_about)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        # Strip markdown fences if the model added them despite instructions
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        result = json.loads(raw_text)

        # Validate / normalise management_llm_score
        score = result.get("management_llm_score", _FALLBACK_SCORE)
        result["management_llm_score"] = max(0, min(100, int(score)))

        log.info("LLM scored %s: %d", symbol, result["management_llm_score"])
        return result

    except json.JSONDecodeError as exc:
        log.warning("LLM JSON parse error for %s: %s", symbol, exc)
        return {"management_llm_score": _FALLBACK_SCORE}
    except Exception as exc:
        log.warning("LLM scoring failed for %s: %s", symbol, exc)
        return {"management_llm_score": _FALLBACK_SCORE}


def score_sector_llm(
    sector: str,
    symbols: list[str],
    kpis: list[str],
    artifacts_dir: Path,
    client: Any = None,
    model: str = "claude-haiku-4-5-20251001",
    delay: float = 1.0,
) -> dict[str, dict]:
    """Score all stocks in a sector via Sonnet.

    Args:
        sector:        Sector key (e.g. "Energy")
        symbols:       List of NSE ticker symbols in this sector
        kpis:          Sector-specific KPI list
        artifacts_dir: Path to opus/artifacts/ root
        client:        anthropic.Anthropic() instance (shared across calls)
        model:         Sonnet model ID
        delay:         Seconds to sleep between API calls (rate-limit courtesy)

    Returns:
        {symbol: llm_result_dict} for every symbol in the sector.
        Missing/failed stocks get {"management_llm_score": 50}.
    """
    # Lazy import
    try:
        import anthropic as _anthropic
    except ImportError:
        log.error("anthropic package not installed — skipping LLM sector scoring")
        return {s: {"management_llm_score": _FALLBACK_SCORE} for s in symbols}

    if client is None:
        client = _anthropic.Anthropic()

    results: dict[str, dict] = {}
    total = len(symbols)

    for i, symbol in enumerate(symbols, 1):
        log.info("LLM scoring %s (%d/%d) in sector=%s", symbol, i, total, sector)
        results[symbol] = score_stock_llm(
            symbol=symbol,
            sector=sector,
            kpis=kpis,
            artifacts_dir=artifacts_dir,
            client=client,
            model=model,
        )
        if i < total and delay > 0:
            time.sleep(delay)

    return results
