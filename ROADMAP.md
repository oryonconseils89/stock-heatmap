# Stock Heatmap — Roadmap & Decisions Log

> Ce document est la source de vérité unique sur l'état du produit, les décisions prises, et la direction future. Il vit dans le repo GitHub et une copie est chargée dans le projet Claude pour assurer la continuité entre les conversations.
>
> Dernière mise à jour : mars 2026

---

## Produit en production — V1

**Ce que ça fait.** Un treemap interactif qui affiche une watchlist personnelle de titres boursiers, où chaque rectangle est dimensionné proportionnellement à la capitalisation boursière du titre au sein du sous-ensemble affiché. Les couleurs représentent la variation du jour (vert = hausse, rouge = baisse). Des filtres permettent d'isoler les titres en baisse, au-delà d'un seuil custom, ou de trier par variation. Un tooltip au hover affiche le nom, le secteur, le prix, la market cap et la variation exacte.

**Stack technique.** Le script `fetch_data.py` utilise la librairie Python yfinance pour récupérer les données de marché. Il lit le champ `regularMarketChangePercent` directement depuis Yahoo Finance (même chiffre que Google Finance et les plateformes de trading). Le script est exécuté chaque jour de semaine à 9h30 heure de Montréal par GitHub Actions (`daily.yml`). Il produit un fichier `data.json` qui est committé automatiquement dans le repo. Le frontend est un fichier `index.html` unique (vanilla HTML/JS + D3.js) hébergé sur GitHub Pages qui lit ce JSON au chargement.

**Fichiers du repo.**

- `watchlist.yaml` — liste des titres suivis, éditable manuellement
- `fetch_data.py` — script de collecte de données
- `.github/workflows/daily.yml` — orchestration automatique
- `index.html` — site web / treemap interactif
- `data.json` — données de marché (auto-généré, ne pas éditer)
- `ROADMAP.md` — ce fichier

**Comment modifier la watchlist.** Ouvrir `watchlist.yaml` sur GitHub, cliquer sur le crayon pour éditer, ajouter ou supprimer des lignes (format : ticker + secteur), commit. Le prochain run du script prendra les changements en compte. On peut aussi déclencher un run manuel depuis l'onglet Actions.

**Coût.** 0$ — yfinance est gratuit, GitHub Actions free tier (2000 min/mois, on en utilise ~15), GitHub Pages est gratuit pour les repos publics.

---

## Phases futures

### Phase 2 — Post-its AI (résumés explicatifs au hover)

**Objectif.** Quand on survole un titre en baisse significative, afficher un post-it avec 3 phrases concises qui expliquent les raisons de la baisse.

**Approche technique envisagée.** Le script Python récupère les headlines récentes via les flux RSS de Google News (gratuit, pas d'API key). Pour chaque titre en baisse au-delà d'un seuil (ex: > 3%), les headlines passent dans un appel à l'API Gemini de Google (free tier : 15 req/min, 1M tokens/jour). Le prompt demande un résumé en exactement 3 phrases. Le résultat est stocké dans le JSON sous une clé `newsDigest` par ticker. Le frontend affiche ce contenu dans le tooltip.

**Statut.** Non commencé. Prêt à développer.

### Phase 3 — Classification des mouvements

**Objectif.** Chaque titre en mouvement reçoit un label parmi trois catégories :

- **Conjoncturel** (cautious) — la baisse est liée à un événement temporaire ou cyclique
- **Structurel** (too risky) — la baisse reflète un changement fondamental (perte de contrat, changement réglementaire, etc.)
- **Anecdotique** (opportunité potentielle) — panique de marché non justifiée par des fondamentaux propres au titre

**Approche technique envisagée.** Même appel Gemini que la phase 2, avec un prompt enrichi qui demande aussi la classification et une justification d'une ligne. Les règles de classification seront co-définies et documentées dans ce fichier. Le frontend affiche un badge coloré sur chaque tuile du treemap.

**Statut.** Non commencé. Les règles de classification restent à définir.

### Phase 4 — Calendrier de catalysts

**Objectif.** Une vue calendrier qui affiche les événements à venir pour les titres de la watchlist : dates d'earnings, ex-dividendes, et catalysts spécifiques (FDA decisions, lancements produits, dates de contrats, etc.).

**Approche technique envisagée.** yfinance fournit les dates d'earnings et d'ex-dividendes gratuitement. Les catalysts spécifiques seront curés manuellement dans un fichier `catalysts.yaml` dans le repo. Le script Python combine les deux sources dans un second JSON. Le frontend ajoute une vue calendrier à côté du treemap.

**Statut.** Non commencé. Le concept précis de "catalyst" sera défini plus tard.

### Future — Couche de distribution (n8n)

**Objectif.** Alertes et digests poussés vers des canaux de communication : email, Slack, Pushover.

**Approche technique envisagée.** n8n, soit cloud soit self-hosted, branché sur le data.json ou sur une API intermédiaire. Ce n'est pas un remplacement du pipeline GitHub Actions — c'est une couche additionnelle au-dessus.

**Statut.** Pas encore planifié. Sera développé quand les phases 2-4 seront stables.

---

## Décisions techniques et justifications

| Décision | Justification |
|---|---|
| GitHub Actions plutôt que n8n pour le pipeline | Le flux est linéaire (cron → script → JSON → site statique). n8n est conçu pour l'orchestration multi-système complexe ; il serait surdimensionné ici et imposerait soit un coût cloud soit un serveur self-hosted. |
| `regularMarketChangePercent` plutôt que calcul manuel | Le champ Yahoo Finance correspond exactement à ce que Google Finance et les plateformes de trading affichent. Calculer la variation soi-même à partir des prix de clôture introduit des divergences (after-hours, ajustements). |
| HTML/JS vanilla plutôt que React | Un seul fichier `index.html` sans build step, directement servi par GitHub Pages. Pas besoin de framework pour une page unique. Simplifie la maintenance et le déploiement. |
| YAML pour la watchlist plutôt que JSON | Plus lisible et éditable à la main, avec support des commentaires. Adapté à un fichier que l'utilisateur modifie régulièrement. |
| Gemini free tier pour les phases AI | 15 req/min et 1M tokens/jour suffisent largement pour 50-100 titres/jour. Pas de carte de crédit requise. Si le free tier disparaît, migration simple vers Groq ou autre (un changement d'URL d'endpoint). |
| Repo public | Obligatoire pour GitHub Pages gratuit. Le repo ne contient aucune donnée sensible — uniquement des tickers publics et des données de marché publiques. |

---

## Backlog d'idées (non priorisé)

- Panneau d'admin dans le treemap pour gérer la watchlist sans aller sur GitHub
- Option Google Sheet comme source de la watchlist
- Vue par secteur (regroupement des tuiles par secteur avec sous-treemaps)
- Historique de performance sur N jours (sparklines dans le tooltip)
- Mode comparaison : variation de la watchlist vs S&P 500
- Export PDF du heatmap quotidien
