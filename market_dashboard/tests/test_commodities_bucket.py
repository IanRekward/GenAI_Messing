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


def test_crack_spread_321_arithmetic():
    """3-2-1 crack formula: (2*RBOB*42 + ULSD*42)/3 - WTI, hand-verifiable values."""
    wti_s  = _series([60.0, 70.0, 80.0])
    rbob_s = _series([2.0, 2.5, 3.0])
    ulsd_s = _series([2.0, 2.5, 3.0])

    def mock_fetch(ticker, env, years):
        return {"CL=F": wti_s, "RB=F": rbob_s, "HO=F": ulsd_s}[ticker]

    with patch("src.fetch.fetch_yfinance_series", side_effect=mock_fetch):
        raw, series = _handler_crack_spread_321("crack_spread_321", {}, {}, {}, 10)

    # Last row: (2*3.0*42 + 1*3.0*42)/3 - 80 = (252 + 126)/3 - 80 = 126 - 80 = 46.0
    assert raw == pytest.approx(46.0)
    assert float(series.iloc[-1]) == pytest.approx(46.0)
    assert "crack_spread_321" in COMPUTED_HANDLERS


def test_copper_gold_ratio_arithmetic():
    """Ratio = copper / gold; last row hand-verifiable."""
    copper_s = _series([4.0, 5.0])
    gold_s   = _series([2000.0, 2000.0])

    def mock_fetch(ticker, env, years):
        return {"HG=F": copper_s, "GC=F": gold_s}[ticker]

    with patch("src.fetch.fetch_yfinance_series", side_effect=mock_fetch):
        raw, series = _handler_copper_gold_ratio("copper_gold_ratio", {}, {}, {}, 10)

    assert raw == pytest.approx(5.0 / 2000.0)
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
