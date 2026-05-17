#!/usr/bin/env python3
"""
Stocks Screener — Dashboard Builder v3
=======================================
Rigueur factuelle, sources, palette sobre.
- Value network : 1 ticker par catégorie avec rationale au hover
- Chiffres clés : chacun avec sa source visible
- Context grid : source globale affichée sous la grille
- Macro bar : couleur = signal pour long-equity (rouge = bad, vert = good, gris = neutre)
- Méthodologie réécrite avec backing recherche académique
"""

import argparse
import json
from pathlib import Path


TOOLTIPS = {
    "price": "Le prix actuel du titre, en dollars. Source : dernière cotation Yahoo Finance à l'horodatage du pull.",
    "cap": "Capitalisation boursière (prix × nombre d'actions). Le screener ne retient que les ≥ 50 milliards $ — sociétés assez solides pour qu'un drawdown court terme se rattrape statistiquement plus vite. Source : Yahoo Finance.",
    "sector": "Performance du jour de l'ETF SPDR du secteur GICS du titre. XLK = Tech, XLF = Finance, XLV = Santé, XLY = Conso cyclique, XLP = Conso défensive, XLC = Comm services, XLI = Industriels, XLE = Énergie, XLU = Utilities, XLRE = Real Estate, XLB = Matériaux. Sert à distinguer une chute sectorielle (souvent du bruit) d'une chute idiosyncratique (à investiguer). Source : Yahoo Finance.",
    "vol": "Volume échangé aujourd'hui rapporté à la moyenne 30 jours. >2× = flux institutionnel lourd (souvent capitulation ou repositionnement majeur). <0.7× = vente légère, prises de profits (renforce thèse de bruit). Source : Yahoo Finance.",
    "pos52": "Position du prix entre le plancher et le plafond des 12 derniers mois, en %. 0% = plancher annuel, le titre tombe en continu (risque élevé de continuation). 100% = plafond annuel, redescend après un rallye (pullback technique probable). Calcul : (prix - 52w low) / (52w high - 52w low). Source : Yahoo Finance.",
    "range": "Plus bas et plus haut atteints sur 52 semaines glissantes. Source : Yahoo Finance.",

    "strategic_group": "Concurrents directs du titre — même niche stratégique, taille et positionnement comparables. Si tous baissent ensemble = mouvement de cohort (souvent bruit). Si seul ce titre plonge = idiosyncratique, exige un catalyseur identifié.",
    "value_network": "Cartographie des partenaires économiques du titre selon Brandenburger & Nalebuff (Value Net, 1996). 1 ticker par catégorie pour la lisibilité. Survole chaque chip pour voir la nature précise de la relation.",
    "vn_customers": "L'acheteur principal et public du titre. Quand il vibre, notre titre vibre par sympathie ou anti-sympathie.",
    "vn_suppliers": "Le fournisseur critique sans lequel l'entreprise ne peut pas produire. Une rupture chez lui paralyse notre titre.",
    "vn_substitutes": "L'alternative que les clients pourraient choisir à la place de notre produit. Plus il se renforce, plus la position concurrentielle s'érode.",
    "vn_complementors": "L'entreprise dont les produits amplifient la valeur du nôtre (effet de réseau ou écosystème). Quand elle monte, elle tire souvent notre titre avec.",

    "macro_spy": "S&P 500 — l'indice des 500 plus grandes entreprises américaines. Représente la direction générale du marché actions US.",
    "macro_vix": "L'indice de la peur. Mesure combien les investisseurs paient pour se protéger d'une chute du S&P 500 sur les 30 prochains jours. Plus il est haut, plus le marché anticipe de la volatilité.",
    "macro_us10y": "Le rendement des obligations d'État américaines à 10 ans. C'est le taux de référence du système financier — il détermine ce que rapporte un placement sans risque, ce qui influence la valeur de toutes les actions.",
    "macro_dxy": "L'indice qui mesure la force du dollar américain face à un panier des principales devises mondiales (euro, yen, livre, etc.). Plus haut = dollar plus fort.",
    "macro_wti": "Le prix du baril de pétrole brut américain (West Texas Intermediate) en dollars. Indicateur clé de la demande économique mondiale et moteur d'inflation.",
    "market_bar": "Survole un chiffre pour la définition de l'indicateur. Clique sur 'Code couleur' juste en dessous pour le tableau complet des seuils.",

    "key_metrics": "Trois indicateurs spécifiquement choisis pour ce titre dans son contexte du jour. L'interprétation qui suit dit pourquoi ces 3 chiffres-là sont les bons à regarder maintenant et ce qu'ils racontent ensemble. Chaque chiffre est sourcé pour vérification.",
}


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Stocks Screener — Dashboard</title>
<style>
  :root {
    color-scheme: light;
    --bg: #f7f8fa;
    --panel: #ffffff;
    --border: #e4e7eb;
    --border-strong: #d1d5db;
    --text: #1f2937;
    --text-muted: #6b7280;
    --text-faint: #9ca3af;
    --accent: #4f46e5;
    --good: #047857;
    --bad: #b91c1c;
    --neutral: #6b7280;
    --good-bg: #ecfdf5;
    --bad-bg: #fef2f2;
    --neutral-bg: #f3f4f6;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 16px; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.55; }
  .header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border-strong); }
  .header h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.2px; }
  .header .meta { color: var(--text-muted); font-size: 13px; font-variant-numeric: tabular-nums; }

  /* HOW IT WORKS PANEL */
  .howto { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 14px; overflow: hidden; }
  .howto-header { padding: 10px 14px; cursor: pointer; user-select: none; display: flex; justify-content: space-between; align-items: center; font-size: 12.5px; color: var(--text); font-weight: 600; }
  .howto-header:hover { background: #fafbfc; }
  .howto-header .arrow { font-size: 10px; transition: transform 0.15s; color: var(--text-muted); }
  .howto.open .howto-header .arrow { transform: rotate(90deg); }
  .howto-body { display: none; padding: 4px 18px 18px; font-size: 13px; color: var(--text); line-height: 1.65; border-top: 1px solid var(--border); }
  .howto.open .howto-body { display: block; }
  .howto-body h4 { font-size: 11px; text-transform: uppercase; color: var(--accent); margin: 14px 0 6px; font-weight: 700; letter-spacing: 0.5px; }
  .howto-body p { margin: 6px 0; }
  .howto-body .vbox { display: flex; gap: 10px; margin: 6px 0; flex-wrap: wrap; align-items: baseline; }
  .howto-body .vchip { padding: 3px 9px; border-radius: 4px; font-size: 11px; font-weight: 600; font-family: ui-monospace, "SF Mono", monospace; }
  .howto-body .vchip.entry { background: var(--good-bg); color: var(--good); }
  .howto-body .vchip.passe { background: var(--bad-bg); color: var(--bad); }
  .howto-body .vchip.h { background: #1f2937; color: #fff; }
  .howto-body .vchip.m { background: #6b7280; color: #fff; }
  .howto-body .vchip.l { background: #d1d5db; color: #374151; }
  .howto-body ol { margin: 4px 0 8px; padding-left: 20px; }
  .howto-body ol li { margin: 6px 0; }
  .howto-body cite { color: var(--text-muted); font-size: 11px; font-style: italic; }

  /* MARKET BAR — 5 macros standardisés. overflow:visible pour ne pas clipper les tooltips. */
  .market-bar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; padding: 0; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 16px; position: relative; cursor: help; overflow: visible; }
  .market-bar > .macro:first-child { border-top-left-radius: 5px; border-bottom-left-radius: 5px; }
  .market-bar > .macro:last-child { border-top-right-radius: 5px; border-bottom-right-radius: 5px; }
  .market-bar:hover .market-mood-tip { visibility: visible; opacity: 1; }
  /* Si le curseur est sur le ⓘ d'un KPI, on cache la lecture globale pour ne pas écraser la définition KPI */
  .market-bar:has(.mlabel:hover) .market-mood-tip { visibility: hidden !important; opacity: 0 !important; }
  .macro { padding: 14px 14px; border-right: 1px solid var(--border); min-height: 80px; display: flex; flex-direction: column; justify-content: space-between; }
  .macro:last-child { border-right: none; }
  .macro .mlabel { font-size: 10px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.6px; font-weight: 600; cursor: help; position: relative; display: inline-block; }
  .macro .mlabel::after { content: ' ⓘ'; opacity: 0.35; font-size: 9px; }
  .macro .mlabel .mtip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; top: calc(100% + 6px); left: 0; z-index: 200; background: #1f2937; color: #fff; padding: 10px 12px; border-radius: 5px; font-size: 11.5px; line-height: 1.5; font-weight: 400; width: 280px; text-transform: none; letter-spacing: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.2); pointer-events: none; }
  .macro .mlabel:hover .mtip { visibility: visible; opacity: 1; }
  .macro .mvalue { font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.1; margin-top: 4px; }
  .macro .mdelta { font-size: 11.5px; font-variant-numeric: tabular-nums; margin-top: 4px; font-weight: 500; }
  .mvalue.signal-good, .mdelta.signal-good { color: var(--good); }
  .mvalue.signal-bad, .mdelta.signal-bad { color: var(--bad); }
  .mvalue.signal-neutral, .mdelta.signal-neutral { color: var(--text-faint); }  /* gris clair — non interprétable */
  .market-mood-tip { visibility: hidden; opacity: 0; transition: opacity 0.2s; position: absolute; top: calc(100% + 8px); left: 0; right: 0; z-index: 150; background: #1f2937; color: #fff; padding: 14px 16px; border-radius: 6px; font-size: 13px; line-height: 1.6; font-weight: 400; box-shadow: 0 6px 20px rgba(0,0,0,0.2); pointer-events: none; }
  .market-mood-tip::before { content: 'Lecture du marché'; display: block; font-size: 10px; text-transform: uppercase; color: var(--text-faint); letter-spacing: 0.6px; margin-bottom: 6px; font-weight: 700; }

  /* COLOR CODE TABLE (foldable, sous la market bar) */
  .color-code { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 16px; overflow: hidden; }
  .color-code-header { padding: 9px 14px; cursor: pointer; user-select: none; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); font-weight: 600; }
  .color-code-header:hover { background: #fafbfc; color: var(--text); }
  .color-code-header .arrow { font-size: 10px; transition: transform 0.15s; }
  .color-code.open .color-code-header .arrow { transform: rotate(90deg); }
  .color-code-body { display: none; padding: 4px 16px 18px; border-top: 1px solid var(--border); }
  .color-code.open .color-code-body { display: block; }
  .color-code-intro { font-size: 12.5px; color: var(--text-muted); margin: 12px 0 14px; line-height: 1.55; }
  .cc-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
  .cc-table thead th { text-align: left; padding: 8px 10px; background: #f9fafb; border-bottom: 1px solid var(--border); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700; }
  .cc-table thead th:nth-child(1) { width: 16%; }
  .cc-table thead th:nth-child(2), .cc-table thead th:nth-child(3) { width: 42%; }
  .cc-table tbody th { text-align: left; padding: 14px 10px; font-weight: 700; font-size: 12.5px; vertical-align: middle; color: var(--text); border-bottom: 1px solid var(--border); }
  .cc-table tbody td { padding: 10px 8px; vertical-align: middle; border-bottom: 1px solid var(--border); color: var(--text); }
  .cc-table tbody tr:last-child th, .cc-table tbody tr:last-child td { border-bottom: none; }
  /* 3-column sub-grid per cell — perfect symmetry */
  .cc-cell-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
  .cc-sub { padding: 8px 6px; border-radius: 4px; text-align: center; background: #fafbfc; border: 1px solid var(--border); }
  .cc-sub.cc-sub-good { background: var(--good-bg); border-color: #a7f3d0; }
  .cc-sub.cc-sub-neutral { background: var(--neutral-bg); border-color: #e5e7eb; }
  .cc-sub.cc-sub-bad { background: var(--bad-bg); border-color: #fecaca; }
  .cc-sub.cc-sub-empty { background: transparent; border: 1px dashed var(--border); }
  .cc-pill { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 9.5px; font-weight: 700; font-family: ui-monospace, "SF Mono", monospace; letter-spacing: 0.4px; margin-bottom: 5px; text-transform: uppercase; }
  .cc-pill.cc-good { background: var(--good); color: #fff; }
  .cc-pill.cc-bad { background: var(--bad); color: #fff; }
  .cc-pill.cc-neutral { background: var(--text-muted); color: #fff; }
  .cc-sub-cond { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); line-height: 1.3; }
  .cc-sub-gloss { font-size: 10.5px; color: var(--text-muted); margin-top: 3px; line-height: 1.35; }
  .cc-sub-empty .cc-pill { background: transparent; color: var(--text-faint); border: 1px solid var(--border); }
  .cc-sub-empty .cc-sub-cond { color: var(--text-faint); font-weight: 500; }
  .cc-footer { font-size: 11.5px; color: var(--text-muted); margin: 14px 0 0; line-height: 1.55; font-style: italic; padding-top: 12px; border-top: 1px dashed var(--border); }

  .pos { color: var(--good); }
  .neg { color: var(--bad); }
  .neutral { color: var(--text-muted); }

  /* SESSION HEADER */
  .session-summary { display: flex; justify-content: space-between; align-items: baseline; padding: 4px 2px 12px; margin-bottom: 8px; }
  .session-summary .count { font-size: 13px; color: var(--text-muted); }
  .session-tally { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; line-height: 1.5; font-family: ui-monospace, "SF Mono", monospace; white-space: nowrap; }
  .pill.entry-h { background: var(--good-bg); color: var(--good); }
  .pill.entry-m { background: #f0fdf4; color: #15803d; }
  .pill.entry-l { background: var(--neutral-bg); color: var(--text-muted); }
  .pill.passe-h { background: var(--bad-bg); color: var(--bad); }
  .pill.passe-m { background: #fef3f2; color: #b91c1c; }
  .pill.passe-l { background: var(--neutral-bg); color: var(--text-muted); }

  /* TICKERS */
  .ticker { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; overflow: visible; background: var(--panel); }
  .ticker-row { display: grid; grid-template-columns: 80px 1fr 70px 80px 160px; gap: 12px; align-items: center; padding: 11px 14px; cursor: pointer; user-select: none; min-height: 48px; }
  .ticker-verdict { text-align: right; white-space: nowrap; }
  .ticker-row:hover { background: #fafbfc; }
  .ticker-symbol { font-weight: 700; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 14px; letter-spacing: -0.3px; }
  .ticker-name { color: var(--text-muted); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ticker-change { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
  .ticker-cap { text-align: right; color: var(--text-muted); font-variant-numeric: tabular-nums; font-size: 12px; }
  .ticker-verdict { text-align: right; }
  .ticker-detail { display: none; padding: 14px 18px 18px; background: #fcfcfd; border-top: 1px solid var(--border); }
  .ticker.open .ticker-detail { display: block; }
  .ticker.open .ticker-row { background: #fafbfc; }

  .verdict-banner { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-radius: 5px; margin-bottom: 16px; font-weight: 600; }
  .verdict-banner.ENTRY { background: var(--good-bg); color: var(--good); border-left: 3px solid var(--good); }
  .verdict-banner.PASSE { background: var(--bad-bg); color: var(--bad); border-left: 3px solid var(--bad); }
  .verdict-banner .conf { font-size: 11px; font-weight: 500; padding: 2px 8px; background: rgba(0,0,0,0.06); border-radius: 4px; font-family: ui-monospace, "SF Mono", monospace; }

  /* Section blocks — uniformes, palette sobre */
  .section { margin-bottom: 14px; padding: 14px 16px; border-radius: 5px; font-size: 13.5px; line-height: 1.65; background: var(--panel); border: 1px solid var(--border); }
  .section .label { font-size: 10px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.6px; margin-bottom: 10px; color: var(--text-muted); display: block; }
  .section.situation { border-left: 3px solid #d97706; }
  .section.situation .label { color: #d97706; }
  .section.interpretation { border-left: 3px solid var(--accent); }
  .section.interpretation .label { color: var(--accent); }
  .section.key-metrics { border-left: 3px solid #0d9488; }
  .section.key-metrics .label { color: #0d9488; cursor: help; position: relative; }
  .section.key-metrics .label::after { content: ' ⓘ'; opacity: 0.4; font-size: 9px; }
  .section.key-metrics .label .km-tip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; bottom: calc(100% + 6px); left: 0; z-index: 100; background: #1f2937; color: #fff; padding: 10px 12px; border-radius: 5px; font-size: 11.5px; line-height: 1.5; font-weight: 400; width: 290px; text-transform: none; letter-spacing: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; }
  .section.key-metrics .label:hover .km-tip { visibility: visible; opacity: 1; }
  .km-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 8px 0 12px; }
  .km-card { background: #f9fafb; border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; display: flex; flex-direction: column; min-height: 100px; }
  .km-card .km-label { font-size: 10px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; letter-spacing: 0.4px; margin-bottom: 5px; }
  .km-card .km-value { font-size: 13.5px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); }
  .km-card .km-ctx { font-size: 11.5px; color: var(--text-muted); margin-top: 4px; font-style: italic; flex-grow: 1; }
  .km-card .km-source { font-size: 10px; color: var(--text-faint); margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border); }
  .km-card .km-source::before { content: 'Source : '; font-weight: 600; }
  .km-interp { font-size: 13px; color: var(--text); line-height: 1.6; }

  /* Context grid — uniformisé */
  .context-block { margin-bottom: 14px; }
  .context-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; }
  .ctx { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 9px 11px; position: relative; cursor: help; min-height: 56px; }
  .ctx .k { font-size: 10px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.4px; margin-bottom: 4px; font-weight: 600; }
  .ctx .k::after { content: ' ⓘ'; opacity: 0.35; font-size: 9px; }
  .ctx .v { font-weight: 700; font-size: 13.5px; font-variant-numeric: tabular-nums; }
  .ctx .tip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; bottom: calc(100% + 6px); left: 0; z-index: 100; background: #1f2937; color: #fff; padding: 10px 13px; border-radius: 5px; font-size: 12px; line-height: 1.55; font-weight: 400; width: 300px; max-width: 300px; text-transform: none; letter-spacing: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; }
  .ctx:hover .tip { visibility: visible; opacity: 1; }
  .context-source-line { font-size: 10.5px; color: var(--text-faint); margin-top: 6px; text-align: right; font-style: italic; }
  .context-source-line::before { content: 'Source : '; font-weight: 600; font-style: normal; }

  /* Groupe stratégique + Réseau de valeur side-by-side */
  .strategic-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
  @media (max-width: 800px) { .strategic-row { grid-template-columns: 1fr; } }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 12px 14px; min-height: 180px; }
  .panel .ptitle { font-size: 10px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.6px; font-weight: 700; margin-bottom: 10px; cursor: help; position: relative; display: inline-block; }
  .panel .ptitle::after { content: ' ⓘ'; opacity: 0.35; font-size: 9px; }
  .panel .ptitle .ptip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; bottom: calc(100% + 6px); left: 0; z-index: 100; background: #1f2937; color: #fff; padding: 10px 12px; border-radius: 5px; font-size: 11.5px; line-height: 1.5; font-weight: 400; width: 280px; text-transform: none; letter-spacing: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; }
  .panel .ptitle:hover .ptip { visibility: visible; opacity: 1; }

  /* Strategic group — chips empilés verticalement avec rationale */
  .sg-list { display: flex; flex-direction: column; gap: 6px; }
  .sg-row { display: grid; grid-template-columns: 60px 70px 1fr; gap: 8px; padding: 5px 8px; background: #f9fafb; border-radius: 3px; font-size: 11.5px; align-items: baseline; cursor: help; position: relative; }
  .sg-row .sg-tk { font-family: ui-monospace, "SF Mono", monospace; font-weight: 700; }
  .sg-row .sg-ch { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
  .sg-row .sg-why { color: var(--text-muted); font-size: 11px; line-height: 1.45; }

  /* Réseau de valeur — 2x2 grid */
  .vn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .vn-cell { background: #f9fafb; border: 1px solid var(--border); border-radius: 4px; padding: 9px 11px; min-height: 70px; display: flex; flex-direction: column; }
  .vn-cell .vn-cell-title { font-size: 10px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; letter-spacing: 0.4px; margin-bottom: 6px; cursor: help; position: relative; display: inline-block; }
  .vn-cell .vn-cell-title::after { content: ' ⓘ'; opacity: 0.35; font-size: 9px; }
  .vn-cell .vn-cell-title .vntip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; bottom: calc(100% + 6px); left: 0; z-index: 100; background: #1f2937; color: #fff; padding: 9px 11px; border-radius: 5px; font-size: 11px; line-height: 1.45; font-weight: 400; width: 240px; text-transform: none; letter-spacing: 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; }
  .vn-cell .vn-cell-title:hover .vntip { visibility: visible; opacity: 1; }
  .vn-ticker-row { display: grid; grid-template-columns: auto 1fr; gap: 6px; align-items: baseline; cursor: help; position: relative; padding: 2px 0; }
  .vn-ticker-row .vnt-sym { font-family: ui-monospace, "SF Mono", monospace; font-weight: 700; font-size: 12px; }
  .vn-ticker-row .vnt-data { text-align: right; font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .vn-ticker-row .vnt-tip { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; bottom: calc(100% + 4px); left: 0; z-index: 100; background: #1f2937; color: #fff; padding: 10px 12px; border-radius: 5px; font-size: 11px; line-height: 1.55; font-weight: 400; width: 320px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; white-space: pre-wrap; }
  .vn-ticker-row:hover .vnt-tip { visibility: visible; opacity: 1; }
  .vnt-source { font-size: 10px; color: var(--accent); text-decoration: none; font-weight: 600; margin-left: 4px; padding: 1px 6px; border: 1px solid var(--accent); border-radius: 3px; pointer-events: auto; white-space: nowrap; }
  .vnt-source:hover { background: var(--accent); color: #fff; }
  .vn-ticker-row { grid-template-columns: auto 1fr auto; }
  .vn-unsourced { font-size: 10.5px; color: var(--text-faint); font-style: italic; padding: 4px 0; line-height: 1.4; }

  /* News */
  .news { margin-top: 14px; padding: 12px 14px; background: var(--panel); border: 1px solid var(--border); border-radius: 5px; }
  .news .label { font-size: 10px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; letter-spacing: 0.6px; margin-bottom: 6px; }
  .news-item { padding: 5px 0; font-size: 13px; }
  .news-item a { color: var(--accent); text-decoration: none; font-weight: 500; }
  .news-item a:hover { text-decoration: underline; }
  .news-item .src { color: var(--text-muted); font-size: 11px; margin-left: 6px; }
  .news-item .news-note { color: var(--text-muted); font-size: 11.5px; font-style: italic; margin-top: 4px; }

  .empty { padding: 40px; text-align: center; color: var(--text-muted); background: var(--panel); border: 1px dashed var(--border-strong); border-radius: 6px; }
</style>
</head>
<body>

<div class="header">
  <h1>Stocks Screener</h1>
  <div class="meta" id="header-meta"></div>
</div>

<div class="howto" id="howto">
  <div class="howto-header" onclick="document.getElementById('howto').classList.toggle('open')">
    <span>&#9432; Méthodologie de classification</span>
    <span class="arrow">&#9654;</span>
  </div>
  <div class="howto-body">
    <h4>Le verdict (binaire)</h4>
    <div class="vbox"><span class="vchip entry">ENTRY</span><span>setup pour entrer en position : la baisse est probablement du bruit qui se résorbera dans les 24-72h.</span></div>
    <div class="vbox"><span class="vchip passe">PASSE</span><span>ne pas toucher : la baisse a une raison structurelle ou le titre est en chute libre, risque élevé de continuation.</span></div>

    <h4>Le niveau de confiance</h4>
    <div class="vbox"><span class="vchip h">HIGH</span><span>signaux convergents et clairs, peu de doute sur le verdict.</span></div>
    <div class="vbox"><span class="vchip m">MEDIUM</span><span>signaux dominants mais avec des contradictions ou des nuances.</span></div>
    <div class="vbox"><span class="vchip l">LOW</span><span>situation ambiguë, le verdict est mon meilleur jugement avec marge d'erreur réelle.</span></div>

    <h4>Le framework analytique (4 étapes intégrées, pas séquentielles)</h4>
    <p>Les 4 dimensions sont évaluées <i>simultanément</i> et se croisent — pas un checklist linéaire. Ce qui distingue un signal structurel d'un signal de bruit n'est pas la news isolée mais la convergence des 4.</p>

    <ol>
      <li><b>Catalyseur — nature de la news.</b> La taxonomie repose sur la recherche en finance comportementale (Tetlock, "Giving Content to Investor Sentiment", JoF 2007). Les news qui prédisent des sous-performances persistantes appartiennent à 4 catégories : <i>(a) révisions de guidance baissière, particulièrement annuelle</i> ; <i>(b) actions réglementaires actives (SEC enforcement, FDA non-approval, DOJ probe)</i> — Karpoff et al. ont montré que la perte de réputation dépasse 2-3× les amendes ; <i>(c) départs de top management non planifiés</i> — Lel & Miller, "International CEO Turnover", JFE 2015 montrent un drift négatif de 20-30% sur 12 mois ; <i>(d) effondrement d'un metric opérationnel critique</i> (perte de client >10% du CA, recall majeur, breach matériel). À l'opposé, les news qui se résorbent statistiquement : sell-the-news post-beat (De Bondt & Thaler 1985), downgrades isolés sans révision consensus (Womack 1996, JF), pullback technique après >20% rally (Jegadeesh & Titman 1993 — mean reversion court terme).</li>

      <li><b>Idiosyncrasie — décomposition de la chute.</b> J'utilise le modèle Fama-French simplifié : décomposer la variation du titre en composantes <i>marché</i> (SPY), <i>sectorielle</i> (XLK/XLF/etc.) et <i>spécifique</i>. Une chute majoritairement spécifique exige un catalyseur identifié et nommé. Une chute majoritairement sectorielle ou de marché penche vers le bruit. Si le titre baisse pendant que ses pairs montent (cas QCOM aujourd'hui), c'est 100% idiosyncratique — drapeau qui exige la qualité du catalyseur le plus haute.</li>

      <li><b>Signaux faibles — convergence/divergence.</b> Cinq signaux faibles indépendants, pondérés ensemble :
        <ul style="margin: 4px 0 0; padding-left: 20px;">
          <li><b>Volume vs moy. 30j</b> : >2× = capitulation institutionnelle ou repositionnement (Easley et al., "Liquidity, Information, and Less-Frequently Traded Stocks", JF 1996). <0.7× = rebalancing technique, pas de panique.</li>
          <li><b>Position 52 semaines</b> : <10% = "couteau qui tombe", George & Hwang (JF 2004) ont montré que les titres faisant de nouveaux lows continuent de sous-performer en moyenne. >85% = pullback après rallye, mean reversion attendue.</li>
          <li><b>Groupe stratégique</b> : si les concurrents directs bougent dans le même sens et la même magnitude, c'est un effet cohort (bruit). S'ils divergent, le mouvement est idiosyncratique.</li>
          <li><b>Réseau de valeur</b> : clients/fournisseurs/substituts/complémenteurs comme signaux d'écosystème. Si les clients chutent aussi, c'est de la demande qui faiblit (structurel). Si seuls les substituts montent, c'est un transfert de part de marché (structurel). Si l'écosystème entier est faible, c'est macro.</li>
          <li><b>Macro contextuel</b> : SPY/VIX/US10Y/DXY/WTI. Un mouvement idiosyncratique dans un VIX qui spike est moins inquiétant que le même mouvement dans un VIX calme (la peur ambiante "explique" sans expliquer).</li>
        </ul>
      </li>

      <li><b>Structure du titre — qualité défensive.</b> La capacité à rebondir dépend du balance sheet et de la position concurrentielle. Le filtre cap ≥ 50B élimine déjà 95% des cas vraiment fragiles, mais à l'intérieur de cet univers, je pondère implicitement : leverage, marges historiques, dépendance à un client unique, vulnérabilité réglementaire.</li>
    </ol>

    <h4>Règle finale</h4>
    <p><b>ENTRY</b> requiert la convergence de : catalyseur identifié et classifié comme bruit, idiosyncrasie limitée OU justifiée par mean reversion, signaux faibles globalement bénins, structure défensive. <b>PASSE</b> dès qu'un catalyseur structurel est présent OU que le titre est en couteau qui tombe (position 52w <10% + idiosyncrasie pure).</p>
    <p><cite>Sources principales : Tetlock (2007), Karpoff et al. (2008), Lel & Miller (2015), Womack (1996), De Bondt & Thaler (1985), Jegadeesh & Titman (1993), George & Hwang (2004).</cite></p>
  </div>
</div>

<div class="market-bar" id="market-bar" style="display:none;">
  <div class="market-mood-tip" id="mood-tip"></div>
</div>

<div class="color-code" id="color-code" style="display:none;">
  <div class="color-code-header" onclick="document.getElementById('color-code').classList.toggle('open')">
    <span>Code couleur des indicateurs macro</span>
    <span class="arrow">&#9654;</span>
  </div>
  <div class="color-code-body">
    <p class="color-code-intro">Chaque indicateur a <b>deux couleurs indépendantes</b> : le gros chiffre (niveau absolu) et le delta en dessous (mouvement du jour). Les seuils suivent les conventions standards en analyse de marché.</p>
    <table class="cc-table">
      <thead>
        <tr>
          <th>Indicateur</th>
          <th>Niveau (gros chiffre)</th>
          <th>Delta (Δ% du jour)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th>SPY<br><span style="font-weight:400;font-size:11px;color:var(--text-muted);">S&amp;P 500</span></th>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-empty"><span class="cc-pill">vert</span><div class="cc-sub-cond">—</div><div class="cc-sub-gloss">n/a</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">toujours</div><div class="cc-sub-gloss">prix d'indice, pas de seuil</div></div>
              <div class="cc-sub cc-sub-empty"><span class="cc-pill">rouge</span><div class="cc-sub-cond">—</div><div class="cc-sub-gloss">n/a</div></div>
            </div>
          </td>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">Δ ≥ +0.2%</div><div class="cc-sub-gloss">SPY monte</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">|Δ| &lt; 0.2%</div><div class="cc-sub-gloss">bruit</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">Δ ≤ -0.2%</div><div class="cc-sub-gloss">SPY baisse</div></div>
            </div>
          </td>
        </tr>
        <tr>
          <th>VIX<br><span style="font-weight:400;font-size:11px;color:var(--text-muted);">volatilité</span></th>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">&lt; 15</div><div class="cc-sub-gloss">calme</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">15 – 20</div><div class="cc-sub-gloss">normal</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">&gt; 20</div><div class="cc-sub-gloss">anxiété (panique &gt; 30)</div></div>
            </div>
          </td>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">Δ ≤ -2%</div><div class="cc-sub-gloss">peur retombe</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">|Δ| &lt; 2%</div><div class="cc-sub-gloss">bruit</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">Δ ≥ +2%</div><div class="cc-sub-gloss">peur s'installe</div></div>
            </div>
          </td>
        </tr>
        <tr>
          <th>US 10Y<br><span style="font-weight:400;font-size:11px;color:var(--text-muted);">taux</span></th>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">&lt; 3%</div><div class="cc-sub-gloss">taux bas, soutient actions</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">3 – 4.5%</div><div class="cc-sub-gloss">modéré, gérable</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">&gt; 4.5%</div><div class="cc-sub-gloss">pression sur actions</div></div>
            </div>
          </td>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">Δ ≤ -1%</div><div class="cc-sub-gloss">taux baissent</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">|Δ| &lt; 1%</div><div class="cc-sub-gloss">bruit</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">Δ ≥ +1%</div><div class="cc-sub-gloss">taux montent</div></div>
            </div>
          </td>
        </tr>
        <tr>
          <th>DXY<br><span style="font-weight:400;font-size:11px;color:var(--text-muted);">dollar</span></th>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">&lt; 95</div><div class="cc-sub-gloss">dollar faible</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">95 – 100</div><div class="cc-sub-gloss">normal</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">&gt; 100</div><div class="cc-sub-gloss">dollar fort</div></div>
            </div>
          </td>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">Δ ≤ -0.15%</div><div class="cc-sub-gloss">dollar baisse</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">|Δ| &lt; 0.15%</div><div class="cc-sub-gloss">bruit</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">Δ ≥ +0.15%</div><div class="cc-sub-gloss">dollar monte</div></div>
            </div>
          </td>
        </tr>
        <tr>
          <th>WTI<br><span style="font-weight:400;font-size:11px;color:var(--text-muted);">pétrole</span></th>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">&lt; 80$</div><div class="cc-sub-gloss">pas de pression inflation</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">80 – 100$</div><div class="cc-sub-gloss">zone moyenne</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">&gt; 100$</div><div class="cc-sub-gloss">pression inflationniste</div></div>
            </div>
          </td>
          <td>
            <div class="cc-cell-grid">
              <div class="cc-sub cc-sub-good"><span class="cc-pill cc-good">vert</span><div class="cc-sub-cond">Δ ≤ -1.5%</div><div class="cc-sub-gloss">désinflation</div></div>
              <div class="cc-sub cc-sub-neutral"><span class="cc-pill cc-neutral">gris</span><div class="cc-sub-cond">|Δ| &lt; 1.5%</div><div class="cc-sub-gloss">bruit</div></div>
              <div class="cc-sub cc-sub-bad"><span class="cc-pill cc-bad">rouge</span><div class="cc-sub-cond">Δ ≥ +1.5%</div><div class="cc-sub-gloss">inflation up</div></div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="cc-footer">Le delta est <b>vert</b> quand le mouvement du jour est favorable au marché actions, <b>rouge</b> quand défavorable, <b>gris</b> quand le mouvement reste dans la volatilité daily typique (donc non interprétable comme signal).</p>
  </div>
</div>

<div id="content"></div>

<script id="dashboard-data" type="application/json">__DATA_JSON__</script>
<script id="tooltips-data" type="application/json">__TIPS_JSON__</script>
<script>
function fmtPct(p){if(p===null||p===undefined)return"—";return(p>0?"+":"")+p.toFixed(2)+"%";}
function pctClass(p){if(p===null||p===undefined)return"neutral";return p>0?"pos":(p<0?"neg":"neutral");}
function verdictPillClass(v,conf){const c=(conf||"").toUpperCase();if(v==="ENTRY")return c==="HIGH"?"entry-h":(c==="LOW"?"entry-l":"entry-m");if(v==="PASSE")return c==="HIGH"?"passe-h":(c==="LOW"?"passe-l":"passe-m");return"passe-m";}
function escapeHTML(s){if(s===null||s===undefined)return"";return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function fmtDateTime(iso){if(!iso)return"";try{const d=new Date(iso);const months=['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()} · ${String(d.getHours()).padStart(2,'0')}h${String(d.getMinutes()).padStart(2,'0')} ET`;}catch(e){return iso;}}

const TIPS=JSON.parse(document.getElementById('tooltips-data').textContent);

function macroSignalClass(signal){
  if(signal === 'good') return 'signal-good';
  if(signal === 'bad') return 'signal-bad';
  return 'signal-neutral';
}

// ============================================================================
// MACRO COLOR LOGIC — 2 dimensions indépendantes
// ============================================================================
// 1) LEVEL signal : où en est le KPI dans l'absolu, selon les seuils de la
//    pratique courante des analystes.
// 2) DELTA signal : comment le KPI a bougé aujourd'hui, selon sa volatilité
//    daily typique (seuil au-dessus duquel le mouvement devient signifiant).
//
// SPY : niveau absolu non interprétable (prix d'un indice), reste toujours
//       en gris. Seul le delta porte un signal.
// ============================================================================

function levelSignal(key, level){
  if(level === null || level === undefined) return 'neutral';
  if(key === 'spy') return 'neutral';  // pas de seuil absolu pour un prix d'indice
  if(key === 'vix'){
    if(level < 15) return 'good';      // calme, marché complaisant
    if(level < 20) return 'neutral';   // zone normale
    return 'bad';                       // 20+ = anxiété installée, 30+ = panique
  }
  if(key === 'us10y'){
    if(level < 3) return 'good';        // taux bas, soutient les multiples actions
    if(level < 4.5) return 'neutral';   // zone modérée, gérable
    return 'bad';                       // 4.5%+ pression réelle sur valorisations growth
  }
  if(key === 'dxy'){
    if(level < 95) return 'good';       // dollar faible, bénéfique pour multinationales US et EM
    if(level < 100) return 'neutral';   // zone normale
    return 'bad';                       // 100+ = dollar fort, pression sur revenus étrangers
  }
  if(key === 'wti'){
    if(level < 80) return 'good';       // prix modéré, ne pèse pas sur l'inflation consommateur
    if(level < 100) return 'neutral';   // zone moyenne
    return 'bad';                       // 100+ = pression inflationniste matérielle
  }
  return 'neutral';
}

// Seuils sous lesquels un mouvement est du bruit quotidien (pas de signal).
const NEUTRAL_THRESHOLDS = { spy: 0.2, vix: 2.0, us10y: 1.0, dxy: 0.15, wti: 1.5 };

function deltaSignal(key, change_pct){
  if(change_pct === null || change_pct === undefined) return 'neutral';
  const threshold = NEUTRAL_THRESHOLDS[key] || 0.2;
  if(Math.abs(change_pct) < threshold) return 'neutral';
  if(key === 'spy') return change_pct > 0 ? 'good' : 'bad';
  return change_pct > 0 ? 'bad' : 'good';  // pour VIX/10Y/DXY/WTI : up = bad pour equity
}

function renderMacro(key, label, data){
  if(!data) return '';
  // Niveau absolu = gros chiffre coloré selon les seuils standards (cf levelSignal).
  // Delta = petit chiffre coloré selon la trend (cf deltaSignal).
  const isPercent = key === 'us10y';
  const levelStr = isPercent ? `${data.last}%` : `${data.last}`;
  const lvlSig = levelSignal(key, data.last);
  const dltSig = deltaSignal(key, data.change_pct);
  return `<div class="macro">
    <div>
      <div class="mlabel">${escapeHTML(label)}<div class="mtip">${escapeHTML(TIPS['macro_'+key]||'')}</div></div>
    </div>
    <div>
      <div class="mvalue ${macroSignalClass(lvlSig)}">${levelStr}</div>
      <div class="mdelta ${macroSignalClass(dltSig)}">Δ ${fmtPct(data.change_pct)}</div>
    </div>
  </div>`;
}

function ctx(key,label,value,valueClass){return `<div class="ctx"><div class="k">${escapeHTML(label)}</div><div class="v ${valueClass||''}">${value}</div><div class="tip">${escapeHTML(TIPS[key]||'')}</div></div>`;}

function renderVnCell(title, key, items){
  // Honesty contract: null OR empty array → display "non documentable de manière fiable"
  if(items === null || items === undefined || (Array.isArray(items) && items.length === 0)){
    return `<div class="vn-cell">
      <div class="vn-cell-title">${escapeHTML(title)}<div class="vntip">${escapeHTML(TIPS[key]||'')}</div></div>
      <div class="vn-unsourced">non documentable de manière fiable</div>
    </div>`;
  }
  // Normalize to array (some entries might be a single object)
  const arr = Array.isArray(items) ? items : [items];
  const rows = arr.map(t => {
    // Build the source link + quote tooltip
    let sourceBadge = '';
    if (t.source_url) {
      const quote = t.source_quote || t.rationale || '';
      sourceBadge = `<a href="${escapeHTML(t.source_url)}" target="_blank" rel="noopener" class="vnt-source" title="${escapeHTML(quote)}">source ↗</a>`;
    }
    // Hover tooltip combines rationale + (if available) source quote
    const tipContent = t.source_quote
      ? `${escapeHTML(t.rationale||'')}\n\n« ${escapeHTML(t.source_quote)} »`
      : escapeHTML(t.rationale||'');
    return `<div class="vn-ticker-row">
      <span class="vnt-sym">${escapeHTML(t.ticker)}</span>
      <span class="vnt-data">$${t.price?t.price.toFixed(2):'—'} <span class="${pctClass(t.change_pct)}">${fmtPct(t.change_pct)}</span></span>
      ${sourceBadge}
      ${t.rationale ? `<div class="vnt-tip">${tipContent}</div>` : ''}
    </div>`;
  }).join('');
  return `<div class="vn-cell">
    <div class="vn-cell-title">${escapeHTML(title)}<div class="vntip">${escapeHTML(TIPS[key]||'')}</div></div>
    ${rows}
  </div>`;
}

function renderKeyMetrics(metrics, interpretation){
  if(!metrics || metrics.length === 0) return '';
  const cards = metrics.map(m => `<div class="km-card">
    <div class="km-label">${escapeHTML(m.label)}</div>
    <div class="km-value">${escapeHTML(m.value)}</div>
    <div class="km-ctx">${escapeHTML(m.context||'')}</div>
    ${m.source ? `<div class="km-source">${escapeHTML(m.source)}</div>` : ''}
  </div>`).join('');
  return `<div class="section key-metrics">
    <div class="label">Chiffres clés<div class="km-tip">${escapeHTML(TIPS.key_metrics||'')}</div></div>
    <div class="km-grid">${cards}</div>
    <div class="km-interp">${escapeHTML(interpretation||'')}</div>
  </div>`;
}

function renderTicker(c, contextSource) {
  const verdictClass = verdictPillClass(c.verdict, c.confidence);
  const verdictLabel = (c.verdict || "?") + (c.confidence ? " · " + c.confidence : "");

  // Strategic group — empilé avec rationale visible
  const sgRows = (c.strategic_group || []).map(p =>
    `<div class="sg-row">
      <span class="sg-tk">${escapeHTML(p.ticker)}</span>
      <span class="sg-ch ${pctClass(p.change_pct)}">${fmtPct(p.change_pct)}</span>
      <span class="sg-why">${escapeHTML(p.rationale || '')}</span>
    </div>`
  ).join("");

  // News
  const newsHTML = (c.news || []).length
    ? c.news.map(n => `<div class="news-item">
        <a href="${escapeHTML(n.url || '#')}" target="_blank" rel="noopener">${escapeHTML(n.title)}</a>
        <span class="src">— ${escapeHTML(n.source || '')}</span>
        ${n.note ? `<div class="news-note">${escapeHTML(n.note)}</div>` : ''}
      </div>`).join("")
    : '<div class="news-item" style="color:var(--text-faint);font-style:italic;">Aucune news propre au ticker dans les dernières 48h</div>';

  const r52 = c.range_52w || {};
  const sectorEtf = c.sector_etf || {};
  const vn = c.value_network || {};

  return `<div class="ticker">
    <div class="ticker-row" onclick="this.parentElement.classList.toggle('open')">
      <div class="ticker-symbol">${escapeHTML(c.ticker)}</div>
      <div class="ticker-name">${escapeHTML(c.name || '')}</div>
      <div class="ticker-change ${pctClass(c.change_pct)}">${fmtPct(c.change_pct)}</div>
      <div class="ticker-cap">$${(c.market_cap_b||0).toFixed(1)}B</div>
      <div class="ticker-verdict"><span class="pill ${verdictClass}">${escapeHTML(verdictLabel)}</span></div>
    </div>
    <div class="ticker-detail">
      <div class="verdict-banner ${c.verdict||''}">
        <span>${c.verdict==='ENTRY'?'✓ Entrée légitime':'✕ Passe ton chemin'}</span>
        <span class="conf">Confiance ${escapeHTML(c.confidence||'')}</span>
      </div>

      <div class="section situation"><div class="label">Situation</div>${escapeHTML(c.situation || 'N/A')}</div>
      <div class="section interpretation"><div class="label">Interprétation</div>${escapeHTML(c.interpretation || '')}</div>
      ${renderKeyMetrics(c.key_metrics, c.key_metrics_interpretation)}

      <div class="context-block">
        <div class="context-grid">
          ${ctx('price', 'Prix', '$'+(c.price||0).toFixed(2))}
          ${ctx('cap', 'Capitalisation', '$'+(c.market_cap_b||0).toFixed(1)+'B')}
          ${ctx('sector', 'Secteur ('+escapeHTML(sectorEtf.symbol||'?')+')', fmtPct(sectorEtf.change_pct), pctClass(sectorEtf.change_pct))}
          ${ctx('vol', 'Volume vs moy. 30j', c.volume_ratio?c.volume_ratio.toFixed(2)+'x':'—')}
          ${ctx('pos52', 'Position 52w', r52.position_pct!==null&&r52.position_pct!==undefined?r52.position_pct.toFixed(1)+'%':'—')}
          ${ctx('range', 'Range 52w', '<span style="font-size:11px;">$'+(r52.low||0).toFixed(2)+'–$'+(r52.high||0).toFixed(2)+'</span>')}
        </div>
        ${contextSource ? `<div class="context-source-line">${escapeHTML(contextSource)}</div>` : ''}
      </div>

      <div class="strategic-row">
        <div class="panel">
          <div class="ptitle">Groupe stratégique<div class="ptip">${escapeHTML(TIPS.strategic_group||'')}</div></div>
          <div class="sg-list">${sgRows || '<div style="font-size:11px;color:var(--text-faint);font-style:italic;">aucun concurrent direct comparable</div>'}</div>
        </div>
        <div class="panel">
          <div class="ptitle">Réseau de valeur<div class="ptip">${escapeHTML(TIPS.value_network||'')}</div></div>
          <div class="vn-grid">
            ${renderVnCell('Clients', 'vn_customers', vn.customers)}
            ${renderVnCell('Fournisseurs', 'vn_suppliers', vn.suppliers)}
            ${renderVnCell('Substituts', 'vn_substitutes', vn.substitutes)}
            ${renderVnCell('Complémenteurs', 'vn_complementors', vn.complementors)}
          </div>
        </div>
      </div>

      <div class="news"><div class="label">Source</div>${newsHTML}</div>
    </div>
  </div>`;
}

(function render() {
  const data = JSON.parse(document.getElementById('dashboard-data').textContent);
  const root = document.getElementById('content');

  if (!data.candidates || !data.candidates.length) {
    root.innerHTML = `<div class="empty">Aucun candidat encore. Le prochain scan tourne au prochain horaire planifié<br><small style="color:var(--text-faint)">(9h35, 11h30, 13h30, ou 15h30 ET, jours ouvrables)</small></div>`;
    document.getElementById('header-meta').textContent = '—';
    return;
  }

  document.getElementById('header-meta').textContent = fmtDateTime(data.as_of);

  const ctx_macro = data.market_context || {};
  const macroBar = document.getElementById('market-bar');
  const labels = {spy: 'SPY', vix: 'VIX', us10y: 'US 10Y', dxy: 'DXY', wti: 'WTI'};
  const macroOrder = ['spy', 'vix', 'us10y', 'dxy', 'wti'];
  const macroHTML = macroOrder.map(k => renderMacro(k, labels[k], ctx_macro[k])).join('');
  macroBar.insertAdjacentHTML('afterbegin', macroHTML);
  document.getElementById('mood-tip').textContent = ctx_macro.market_mood || '';
  macroBar.style.display = 'grid';
  document.getElementById('color-code').style.display = 'block';

  const candidates = data.candidates;
  const tallies = {'entry-h':0,'entry-m':0,'entry-l':0,'passe-h':0,'passe-m':0,'passe-l':0};
  candidates.forEach(c => { const k = verdictPillClass(c.verdict, c.confidence); tallies[k] = (tallies[k]||0)+1; });
  let pillsHTML = '';
  if (tallies['entry-h']) pillsHTML += `<span class="pill entry-h">${tallies['entry-h']} ENTRY·H</span>`;
  if (tallies['entry-m']) pillsHTML += `<span class="pill entry-m">${tallies['entry-m']} ENTRY·M</span>`;
  if (tallies['entry-l']) pillsHTML += `<span class="pill entry-l">${tallies['entry-l']} ENTRY·L</span>`;
  if (tallies['passe-h']) pillsHTML += `<span class="pill passe-h">${tallies['passe-h']} PASSE·H</span>`;
  if (tallies['passe-m']) pillsHTML += `<span class="pill passe-m">${tallies['passe-m']} PASSE·M</span>`;
  if (tallies['passe-l']) pillsHTML += `<span class="pill passe-l">${tallies['passe-l']} PASSE·L</span>`;

  const sessionHeader = `<div class="session-summary">
    <div class="count">${candidates.length} candidat${candidates.length>1?'s':''} sur ${data.screened_total||candidates.length} losers screenés</div>
    <div class="session-tally">${pillsHTML}</div>
  </div>`;

  const contextSource = data.context_source || '';
  const tickersHTML = candidates.map(c => renderTicker(c, contextSource)).join('');
  root.innerHTML = sessionHeader + tickersHTML;
})();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    project_root = here.parent
    data_path = Path(args.data) if args.data else (project_root / "data" / "today.json")
    out_path = Path(args.out) if args.out else (project_root / "scripts" / "dashboard.html")
    deploy_path = project_root / "deploy" / "index.html"

    if not data_path.exists():
        data = {"date": "—", "as_of": None, "market_context": {}, "candidates": []}
    else:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    data_json = json.dumps(data, ensure_ascii=False)
    tips_json = json.dumps(TOOLTIPS, ensure_ascii=False)

    data_json_safe = data_json.replace("</script>", "<\\/script>")
    tips_json_safe = tips_json.replace("</script>", "<\\/script>")

    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json_safe).replace("__TIPS_JSON__", tips_json_safe)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    if deploy_path.parent.exists():
        with open(deploy_path, "w", encoding="utf-8") as f:
            f.write(html)

    candidates = len(data.get("candidates", []))
    print(f"OK — wrote {len(html)} bytes to {out_path} ({candidates} candidates)")
    if deploy_path.parent.exists():
        print(f"     mirrored to {deploy_path}")


if __name__ == "__main__":
    main()
