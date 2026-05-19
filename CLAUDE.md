# CLAUDE.md — Stocks Screener Project Memory

> Ce fichier est chargé automatiquement par Claude Code en début de chaque session.
> Il contient tout le contexte projet, les conventions, et les leçons apprises.
> Maintiens-le à jour : si tu apprends quelque chose de nouveau ou changes une convention, mets ce fichier à jour avant la fin de la session.

---

## 1. Mission

Pipeline automatisé qui scanne le marché US trois fois par jour ouvrable, identifie les large caps en baisse significative, classifie chaque candidat ENTRY (rebond probable) ou PASSE (à éviter) avec analyse sourcée, et publie un dashboard live sur Vercel.

L'utilisateur trade les ENTRY manuellement depuis comptes CELI canadiens (tax-sheltered). Stratégie : entrer sur un dip que le marché surinterprète, attendre intraday/48h que la poussière retombe, sortir sur petit profit. Vélocité × volume × abri fiscal = cash significatif en fin de semaine.

**Filtres de sélection** :
- Cap marché ≥ 25 milliards USD
- Performance intraday ≤ -3%
- Top 10 baisseurs uniquement (les 10 plus gros loss en %)

## 2. Architecture

```
┌──────────────┐        ┌──────────────┐        ┌────────────────┐
│  Yahoo (yf)  │───┐    │ cron (Oracle)│        │ build_dashboard│
│ Google News  │───┼───▶│   3x/j ET    │───────▶│   regen HTML   │───▶ Vercel
│   Finnhub    │───┘    │ claude -p    │        │  + redeploy    │     │
└──────────────┘        └──────────────┘        └────────────────┘     │
                              │                                          ▼
┌──────────────┐              │                  ┌────────────────┐  https://
│  SEC EDGAR   │──────────────┘                  │  today.json    │  stocks-
└──────────────┘                                 │   (overwrite)  │  screener-
                                                 └────────────────┘  chi
                                                                     .vercel.app
```

L'orchestration tourne sur un serveur Oracle Cloud Always Free Tier. Le `cron` déclenche `run_scan.sh` qui appelle `claude -p` en mode headless avec le `screening_prompt.md`. Claude exécute le pipeline (gather → analyse → build → deploy) en autonome.

## 3. Fichiers et rôles

| Fichier | Rôle |
|---|---|
| `scripts/is_market_open.py` | Check NYSE ouvert (week-end + fériés US 2026-2028 hardcodés). Exit 0 si ouvert, non-zéro sinon. |
| `scripts/gather_data.py` | Screener Yahoo + 5 macros (SPY/VIX/US10Y/DXY/WTI) + news multi-source dédupliqué. Defaults : `--min-cap 25` (B$), `--max-tickers 10`. |
| `scripts/sec_lookup.py` | Extrait Customer/Supplier disclosures depuis 10-K via SEC EDGAR. Cache 30j. |
| `scripts/fetch_quotes.py` | Prix temps-réel pour une liste de tickers. |
| `scripts/vn_cache.py` | Cache value_network + strategic_group par ticker (TTL 90j). |
| `scripts/build_dashboard.py` | Génère le dashboard HTML self-contained avec données inlinées dans `<script>`. |
| `scripts/screening_prompt.md` | Le prompt complet exécuté par `claude -p` à chaque scan. C'est le brain du système. |
| `scripts/run_scan.sh` | Wrapper bash : check market open → appelle claude -p avec timeout 15 min → log. |

## 4. Sources de données

- **Prix / volume / range 52w / cap** : Yahoo Finance via `yfinance`
- **News** : Yahoo Finance + Google News RSS + Finnhub (3 sources, dédupliquées par titre normalisé)
- **Customer / Supplier (Value Network)** : SEC EDGAR 10-K filings (programmatique, citations vérifiables). Fallback knowledge model si SEC ne renvoie rien d'utile.
- **Macros** : SPY (S&P 500 ETF), ^VIX, ^TNX (10Y yield), DX-Y.NYB (DXY), CL=F (WTI) via Yahoo

## 5. Cadence

Trois scans par jour ouvrable, heure de l'Est (NYSE) :

| Heure ET | Cron | Rationale |
|---|---|---|
| 09h40 | `40 9 * * 1-5` | Post-ouverture, marché stabilisé (40 min après bell) |
| 12h00 | `0 12 * * 1-5` | Mi-séance, capture le pivot lunch |
| 15h15 | `15 15 * * 1-5` | Pré-clôture, 45 min avant bell, dernière fenêtre d'entry |

Skip automatique week-end + jours fériés US (calendrier NYSE hardcodé jusqu'à 2028 dans `is_market_open.py`).

**État actuel : crons en PAUSE** (depuis le 18 mai 2026). Pour réactiver côté serveur : `crontab ~/crontab.backup`.

## 6. Méthodologie de classification

Chaque candidat est classifié ENTRY ou PASSE avec confiance HIGH/MEDIUM/LOW, basé sur 8 piliers académiques :

1. **Tetlock 2007** — Pessimisme media → predictable pullback puis reversal. Si la news est principalement émotionnelle/sentiment plutôt que factuelle structurelle, biais ENTRY.
2. **Karpoff 2008** — Reputational damage from regulatory action / fraud → persistent underperformance. Biais PASSE.
3. **Lel & Miller 2015** — Cross-listed firm enforcement → durable damage. Biais PASSE.
4. **Womack 1996** — Sell-side downgrade reaction → typically overshoots short-term. Biais ENTRY si pas accompagné de earnings miss.
5. **De Bondt & Thaler 1985** — Overreaction hypothesis → 3-5y reversal. Pour intraday, signal seulement si magnitude extrême + pas de news structurelle.
6. **Jegadeesh & Titman 1993** — Momentum → opposes overreaction at short horizon. Si stock était en momentum baissier avant aujourd'hui, biais PASSE (momentum continue).
7. **George & Hwang 2004** — 52-week high anchor → mean reversion vers anchor. Si current price très éloigné du 52w high SANS news structurelle, biais ENTRY.
8. **Brandenburger & Nalebuff Value Net 1996** — Position dans chaîne de valeur (Customers/Suppliers/Competitors/Complementors) détermine vulnérabilité aux chocs sectoriels.

**Triggers PASSE forts** : litigation matérielle, fraud SEC inquiry, FDA rejection, earnings miss + guidance cut, key product recall, CEO/CFO démission soudaine sans successeur clair, regulatory ban dans marché principal, substitution disruption documentée (ex: Kodak vs digital).

**Triggers ENTRY forts** : market-wide panic spillover, secteur entier qui dump pour macro (rate move, geopolitical), management change "amicale" annoncée à l'avance, pullback après rally extended, news émotionnelle sans impact P&L durable.

## 7. Discipline d'économie de tokens — 4 leviers

Token budget = limite Claude Max subscription du user. Chaque scan doit rester dans une enveloppe raisonnable pour éviter d'épuiser la limite hebdo.

1. **Cache 90 jours** sur `value_networks` et `strategic_groups` (changent à la cadence des 10-K, pas des scans). Implémenté dans `vn_cache.py`.
2. **Delta scans** : si un candidat était déjà classifié dans la journée et son Δ% n'a pas bougé de plus de 1 point, réutilise le narrative existant. Seuls les prix sont rafraîchis.
3. **Payload caps stricts** dans le prompt :
   - news : max 4 items × 150 ch summary
   - situation : 350 ch
   - interpretation : 600 ch
   - key_metrics_interpretation : 400 ch
   - market_mood : 800 ch
4. **Market-open check en première étape** : zéro token brûlé week-end/férié. `run_scan.sh` appelle `is_market_open.py` AVANT `claude -p`.

## 8. Anti-patterns observés (semaine du 11-18 mai 2026) — DO NOT REPEAT

Cette section documente les plantages réels avec causes racines et mitigations en place. Avant de modifier le pipeline, relis cette section.

### Anti-pattern #1 : Bâclage scan avec trop de candidats

**Symptôme observé**. Scan du 9h40 le 18 mai a traité 17 candidats en 3m25s (~12s/candidat vs ~45s attendus en test isolé). 10 verdicts sur 17 étaient classés LOW avec du texte placeholder type "analyse omise pour optimisation temps" ou "analyse en attente".

**Cause racine**. Default `--max-tickers` valait 250 dans `gather_data.py`. Combiné au fait que `claude -p` a des limites de temps/tokens budget dans un appel monolithique unique, traiter trop de candidats fait que Claude rush et remplit des placeholders pour finir dans le temps imparti.

**Mitigations en place** :
- `gather_data.py` default `--max-tickers` abaissé à 10
- `run_scan.sh` `timeout` étendu à 900s (15 min)
- Instruction anti-placeholder explicite ajoutée au prompt `claude -p` : "Pas de raccourcis 'analyse omise pour optimisation temps' ou 'analyse en attente' — tu produis du vrai contenu pour chaque candidat ou tu marques honnêtement Confiance LOW avec un raisonnement explicite."
- Seuil cap relevé/recadré à ≥25B (au lieu de 50B) MAIS top 10 max — donc plus de couverture du marché mid-large cap tout en gardant la qualité d'analyse

**Comment appliquer**. Ne jamais remonter `--max-tickers` au-dessus de 10 sans valider d'abord la qualité d'analyse par candidat. Si besoin de couverture plus large, faire plusieurs scans séquentiels plutôt qu'un seul plus gros.

### Anti-pattern #2 : Value Network et Strategic Group vides sur tickers étrangers/niche

**Symptôme observé**. Pour BE (Bloom Energy), NGG (National Grid) et similaires, le lookup SEC EDGAR ne renvoyait pas de disclosures customer/supplier exploitables, et Claude laissait ces sections vides dans le verdict. L'utilisateur a noté à juste titre que Claude a la connaissance générale de ces sociétés et que laisser vide = paresse.

**Cause racine**. Le `screening_prompt.md` section 6.3 disait "SOURCE OBLIGATOIRE : SEC EDGAR uniquement", que Claude a interprété strictement comme interdiction d'utiliser sa propre knowledge.

**Mitigations en place** :
- Section 6.3 réécrite en "DISCIPLINE INTELLIGENTE" : si SEC ne renvoie rien d'utile, Claude utilise sa connaissance générale avec rationale concret (analyse industrie, partnerships publics connus, chaîne d'approvisionnement documentée hors SEC)
- Section 6.4 ajoutée pour fallback strategic_group quand le `peer_snapshot` de gather_data est vide

**Comment appliquer**. Quand une source de données échoue, fallback sur la knowledge model avec raisonnement explicite. Ne jamais laisser une section vide sans expliquer pourquoi aucune info n'est disponible. La discipline "SOURCE OBLIGATOIRE" ne doit s'appliquer que pour les revendications factuelles spécifiques (chiffres, contrats nommés) — pas pour la compréhension structurelle générale.

### Anti-pattern #3 : Utiliser API key au lieu de Max subscription

**Symptôme observé**. Risque initial de configurer Claude Code avec une `ANTHROPIC_API_KEY` au lieu de l'auth Max subscription → consommation token billée à la demande au lieu de gratuit dans le plan.

**Mitigation en place**. Sur le serveur Oracle, Claude Code 2.0.14 est auth via `claude login` avec le compte Max du user. Aucun `ANTHROPIC_API_KEY` n'est défini.

**Comment appliquer**. Avant de déployer Claude Code dans un nouvel environnement, vérifier l'auth method. Si tu vois une API key configurée, c'est probablement une erreur — désactiver et login via OAuth Max.

### Anti-pattern #4 : Claude Code 2.1.143 OAuth bug

**Symptôme observé**. Erreur "Unknown scope: org:create_" lors du `claude login` avec Claude Code v2.1.143.

**Mitigation en place**. Downgrade à v2.0.14, qui fonctionne.

**Comment appliquer**. Ne pas upgrader Claude Code sur le serveur sans tester d'abord en environnement isolé que `claude login` fonctionne.

## 9. Préférences de collaboration utilisateur

Extrait pertinent pour adapter ton ton et ta forme :

- **Profil** : non-technique mais profondément curieux de comprendre les mécanismes. Veut apprendre, pas être protégé de la complexité.
- **Forme préférée** : prose dense en paragraphes auto-portés avec structure logique visible. Chaque paragraphe = une idée complète. Pas de fragmentation en bullets / mots-clés / demi-phrases que le lecteur doit assembler.
- **Densité** : chaque phrase doit gagner sa place. Pas de filler, pas de qualifiers vagues, pas de padding rhétorique. Généreux en substance, serré en expression.
- **Profondeur** : explique les concepts avec vrai niveau de détail (le quoi et le comment), puis construis la compréhension via exemples concrets organisationnels/professionnels. Jamais de simplification analogique enfantine.
- **Honnêteté intellectuelle** : quand son raisonnement est faux ou incomplet, corrige directement et explique ce qui manquait. Ne valide jamais un raisonnement incorrect par politesse.
- **Bullets** : utilisés UNIQUEMENT si strictement nécessaires (vraie liste énumérative, tableau structuré) ou explicitement demandés. Pour explications, reports, Q&A : prose pleine.
- **Langue** : français Québec primaire. Anglais OK pour code/config/termes techniques. Il jure beaucoup quand frustré — ne match pas le ton, livre juste le contenu.

## 10. Conventions git et déploiement

- **Branche** : toujours `main`. Pas de feature branches sur ce projet (solo).
- **Commits** : présent indicatif, max 72 caractères sujet, français OK. Exemples : "Fix bâclage scan 09:40", "Loosen Value Network discipline", "Threshold cap ≥25B".
- **Push** : direct vers `origin/main` après test local.
- **Pas de PR workflow** (projet solo).
- **Pas de tests automatisés** pour le moment — validation manuelle via dry-run (`./scripts/run_scan.sh "test-$(date +%H:%M)"`).

## 11. Accès infrastructure

### Serveur production (Oracle Cloud)
- Provider : Oracle Cloud Always Free Tier
- Shape : AMD x86 VM.Standard.E2.1.Micro (ARM était out of capacity)
- Distro : Ubuntu 22.04
- User : `ubuntu`
- SSH key (local Mac) : `~/.ssh/oracle-screening.key` (permissions 600)
- Connection : `ssh -i ~/.ssh/oracle-screening.key ubuntu@<ORACLE_IP>` (IP stockée dans `~/.ssh/config` côté Mac, à adapter)
- Repo path serveur : `~/stock-heatmap` (clone GitHub)
- Logs : `~/stock-heatmap/logs/YYYY-MM-DD.log`
- Claude Code version : 2.0.14 (downgrade volontaire, voir anti-pattern #4)
- Auth Claude Code : OAuth Max subscription (PAS d'API key)
- Crontab actuelle : VIDE (en pause depuis 18 mai 2026). Backup dispo à `~/crontab.backup` côté serveur.

### GitHub
- Repo : `oryonconseils89/stock-heatmap` (PRIVÉ)
- Branche : `main`
- PAT : fine-grained, scopes Contents Read+Write
- PAT stocké dans `.env` côté serveur, jamais commité

### Vercel
- Org : `oryonconseils89's-projects`
- Project : `stocks-screener`
- Stable alias prod : `https://stocks-screener-chi.vercel.app`
- Deploy : `vercel deploy --prod` depuis `~/stock-heatmap` côté serveur
- Tokens dans `.env` côté serveur : `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, `VERCEL_ORG_ID`
- Finnhub API key : `FINNHUB_API_KEY` dans `.env` (free tier)

## 12. URLs et endpoints

- Dashboard live : https://stocks-screener-chi.vercel.app
- GitHub repo : https://github.com/oryonconseils89/stock-heatmap
- Vercel project : https://vercel.com/oryonconseils89s-projects/stocks-screener

## 13. Workflow local → server deploy

Étapes standards quand tu modifies du code :

1. Edit fichiers dans `~/Documents/Claude/Projects/Stocks screener/` côté Mac
2. Test local si possible (run scripts standalone, check JSON output, lint)
3. `git add -A && git commit -m "<message clair>" && git push origin main`
4. SSH au serveur : `ssh -i ~/.ssh/oracle-screening.key ubuntu@<ORACLE_IP>`
5. `cd ~/stock-heatmap && git pull`
6. Prochain cron run prendra le nouveau code (si crons actifs)
7. Si test urgent : `./scripts/run_scan.sh "test-$(date +%H:%M)"` — attention, consomme la limite Max subscription

## 14. Quand mettre à jour ce fichier

Mets à jour `CLAUDE.md` quand :
- Un nouveau plantage est observé → ajoute-le à la section 8 avec cause racine et mitigation
- Une convention change (seuils, cadence, sources de données)
- Une URL, un path, ou un accès change
- L'utilisateur exprime une nouvelle préférence de collaboration → section 9
- Un nouveau script est ajouté ou un existant change de rôle → section 3

Le but : qu'une session Claude Code à froid, ouverte dans 6 mois, ait tout le contexte nécessaire pour collaborer immédiatement sans avoir à redécouvrir les leçons déjà apprises.
