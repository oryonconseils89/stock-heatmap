#!/usr/bin/env python3
"""
SEC EDGAR lookup — extrait les disclosures Customer Concentration et Suppliers
depuis les filings 10-K les plus récents d'un ticker US.

Usage:
    python3 sec_lookup.py QCOM
    python3 sec_lookup.py QCOM --json

Output JSON shape:
    {
      "ticker": "QCOM",
      "cik": "0000804328",
      "filing": {
        "type": "10-K",
        "filing_date": "2025-11-05",
        "report_date": "2025-09-28",
        "url": "https://www.sec.gov/...",
        "accession": "0000804328-25-000085"
      },
      "customer_disclosures": [
        "In fiscal 2025, revenues from Apple, Samsung and Xiaomi each comprised 10% or more...",
        ...
      ],
      "supplier_disclosures": [
        "We rely on sole- or limited-source suppliers for some products...",
        ...
      ]
    }

Le cache local (sec_cache/) évite de retaper EDGAR à chaque scan : un 10-K change une
fois par an, donc on cache 30 jours par défaut.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

UA = "Stocks Screener Research research@stocksscreener.local"
CACHE_DIR = Path(__file__).parent.parent / "sec_cache"
CACHE_TTL_DAYS = 30

# Cache du mapping ticker → CIK (rare update)
_TICKER_MAP = None


def _fetch(url: str, timeout: int = 30) -> str:
    """HTTP GET avec User-Agent SEC-conforme + retry minimal."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1)
    return ""


def _ticker_map() -> dict[str, str]:
    """Lazy-load le mapping ticker → CIK zero-padded à 10 chiffres."""
    global _TICKER_MAP
    if _TICKER_MAP is None:
        data = json.loads(_fetch("https://www.sec.gov/files/company_tickers.json"))
        _TICKER_MAP = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
    return _TICKER_MAP


def _latest_10k(cik: str) -> dict | None:
    """Trouve le 10-K le plus récent pour ce CIK."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    sub = json.loads(_fetch(url))
    recent = sub["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            acc_clean = recent["accessionNumber"][i].replace("-", "")
            cik_int = int(cik)
            doc = recent["primaryDocument"][i]
            return {
                "type": "10-K",
                "filing_date": recent["filingDate"][i],
                "report_date": recent["reportDate"][i],
                "accession": recent["accessionNumber"][i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}",
            }
    return None


class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, d: str):
        self.text.append(d)


def _html_to_text(html: str) -> str:
    ts = _TextStripper()
    try:
        ts.feed(html)
    except Exception:
        pass
    text = " ".join(ts.text)
    return re.sub(r"\s+", " ", text)


# Mots-clés simples qui qualifient une phrase comme candidate, puis on filtre par seconde passe.
# On évite les regex catastrophiques en travaillant sentence-by-sentence sur du texte segmenté.

CUSTOMER_KEYWORDS = [
    re.compile(r"\b\d{1,2}\s*%\s+(?:or|of)\b", re.IGNORECASE),  # "10% or more", "22% of revenues"
    re.compile(r"\b\d{1,2}\s*%[,\s]+(?:respectively|in\s+fiscal|in\s+\d{4})", re.IGNORECASE),  # tableaux fiscal
    re.compile(r"\b(?:one|two|three|certain|major|significant|largest)\s+customer", re.IGNORECASE),
    re.compile(r"customer[/\s]+licensee", re.IGNORECASE),
    re.compile(r"(?:customer|revenue)\s+concentration", re.IGNORECASE),
    re.compile(r"each\s+(?:comprised|represented|accounted)", re.IGNORECASE),
]
CUSTOMER_REQUIRED = re.compile(r"\b(customer|client|licensee|revenu|net sales|accounted for|comprised|represented)\b", re.IGNORECASE)

SUPPLIER_KEYWORDS = [
    re.compile(r"\b(?:sole|single|limited)[-\s]source\s+supplier", re.IGNORECASE),
    re.compile(r"\bdepend(?:s|ed)?\s+(?:on|upon)\s+[^.]{0,80}(?:supplier|manufacturer|foundry)", re.IGNORECASE),
    re.compile(r"\bwe\s+rely\s+on\b", re.IGNORECASE),
    re.compile(r"\b(?:TSMC|Samsung\s+Foundry|ASML|Applied\s+Materials|Lam\s+Research|Tokyo\s+Electron)\b", re.IGNORECASE),
]
SUPPLIER_REQUIRED = re.compile(r"\b(supplier|manufacturer|foundry|rely on|depend|source)\b", re.IGNORECASE)


def _split_sentences(text: str) -> list[str]:
    """Découpe le texte en phrases approximatives — utile pour limiter le scope regex."""
    # Sentence boundary heuristic: période suivie d'espace + majuscule, OU saut significatif.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)
    return [p for p in parts if 30 < len(p) < 1200]


def _extract_disclosures(text: str, keywords: list, required: re.Pattern, max_items: int = 5) -> list[str]:
    """Pour chaque phrase, vérifier (a) qu'elle matche au moins un keyword pertinent,
    (b) qu'elle contient le mot-clé requis (customer/supplier/etc.). Retourne les phrases uniques."""
    found = []
    seen = set()
    for sent in _split_sentences(text):
        if not required.search(sent):
            continue
        if not any(kw.search(sent) for kw in keywords):
            continue
        norm = re.sub(r"\s+", " ", sent.lower())[:200]
        if norm in seen:
            continue
        seen.add(norm)
        found.append(sent.strip())
        if len(found) >= max_items:
            break
    return found


def lookup(ticker: str, use_cache: bool = True) -> dict:
    """Récupère et parse le 10-K le plus récent du ticker.
    Retourne les disclosures clients et fournisseurs avec citation source."""
    ticker = ticker.upper()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker}.json"

    if use_cache and cache_file.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age < timedelta(days=CACHE_TTL_DAYS):
            with open(cache_file) as f:
                return json.load(f)

    tmap = _ticker_map()
    cik = tmap.get(ticker)
    if not cik:
        return {"ticker": ticker, "error": f"CIK introuvable pour {ticker} (pas une société listée US ?)"}

    try:
        filing = _latest_10k(cik)
        if not filing:
            return {"ticker": ticker, "cik": cik, "error": "Aucun 10-K trouvé dans les filings récents"}

        html = _fetch(filing["url"])
        text = _html_to_text(html)

        result = {
            "ticker": ticker,
            "cik": cik,
            "filing": filing,
            # Payload discipline (Levier 4) : cap à 2 disclosures par catégorie.
            # Au final on n'en utilise qu'1 par catégorie dans le dashboard.
            "customer_disclosures": _extract_disclosures(text, CUSTOMER_KEYWORDS, CUSTOMER_REQUIRED, max_items=2),
            "supplier_disclosures": _extract_disclosures(text, SUPPLIER_KEYWORDS, SUPPLIER_REQUIRED, max_items=2),
            "fetched_at": datetime.now().isoformat(),
        }

        # Cache result
        with open(cache_file, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        return result
    except Exception as e:
        return {"ticker": ticker, "cik": cik, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--no-cache", action="store_true", help="Bypass local cache")
    args = p.parse_args()

    result = lookup(args.ticker, use_cache=not args.no_cache)

    if args.json:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return

    f = result["filing"]
    print(f"=== {args.ticker.upper()} ===")
    print(f"CIK: {result['cik']}")
    print(f"Latest 10-K filed {f['filing_date']} (period {f['report_date']})")
    print(f"URL: {f['url']}\n")

    print(f"CUSTOMER DISCLOSURES ({len(result['customer_disclosures'])} found):")
    for i, d in enumerate(result["customer_disclosures"], 1):
        print(f"  {i}. {d[:400]}{'...' if len(d)>400 else ''}\n")

    print(f"SUPPLIER DISCLOSURES ({len(result['supplier_disclosures'])} found):")
    for i, d in enumerate(result["supplier_disclosures"], 1):
        print(f"  {i}. {d[:400]}{'...' if len(d)>400 else ''}\n")


if __name__ == "__main__":
    main()
