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


def test_panel_renders_full_envelope():
    uri = _js_uri("panel.js")
    src = f"""
    import {{ renderCardHtml }} from '{uri}';
    const env = {{
      engine: 'fcs', ticker: 'RELIANCE', verdict: 'LONG',
      conviction_0_100: 72,
      evidence: [{{name: 'rs_10d', contribution: 0.38, direction: 'pos'}}],
      health: {{band: 'GREEN', detail: 'mean AUC 0.61'}},
      calibration: 'walk_forward',
      computed_at: '2026-04-23T13:57:00+05:30',
      source: 'own',
    }};
    const html = renderCardHtml(env, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{html}}));
    """
    out = _run(src)
    h = out["html"]
    assert "RELIANCE" in h
    assert "LONG" in h
    assert "72" in h
    assert "var(--accent-gold)" in h
    assert "GREEN" in h


def test_panel_renders_unavailable_with_reason():
    uri = _js_uri("panel.js")
    src = f"""
    import {{ renderCardHtml }} from '{uri}';
    const env = {{
      engine: 'ta', ticker: 'ITC', verdict: 'UNAVAILABLE',
      conviction_0_100: null, evidence: [],
      health: {{band: 'UNAVAILABLE', detail: 'pilot'}},
      calibration: 'heuristic',
      empty_state_reason: 'TA pilot \u2014 RELIANCE only, 212 tickers await v2 rollout',
    }};
    const html = renderCardHtml(env, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{html}}));
    """
    out = _run(src)
    assert "TA pilot" in out["html"]
    assert "ITC" in out["html"]


def test_panel_calibration_styling():
    uri = _js_uri("panel.js")
    src = f"""
    import {{ renderCardHtml }} from '{uri}';
    const wf = {{engine:'fcs',ticker:'X',verdict:'LONG',conviction_0_100:72,
                calibration:'walk_forward',evidence:[],
                health:{{band:'GREEN',detail:''}},computed_at:'2026-04-23T14:00:00+05:30'}};
    const h  = {{engine:'spread',ticker:'X',verdict:'LONG',conviction_0_100:60,
                calibration:'heuristic',evidence:[],
                health:{{band:'GREEN',detail:''}},computed_at:'2026-04-23T14:00:00+05:30'}};
    const wfHtml = renderCardHtml(wf, '2026-04-23T14:00:00+05:30');
    const heuristicHtml = renderCardHtml(h, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{wf: wfHtml, heuristic: heuristicHtml}}));
    """
    out = _run(src)
    assert "var(--accent-gold)" in out["wf"]
    assert "var(--text-muted)" in out["heuristic"]
    # The class attribute looks like: class="analysis-card__conviction analysis-card__conviction--heuristic"
    # Check for the modifier class substring (tightened from the original spec assertion).
    assert "analysis-card__conviction--heuristic" in out["heuristic"]
