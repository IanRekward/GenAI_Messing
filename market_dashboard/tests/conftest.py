"""Shared pytest fixtures — no network access allowed in tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make src/ importable from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def known_series():
    """Simple [1,2,3,4,5] series with predictable percentile answers."""
    return pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])


@pytest.fixture
def short_series():
    """5-element series — triggers the <10 length guard."""
    return pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])


@pytest.fixture
def synthetic_price_series():
    """10yr of daily prices via geometric Brownian motion, fixed seed."""
    np.random.seed(42)
    n = 252 * 10
    returns = np.random.normal(0.0003, 0.01, n)
    prices = 100.0 * np.cumprod(1 + returns)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


@pytest.fixture
def constant_series():
    """Series of identical values — guards against zero-std division."""
    return pd.Series([5.0] * 20)


@pytest.fixture
def monthly_series():
    """Monthly series growing at 1%/month — for yoy_series test."""
    idx = pd.date_range("2014-01-01", periods=25, freq="MS")
    values = [100.0 * (1.01 ** i) for i in range(25)]
    return pd.Series(values, index=idx)


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """Fail loudly if any test accidentally touches the network.

    Tests marked @pytest.mark.live are exempt — they need real FRED/yfinance fetches.
    """
    if "live" in request.keywords:
        return

    def _no_requests(*args, **kwargs):
        raise RuntimeError("Network access not allowed in tests — use fixtures")

    monkeypatch.setattr("requests.get", _no_requests, raising=False)
    monkeypatch.setattr("requests.post", _no_requests, raising=False)

    try:
        import yfinance as yf
        monkeypatch.setattr(yf, "download", _no_requests)
    except ImportError:
        pass
