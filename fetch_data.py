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
# On ouvre le fichier YAML et on le transforme en liste Python.

with open("watchlist.yaml", "r") as f:
    watchlist = yaml.safe_load(f)

print(f"Watchlist chargée : {len(watchlist)} titres")

# ── Étape 2 : Récupérer les données de marché ──────────────────
# yfinance va chercher les infos directement sur Yahoo Finance.
# Pour chaque titre, on récupère :
#   - le nom complet de l'entreprise
#   - la capitalisation boursière (market cap)
#   - le prix actuel
#   - la variation du jour en pourcentage

stocks = []

# On récupère tous les tickers d'un coup (plus rapide que un par un)
tickers_str = " ".join([item["ticker"] for item in watchlist])
data = yf.download(tickers_str, period="2d", group_by="ticker", progress=False)

for item in watchlist:
    ticker = item["ticker"]
    sector = item.get("sector", "Autre")

    try:
        # Récupérer les infos détaillées du titre
        info = yf.Ticker(ticker).info

        # Extraire la market cap (en milliards pour lisibilité)
        market_cap_raw = info.get("marketCap", 0)
        market_cap_b = round(market_cap_raw / 1_000_000_000, 2)

        # Calculer la variation journalière en pourcentage
        # On prend les deux derniers jours de prix de clôture
        if len(watchlist) == 1:
            # Cas spécial : un seul ticker, la structure est différente
            hist = data["Close"].dropna()
        else:
            hist = data[ticker]["Close"].dropna()

        if len(hist) >= 2:
            previous_close = float(hist.iloc[-2])
            current_close = float(hist.iloc[-1])
            change_pct = round(((current_close - previous_close) / previous_close) * 100, 2)
        else:
            current_close = float(hist.iloc[-1]) if len(hist) == 1 else 0
            change_pct = 0.0

        stock_entry = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": sector,
            "marketCap": market_cap_b,
            "price": round(current_close, 2),
            "change": change_pct,
        }

        stocks.append(stock_entry)
        print(f"  ✓ {ticker}: ${current_close:.2f} ({change_pct:+.2f}%) — Cap: ${market_cap_b}B")

    except Exception as e:
        print(f"  ✗ {ticker}: erreur — {e}")

# ── Étape 3 : Produire le fichier JSON ─────────────────────────
# Ce fichier sera lu par le site web pour afficher le treemap.

output = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "count": len(stocks),
    "stocks": stocks,
}

with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nTerminé ! {len(stocks)} titres exportés dans data.json")
