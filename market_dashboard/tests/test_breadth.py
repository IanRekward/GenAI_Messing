"""Tests for breadth & flow indicators: sector_breadth and spx_200dma_distance."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch

from src.scoring import _compute_sector_breadth, _compute_spx_200dma_distance


def _make_series(values: list[float], start: str = "2015-01-01") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=index, dtype=float)


# ── _compute_sector_breadth ───────────────────────────────────────────────────

def _sector_fetch(all_above: bool = True):
    """Return a fetch-side-effect that gives either all-above or all-below series."""
    n = 400
    if all_above:
        # All prices above 200d MA: make prices rising over time
        prices = [100 + i * 0.01 for i in range(n)]  # gently rising
    else:
        # All prices below 200d MA: make prices falling sharply at the end
        prices = [100 + i * 0.1 for i in range(n - 50)] + [50.0] * 50  # crash last 50

    s = _make_series(prices)

    def _fake_fetch(ticker, env, years):
        return s.copy()

    return _fake_fetch


def test_sector_breadth_all_above_gives_low_value():
    with patch("src.scoring.fetch.fetch_yfinance_series", side_effect=_sector_fetch(all_above=True)):
        raw, series = _compute_sector_breadth({"CACHE_HOURS": "0"}, 10)
    assert isinstance(raw, float)
    # All sectors rising → should be at/near 0% below MA
    assert raw < 30.0, f"Expected low breadth stress, got {raw}"


def test_sector_breadth_all_below_gives_high_value():
    with patch("src.scoring.fetch.fetch_yfinance_series", side_effect=_sector_fetch(all_above=False)):
        raw, series = _compute_sector_breadth({"CACHE_HOURS": "0"}, 10)
    assert raw > 50.0, f"Expected high breadth stress, got {raw}"


def test_sector_breadth_returns_series():
    with patch("src.scoring.fetch.fetch_yfinance_series", side_effect=_sector_fetch()):
        raw, series = _compute_sector_breadth({"CACHE_HOURS": "0"}, 10)
    assert isinstance(series, pd.Series)
    assert len(series) > 0
    assert (series >= 0).all() and (series <= 100).all()


def test_sector_breadth_raises_with_too_few_sectors():
    call_count = {"n": 0}

    def _failing_fetch(ticker, env, years):
        call_count["n"] += 1
        if call_count["n"] > 3:
            raise RuntimeError("network error")
        return _make_series([100 + i for i in range(400)])

    with patch("src.scoring.fetch.fetch_yfinance_series", side_effect=_failing_fetch):
        with pytest.raises(RuntimeError, match="sector_breadth"):
            _compute_sector_breadth({"CACHE_HOURS": "0"}, 10)


# ── _compute_spx_200dma_distance ──────────────────────────────────────────────

def test_spx_200dma_distance_above_gives_positive():
    # Price well above its historical average → positive distance
    n = 400
    prices = [100 + i * 0.05 for i in range(n)]  # steady rise
    s = _make_series(prices)
    with patch("src.scoring.fetch.fetch_yfinance_series", return_value=s):
        raw, series = _compute_spx_200dma_distance({"CACHE_HOURS": "0"}, 10)
    # Last price > 200d MA of steadily rising series → positive
    assert raw > 0, f"Expected positive distance above MA, got {raw}"


def test_spx_200dma_distance_below_gives_negative():
    # Price crashes at the end → below 200d MA
    n = 400
    prices = [100 + i * 0.1 for i in range(n - 50)] + [50.0] * 50
    s = _make_series(prices)
    with patch("src.scoring.fetch.fetch_yfinance_series", return_value=s):
        raw, series = _compute_spx_200dma_distance({"CACHE_HOURS": "0"}, 10)
    assert raw < 0, f"Expected negative distance below MA, got {raw}"


def test_spx_200dma_distance_returns_series():
    n = 400
    prices = [100 + i * 0.05 for i in range(n)]
    s = _make_series(prices)
    with patch("src.scoring.fetch.fetch_yfinance_series", return_value=s):
        raw, series = _compute_spx_200dma_distance({"CACHE_HOURS": "0"}, 10)
    assert isinstance(series, pd.Series)
    assert len(series) > 0
