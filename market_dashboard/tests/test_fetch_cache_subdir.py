"""Tests for cache_subdir parameter on fetch functions (Brief 21D)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.fetch import fetch_fred_series, fetch_yfinance_series


class _FakeFredResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "observations": [
                {"date": "2020-01-01", "value": "1.0"},
                {"date": "2020-01-02", "value": "2.0"},
            ]
        }


def _seed_yf_cache(tmp_path: Path, cache_subdir: str, safe: str, n: int = 20) -> Path:
    d = tmp_path / "cache" / cache_subdir if cache_subdir else tmp_path / "cache"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    path = d / f"yf_{safe}.json"
    path.write_text(json.dumps({
        "dates": [x.strftime("%Y-%m-%d") for x in idx],
        "values": list(range(1, n + 1)),
    }))
    return path


def test_fred_cache_subdir_writes_to_subdirectory(monkeypatch, tmp_path):
    """cache_subdir='backtest' writes fred_ file inside data/cache/backtest/, not data/cache/."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeFredResponse())
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"FRED_API_KEY": "testkey", "CACHE_HOURS": "0"}
    fetch_fred_series("TESTSERIES", env, cache_subdir="backtest")

    bt_file = tmp_path / "cache" / "backtest" / "fred_TESTSERIES.json"
    live_file = tmp_path / "cache" / "fred_TESTSERIES.json"
    assert bt_file.exists(), "backtest cache file should exist"
    assert not live_file.exists(), "live cache file must not be created"


def test_fred_cache_subdir_does_not_collide_with_live(monkeypatch, tmp_path):
    """Fetching with cache_subdir='backtest' and years=26 doesn't overwrite a live cache."""
    call_count = {"n": 0}

    def _counted(*a, **kw):
        call_count["n"] += 1
        return _FakeFredResponse()

    monkeypatch.setattr("requests.get", _counted)
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"FRED_API_KEY": "testkey", "CACHE_HOURS": "0"}
    fetch_fred_series("T10Y2Y", env, years=10)
    fetch_fred_series("T10Y2Y", env, years=26, cache_subdir="backtest")

    live_file = tmp_path / "cache" / "fred_T10Y2Y.json"
    bt_file = tmp_path / "cache" / "backtest" / "fred_T10Y2Y.json"
    assert live_file.exists()
    assert bt_file.exists()
    assert call_count["n"] == 2


def test_yf_cache_subdir_writes_to_subdirectory(monkeypatch, tmp_path):
    """cache_subdir='backtest' writes yf_ file inside backtest/ subdirectory."""
    import yfinance as yf

    fake_df = pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )

    monkeypatch.setattr("yfinance.download", lambda *a, **kw: fake_df)
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"CACHE_HOURS": "0"}
    fetch_yfinance_series("^VIX", env, cache_subdir="backtest")

    bt_file = tmp_path / "cache" / "backtest" / "yf_XVIX.json"
    live_file = tmp_path / "cache" / "yf_XVIX.json"
    assert bt_file.exists(), "backtest cache file should exist"
    assert not live_file.exists(), "live cache file must not be created"


def test_cache_hours_override_respected(monkeypatch, tmp_path):
    """cache_hours parameter takes precedence over CACHE_HOURS env value."""
    call_count = {"n": 0}

    def _counted(*a, **kw):
        call_count["n"] += 1
        return _FakeFredResponse()

    monkeypatch.setattr("requests.get", _counted)
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"FRED_API_KEY": "testkey", "CACHE_HOURS": "0"}
    fetch_fred_series("UNRATE", env, cache_subdir="backtest")
    # Second call with cache_hours=168 should hit cache, not re-fetch
    fetch_fred_series("UNRATE", env, cache_subdir="backtest", cache_hours=168.0)
    assert call_count["n"] == 1, "second call should have been served from cache"
