#!/usr/bin/env python3
"""
Fetch quick quote (price + change_pct) for a list of tickers.
Used by the scheduled task to enrich the Réseau de valeur cards after
Claude has identified which tickers populate each quadrant.

Usage:
    python3 fetch_quotes.py AAPL TSM ASML
    python3 fetch_quotes.py --json AAPL TSM ASML  # output JSON instead of table
"""

import argparse
import json
import sys

import yfinance as yf


def fetch(symbols):
    out = []
    for sym in symbols:
        try:
            info = yf.Ticker(sym).fast_info
            last = info.last_price
            prev = info.previous_close
            change_pct = ((last - prev) / prev * 100) if (last and prev) else None
            out.append({
                "ticker": sym,
                "price": round(last, 2) if last else None,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            })
        except Exception as e:
            out.append({
                "ticker": sym,
                "price": None,
                "change_pct": None,
                "error": f"{type(e).__name__}: {str(e)[:120]}",
            })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("symbols", nargs="+", help="Tickers to quote")
    p.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = p.parse_args()

    results = fetch(args.symbols)
    if args.json:
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in results:
            if r.get("error"):
                print(f"{r['ticker']:<8}  ERROR  {r['error']}")
            else:
                cp = r['change_pct']
                cp_str = f"{cp:+.2f}%" if cp is not None else "—"
                print(f"{r['ticker']:<8}  ${r['price']:>8.2f}  {cp_str:>8}")


if __name__ == "__main__":
    main()
