#!/usr/bin/env python3
"""
Stocks Screener — Data Gathering
=================================
Pulls top US-listed losers (mkt cap >= 50B, change <= -3%) from Yahoo Finance,
enriches each candidate with sector context, peer behavior, and recent news,
and outputs a JSON to stdout for downstream classification by Claude.

Usage:
    python3 gather_data.py [--min-cap 50] [--max-change -3] [--max-tickers 20]

Output JSON shape:
    {
      "as_of": "2026-05-14T13:35:00-04:00",
      "session_label": "09:35",
      "market_context": {"spy_change_pct": -0.3, "qqq_change_pct": -0.5},
      "screened_total": 47,
      "candidates": [
        {
          "ticker": "QCOM",
          "name": "Qualcomm",
          "exchange": "NasdaqGS",
          "sector": "Technology",
          "industry": "Semiconductors",
          "price": 175.32,
          "change_pct": -6.14,
          "market_cap_b": 210.9,
          "volume": 24500000,
          "avg_volume_30d": 11200000,
          "volume_ratio": 2.18,
          "range_52w": {"low": 120.0, "high": 235.0, "position_pct": 48.1},
          "sector_etf": {"symbol": "XLK", "change_pct": -0.5},
          "peers": [{"ticker": "AVGO", "change_pct": -1.2}, ...],
          "news": [{"title": "...", "summary": "...", "url": "...",
                    "source": "...", "published_at": "..."}, ...]
        }
      ]
    }
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import yfinance as yf
from yfinance import EquityQuery


# Maps Yahoo's "sector" to the SPDR sector ETF most market participants watch.
SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
}


def screen_losers(min_cap_billions: float, max_change_pct: float, size: int) -> list[dict[str, Any]]:
    """Run the Yahoo custom screener for US-listed large-cap losers."""
    query = EquityQuery(
        "and",
        [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("gte", ["intradaymarketcap", int(min_cap_billions * 1e9)]),
            EquityQuery("lte", ["percentchange", max_change_pct]),
            EquityQuery(
                "or",
                [
                    EquityQuery("eq", ["exchange", "NMS"]),  # NASDAQ
                    EquityQuery("eq", ["exchange", "NYQ"]),  # NYSE
                ],
            ),
        ],
    )
    res = yf.screen(query, sortField="percentchange", sortAsc=True, size=size)
    return res.get("quotes", [])


def market_context() -> dict[str, Any]:
    """Snapshot of 5 MECE macro indicators for a 360° market view:
    - SPY (S&P 500) : broad equity direction
    - VIX            : fear/complacency
    - US10Y (^TNX)   : risk-free rate / inflation expectations
    - DXY            : USD strength / global risk-on-off
    - WTI (CL=F)     : commodity demand / global economy proxy
    """
    indicators = [
        ("SPY", "spy", "level_pct"),       # report % change (equity index proxy)
        ("^VIX", "vix", "level"),          # report absolute level (fear gauge)
        ("^TNX", "us10y", "level"),        # report yield level (rate signal)
        ("DX-Y.NYB", "dxy", "level_pct"),  # report % change (currency direction)
        ("CL=F", "wti", "level_pct"),      # report % change (commodity direction)
    ]
    out = {}
    for sym, key, mode in indicators:
        try:
            info = yf.Ticker(sym).fast_info
            last = info.last_price
            prev = info.previous_close
            change_pct = ((last - prev) / prev * 100) if (prev and last) else None
            out[key] = {
                "symbol": sym,
                "last": round(last, 2) if last else None,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "display_mode": mode,
            }
        except Exception:
            out[key] = {"symbol": sym, "last": None, "change_pct": None, "display_mode": mode}
    return out


def sector_etf_snapshot(sector: str | None) -> dict[str, Any] | None:
    """Pull the day's % change for the sector's SPDR ETF, if known."""
    if not sector or sector not in SECTOR_ETF:
        return None
    sym = SECTOR_ETF[sector]
    try:
        info = yf.Ticker(sym).fast_info
        change = ((info.last_price - info.previous_close) / info.previous_close) * 100
        return {"symbol": sym, "change_pct": round(change, 2)}
    except Exception:
        return None


def peer_snapshot(industry: str | None, exclude: str, max_peers: int = 5) -> list[dict[str, Any]]:
    """Find peers in the same industry and pull their day change. Used to detect
    sector contagion vs idiosyncratic moves."""
    if not industry:
        return []
    try:
        # Look for large-cap peers in the same industry
        query = EquityQuery(
            "and",
            [
                EquityQuery("eq", ["region", "us"]),
                EquityQuery("eq", ["industry", industry]),
                EquityQuery("gte", ["intradaymarketcap", 10_000_000_000]),  # >=10B peers
            ],
        )
        res = yf.screen(query, sortField="intradaymarketcap", sortAsc=False, size=10)
        peers = []
        for q in res.get("quotes", []):
            sym = q.get("symbol")
            if not sym or sym == exclude:
                continue
            peers.append(
                {
                    "ticker": sym,
                    "name": (q.get("shortName") or q.get("longName") or "")[:40],
                    "change_pct": round(q.get("regularMarketChangePercent") or 0, 2),
                    "market_cap_b": round((q.get("marketCap") or 0) / 1e9, 1),
                }
            )
            if len(peers) >= max_peers:
                break
        return peers
    except Exception:
        return []


def _news_from_yahoo(symbol: str, cutoff: datetime) -> list[dict[str, Any]]:
    """Yahoo Finance news via yfinance."""
    out = []
    try:
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []
    for n in items:
        content = n.get("content", n)
        title = content.get("title")
        if not title:
            continue
        pub_raw = content.get("pubDate") or content.get("providerPublishTime")
        pub_dt = None
        if isinstance(pub_raw, (int, float)):
            pub_dt = datetime.fromtimestamp(pub_raw, tz=timezone.utc)
        elif isinstance(pub_raw, str):
            try:
                pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        if pub_dt and pub_dt < cutoff:
            continue
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        url = url_obj.get("url") if isinstance(url_obj, dict) else url_obj
        provider = (content.get("provider") or {}).get("displayName") or "Yahoo"
        out.append({
            "title": title,
            "summary": (content.get("summary") or "")[:150],
            "url": url,
            "source": provider,
            "published_at": pub_dt.isoformat() if pub_dt else None,
            "origin": "yahoo",
        })
    return out


def _news_from_google_rss(symbol: str, cutoff: datetime, max_items: int = 20, company_name: str = None) -> list[dict[str, Any]]:
    """Google News RSS — gratuit, sans clé, retourne ~100 articles indexés.
    Pour les tickers courts (1-2 caractères : F, B, T, SE, BA), utiliser le nom de société
    plutôt que le ticker pour éviter les faux positifs avec des sociétés européennes
    qui ont 'SE' ou 'AG' dans leur ticker."""
    out = []
    try:
        if company_name and len(symbol) <= 3:
            # Strip common corporate suffixes pour query plus propre
            clean_name = re.sub(r'\s+(Inc\.?|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|Holdings?|Group|PLC)$',
                                '', company_name, flags=re.IGNORECASE).strip()
            query = f'"{clean_name}" {symbol} stock'
        else:
            query = f"{symbol} stock"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            # Parse published date
            pub_dt = None
            if entry.get("published_parsed"):
                try:
                    pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            if pub_dt and pub_dt < cutoff:
                continue
            # Extract source name — format "Title - Source"
            source_name = (entry.get("source") or {}).get("title") or "Google News"
            # Clean title (remove trailing " - SourceName")
            if title.endswith(f" - {source_name}"):
                title = title[: -len(f" - {source_name}")]
            out.append({
                "title": title,
                "summary": (entry.get("summary") or "")[:150],
                "url": entry.get("link"),
                "source": source_name,
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "origin": "google_news",
            })
    except Exception:
        pass
    return out


def _news_from_finnhub(symbol: str, cutoff: datetime, max_items: int = 20) -> list[dict[str, Any]]:
    """Finnhub free tier (60 calls/min) — requires FINNHUB_API_KEY env var.
    Returns empty list if key not set."""
    token = os.environ.get("FINNHUB_API_KEY")
    if not token:
        return []
    out = []
    try:
        today = datetime.now(timezone.utc).date()
        frm = (today - timedelta(days=3)).isoformat()
        to = today.isoformat()
        url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={frm}&to={to}&token={token}"
        req = urllib.request.Request(url, headers={"User-Agent": "stocks-screener/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        for item in data[:max_items]:
            pub_dt = datetime.fromtimestamp(item.get("datetime", 0), tz=timezone.utc) if item.get("datetime") else None
            if pub_dt and pub_dt < cutoff:
                continue
            out.append({
                "title": item.get("headline", "").strip(),
                "summary": (item.get("summary") or "")[:150],
                "url": item.get("url"),
                "source": item.get("source", "Finnhub"),
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "origin": "finnhub",
            })
    except Exception:
        pass
    return out


def _normalize_title_for_dedup(title: str) -> str:
    """Pour la dedup : lowercase, sans ponctuation, sans articles courts."""
    import re
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\b(the|a|an|of|for|to|in|on|at|is|are|was|were)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def recent_news(symbol: str, max_items: int = 4, lookback_hours: int = 48, company_name: str = None) -> list[dict[str, Any]]:
    """Aggregateur multi-source : Yahoo + Google News RSS + Finnhub (si clé dispo).
    Déduplique par titre normalisé, trie par date desc, limite au max_items.
    Le paramètre company_name améliore Google News pour les tickers courts.

    DISCIPLINE PAYLOAD (Levier 4) : max 4 news par ticker, summary 150 chars max.
    Au final on n'en sélectionne qu'1 pour le dashboard, donc 4 est largement suffisant."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    all_items = []
    all_items.extend(_news_from_yahoo(symbol, cutoff))
    all_items.extend(_news_from_google_rss(symbol, cutoff, company_name=company_name))
    all_items.extend(_news_from_finnhub(symbol, cutoff))

    # Dedup par titre normalisé — garde la première occurrence (donc Yahoo prioritaire,
    # puis Google, puis Finnhub) qui a généralement le meilleur URL canonique.
    seen = set()
    deduped = []
    for item in all_items:
        key = _normalize_title_for_dedup(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # Sort par date descendante (most recent first)
    def _sort_key(x):
        d = x.get("published_at")
        if not d:
            return ""
        return d
    deduped.sort(key=_sort_key, reverse=True)

    return deduped[:max_items]


def enrich_ticker(quote: dict[str, Any]) -> dict[str, Any]:
    """Enrich a screener hit with sector context, peers, and news."""
    symbol = quote.get("symbol")
    ticker = yf.Ticker(symbol)

    # Pull richer info — sector, industry, volume averages
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    sector = info.get("sector")
    industry = info.get("industry")
    avg_vol_30d = info.get("averageVolume") or info.get("averageDailyVolume3Month")
    current_vol = quote.get("regularMarketVolume") or info.get("regularMarketVolume")
    range_low = info.get("fiftyTwoWeekLow") or quote.get("fiftyTwoWeekLow")
    range_high = info.get("fiftyTwoWeekHigh") or quote.get("fiftyTwoWeekHigh")
    price = quote.get("regularMarketPrice") or info.get("regularMarketPrice")

    # Position in 52w range as %  (0% = at low, 100% = at high)
    range_pos_pct = None
    if range_low and range_high and price and range_high > range_low:
        range_pos_pct = round(((price - range_low) / (range_high - range_low)) * 100, 1)

    return {
        "ticker": symbol,
        "name": quote.get("shortName") or quote.get("longName") or info.get("shortName"),
        "exchange": quote.get("fullExchangeName") or info.get("exchange"),
        "sector": sector,
        "industry": industry,
        "price": round(price, 2) if price else None,
        "change_pct": round(quote.get("regularMarketChangePercent") or 0, 2),
        "change_dollar": round(quote.get("regularMarketChange") or 0, 2),
        "market_cap_b": round((quote.get("marketCap") or 0) / 1e9, 1),
        "volume": current_vol,
        "avg_volume_30d": avg_vol_30d,
        "volume_ratio": round(current_vol / avg_vol_30d, 2) if (current_vol and avg_vol_30d) else None,
        "range_52w": {
            "low": round(range_low, 2) if range_low else None,
            "high": round(range_high, 2) if range_high else None,
            "position_pct": range_pos_pct,
        },
        "sector_etf": sector_etf_snapshot(sector),
        "peers": peer_snapshot(industry, exclude=symbol),
        "news": recent_news(symbol),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-cap", type=float, default=50.0, help="Min market cap in billions USD")
    parser.add_argument("--max-change", type=float, default=-3.0, help="Max day change pct (negative)")
    parser.add_argument("--max-tickers", type=int, default=250, help="Max candidates (default 250 = effectively unlimited; Yahoo screener API hard cap)")
    parser.add_argument("--session-label", type=str, default=None, help="e.g. '09:35'")
    args = parser.parse_args()

    # Run the screener
    raw_quotes = screen_losers(args.min_cap, args.max_change, args.max_tickers)

    # Enrich each (this is where the per-ticker work happens)
    candidates = []
    for q in raw_quotes:
        try:
            candidates.append(enrich_ticker(q))
        except Exception as e:
            # Don't fail the whole run on one bad ticker
            candidates.append(
                {
                    "ticker": q.get("symbol"),
                    "name": q.get("shortName"),
                    "change_pct": round(q.get("regularMarketChangePercent") or 0, 2),
                    "market_cap_b": round((q.get("marketCap") or 0) / 1e9, 1),
                    "_error": f"{type(e).__name__}: {str(e)[:200]}",
                }
            )

    now = datetime.now().astimezone()
    output = {
        "as_of": now.isoformat(),
        "session_label": args.session_label or now.strftime("%H:%M"),
        "market_context": market_context(),
        "filters": {
            "min_cap_b": args.min_cap,
            "max_change_pct": args.max_change,
            "exchanges": ["NYSE", "NASDAQ"],
        },
        "screened_total": len(raw_quotes),
        "candidates": candidates,
    }

    json.dump(output, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
