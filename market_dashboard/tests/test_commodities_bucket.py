"""Tests for Brief 19 — Commodities & Energy bucket diversification."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch

from src.scoring import (
    _handler_crack_spread_321,
    _handler_copper_gold_ratio,
    COMPUTED_HANDLERS,
    load_weights,
    load_thresholds,
)
from src.config import validate_config, _WEIGHT_TOLERANCE


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def test_crack_spread_321_deviation_arithmetic():
    """Raw = crack level minus trailing median (D2 transform). With a flat
    history and a final jump, the deviation equals the jump size."""
    n = 20
    wti_s  = _series([60.0] * n + [60.0])
    rbob_s = _series([2.0] * n + [3.0])
    ulsd_s = _series([2.0] * n + [3.0])

    def mock_fetch(ticker, env, years):
        return {"CL=F": wti_s, "RB=F": rbob_s, "HO=F": ulsd_s}[ticker]

    with patch("src.fetch.fetch_yfinance_series", side_effect=mock_fetch):
        raw, series = _handler_crack_spread_321("crack_spread_321", {}, {}, {}, 10)

    # crack level: flat at (2*2*42+2*42)/3-60 = 84-60 = 24, jumps to 126-60 = 66
    # → deviation from trailing median = 66 - 24 = 42
    assert raw == pytest.approx(42.0)
    assert "crack_spread_321" in COMPUTED_HANDLERS


def test_copper_gold_ratio_deviation_arithmetic():
    """Raw = (ratio minus trailing median) × 1000; a drop below a flat history
    shows as a negative deviation (stress, direction low)."""
    n = 20
    copper_s = _series([4.0] * n + [3.0])
    gold_s   = _series([2000.0] * (n + 1))

    def mock_fetch(ticker, env, years):
        return {"HG=F": copper_s, "GC=F": gold_s}[ticker]

    with patch("src.fetch.fetch_yfinance_series", side_effect=mock_fetch):
        raw, series = _handler_copper_gold_ratio("copper_gold_ratio", {}, {}, {}, 10)

    # ratio flat at 0.002, drops to 0.0015 → dev = -0.0005 → ×1000 = -0.5
    assert raw == pytest.approx(-0.5)
    assert "copper_gold_ratio" in COMPUTED_HANDLERS


def test_commodities_bucket_validates():
    """commodities bucket has the four expected indicators; weights sum to 1.0."""
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    validate_config(weights, thresholds, frozenset(COMPUTED_HANDLERS.keys()))

    bucket = weights["buckets"]["commodities"]["indicators"]
    assert set(bucket.keys()) == {"wti_crude", "crack_spread_321", "natgas", "copper_gold_ratio"}

    ind_sum = sum(float(v["weight"]) for v in bucket.values())
    assert abs(ind_sum - 1.0) <= _WEIGHT_TOLERANCE
