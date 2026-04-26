"""Phase 2 alias resolver — close the 4 alias gaps from Phase 1 §17 caveat (c).

Truth source: docs/superpowers/specs/tickers list .xlsx +
pipeline/data/kite_cache/instruments_nse.csv +
pipeline/data/fno_universe_history.json.

Verified 2026-04-26. Each mapping cites the historical event in
pipeline/data/research/etf_v3_evaluation/phase_2_backtest/aliases_resolution.md.
Value = None means documented exclusion (delisted with no tradable successor
in the v0.2 window 2026-02-26..2026-04-23).
"""
from __future__ import annotations

# Verified 2026-04-26 against:
#   - pipeline/data/kite_cache/instruments_nse.csv   (NSE EQ spot)
#   - pipeline/data/kite_cache/instruments_nfo.csv   (NFO futures)
#   - pipeline/data/fno_universe_history.json        (monthly F&O snapshots)
#   - docs/superpowers/specs/tickers list .xlsx      (PIT name-change registry)
KNOWN_ALIASES: dict[str, str | None] = {
    # L&T Finance Holdings (LTFH) → L&T Finance (LTF).
    # NSE renamed the symbol to LTF as part of the L&T Finance restructuring;
    # LTF is present in NSE spot instruments (token 6386689), NFO futures, and
    # the FNO universe Feb 2026 snapshot. The Phase 1 failure was caused by the
    # "&" character in the old symbol making token lookup fail.
    "L&TFH": "LTF",

    # LTI Mindtree (LTIM, formed by merger of L&T Infotech + Mindtree) was
    # renamed to LTM on NSE in early 2026. LTIM was in the FNO universe through
    # Jan 2026 but dropped from the Feb 2026 snapshot; LTM appeared in its place
    # (FNO Feb 2026 snapshot confirmed). LTM has NSE spot token 4561409 and
    # active NFO futures. The v0.2 backfill window starts 2026-02-26, so LTM is
    # the correct symbol for the entire window.
    "LTIM": "LTM",

    # Zomato Ltd rebranded to Eternal Limited effective early 2026.
    # NSE instruments file shows tradingsymbol=ETERNAL, name="ETERNAL - ZOMATO"
    # (token 1304833). ETERNAL is in the FNO universe from Feb 2026 snapshot.
    "ZOMATO": "ETERNAL",

    # United Spirits (formerly McDowell & Company Ltd, NSE: MCDOWELL-N) trades
    # as UNITDSPR on NSE (token 2674433). UNITDSPR is present in NSE spot,
    # NFO futures, and the FNO universe Feb 2026 snapshot.
    "MCDOWELL-N": "UNITDSPR",
}


def resolve_alias(ticker: str) -> str | None:
    """Return modern tradable symbol, or None if documented exclusion.

    Unknown tickers are returned unchanged (pass-through).
    """
    return KNOWN_ALIASES.get(ticker, ticker)
