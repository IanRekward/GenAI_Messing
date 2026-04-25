"""Tests for rolling_composite_ic in src/evaluation.py (Brief 15)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluation import rolling_composite_ic


def _make_spx(n: int = 400, start: str = "2024-01-01") -> pd.Series:
    rng = np.random.default_rng(42)
    prices = np.cumsum(rng.standard_normal(n)) + 4500
    return pd.Series(prices, index=pd.date_range(start, periods=n, freq="B"))


def _make_history(composite: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(composite), freq="B")
    return pd.DataFrame({
        "timestamp": dates,
        "composite": composite,
    })


def test_rolling_composite_ic_perfect_predictor():
    """When composite perfectly tracks forward drawdown the IC should be ≈ 1.0."""
    n = 400
    spx = _make_spx(n=n)

    # Build the "true" forward drawdown first, then set composite = drawdown * 100
    from src.evaluation import build_forward_drawdown
    target = build_forward_drawdown(spx, horizon_days=21)

    # Only use rows where target is not NaN (i.e., exclude the last 21 days)
    valid_idx = target.dropna().index
    composite_vals = (target.loc[valid_idx] * 100).tolist()

    history = pd.DataFrame({
        "timestamp": valid_idx,
        "composite": composite_vals,
    })

    result = rolling_composite_ic(history, spx, window_days=252, horizon_days=21)

    assert result["ic"] is not None, "IC should not be None with sufficient data"
    assert result["ic"] > 0.8, f"Expected IC ≈ 1.0 for perfect predictor, got {result['ic']:.3f}"
    assert result["n_obs"] >= 30


def test_rolling_composite_ic_insufficient_data():
    """With only 10 history rows the function should return ic=None."""
    spx = _make_spx(n=400)
    history = _make_history([50.0] * 10)

    result = rolling_composite_ic(history, spx, window_days=252, horizon_days=21)

    assert result["ic"] is None, "Expected ic=None for insufficient history"
    assert result["n_obs"] < 30
    assert result["horizon_days"] == 21
    assert result["window_days"] == 252
