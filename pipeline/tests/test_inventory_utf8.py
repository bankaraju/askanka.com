from pathlib import Path
import json

INV = Path(__file__).parent.parent / "config" / "anka_inventory.json"


def test_inventory_is_valid_utf8_no_mojibake():
    raw = INV.read_bytes()
    # Must decode as UTF-8 cleanly
    text = raw.decode("utf-8")
    # No Windows-1252 mojibake for em-dash
    assert "â€" not in text, "inventory has Windows-1252 em-dash mojibake"
    # Must parse as valid JSON
    data = json.loads(text)
    assert "tasks" in data
