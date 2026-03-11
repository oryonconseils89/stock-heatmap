"""
fetch_data.py — Robot quotidien de la watchlist

Ce script fait 5 choses :
1. Lit watchlist.yaml pour connaître les titres à suivre (ticker, secteur, moat)
2. Va chercher les données de marché via Yahoo Finance (gratuit)
3. Pour chaque titre, récupère les 3 articles les plus frais via Google News RSS,
   en extrayant non seulement les titres mais aussi le contenu des articles
4. Envoie le contenu au LLM (Groq / Llama 3.3 70B) pour produire un Smart News Summary
   sous forme de 2 mini-paragraphes d'analyse experte
5. Produit un fichier data.json que le site web va afficher

Il est exécuté automatiquement chaque matin par GitHub Actions.
"""

import json
import yaml
import re
import yfinance as yf
import feedparser
import requests
import time
import os
from datetime import datetime, timezone
from urllib.parse import quote

# ── Configuration ───────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

DELAY_BETWEEN_CALLS = 2
ARTICLE_FETCH_TIMEOUT = 8  # secondes max pour récupérer un article
MAX_ARTICLES = 3           # on veut les 3 articles les plus frais

# ── Étape 1 : Lire la watchlist ─────────────────────────────────

with open("watchlist.yaml", "r") as f:
    watchlist = yaml.safe_load(f)

print(f"Watchlist chargée : {len(watchlist)} titres")

# ── Étape 2 : Récupérer les données de marché ──────────────────

stocks = []

for item in watchlist:
    ticker = item["ticker"]
    sector = item.get("sector", "Autre")
    moat = item.get("moat", "none")

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
            "moat": moat,
            "marketCap": market_cap_b,
            "price": price,
            "change": change_pct,
        }

        stocks.append(stock_entry)
        print(f"  ✓ {ticker}: ${price:.2f} ({change_pct:+.2f}%) — Cap: ${market_cap_b}B — Moat: {moat}")

    except Exception as e:
        print(f"  ✗ {ticker}: erreur — {e}")

# ── Helpers : nettoyage HTML ────────────────────────────────────

def strip_html(text):
    """Retire les balises HTML et nettoie le texte."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_article_text(url):
    """Tente de récupérer le début du texte d'un article via son URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; StockHeatmapBot/1.0)"
        }
        resp = requests.get(url, headers=headers, timeout=ARTICLE_FETCH_TIMEOUT)
        if resp.status_code != 200:
            return ""

        html = resp.text

        # Stratégie simple : chercher les balises <p> et extraire le texte
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        if not paragraphs:
            return ""

        # Garder les paragraphes substantiels (> 80 caractères)
        good_paragraphs = []
        for p in paragraphs:
            clean = strip_html(p)
            if len(clean) > 80:
                good_paragraphs.append(clean)
            if len(good_paragraphs) >= 3:
                break

        return " ".join(good_paragraphs)[:1500]  # Max 1500 chars par article

    except Exception:
        return ""

# ── Étape 3 : Récupérer les 3 articles les plus frais ──────────
#
# Pour chaque titre, on interroge Google News RSS.
# On prend les 3 premiers articles et on tente de récupérer
# le contenu réel de chaque article (titre + extrait RSS + texte).
# C'est cette matière riche qui permet au LLM de produire
# une analyse de qualité, pas juste des paraphrases de titres.

def fetch_articles(ticker, company_name):
    """Récupère les 3 articles les plus frais avec leur contenu."""
    try:
        query = f"{ticker} {company_name} stock"
        encoded_query = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
        feed = feedparser.parse(url)

        articles = []
        for entry in feed.entries[:MAX_ARTICLES]:
            title = entry.get("title", "")

            # L'extrait RSS (souvent 1-2 phrases de contexte)
            rss_summary = strip_html(entry.get("summary", ""))

            # Tenter de récupérer le texte de l'article
            link = entry.get("link", "")
            article_text = extract_article_text(link) if link else ""

            # Assembler le contenu disponible
            content_parts = [f"HEADLINE: {title}"]
            if rss_summary and len(rss_summary) > 50:
                content_parts.append(f"EXCERPT: {rss_summary}")
            if article_text and len(article_text) > 100:
                content_parts.append(f"ARTICLE: {article_text}")

            articles.append({
                "title": title,
                "content": "\n".join(content_parts),
                "has_body": len(article_text) > 100
            })

        return articles

    except Exception as e:
        print(f"    ⚠ RSS échoué pour {ticker}: {e}")
        return []

# ── Étape 4 : Smart News Summary via Groq ──────────────────────
#
# Le prompt demande 2 mini-paragraphes d'analyse experte.
# Pas du copy-paste de news. Un effort analytique : WHY, SO WHAT.

def generate_summary(ticker, company_name, sector, moat, change_pct, articles, attempt=1):
    """Appelle Groq pour produire le Smart News Summary."""

    if not GROQ_API_KEY:
        print(f"    ⚠ Pas de clé API Groq — summary sauté pour {ticker}")
        return []

    if not articles:
        print(f"    ⚠ Aucun article pour {ticker} — summary sauté")
        return []

    # Assembler le contenu des articles
    articles_text = ""
    for i, a in enumerate(articles, 1):
        articles_text += f"\n--- Article {i} ---\n{a['content']}\n"

    prompt = f"""You are a senior equity analyst producing a daily briefing for a portfolio manager.

STOCK CONTEXT:
- Ticker: {ticker}
- Company: {company_name}
- Sector: {sector}
- Economic Moat: {moat}
- Today's move: {change_pct:+.2f}%

RECENT NEWS COVERAGE:
{articles_text}

YOUR TASK:
Write exactly 2 short paragraphs that synthesize what's happening with this stock.

PARAGRAPH 1 — THE SITUATION:
What is driving today's move? Connect the news to the price action. Be specific about catalysts: earnings, guidance, analyst actions, macro, sector rotation, insider activity. If the move is large (>5%), be precise about the primary cause.

PARAGRAPH 2 — THE SIGNAL:
What does this mean for someone holding or watching this stock? Is this noise or signal? Consider the company's competitive position (moat: {moat}) when assessing whether this is a temporary dislocation or a structural shift.

RULES:
- Each paragraph is 2-3 sentences maximum. Dense, not fluffy.
- Write like a sharp analyst, not a news aggregator. Analytical value over information relay.
- If the news is thin or irrelevant to the stock's move, say so directly.
- No intro, no sign-off, no headers, no bullet points.

FORMAT:
Return ONLY a JSON array with exactly 2 strings (one per paragraph). Example:
["First paragraph here.", "Second paragraph here."]"""

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
                "max_tokens": 400,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"    ⚠ Groq erreur HTTP {response.status_code} pour {ticker}")
            return []

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Nettoyage : retirer les backticks markdown si présents
        content = content.replace("```json", "").replace("```", "").strip()

        # Parsing principal
        paragraphs = json.loads(content)

        if isinstance(paragraphs, list) and all(isinstance(p, str) for p in paragraphs):
            return paragraphs[:2]

        print(f"    ⚠ Format inattendu pour {ticker}")
        return []

    except json.JSONDecodeError:
        # ── Fallback : extraire le JSON array avec regex ──
        print(f"    ⚠ JSON parse échoué pour {ticker}, tentative regex...")
        try:
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                paragraphs = json.loads(match.group())
                if isinstance(paragraphs, list) and all(isinstance(p, str) for p in paragraphs):
                    return paragraphs[:2]
        except Exception:
            pass

        # ── Retry : second appel avec prompt simplifié ──
        if attempt < 2:
            print(f"    ↻ Retry pour {ticker}...")
            time.sleep(1)
            return generate_summary(ticker, company_name, sector, moat, change_pct, articles, attempt=2)

        print(f"    ✗ Échec définitif pour {ticker}")
        return []

    except Exception as e:
        print(f"    ⚠ Groq appel échoué pour {ticker}: {e}")
        return []

# ── Exécution des étapes 3 et 4 pour chaque titre ──────────────

print(f"\n--- Smart News Summaries ---")

for stock in stocks:
    ticker = stock["ticker"]
    print(f"  → {ticker}...")

    # Étape 3 : récupérer les articles
    articles = fetch_articles(ticker, stock["name"])
    articles_with_body = sum(1 for a in articles if a.get("has_body"))
    print(f"    {len(articles)} articles trouvés ({articles_with_body} avec contenu)")

    # Calculer la confiance (basée sur le nombre d'articles récupérés)
    # 3 articles = confident, 2 = decent, 1 ou 0 = weak
    if len(articles) >= 3:
        confidence = "confident"
    elif len(articles) >= 2:
        confidence = "decent"
    else:
        confidence = "weak"

    # Étape 4 : summary
    paragraphs = generate_summary(
        ticker, stock["name"], stock["sector"], stock["moat"],
        stock["change"], articles
    )
    stock["newsDigest"] = paragraphs
    stock["newsConfidence"] = confidence
    stock["newsSourceCount"] = len(articles)
    print(f"    {len(paragraphs)} paragraphes générés — confiance: {confidence}")

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
