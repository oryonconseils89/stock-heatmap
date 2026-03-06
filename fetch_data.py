"""
fetch_data.py — Robot quotidien de la watchlist

Ce script fait 5 choses :
1. Lit watchlist.yaml pour connaître les titres à suivre
2. Va chercher les données de marché via Yahoo Finance (gratuit)
3. Pour chaque titre, récupère les headlines récentes via Google News RSS (gratuit)
4. Envoie les headlines à Groq (Llama 3.3 70B) pour produire un Smart News Summary
5. Produit un fichier data.json que le site web va afficher

Il est exécuté automatiquement chaque matin par GitHub Actions.
Tu n'as jamais besoin de le lancer toi-même.
"""

import json
import yaml
import yfinance as yf
import feedparser
import requests
import time
import os
from datetime import datetime, timezone

# ── Configuration ───────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Délai entre chaque appel Groq (en secondes) pour respecter le rate limit
DELAY_BETWEEN_CALLS = 2

# ── Étape 1 : Lire la watchlist ─────────────────────────────────

with open("watchlist.yaml", "r") as f:
    watchlist = yaml.safe_load(f)

print(f"Watchlist chargée : {len(watchlist)} titres")

# ── Étape 2 : Récupérer les données de marché ──────────────────

stocks = []

for item in watchlist:
    ticker = item["ticker"]
    sector = item.get("sector", "Autre")

    try:
        info = yf.Ticker(ticker).info

        change_pct = round(info.get("regularMarketChangePercent", 0), 2)
        price = round(info.get("regularMarketPrice", 0), 2)
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

# ── Étape 3 : Récupérer les headlines via Google News RSS ───────
#
# Pour chaque titre, on interroge Google News avec "TICKER stock".
# Google retourne un flux RSS (XML) avec les ~15 articles les plus
# récents. On extrait juste les titres — c'est la matière brute
# que le LLM va analyser.

def fetch_headlines(ticker, company_name):
    """Récupère les headlines récentes depuis Google News RSS."""
    try:
        query = f"{ticker} {company_name} stock"
        url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
        feed = feedparser.parse(url)

        headlines = []
        for entry in feed.entries[:10]:
            headlines.append(entry.title)

        return headlines

    except Exception as e:
        print(f"    ⚠ RSS échoué pour {ticker}: {e}")
        return []

# ── Étape 4 : Smart News Summary via Groq ──────────────────────
#
# On envoie les headlines + la variation du jour au LLM.
# Le prompt lui demande de produire 2-4 bullets analytiques
# qui expliquent la situation du titre — pas un résumé passif
# des news, mais un effort explicatif sharp et utile.

def generate_summary(ticker, company_name, sector, change_pct, headlines):
    """Appelle Groq pour produire le Smart News Summary."""

    if not GROQ_API_KEY:
        print(f"    ⚠ Pas de clé API Groq — summary sauté pour {ticker}")
        return []

    if not headlines:
        print(f"    ⚠ Aucune headline pour {ticker} — summary sauté")
        return []

    headlines_text = "\n".join(f"- {h}" for h in headlines)

    prompt = f"""You are a sharp, concise equity analyst assistant.

CONTEXT:
- Ticker: {ticker}
- Company: {company_name}
- Sector: {sector}
- Today's move: {change_pct:+.2f}%

RECENT HEADLINES:
{headlines_text}

TASK:
Based on the headlines above, produce 2 to 4 bullet points that explain what's going on with this stock today. You decide how many bullets are needed — use 2 if the signal is thin, up to 4 if there's a lot happening.

RULES:
- Each bullet is one sentence, sharp and analytical — not a copy-paste of headlines.
- Connect the dots: explain WHY the stock is moving, not just WHAT happened.
- If the move is dramatic (>5%), be especially precise about the cause.
- If there's no meaningful news, say so honestly in one bullet.
- Do NOT start bullets with the ticker name.
- Do NOT add any intro, outro, or commentary outside the bullets.

FORMAT:
Return ONLY a JSON array of strings. Example:
["First bullet.", "Second bullet.", "Third bullet."]"""

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"    ⚠ Groq erreur HTTP {response.status_code} pour {ticker}")
            return []

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Le LLM retourne un JSON array — on le parse
        # On nettoie au cas où il ajouterait des backticks markdown
        content = content.replace("```json", "").replace("```", "").strip()
        bullets = json.loads(content)

        if isinstance(bullets, list) and all(isinstance(b, str) for b in bullets):
            return bullets[:4]  # Sécurité : max 4 bullets
        else:
            print(f"    ⚠ Format inattendu pour {ticker}")
            return []

    except json.JSONDecodeError:
        print(f"    ⚠ JSON invalide retourné par Groq pour {ticker}")
        return []
    except Exception as e:
        print(f"    ⚠ Groq appel échoué pour {ticker}: {e}")
        return []

# ── Exécution des étapes 3 et 4 pour chaque titre ──────────────

print(f"\n--- Smart News Summaries ---")

for stock in stocks:
    ticker = stock["ticker"]
    print(f"  → {ticker}...")

    # Étape 3 : headlines
    headlines = fetch_headlines(ticker, stock["name"])
    print(f"    {len(headlines)} headlines trouvées")

    # Étape 4 : summary
    bullets = generate_summary(
        ticker, stock["name"], stock["sector"], stock["change"], headlines
    )
    stock["newsDigest"] = bullets
    print(f"    {len(bullets)} bullets générées")

    # Pause entre les appels pour respecter le rate limit Groq
    if GROQ_API_KEY:
        time.sleep(DELAY_BETWEEN_CALLS)

# ── Étape 5 : Produire le fichier JSON ─────────────────────────

output = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "count": len(stocks),
    "stocks": stocks,
}

with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nTerminé ! {len(stocks)} titres exportés dans data.json")
