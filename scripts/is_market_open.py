#!/usr/bin/env python3
"""
US market open check — appelé en tout début de scheduled task pour éviter de
brûler des tokens quand NYSE/NASDAQ sont fermés (week-ends + jours fériés US).

Usage:
    python3 is_market_open.py           # exit 0 si ouvert, 1 si fermé
    python3 is_market_open.py --verbose # explique pourquoi

Liste des fériés boursiers US 2026-2028 hardcodée (jours où NYSE/NASDAQ fermés).
Source officielle : NYSE Holiday calendar (https://www.nyse.com/markets/hours-calendars).
"""

import argparse
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

# Jours fériés boursiers US — NYSE/NASDAQ fermés ces jours-là (full close, pas early close)
US_MARKET_HOLIDAYS = {
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 1, 19):  "Martin Luther King Jr. Day",
    date(2026, 2, 16):  "Presidents Day",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 5, 25):  "Memorial Day",
    date(2026, 6, 19):  "Juneteenth",
    date(2026, 7, 3):   "Independence Day (observed)",
    date(2026, 9, 7):   "Labor Day",
    date(2026, 11, 26): "Thanksgiving",
    date(2026, 12, 25): "Christmas",
    # 2027
    date(2027, 1, 1):   "New Year's Day",
    date(2027, 1, 18):  "Martin Luther King Jr. Day",
    date(2027, 2, 15):  "Presidents Day",
    date(2027, 3, 26):  "Good Friday",
    date(2027, 5, 31):  "Memorial Day",
    date(2027, 6, 18):  "Juneteenth (observed)",
    date(2027, 7, 5):   "Independence Day (observed)",
    date(2027, 9, 6):   "Labor Day",
    date(2027, 11, 25): "Thanksgiving",
    date(2027, 12, 24): "Christmas (observed)",
    # 2028
    date(2028, 1, 17):  "Martin Luther King Jr. Day",
    date(2028, 2, 21):  "Presidents Day",
    date(2028, 4, 14):  "Good Friday",
    date(2028, 5, 29):  "Memorial Day",
    date(2028, 6, 19):  "Juneteenth",
    date(2028, 7, 4):   "Independence Day",
    date(2028, 9, 4):   "Labor Day",
    date(2028, 11, 23): "Thanksgiving",
    date(2028, 12, 25): "Christmas",
}


def check(now: datetime = None) -> tuple[bool, str]:
    """Retourne (is_open, reason)."""
    if now is None:
        now = datetime.now(ZoneInfo("America/New_York"))
    today = now.date()
    weekday = today.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:
        return False, f"Week-end ({today.strftime('%A')})"
    if today in US_MARKET_HOLIDAYS:
        return False, f"Férié US — {US_MARKET_HOLIDAYS[today]}"
    return True, f"Marché ouvert ({today.strftime('%A')} {today.isoformat()})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    is_open, reason = check()
    if args.verbose:
        print(reason)
    sys.exit(0 if is_open else 1)


if __name__ == "__main__":
    main()
