"""
NSE/BSE Trading Calendar — Holiday check for Indian stock markets.
All scheduled tasks MUST call is_trading_day() before generating signals.
"""
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# NSE holidays 2026 (official list — update annually in January)
# Source: https://www.nseindia.com/resources/exchange-communication-holidays
NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day",
    "2026-02-17": "Mahashivratri",
    "2026-03-10": "Holi",
    "2026-03-30": "Id-Ul-Fitr (Ramadan)",
    "2026-03-31": "Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-25": "Buddha Purnima",
    "2026-06-07": "Bakri Id",
    "2026-07-07": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-08-16": "Parsi New Year",
    "2026-09-05": "Milad-un-Nabi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-10-21": "Dussehra (additional)",
    "2026-11-09": "Diwali (Laxmi Pujan)",
    "2026-11-10": "Diwali Balipratipada",
    "2026-11-27": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",
}


def is_trading_day(dt=None):
    """Return True if NSE is open on this date. Checks weekends + gazetted holidays."""
    if dt is None:
        dt = datetime.now(IST)
    # Weekend
    if dt.weekday() >= 5:
        return False
    # Holiday
    date_str = dt.strftime("%Y-%m-%d")
    if date_str in NSE_HOLIDAYS_2026:
        return False
    return True


def get_holiday_name(dt=None):
    """Return the holiday name if today is a holiday, else None."""
    if dt is None:
        dt = datetime.now(IST)
    return NSE_HOLIDAYS_2026.get(dt.strftime("%Y-%m-%d"))


def next_trading_day(dt=None):
    """Return the next trading day after the given date."""
    if dt is None:
        dt = datetime.now(IST)
    dt = dt + timedelta(days=1)
    while not is_trading_day(dt):
        dt = dt + timedelta(days=1)
    return dt
