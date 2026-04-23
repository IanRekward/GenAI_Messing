"""Tests for cross_bucket_correlation and correlation_regime (Brief 5)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.history import cross_bucket_correlation, correlation_regime


def _make_history_with_buckets(bucket_data: dict[str, list[float]], start: str = "2026-01-01") -> pd.DataFrame:
    """Build a history DataFrame with composite + per-bucket columns."""
    n = len(next(iter(bucket_data.values())))
    dates = pd.date_range(start, periods=n, freq="D")
    df = pd.DataFrame({"timestamp": dates, "composite": [50.0] * n})
    for bkey, vals in bucket_data.items():
        df[f"bucket_{bkey}"] = vals
    return df


def test_insufficient_data_returns_none():
    df = _make_history_with_buckets({"a": [50.0] * 3, "b": [50.0] * 3})
    assert cross_bucket_correlation(df) is None


def test_empty_history_returns_none():
    assert cross_bucket_correlation(pd.DataFrame()) is None


def test_fully_synchronous_returns_one():
    """All buckets identical → mean absolute correlation = 1.0."""
    vals = list(range(1, 51))
    df = _make_history_with_buckets({"a": vals, "b": vals, "c": vals})
    result = cross_bucket_correlation(df)
    assert result is not None
    assert result == pytest.approx(1.0, abs=0.01)


def test_independent_buckets_near_zero():
    """Independent random walks → mean absolute correlation close to 0."""
    rng = np.random.default_rng(42)
    n = 60
    data = {chr(97 + i): list(rng.normal(0, 1, n)) for i in range(5)}
    df = _make_history_with_buckets(data)
    result = cross_bucket_correlation(df)
    assert result is not None
    assert result < 0.50  # loose bound — random, but typically << 0.5


def test_regime_decorrelated():
    assert correlation_regime(0.15) == "decorrelated"


def test_regime_normal():
    assert correlation_regime(0.45) == "normal"


def test_regime_crisis_synchronous():
    assert correlation_regime(0.75) == "crisis_synchronous"


def test_regime_none_is_insufficient():
    assert correlation_regime(None) == "insufficient"


def test_regime_boundaries():
    assert correlation_regime(0.30) == "normal"   # exactly at boundary
    assert correlation_regime(0.60) == "crisis_synchronous"


def test_single_bucket_column_returns_none():
    df = _make_history_with_buckets({"a": list(range(1, 41))})
    assert cross_bucket_correlation(df) is None


def test_constant_column_dropped_still_works():
    """A near-constant bucket (std < 0.5) should be dropped without crashing."""
    n = 40
    vals = list(range(1, n + 1))
    df = _make_history_with_buckets({
        "moving": vals,
        "also_moving": [v * 0.9 for v in vals],
        "constant": [50.0] * n,  # std=0, should be dropped
    })
    result = cross_bucket_correlation(df)
    # Two moving columns are perfectly correlated → result near 1.0
    assert result is not None
    assert result > 0.90
