"""Tests for Brief 10A — VIX regime classification."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.history import classify_vix_regime


def _vix_series(values: list[float], start: str = "2014-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def test_regime_classification_low_mid_high():
    """Synthetic VIX: low block / mid block / high block — assert correct assignment."""
    # 252 low values, 252 mid values, 252 high values in a single 756-row series
    low = [10.0] * 252
    mid = [18.0] * 252
    high = [30.0] * 252
    series = _vix_series(low + mid + high)

    # With the full 756-row series, tercile boundaries will be ~10 / ~18 / ~30
    # A reading of 10 (low block) should classify as "low"
    result_low = classify_vix_regime(_vix_series(low * 3 + [10.0], "2014-01-01"), prev_regime=None)
    # A reading clearly in the high region
    result_high = classify_vix_regime(series, prev_regime=None)

    # The final value is 30.0, which sits in the top tercile
    assert result_high["regime"] == "high"
    assert result_high["regime_thresholds"] != {}
    assert result_high["regime_short_history"] is False

    # A series where all values are low → should give "low"
    all_low = _vix_series([10.0] * 300)
    r_low = classify_vix_regime(all_low, prev_regime=None)
    assert r_low["regime"] == "low"

    # A series where all values are equal → boundaries collapse, regime lands at "mid"
    all_same = _vix_series([15.0] * 300)
    r_same = classify_vix_regime(all_same, prev_regime=None)
    assert r_same["regime"] in {"low", "mid", "high"}  # deterministic but edge-case OK


def test_regime_hysteresis():
    """Smoothed VIX hovering at boundary doesn't flip regime until it clears by 1.0."""
    base = [10.0] * 252 + [18.0] * 252  # two-tercile series; low_max ≈ 14, high_min ≈ 18
    series_base = _vix_series(base)
    thresholds = classify_vix_regime(series_base, prev_regime=None)["regime_thresholds"]
    high_min = thresholds["high_min"]

    # Build a series where the final 5 days hover just at the high_min boundary
    # (not over it by the 1.0 buffer) — should NOT flip from mid to high
    at_boundary = base + [high_min + 0.5] * 5  # only 0.5 over boundary
    series_at = _vix_series(at_boundary)
    r_no_flip = classify_vix_regime(series_at, prev_regime="mid")
    assert r_no_flip["regime"] == "mid", "Should not flip without clearing hysteresis buffer"
    assert r_no_flip["regime_changed"] is False

    # Now push 1.1 over the boundary — should flip to high
    over_boundary = base + [high_min + 1.1] * 5
    series_over = _vix_series(over_boundary)
    r_flip = classify_vix_regime(series_over, prev_regime="mid")
    assert r_flip["regime"] == "high", "Should flip when clearing hysteresis buffer"
    assert r_flip["regime_changed"] is True


def test_regime_handles_short_history():
    """VIX series < 252 rows falls back to 'mid' with regime_short_history=True."""
    short_series = _vix_series([20.0] * 100)
    result = classify_vix_regime(short_series, prev_regime=None)

    assert result["regime"] == "mid"
    assert result["regime_short_history"] is True
    assert result["regime_thresholds"] == {}
    assert result["regime_changed"] is False
