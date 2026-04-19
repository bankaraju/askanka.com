"""Simple script to run open price capture."""
from spread_leaderboard import capture_open_prices
capture_open_prices()

try:
    from pipeline.atm_premium_capture import run as capture_atm
    capture_atm()
except Exception as e:
    print(f"ATM premium capture failed: {e}")
