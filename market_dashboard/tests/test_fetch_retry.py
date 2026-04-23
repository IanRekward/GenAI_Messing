"""Tests for retry + stale-cache fallback in fetch layer (Brief 7)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.fetch import StaleCacheFallback, _retry_get, fetch_fred_series


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
