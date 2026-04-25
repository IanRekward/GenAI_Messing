"""Tests for Brief 10B — per_regime_bucket_ic in src/evaluation.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluation import per_regime_bucket_ic


def _make_backtest_df(n: int = 300, regimes: list[str] | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    if regimes is None:
        r_each = n // 3
        remainder = n - r_each * 3
        regimes = ["low"] * r_each + ["mid"] * r_each + ["high"] * (r_each + remainder)
    data = {
        "composite": rng.uniform(20, 60, n),
        "bucket_equity_volatility": rng.uniform(10, 80, n),
        "bucket_credit_spreads": rng.uniform(10, 80, n),
        "regime": regimes,
    }
    return pd.DataFrame(data, index=idx)


def _make_spx(n: int = 340) -> pd.Series:
    rng = np.random.default_rng(7)
    prices = np.cumsum(rng.standard_normal(n)) + 4000
    return pd.Series(prices, index=pd.date_range("2018-01-01", periods=n, freq="B"))


def test_per_regime_ic_returns_correct_shape():
    """Result must be (n_buckets, 3) with columns [low, mid, high]."""
    df = _make_backtest_df()
    spx = _make_spx()
    result = per_regime_bucket_ic(df, spx, horizon_days=21)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["low", "mid", "high"]
    assert "equity_volatility" in result.index
    assert "credit_spreads" in result.index
    assert result.shape == (2, 3)


def test_per_regime_ic_handles_empty_regime():
    """When one regime has no rows, its column must be all NaN, no crash."""
    n = 200
    regimes = ["low"] * 100 + ["mid"] * 100  # no "high" rows
    df = _make_backtest_df(n=n, regimes=regimes)
    spx = _make_spx(n=240)
    result = per_regime_bucket_ic(df, spx, horizon_days=21)

    assert result.shape[1] == 3
    assert all(np.isnan(result["high"])), "high regime column should be all NaN"
    # low and mid should have some valid IC values (may be NaN if insufficient overlap too)
    assert "equity_volatility" in result.index
