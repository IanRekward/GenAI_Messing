"""Tests for src/analogs.py — historical analog finder."""
from __future__ import annotations

import math
import pytest

from src.analogs import find_analog, MIN_COMPOSITE, _BUCKET_KEYS, _EPISODES


def _make_scoring(bucket_scores: dict, composite: float = 60.0) -> dict:
    """Build a minimal scoring dict for find_analog."""
    buckets = {
        k: {"score": bucket_scores.get(k, 0.0), "band": "green"}
        for k in _BUCKET_KEYS
    }
    return {"composite": composite, "buckets": buckets}


# ── Basic contract ────────────────────────────────────────────────────────────

def test_returns_list():
    s = _make_scoring({"equity_volatility": 80, "credit_spreads": 70})
    result = find_analog(s, top_n=2)
    assert isinstance(result, list)


def test_top_n_respected():
    s = _make_scoring({"equity_volatility": 80})
    assert len(find_analog(s, top_n=1)) == 1
    assert len(find_analog(s, top_n=3)) == 3


def test_result_keys():
    s = _make_scoring({"equity_volatility": 80})
    result = find_analog(s, top_n=1)
    r = result[0]
    assert "name" in r
    assert "date_range" in r
    assert "tags" in r
    assert "similarity" in r


def test_similarity_between_0_and_1():
    s = _make_scoring({"equity_volatility": 80, "credit_spreads": 70})
    for r in find_analog(s, top_n=len(_EPISODES)):
        assert 0.0 <= r["similarity"] <= 1.0 + 1e-9, f"Out of range: {r['similarity']}"


def test_sorted_descending():
    s = _make_scoring({"equity_volatility": 80, "credit_spreads": 70})
    result = find_analog(s, top_n=len(_EPISODES))
    sims = [r["similarity"] for r in result]
    assert sims == sorted(sims, reverse=True)


# ── Suppression at low composite ─────────────────────────────────────────────

def test_empty_when_composite_low():
    s = _make_scoring({"equity_volatility": 80}, composite=MIN_COMPOSITE - 1)
    assert find_analog(s) == []


def test_non_empty_at_threshold():
    s = _make_scoring({"equity_volatility": 50}, composite=MIN_COMPOSITE)
    assert len(find_analog(s)) > 0


# ── Pattern matching ──────────────────────────────────────────────────────────

def test_gfc_pattern_matches_gfc():
    """A GFC-like pattern (credit + funding + equity) should rank GFC first."""
    s = _make_scoring({
        "equity_volatility": 95,
        "credit_spreads": 95,
        "funding_liquidity": 90,
        "global_spillover": 90,
        "breadth_flow": 90,
    }, composite=80)
    result = find_analog(s, top_n=2)
    assert result[0]["name"] == "2008 GFC"


def test_inflation_pattern_matches_2022():
    """An inflation + rates pattern should rank 2022 first."""
    s = _make_scoring({
        "inflation": 95,
        "rates_curve": 90,
        "commodities": 85,
        "financial_conditions": 75,
    }, composite=70)
    result = find_analog(s, top_n=2)
    assert result[0]["name"] == "2022 Rate Shock"


def test_funding_spike_matches_repo_crisis():
    """Isolated funding spike should rank 2019 Repo Crisis at or near top."""
    s = _make_scoring({
        "funding_liquidity": 90,
    }, composite=50)
    result = find_analog(s, top_n=len(_EPISODES))
    names = [r["name"] for r in result]
    repo_rank = names.index("2019 Repo Crisis")
    assert repo_rank <= 2, f"Repo crisis ranked {repo_rank}, expected ≤ 2"


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_all_zero_buckets_returns_results():
    s = _make_scoring({}, composite=50)
    result = find_analog(s, top_n=2)
    # All zeros → cosine similarity 0 for everything; should still return items
    assert len(result) == 2
    for r in result:
        assert r["similarity"] == 0.0


def test_perfect_match_similarity_near_1():
    """Copying GFC scores exactly should give similarity close to 1.0."""
    gfc = next(e for e in _EPISODES if e["name"] == "2008 GFC")
    bucket_scores = dict(zip(_BUCKET_KEYS, gfc["scores"]))
    s = _make_scoring(bucket_scores, composite=80)
    result = find_analog(s, top_n=1)
    assert result[0]["name"] == "2008 GFC"
    assert result[0]["similarity"] > 0.99
