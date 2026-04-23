"""Tests for data-staleness detection (Brief 6)."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from src.fetch import check_series_staleness


_CADENCE_CFG = {
    "thresholds": {"daily": 3, "weekly": 10, "monthly": 40},
    "indicators": {
        "vix": "daily",
        "nfci": "weekly",
        "cpi_yoy": "monthly",
    },
}


def _series_ending(days_ago: int, length: int = 30) -> pd.Series:
    """Build a series whose last observation is `days_ago` calendar days ago."""
    end = pd.Timestamp.today().normalize() - pd.Timedelta(days=days_ago)
    idx = pd.date_range(end=end, periods=length, freq="D")
    return pd.Series(range(length), index=idx, dtype=float)


def test_fresh_daily_no_warning():
    s = _series_ending(days_ago=1)
    assert check_series_staleness("vix", s, _CADENCE_CFG) is None


def test_stale_daily_returns_message():
    s = _series_ending(days_ago=5)
    msg = check_series_staleness("vix", s, _CADENCE_CFG)
    assert msg is not None
    assert "STALE" in msg
    assert "vix" in msg
    assert "5d" in msg


def test_fresh_weekly_no_warning():
    s = _series_ending(days_ago=7)
    assert check_series_staleness("nfci", s, _CADENCE_CFG) is None


def test_stale_weekly_returns_message():
    s = _series_ending(days_ago=12)
    msg = check_series_staleness("nfci", s, _CADENCE_CFG)
    assert msg is not None
    assert "nfci" in msg


def test_fresh_monthly_no_warning():
    s = _series_ending(days_ago=30)
    assert check_series_staleness("cpi_yoy", s, _CADENCE_CFG) is None


def test_stale_monthly_returns_message():
    s = _series_ending(days_ago=45)
    msg = check_series_staleness("cpi_yoy", s, _CADENCE_CFG)
    assert msg is not None
    assert "cpi_yoy" in msg


def test_key_not_in_config_returns_none():
    s = _series_ending(days_ago=100)
    assert check_series_staleness("unknown_indicator", s, _CADENCE_CFG) is None


def test_none_series_returns_none():
    assert check_series_staleness("vix", None, _CADENCE_CFG) is None


def test_empty_series_returns_none():
    assert check_series_staleness("vix", pd.Series([], dtype=float), _CADENCE_CFG) is None


def test_empty_config_returns_none():
    s = _series_ending(days_ago=100)
    assert check_series_staleness("vix", s, {}) is None
