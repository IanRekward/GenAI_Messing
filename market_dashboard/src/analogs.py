"""
Historical analog finder: compares current bucket-score pattern to a set of
known stress episodes using cosine similarity on the bucket score vector.

Only meaningful when the composite is elevated (>= MIN_COMPOSITE); returns []
when the market is calm so the dashboard stays uncluttered.
"""
from __future__ import annotations

import math

# ── Ordered bucket keys (must match weights.yaml) ────────────────────────────
_BUCKET_KEYS = [
    "equity_volatility", "credit_spreads", "rates_curve",
    "financial_conditions", "inflation", "funding_liquidity",
    "commodities", "economic_momentum", "sentiment",
    "global_spillover", "breadth_flow",
]

# ── Historical episode signatures ────────────────────────────────────────────
# Approximate bucket scores (0-100) at peak-stress for each major episode.
# eq_vol  credit  rates  fin_cond  infl  funding  commod  econ_mom  sentiment  global  breadth
_EPISODES: list[dict] = [
    {
        "name": "2008 GFC",
        "date_range": "Sep–Nov 2008",
        "tags": ["credit", "funding", "systemic"],
        "scores": [95, 95, 35, 92, 20, 95, 60, 75, 90, 90, 95],
    },
    {
        "name": "2020 COVID Crash",
        "date_range": "Feb–Mar 2020",
        "tags": ["equity", "fast shock", "global"],
        "scores": [95, 85, 15, 80, 10, 80, 80, 60, 95, 85, 95],
    },
    {
        "name": "2022 Rate Shock",
        "date_range": "Jan–Jun 2022",
        "tags": ["inflation", "rates", "slow burn"],
        "scores": [55, 55, 90, 75, 95, 30, 90, 25, 70, 65, 75],
    },
    {
        "name": "2011 Euro Crisis",
        "date_range": "Jul–Sep 2011",
        "tags": ["credit", "global", "contagion"],
        "scores": [70, 75, 50, 60, 25, 50, 50, 45, 75, 90, 78],
    },
    {
        "name": "Q4 2018 Selloff",
        "date_range": "Oct–Dec 2018",
        "tags": ["equity", "rates", "liquidity"],
        "scores": [65, 50, 65, 55, 30, 25, 55, 30, 65, 55, 70],
    },
    {
        "name": "2015–16 EM/Oil Selloff",
        "date_range": "Aug 2015 – Feb 2016",
        "tags": ["commodities", "EM", "global"],
        "scores": [50, 55, 35, 45, 15, 20, 75, 40, 60, 80, 60],
    },
    {
        "name": "2019 Repo Crisis",
        "date_range": "Sep 2019",
        "tags": ["funding", "liquidity"],
        "scores": [20, 30, 40, 40, 25, 85, 35, 30, 30, 35, 25],
    },
    {
        "name": "2023 SVB / Banking Stress",
        "date_range": "Mar 2023",
        "tags": ["credit", "rates", "funding"],
        "scores": [55, 65, 75, 60, 75, 68, 40, 35, 65, 55, 55],
    },
]

# Build pre-normalized vectors once at import time
def _norm(v: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in v))
    return [x / mag for x in v] if mag > 0 else v


_EPISODE_NORMS: list[list[float]] = [_norm(e["scores"]) for e in _EPISODES]

MIN_COMPOSITE = 35  # suppress analogs in calm markets


def find_analog(scoring: dict, top_n: int = 2) -> list[dict]:
    """
    Return the top_n most similar historical episodes to the current bucket state.
    Each result is:
      {"name": str, "date_range": str, "tags": list[str], "similarity": float}
    Returns [] when composite < MIN_COMPOSITE.
    """
    if scoring.get("composite", 0) < MIN_COMPOSITE:
        return []

    buckets = scoring.get("buckets", {})
    current = [float(buckets.get(k, {}).get("score", 0)) for k in _BUCKET_KEYS]
    c_norm = _norm(current)

    results = []
    for ep, ep_norm in zip(_EPISODES, _EPISODE_NORMS):
        sim = sum(a * b for a, b in zip(c_norm, ep_norm))
        results.append({
            "name": ep["name"],
            "date_range": ep["date_range"],
            "tags": ep["tags"],
            "similarity": round(sim, 3),
        })

    results.sort(key=lambda x: -x["similarity"])
    return results[:top_n]
