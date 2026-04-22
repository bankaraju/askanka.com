import subprocess
import json
from pathlib import Path

TERMINAL_JS = Path("pipeline/terminal/static/js/components/analysis")


def _envelope_uri() -> str:
    return (TERMINAL_JS / "envelope.js").resolve().as_uri()


def _run(node_src: str) -> dict:
    """Execute Node script, return parsed JSON of its stdout."""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_src],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def test_envelope_defaults():
    uri = _envelope_uri()
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
    uri = _envelope_uri()
    src = f"""
    import {{ makeEnvelope }} from '{uri}';
    const env = makeEnvelope({{engine: 'fcs', ticker: 'X',
      health: {{band: 'BOGUS', detail: 'x'}}}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["health"]["band"] == "UNAVAILABLE"
