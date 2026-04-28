"""Phase C × FCS bucket backtest (read-only).

Track A #12 / Backlog #90. Replays Phase C SHORT events from the
mechanical replay v2 roster, retro-scores each event with current FCS
ticker_feature_models.json coefficients applied to that date's PIT
features, buckets outcomes by score band, and reports win-rate +
average return per bucket.

Monotonic result -> justifies Rule A (veto >= 55) and Rule C (size
proportional to 100 - score). Flat result -> FCS is noise for
Phase C intraday and stays display-only.
"""
