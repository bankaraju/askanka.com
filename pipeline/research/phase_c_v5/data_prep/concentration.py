"""Load and query the static sector concentration map."""
from __future__ import annotations

import json
from pathlib import Path


def load_concentration(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def top_n_constituents(data: dict, index: str, n: int) -> list[dict]:
    entries = list(data.get(index, {}).get("constituents", []))
    entries.sort(key=lambda c: c["weight"], reverse=True)
    return entries[:n]


def is_in_top_bucket(data: dict, index: str, symbol: str) -> bool:
    entries = sorted(data.get(index, {}).get("constituents", []),
                     key=lambda c: c["weight"], reverse=True)
    threshold = data.get(index, {}).get("top_n_threshold", 0.70)
    cum = 0.0
    for e in entries:
        cum += e["weight"]
        if e["symbol"] == symbol:
            return True
        if cum >= threshold:
            break
    return False
