"""Tests for Brief 21A — backtest indicator coverage gap fix."""
from __future__ import annotations

import pandas as pd
import pytest

from src.backtest import _indicator_pit, _AVAIL, _MANUAL, _IND_TO_SERIES


def _series(values: list[float], start: str = "2010-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def _make_derived(key: str, values: list[float], start: str = "2010-01-01") -> dict:
    return {key: _series(values, start)}


def _dummy_icfg(invert: bool = False) -> dict:
    return {"invert": invert}


# ── vix_term_structure ────────────────────────────────────────────────────────

def test_vix_term_structure_returns_value_after_avail():
    n = 500
    derived = _make_derived("vix_term_structure", [1.1] * n, "2008-06-01")
    date = pd.Timestamp("2012-01-03")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("vix_term_structure", _dummy_icfg(), derived, date, window_start)
    assert raw is not None
    assert isinstance(pct, float)


def test_vix_term_structure_unavailable_before_avail():
    n = 500
    derived = _make_derived("vix_term_structure", [1.1] * n, "1998-01-01")
    date = pd.Timestamp("2007-12-31")  # before 2008-04-01 _AVAIL
    window_start = date - pd.DateOffset(years=10)
    result = _indicator_pit("vix_term_structure", _dummy_icfg(), derived, date, window_start)
    assert result == (None, None, None)


# ── move_index ────────────────────────────────────────────────────────────────

def test_move_index_returns_value():
    n = 500
    derived = _make_derived("move_index", [100.0] * n, "2005-01-01")
    date = pd.Timestamp("2015-06-01")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("move_index", _dummy_icfg(), derived, date, window_start)
    assert raw is not None
    assert 0.0 <= pct <= 100.0


# ── cnn_fear_greed ────────────────────────────────────────────────────────────

def test_cnn_fear_greed_neutral_in_backtest():
    """cnn_fear_greed is in _MANUAL; always returns neutral (0.0, 50.0, 0.0)."""
    assert "cnn_fear_greed" in _MANUAL
    derived = {}
    date = pd.Timestamp("2020-01-02")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("cnn_fear_greed", _dummy_icfg(), derived, date, window_start)
    assert raw == 0.0
    assert pct == 50.0
    assert z == 0.0


# ── treasury_auction_stress ───────────────────────────────────────────────────

def test_treasury_auction_stress_returns_value_after_avail():
    n = 200
    derived = _make_derived("treasury_auction_stress", [0.5] * n, "2009-01-01")
    date = pd.Timestamp("2015-01-02")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("treasury_auction_stress", _dummy_icfg(), derived, date, window_start)
    assert raw is not None


def test_treasury_auction_stress_unavailable_before_avail():
    n = 200
    derived = _make_derived("treasury_auction_stress", [0.5] * n, "2000-01-01")
    date = pd.Timestamp("2007-12-31")  # before 2008-01-01 _AVAIL
    window_start = date - pd.DateOffset(years=10)
    result = _indicator_pit("treasury_auction_stress", _dummy_icfg(), derived, date, window_start)
    assert result == (None, None, None)


# ── sector_breadth ────────────────────────────────────────────────────────────

def test_sector_breadth_returns_value():
    n = 3000  # ~12 years of business days
    derived = _make_derived("sector_breadth", [45.0] * n, "2005-01-01")
    date = pd.Timestamp("2015-06-01")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("sector_breadth", _dummy_icfg(), derived, date, window_start)
    assert raw is not None
    assert 0.0 <= pct <= 100.0


# ── spx_200dma_distance ───────────────────────────────────────────────────────

def test_spx_200dma_distance_returns_value():
    n = 3000  # ~12 years of business days
    derived = _make_derived("spx_200dma_distance", [5.0] * n, "2005-01-01")
    date = pd.Timestamp("2015-06-01")
    window_start = date - pd.DateOffset(years=10)
    raw, pct, z = _indicator_pit("spx_200dma_distance", _dummy_icfg(), derived, date, window_start)
    assert raw is not None


# ── coverage sanity check ─────────────────────────────────────────────────────

def test_all_six_missing_indicators_now_mapped():
    """All six indicators flagged in Brief 21A are now in _IND_TO_SERIES or _MANUAL."""
    expected = {
        "vix_term_structure", "move_index", "cnn_fear_greed",
        "treasury_auction_stress", "sector_breadth", "spx_200dma_distance",
    }
    covered = set(_IND_TO_SERIES.keys()) | _MANUAL
    assert expected <= covered, f"Missing from coverage: {expected - covered}"


def test_oil_vol_removed_from_backtest():
    """oil_vol is no longer in production config; must not appear in _IND_TO_SERIES."""
    assert "oil_vol" not in _IND_TO_SERIES
