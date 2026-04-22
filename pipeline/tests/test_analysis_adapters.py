# -*- coding: utf-8 -*-
import subprocess
import json
from pathlib import Path

TERMINAL_JS = Path("pipeline/terminal/static/js/components/analysis")


def _js_uri(name: str) -> str:
    return (TERMINAL_JS / name).resolve().as_uri()


def _run(node_src: str) -> dict:
    """Execute Node script, return parsed JSON of its stdout."""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_src],
        capture_output=True, text=True, timeout=15, encoding="utf-8",
    )
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def test_envelope_defaults():
    uri = _js_uri("envelope.js")
    src = f"""
    import {{ makeEnvelope }} from '{uri}';
    const env = makeEnvelope({{engine: 'fcs', ticker: 'RELIANCE'}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "fcs"
    assert env["ticker"] == "RELIANCE"
    assert env["verdict"] == "UNAVAILABLE"
    assert env["conviction_0_100"] is None
    assert env["evidence"] == []
    assert env["calibration"] == "heuristic"


def test_envelope_validates_health_band():
    uri = _js_uri("envelope.js")
    src = f"""
    import {{ makeEnvelope }} from '{uri}';
    const env = makeEnvelope({{engine: 'fcs', ticker: 'X',
      health: {{band: 'BOGUS', detail: 'x'}}}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["health"]["band"] == "UNAVAILABLE"


def test_health_colors_match_tokens():
    uri = _js_uri("health.js")
    src = f"""
    import {{ bandToCssVar }} from '{uri}';
    const out = {{
      green: bandToCssVar('GREEN'),
      amber: bandToCssVar('AMBER'),
      red:   bandToCssVar('RED'),
      unav:  bandToCssVar('UNAVAILABLE'),
      weird: bandToCssVar('BOGUS'),
    }};
    console.log(JSON.stringify(out));
    """
    out = _run(src)
    assert out["green"] == "var(--accent-green)"
    assert out["amber"] == "var(--accent-gold)"
    assert out["red"] == "var(--accent-red)"
    assert out["unav"] == "var(--text-muted)"
    assert out["weird"] == "var(--text-muted)"


def test_fmt_relative_labels():
    uri = _js_uri("health.js")
    src = f"""
    import {{ fmtRelative }} from '{uri}';
    const now = new Date('2026-04-23T14:00:00+05:30').toISOString();
    const labels = {{
      just_now: fmtRelative(new Date('2026-04-23T13:57:00+05:30').toISOString(), now),
      yesterday: fmtRelative(new Date('2026-04-21T16:00:00+05:30').toISOString(), now),
      missing: fmtRelative(null, now),
    }};
    console.log(JSON.stringify(labels));
    """
    out = _run(src)
    assert "min" in out["just_now"]
    assert "yesterday" in out["yesterday"].lower() or "day" in out["yesterday"].lower()
    assert out["missing"] == chr(8212)  # em-dash U+2014
