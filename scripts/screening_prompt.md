# Stocks Screener — Prompt de session (v4, optimisé tokens)

Tu exécutes une session de screening US pour Ilias. Lis intégralement, applique tout.

## Étape 1 — Marché ouvert ? (sinon, exit immédiat)

```
WORKSPACE=$(find /sessions -maxdepth 5 -type d -name "Stocks screener" | head -1)
python3 "$WORKSPACE/scripts/is_market_open.py" --verbose
```

Si exit code ≠ 0 (week-end ou férié US), écris une seule ligne dans le log et **arrête immédiatement** :
```
echo "[$(date -u +%H:%M)] SKIP — marché fermé : $(python3 \"$WORKSPACE/scripts/is_market_open.py\" --verbose)" >> "$WORKSPACE/logs/$(date -u +%Y-%m-%d).log"
exit 0
```

Aucun fetch, aucune classification, aucun déploiement quand le marché est fermé. **Zéro token brûlé pour rien.**

## Étape 2 — Charger l'environnement

```
set -a && source "$WORKSPACE/.env" && set +a
export PATH=~/.npm-global/bin:$PATH
```

Le `.env` contient `VERCEL_TOKEN` et `FINNHUB_API_KEY`.

## Étape 3 — Gathering des données factuelles

```
SESSION_LABEL="$(date +%H:%M)"
python3 "$WORKSPACE/scripts/gather_data.py" --session-label "$SESSION_LABEL" > /tmp/raw_session.json 2>> "$WORKSPACE/logs/$(date -u +%Y-%m-%d).log"
```

Retourne : market_context (5 macros + tu vas écrire le market_mood), candidates[] (tous les titres qui passent cap ≥ 50B, baisse ≥ 3%, NYSE+NASDAQ, news multi-source max 4/ticker × 150 char summary).

## Étape 4 — Delta scan (Levier 2) : réutiliser l'existant quand rien n'a bougé

**Logique critique pour économiser les tokens** :

Lis `$WORKSPACE/data/today.json` s'il existe ET si sa `date` correspond à aujourd'hui (US Eastern). Sinon archive-le dans `archive/{date}.json` et démarre une nouvelle journée.

Pour chaque candidat du scan courant :
- **S'il était déjà dans le today.json précédent** ET son `change_pct` n'a pas bougé de plus de **1 point absolu** (ex : -4.2% → -4.8%, OK ; -4.2% → -5.5%, refresh full), tu **réutilises** `situation`, `interpretation`, `key_metrics`, `key_metrics_interpretation`, `verdict`, `confidence`. Tu rafraîchis seulement : prix, volume_ratio, range_52w.position_pct, sector_etf.change_pct, et les prix dans `strategic_group` et `value_network` (via `fetch_quotes.py`, zéro Claude).
- **S'il est nouveau dans la shortlist** OU **a basculé matériellement** : full deep work (étapes 5-7).

Récupère les prix temps réel pour le strategic_group et value_network :
```
python3 "$WORKSPACE/scripts/fetch_quotes.py" --json AAPL TSM ARM AVGO > /tmp/quotes.json
```

## Étape 5 — Génération du market_mood (toujours rafraîchi, scan court)

Lis les 5 macros et écris un paragraphe de 4-6 phrases dans `market_context.market_mood` qui blend les indicateurs. Cap **800 chars**.

Règle d'accessibilité absolue : prose claire pour un non-trader, jargon expliqué en ligne (sell-the-news, risk-off, long duration → tous bannis sans explication).

## Étape 6 — Pour les candidats NEW/CHANGED uniquement : classification + value network

### 6.1 — Cache value_network (Levier 1)

Pour chaque candidat NEW, check d'abord le cache value_network :
```python
from vn_cache import get_cached_vn, set_cached_vn, get_cached_sg, set_cached_sg
vn_cached = get_cached_vn(ticker)
sg_cached = get_cached_sg(ticker)
```

**Si vn_cached non-null** → tu utilises la structure cachée (tickers + rationale + source), tu rafraîchis seulement les prix via fetch_quotes.py. Skip étape 6.3.
**Sinon** → tu génères depuis SEC EDGAR (étape 6.3) puis tu caches via `set_cached_vn(ticker, value_network)`.

Idem pour strategic_group : si `sg_cached` non-null, réutilise-le. Sinon génère et cache.

Le cache est dans `cache/vn/{TICKER}.json` et `cache/sg/{TICKER}.json` avec TTL 90 jours.

### 6.2 — Classification (situation, interpretation, key_metrics)

Applique le framework (idiosyncrasie / catalyseur / nature structurel-bruit / signaux faibles) et produis :
- `situation` : factuel sourcé d'une news (**cap 350 chars**)
- `interpretation` : analyse expert vulgarisée (**cap 600 chars**)
- `key_metrics` : 3 KPI + sources (chaque value ≤ 80 chars, context ≤ 60 chars)
- `key_metrics_interpretation` : (**cap 400 chars**)
- `verdict` : ENTRY ou PASSE
- `confidence` : HIGH / MEDIUM / LOW

Règle news : sélectionne UNE seule news qui explique la chute. Pas de tangentiel. Si rien ne colle, `news: []` + explicite dans situation.

### 6.3 — Génération value_network (si pas en cache) — discipline SOURCE OBLIGATOIRE

Pour les **clients/fournisseurs**, lance :
```
python3 "$WORKSPACE/scripts/sec_lookup.py" {ticker} --json > /tmp/sec_{ticker}.json
```
Retourne `customer_disclosures` et `supplier_disclosures` (cap 2 par catégorie). Tu identifies le ticker mentionné (Apple → AAPL, TSMC → TSM) et tu attaches la citation exacte comme `source_quote` + URL filing comme `source_url`.

Pour **substituts** : seulement si tu peux citer Gartner / IDC / banque sell-side / 10-K Risk Factors Competition. Sinon `null`.

Pour **complémenteurs** : seulement si tu peux citer un communiqué officiel de partnership. Sinon `null`.

**1 ticker max par catégorie**. Quality > quantity. Source ou rien.

Puis cache : `set_cached_vn(ticker, value_network)`.

## Étape 7 — Écriture today.json (overwrite full)

Structure :
```json
{
  "date": "YYYY-MM-DD",
  "as_of": "ISO datetime",
  "market_context": {...5 macros + market_mood...},
  "screened_total": N,
  "filters": {"min_cap_b": 50, "max_change_pct": -3, "exchanges": ["NYSE","NASDAQ"]},
  "context_source": "Données prix, capitalisation, volume, position 52w et perf ETF sectoriel : Yahoo Finance, mises à jour à l'horodatage du pull.",
  "candidates": [...]
}
```

Le scan REMPLACE complètement le précédent (pas de stacking).

## Étape 8 — Regen + redeploy dashboard

```
python3 "$WORKSPACE/scripts/build_dashboard.py"
cd "$WORKSPACE/deploy" && vercel --prod --token=$VERCEL_TOKEN --yes 2>> "$WORKSPACE/logs/$(date -u +%Y-%m-%d).log"
```

URL stable : https://stocks-screener-chi.vercel.app

## Étape 9 — Log final

```
[HH:MM] {N} candidats ({REUSED} réutilisés du cache, {NEW} générés), {E} ENTRY ({EH}H/{EM}M/{EL}L), {P} PASSE ({PH}H/{PM}M/{PL}L)
```

Termine silencieusement. Aucune notification utilisateur.

---

## Discipline transversale — récapitulatif des caps payload (Levier 4)

| Champ | Cap |
|---|---|
| News summary | 150 chars |
| News par ticker | 4 max |
| SEC disclosure par catégorie | 2 max |
| Situation | 350 chars |
| Interpretation | 600 chars |
| Key metric value | 80 chars |
| Key metric context | 60 chars |
| Key metrics interpretation | 400 chars |
| Market mood | 800 chars |
| Strategic group entries | 4 max |
| Value network entries par catégorie | 1 max |

## Quelle quantité de Claude est invoquée ?

- Si marché fermé : **zéro**
- Si scan delta (rien n'a changé) : juste market_mood (~800 tokens)
- Si scan delta partiel (quelques candidats nouveaux) : market_mood + classification des nouveaux uniquement
- Si scan full (premier de la journée ou rotation complète) : tout

Le modèle utilisé est défini au niveau Cowork settings (Sonnet par défaut). Pour le passer en Haiku et économiser ~80% sur les scheduled tasks : **Cowork → Settings → Default model → Haiku 4.5** (le modèle reste Sonnet quand tu interagis avec Claude manuellement dans une session).
