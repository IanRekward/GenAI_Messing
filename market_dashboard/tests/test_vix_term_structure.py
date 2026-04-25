"""Tests for Brief 16 — VIX term-structure indicator."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from src.scoring import _handler_vix_term_structure, COMPUTED_HANDLERS


def _make_price_df(values: list[float], ticker: str = "^VIX") -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.DataFrame({"Close": values}, index=idx)


def test_vix_term_structure_registered():
    assert "vix_term_structure" in COMPUTED_HANDLERS


def test_vix_term_structure_backwardation():
    """VIX > VIX3M → ratio > 1.0 (backwardation / stress)."""
    vix_df = _make_price_df([25.0] * 50)
    vix3m_df = _make_price_df([20.0] * 50)

    with patch("yfinance.download", side_effect=[vix_df, vix3m_df]):
        raw, series = _handler_vix_term_structure("vix_term_structure", {}, {}, {}, 10)

    assert raw == pytest.approx(25.0 / 20.0)
    assert raw > 1.0


def test_vix_term_structure_contango():
    """VIX < VIX3M → ratio < 1.0 (normal contango / calm)."""
    vix_df = _make_price_df([15.0] * 50)
    vix3m_df = _make_price_df([18.0] * 50)

    with patch("yfinance.download", side_effect=[vix_df, vix3m_df]):
        raw, series = _handler_vix_term_structure("vix_term_structure", {}, {}, {}, 10)

    assert raw == pytest.approx(15.0 / 18.0)
    assert raw < 1.0


def test_vix_term_structure_returns_series():
    """Handler must return a Series (not None) for history charting."""
    vix_df = _make_price_df([20.0] * 100)
    vix3m_df = _make_price_df([21.0] * 100)

    with patch("yfinance.download", side_effect=[vix_df, vix3m_df]):
        raw, series = _handler_vix_term_structure("vix_term_structure", {}, {}, {}, 10)

    assert isinstance(series, pd.Series)
    assert len(series) == 100
    assert series.isna().sum() == 0
