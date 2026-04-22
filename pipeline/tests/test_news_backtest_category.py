import json
from pipeline.news_backtest import run_backtest

def test_verdicts_all_carry_nonempty_category(tmp_path, monkeypatch):
    events = {
        "last_scan": "2026-04-22T09:00:00+05:30",
        "events": [
            {"title": "SUZLON Q4 results beat", "matched_stocks": ["SUZLON"],
             "categories": ["results_announcement"]},
            {"title": "Mystery news", "matched_stocks": ["RELIANCE"], "categories": []},
        ],
    }
    events_file = tmp_path / "news_events_today.json"
    events_file.write_text(json.dumps(events))
    verdicts_file = tmp_path / "news_verdicts.json"
    import pipeline.news_backtest as nb
    monkeypatch.setattr(nb, "EVENTS_TODAY", events_file)
    monkeypatch.setattr(nb, "VERDICTS_FILE", verdicts_file)
    monkeypatch.setattr(nb, "EVENTS_HISTORY", tmp_path / "missing.json")
    monkeypatch.setattr(nb, "load_stock_prices", lambda s: None)

    run_backtest(target_date="2026-04-22")

    written = json.loads(verdicts_file.read_text())
    assert len(written) == 1  # mystery event without categories is dropped
    assert written[0]["symbol"] == "SUZLON"
    assert written[0]["category"] == "results_announcement"
    assert written[0]["category"] != ""
