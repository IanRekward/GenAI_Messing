"""Tests for src/indicators.py statistical primitives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.indicators import (
    compute_percentile,
    compute_zscore,
    percentile_to_score,
    realized_vol_series,
    yoy_series,
)


def test_percentile_max_value_in_long_series():
    """Max element in a 10-element series returns 90.0 (strict less-than design).
    With real 10yr daily data (2520 obs) this is 99.96% — negligible in practice.
    """
    s = pd.Series(range(1, 11), dtype=float)  # [1..10], current=10
    result = compute_percentile(s)
    assert result == 90.0, f"Expected 90.0 but got {result}"


def test_percentile_middle_value():
    """Current value = 5 in [1..10] → 40th percentile (4 values strictly below)."""
    s = pd.Series(range(1, 11), dtype=float)
    s.iloc[-1] = 5.0  # current=5; values < 5 are {1,2,3,4} → 4/10 = 40.0
    result = compute_percentile(s)
    assert result == 40.0, f"Expected 40.0 but got {result}"


def test_percentile_short_series_returns_50(short_series):
    """Series with <10 elements returns neutral 50.0."""
    result = compute_percentile(short_series)
    assert result == 50.0


def test_zscore_constant_series_returns_zero(constant_series):
    """Constant series has zero std — must return 0.0 not raise ZeroDivisionError."""
    result = compute_zscore(constant_series)
    assert result == 0.0


def test_zscore_short_series_returns_zero(short_series):
    """Series with <10 elements returns 0.0."""
    result = compute_zscore(short_series)
    assert result == 0.0


def test_realized_vol_zero_return_series():
    """Flat price series → near-zero realized vol."""
    prices = pd.Series([100.0] * 100)
    vol = realized_vol_series(prices)
    assert (vol.abs() < 1e-6).all(), "Zero-return series should produce ~0% vol"


def test_realized_vol_series_length(synthetic_price_series):
    """Output length = input length - window (21) due to rolling."""
    vol = realized_vol_series(synthetic_price_series, window=21)
    assert len(vol) == len(synthetic_price_series) - 21


def test_yoy_series_known_growth(monthly_series):
    """1%/month growth → ~12.68% YoY at month 13."""
    yoy = yoy_series(monthly_series)
    # After 12 periods of 1%/mo: (1.01^12 - 1) * 100 ≈ 12.68
    assert abs(yoy.iloc[-1] - 12.68) < 0.1, f"Expected ~12.68 but got {yoy.iloc[-1]}"


def test_percentile_to_score_normal():
    assert percentile_to_score(70.0, invert=False) == 70.0


def test_percentile_to_score_inverted():
    """Inverted: 80th percentile → score 20 (low value = more stress)."""
    assert percentile_to_score(80.0, invert=True) == 20.0
