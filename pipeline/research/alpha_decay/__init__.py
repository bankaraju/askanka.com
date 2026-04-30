"""Alpha decay monitoring for live and deprecated-but-active spread baskets.

Reads forward-shadow ledgers, computes rolling 30d Sharpe, compares against
in-sample Sharpe frozen at pre-registration time, emits HEALTHY/WATCH/
DECAYING/KILL verdict per basket. No auto-archival — human is the gate.
"""
