#!/usr/bin/env python3
"""
Cache value_network + strategic_group par ticker — TTL 90 jours.

Les value networks (Clients/Fournisseurs/Substituts/Complémenteurs) et les
strategic groups d'un titre sont stables pendant des mois — la composition des
clients/fournisseurs déclarés au 10-K ne change qu'à la prochaine annual filing,
et le groupe stratégique évolue à l'échelle des trimestres, pas des jours.

Plutôt que de regénérer ces structures à chaque scheduled task, on les cache et
on ne les rafraîchit que (a) au-delà du TTL ou (b) si l'utilisateur force un
refresh manuel.

Usage:
    from vn_cache import get_cached_vn, set_cached_vn, get_cached_sg, set_cached_sg
    cached = get_cached_vn("QCOM")
    if cached is None:
        # rebuild via SEC + Claude, then:
        set_cached_vn("QCOM", value_network_dict)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "cache"
VN_TTL_DAYS = 90
SG_TTL_DAYS = 90


def _cache_path(category: str, ticker: str) -> Path:
    """category in {'vn', 'sg'}"""
    d = CACHE_DIR / category
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ticker.upper()}.json"


def _get_cached(category: str, ticker: str, ttl_days: int):
    p = _cache_path(category, ticker)
    if not p.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    if age > timedelta(days=ttl_days):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def _set_cached(category: str, ticker: str, data):
    p = _cache_path(category, ticker)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_cached_vn(ticker: str):
    """Retourne le value_network caché si frais (≤90j), sinon None."""
    return _get_cached("vn", ticker, VN_TTL_DAYS)


def set_cached_vn(ticker: str, value_network: dict):
    """Persiste un value_network (les prix seront rafraîchis ailleurs, le cache
    stocke uniquement la structure : tickers + rationale + source)."""
    # Strip les prix volatils — on ne cache que la structure stable
    stripped = {}
    for cat, items in value_network.items():
        if items is None:
            stripped[cat] = None
            continue
        arr = items if isinstance(items, list) else [items]
        stripped[cat] = [
            {k: v for k, v in item.items() if k not in ("price", "change_pct")}
            for item in arr
        ]
    _set_cached("vn", ticker, stripped)


def get_cached_sg(ticker: str):
    """Retourne le strategic_group caché si frais, sinon None."""
    return _get_cached("sg", ticker, SG_TTL_DAYS)


def set_cached_sg(ticker: str, strategic_group: list):
    """Persiste un strategic_group (juste les tickers + rationale, prix
    rafraîchis ailleurs)."""
    stripped = [
        {k: v for k, v in item.items() if k != "change_pct"}
        for item in strategic_group
    ]
    _set_cached("sg", ticker, stripped)
