"""Phase C sigma-weighted sizing backtest (read-only).

Backlog #104. Tests the user hypothesis (2026-04-23): position sizing
scaled by |z| would have materially helped 3-sigma / 4-sigma cases
where conviction is strongest.

Compares three sizing schemes on the mechanical replay v2 SHORT roster:
1. fixed   — INR 50k per trade (status quo)
2. sigma   — notional proportional to |z| (normalised so total notional matches)
3. parity  — notional proportional to |z| / ATR_pct (vol-parity)

Reports per-scheme Sharpe / max-DD / hit-rate, plus per |z|-bucket
hit-rate and avg captured move.

Read-only — does not change production sizing until verdict supports it.
"""
