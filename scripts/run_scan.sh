#!/bin/bash
set -e
cd ~/stock-heatmap
source .env
export PATH=$PATH:/usr/local/bin:/usr/bin

LABEL="${1:-$(date +%H:%M)}"
LOG="logs/$(date +%Y-%m-%d).log"
mkdir -p logs

echo "[$(date +%H:%M:%S)] === SCAN $LABEL ===" >> "$LOG"

# Check marché ouvert
python3 scripts/is_market_open.py || { echo "[$(date +%H:%M:%S)] SKIP marché fermé" >> "$LOG"; exit 0; }

# Lancer Claude Code en mode headless avec le prompt
# Timeout étendu à 15 min pour permettre une vraie analyse approfondie de 10 candidats max
# (gather_data.py default --max-tickers 10 limite déjà au top 10 baisseurs)
timeout 900 claude -p "Lis intégralement le fichier scripts/screening_prompt.md et suis-le exactement pour la session label \"$LABEL\". Tu as accès aux outils Bash, Read, Write, Edit. Important : prends ton temps, vise la qualité d'analyse pour CHAQUE candidat. Tu as 15 minutes, utilise-les. Pas de raccourcis 'analyse omise pour optimisation temps' ou 'analyse en attente' — tu produis du vrai contenu pour chaque candidat ou tu marques honnêtement Confiance LOW avec un raisonnement explicite. Termine silencieusement." \
  --allowed-tools Bash,Read,Write,Edit >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] === FIN $LABEL ===" >> "$LOG"
