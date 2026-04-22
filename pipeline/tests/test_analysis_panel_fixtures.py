"""Golden-HTML regression: each (engine × verdict) combo has a frozen fixture.
If the adapter + panel output stops matching a fixture, test fails. Regenerate
fixtures deliberately — these are tripwires for silent UI drift."""
import json
import subprocess
from pathlib import Path

TERMINAL_JS = Path("pipeline/terminal/static/js/components/analysis")
FIXTURE_DIR = Path("pipeline/tests/fixtures/analysis-panel")


def _uri(rel: str) -> str:
    return (TERMINAL_JS / rel).resolve().as_uri()


CASES = [
    {
      "name": "fcs-green-long",
      "adapter": "fcs",
      "ticker": "RELIANCE",
      "raw": {
        "score": 72, "band": "HIGH", "health": "GREEN", "source": "own",
        "computed_at": "2026-04-23T14:00:00+05:30",
        "mean_auc": 0.61, "min_fold_auc": 0.54, "n_folds": 6,
        "top_features": [
          {"name": "ticker_rs_10d", "contribution": 0.38},
          {"name": "sector_5d_return", "contribution": 0.22},
          {"name": "realized_vol_60d", "contribution": -0.11},
        ],
      },
      "now": "2026-04-23T14:00:00+05:30",
    },
    {
      "name": "ta-unavailable-non-pilot",
      "adapter": "ta", "ticker": "ITC", "raw": None,
      "now": "2026-04-23T16:00:00+05:30",
    },
    {
      "name": "spread-pass-high",
      "adapter": "spread", "ticker": "HAL",
      "raw": {"name": "Defence vs IT", "conviction": "HIGH",
              "regime_fit": True, "gate_status": "PASS",
              "score": 85, "z_score": 2.1, "action": "LONG",
              "long_legs": ["HAL"], "short_legs": ["INFY"],
              "computed_at": "2026-04-23T13:57:00+05:30"},
      "now": "2026-04-23T14:00:00+05:30",
    },
    {
      "name": "corr-long-negative-sigma",
      "adapter": "corr", "ticker": "HAL",
      "raw": {"sigma": -2.4, "sector_divergence": -1.2,
              "volume_anomaly": 0.3, "trust_delta": 0.1,
              "computed_at": "2026-04-23T13:57:00+05:30"},
      "now": "2026-04-23T14:00:00+05:30",
    },
]


def _render_html(case):
    adapter_uri = _uri(f"adapters/{case['adapter']}.js")
    panel_uri = _uri("panel.js")
    src = f"""
    import {{ adapt }} from '{adapter_uri}';
    import {{ renderCardHtml }} from '{panel_uri}';
    const env = adapt({json.dumps(case["ticker"])}, {json.dumps(case["raw"])});
    console.log(renderCardHtml(env, {json.dumps(case["now"])}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", src],
        capture_output=True, text=True, timeout=15, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_all_fixtures_match():
    mismatches = []
    for case in CASES:
        fixture = FIXTURE_DIR / f"{case['name']}.html"
        rendered = _render_html(case)
        if not fixture.exists():
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text(rendered, encoding="utf-8")
            continue
        expected = fixture.read_text(encoding="utf-8").strip()
        if rendered != expected:
            mismatches.append(case["name"])
    assert not mismatches, f"fixture drift: {mismatches}"
