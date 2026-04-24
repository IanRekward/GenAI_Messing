"""Tests for classify_shock_type() in src/history.py."""
from __future__ import annotations

import pandas as pd
import pytest

from src.history import classify_shock_type


def _make_history(scores: list[float], bucket_scores: list[float] | None = None,
                  start: str = "2026-01-01") -> pd.DataFrame:
    n = len(scores)
    dates = pd.date_range(start, periods=n, freq="D")
    data = {
        "timestamp": dates,
        "composite": scores,
        "composite_band": ["green"] * n,
        "bucket_equity_volatility": bucket_scores if bucket_scores else [50.0] * n,
        "bucket_credit_spreads": [50.0] * n,
        "bucket_rates_curve": [50.0] * n,
    }
    return pd.DataFrame(data)


def _scoring(composite: float) -> dict:
    return {"composite": composite, "buckets": {}}


# ── Insufficient data ─────────────────────────────────────────────────────────

def test_insufficient_history_returns_insufficient():
    h = _make_history([50.0])
    assert classify_shock_type(h, _scoring(50.0)) == "insufficient"


def test_empty_history_returns_insufficient():
    assert classify_shock_type(pd.DataFrame(), _scoring(50.0)) == "insufficient"


# ── Fast shock ────────────────────────────────────────────────────────────────

def test_fast_shock_by_velocity():
    # Large rise in composite over last 7d
    scores = [30.0] * 10 + [38.5]  # 8.5 pts in 7 days
    h = _make_history(scores)
    assert classify_shock_type(h, _scoring(38.5)) == "fast_shock"


def test_fast_shock_by_breadth():
    # Moderate composite velocity but 3 buckets accelerating
    n = 12
    base = [45.0] * (n - 7) + [49.5] * 7   # +4.5 pts in 7d
    bkt_accel = [45.0] * (n - 7) + [50.0] * 7  # +5.0 pts per bucket in 7d
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "timestamp": dates,
        "composite": base,
        "composite_band": ["yellow"] * n,
        "bucket_equity_volatility": bkt_accel,
        "bucket_credit_spreads":    bkt_accel,
        "bucket_rates_curve":       bkt_accel,
        "bucket_financial_conditions": [50.0] * n,
    })
    assert classify_shock_type(df, _scoring(49.5)) == "fast_shock"


# ── Slow burn ─────────────────────────────────────────────────────────────────

def test_slow_burn_elevated_stable():
    # Composite elevated and flat
    scores = [55.0] * 30
    h = _make_history(scores)
    assert classify_shock_type(h, _scoring(55.0)) == "slow_burn"


def test_slow_burn_elevated_slowly_rising():
    # Composite elevated, rising slowly (< 8 pts/7d)
    scores = list(range(45, 45 + 30))  # rising 1 pt/day
    h = _make_history(scores)
    result = classify_shock_type(h, _scoring(74.0))
    # 7d rise = 7 pts < 8 threshold → slow_burn (not fast_shock) since velocity < 8
    assert result == "slow_burn"


def test_not_slow_burn_below_threshold():
    # Low composite should not be slow burn
    scores = [25.0] * 30
    h = _make_history(scores)
    assert classify_shock_type(h, _scoring(25.0)) != "slow_burn"


# ── Recovery ──────────────────────────────────────────────────────────────────

def test_recovery_falling_from_elevated():
    # Composite was elevated, now falling fast (≥5 pts/7d)
    scores = [60.0] * 15 + [53.0]  # -7 pts in 7d
    h = _make_history(scores)
    assert classify_shock_type(h, _scoring(53.0)) == "recovery"


def test_no_recovery_if_composite_too_low():
    # Composite already calm; falling further is not "recovery"
    scores = [20.0] * 10 + [14.0]  # -6 pts but from a low base
    h = _make_history(scores)
    result = classify_shock_type(h, _scoring(14.0))
    assert result != "recovery"


# ── Calm ─────────────────────────────────────────────────────────────────────

def test_calm_flat_low_composite():
    scores = [20.0] * 20
    h = _make_history(scores)
    assert classify_shock_type(h, _scoring(20.0)) == "calm"
