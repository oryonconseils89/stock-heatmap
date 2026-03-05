"""
fetch_data.py — Robot quotidien de la watchlist

Ce script fait 3 choses :
1. Lit watchlist.yaml pour connaître les titres à suivre
2. Va chercher les données de marché via Yahoo Finance (gratuit)
3. Produit un fichier data.json que le site web va afficher

Il est exécuté automatiquement chaque matin par GitHub Actions.
Tu n'as jamais besoin de le lancer toi-même.
"""

import json
import yaml
import yfinance as yf
from datetime import datetime, timezone

# ── Étape 1 : Lire la watchlist ─────────────────────────────────

with open("watchlist.yaml", "r") as f:
    watchlist = yaml.safe_load(f)

print(f"Watchlist chargée : {len(watchlist)} titres")

# ── Étape 2 : Récupérer les données de marché ──────────────────
# Pour chaque titre, on récupère directement depuis Yahoo Finance :
#   - le nom complet de l'entreprise
#   - la capitalisation boursière
#   - le prix actuel
#   - la variation du jour (le même % que Google Finance affiche)
#
# Le champ clé c'est "regularMarketChangePercent" — c'est la
# variation officielle calculée par Yahoo entre le close de la
# veille et le prix actuel (ou dernier prix connu si marché fermé).
# C'est exactement ce que tu vois sur Google Finance.

stocks = []

for item in watchlist:
    ticker = item["ticker"]
    sector = item.get("sector", "Autre")

    try:
        info = yf.Ticker(ticker).info

        # Variation du jour — directement fournie par Yahoo, pas calculée par nous
        change_pct = round(info.get("regularMarketChangePercent", 0), 2)

        # Prix actuel
        price = round(info.get("regularMarketPrice", 0), 2)

        # Market cap en milliards
        market_cap_raw = info.get("marketCap", 0)
        market_cap_b = round(market_cap_raw / 1_000_000_000, 2)

        stock_entry = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": sector,
            "marketCap": market_cap_b,
            "price": price,
            "change": change_pct,
        }

        stocks.append(stock_entry)
        print(f"  ✓ {ticker}: ${price:.2f} ({change_pct:+.2f}%) — Cap: ${market_cap_b}B")

    except Exception as e:
        print(f"  ✗ {ticker}: erreur — {e}")

# ── Étape 3 : Produire le fichier JSON ─────────────────────────

output = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "count": len(stocks),
    "stocks": stocks,
}

with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nTerminé ! {len(stocks)} titres exportés dans data.json")
