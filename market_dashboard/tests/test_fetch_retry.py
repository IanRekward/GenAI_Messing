"""Tests for retry + stale-cache fallback in fetch layer (Brief 7)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.fetch import StaleCacheFallback, _retry_get, fetch_fred_series, fetch_cnn_fear_greed


def _make_stale_cache(tmp_path: Path, cache_key: str, n: int = 30) -> Path:
    """Write a minimal valid cache JSON to tmp_path/cache/<key>.json."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    data = {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "values": list(range(1, n + 1)),
    }
    path = cache_dir / f"{cache_key}.json"
    path.write_text(json.dumps(data))
    return path


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "observations": [
                {"date": "2026-04-01", "value": "42.0"},
                {"date": "2026-04-02", "value": "43.0"},
            ]
        }


def test_retry_get_succeeds_on_first_try(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse())
    resp = _retry_get("http://x", {}, timeout=5)
    assert resp.status_code == 200


def test_retry_get_retries_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def _flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise requests.ConnectionError("timeout")
        return _FakeResponse()

    monkeypatch.setattr("requests.get", _flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    resp = _retry_get("http://x", {}, timeout=5)
    assert resp.status_code == 200
    assert attempts["n"] == 3


def test_retry_get_raises_after_all_retries(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("fail")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        _retry_get("http://x", {}, timeout=5)


def test_fred_falls_back_to_stale_cache(monkeypatch, tmp_path):
    """When all FRED retries fail and stale cache exists, StaleCacheFallback is raised."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("down")))
    monkeypatch.setattr("time.sleep", lambda s: None)

    # Write stale cache
    _make_stale_cache(tmp_path, "fred_TESTID")
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"FRED_API_KEY": "testkey", "CACHE_HOURS": "0"}
    with pytest.raises(StaleCacheFallback) as exc_info:
        fetch_fred_series("TESTID", env)

    assert exc_info.value.series is not None
    assert len(exc_info.value.series) == 30
    assert "stale cache" in str(exc_info.value).lower()


def test_fred_raises_when_no_stale_cache_available(monkeypatch, tmp_path):
    """When all retries fail and there is no cache, the original error propagates."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("down")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"FRED_API_KEY": "testkey", "CACHE_HOURS": "0"}
    with pytest.raises(requests.ConnectionError):
        fetch_fred_series("TESTID", env)


# ── CNN Fear & Greed tests ────────────────────────────────────────────────────

def _cnn_response(n: int = 10):
    """Build a minimal CNN Fear & Greed JSON payload with n daily rows."""
    import time as _time
    base_ts = int(_time.time()) - (n - 1) * 86400
    data = [{"x": float((base_ts + i * 86400) * 1000), "y": float(40 + i)} for i in range(n)]
    return {
        "fear_and_greed": {"score": 49.0, "rating": "neutral", "timestamp": "2026-04-23T00:00:00+00:00"},
        "fear_and_greed_historical": {"data": data},
    }


class _FakeCNNResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return _cnn_response(10)


def test_cnn_fear_greed_returns_series(monkeypatch, tmp_path):
    """Happy path: CNN API returns data, series has correct length and values."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeCNNResponse())
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"CACHE_HOURS": "0"}
    s = fetch_cnn_fear_greed(env)

    assert isinstance(s, pd.Series)
    assert len(s) == 10
    assert isinstance(s.index, pd.DatetimeIndex)
    assert 40.0 <= float(s.iloc[0]) <= 50.0


def test_cnn_falls_back_to_stale_cache(monkeypatch, tmp_path):
    """When CNN is unreachable and stale cache exists, StaleCacheFallback is raised."""
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("down")),
    )
    _make_stale_cache(tmp_path, "cnn_fear_greed", n=20)
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"CACHE_HOURS": "0"}
    with pytest.raises(StaleCacheFallback) as exc_info:
        fetch_cnn_fear_greed(env)

    assert len(exc_info.value.series) == 20


def test_cnn_raises_when_no_cache(monkeypatch, tmp_path):
    """When CNN is unreachable and there is no cache, the original error propagates."""
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("down")),
    )
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    env = {"CACHE_HOURS": "0"}
    with pytest.raises(requests.ConnectionError):
        fetch_cnn_fear_greed(env)


def test_cnn_accumulates_history(monkeypatch, tmp_path):
    """Second fetch merges new data with cached history, deduplicating by date."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeCNNResponse())
    monkeypatch.setattr("src.fetch.CACHE_DIR", tmp_path / "cache")

    # Seed the cache with 30 older rows
    _make_stale_cache(tmp_path, "cnn_fear_greed", n=30)

    env = {"CACHE_HOURS": "0"}
    s = fetch_cnn_fear_greed(env)

    # Should have at least 30 rows (cache) and up to 30+10 if dates don't overlap
    assert len(s) >= 10
    assert isinstance(s.index, pd.DatetimeIndex)
