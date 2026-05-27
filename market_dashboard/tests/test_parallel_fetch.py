"""Tests for parallel indicator fetch — Brief 27."""
from __future__ import annotations

import pandas as pd

from src.fetch import StaleCacheFallback
from src.scoring import compute_composite


def _make_weights(keys_weights: list[tuple[str, float]]) -> dict:
    indicators = {
        key: {"label": key, "weight": w, "invert": False, "unit": "", "manual": False}
        for key, w in keys_weights
    }
    return {
        "buckets": {
            "test_bucket": {
                "label": "Test",
                "weight": 1.0,
                "indicators": indicators,
            }
        }
    }


def _dated_series(value: float = 50.0) -> pd.Series:
    """100-point series with DatetimeIndex and last value = value."""
    s = pd.Series(range(1, 101), dtype=float)
    s.iloc[-1] = value
    s.index = pd.date_range("2015-01-01", periods=100, freq="D")
    return s


def test_parallel_serial_fallback_matches(monkeypatch):
    """MAX_FETCH_WORKERS=1 (serial) and =8 (parallel) produce identical composites."""
    def _fake_fetch(key, cfg, env, manual):
        value = {"ind_a": 75.0, "ind_b": 25.0, "ind_c": 50.0}[key]
        return value, _dated_series(value)

    monkeypatch.setattr("src.scoring._fetch_indicator", _fake_fetch)

    weights = _make_weights([("ind_a", 0.4), ("ind_b", 0.4), ("ind_c", 0.2)])

    serial = compute_composite(weights, {"MAX_FETCH_WORKERS": "1"}, {})
    parallel = compute_composite(weights, {"MAX_FETCH_WORKERS": "8"}, {})

    assert serial["composite"] == parallel["composite"]
    assert serial["errors"] == parallel["errors"]
    assert serial["warnings"] == parallel["warnings"]


def test_parallel_isolates_per_indicator_failures(monkeypatch):
    """A single-indicator failure does not short-circuit others; errors[] is sorted."""
    def _fake_fetch(key, cfg, env, manual):
        if key in ("z_fail", "a_fail"):
            raise RuntimeError(f"boom {key}")
        return 50.0, _dated_series(50.0)

    monkeypatch.setattr("src.scoring._fetch_indicator", _fake_fetch)

    weights = _make_weights([
        ("b_ok", 0.25),
        ("z_fail", 0.25),
        ("c_ok", 0.25),
        ("a_fail", 0.25),
    ])

    result = compute_composite(weights, {"MAX_FETCH_WORKERS": "8"}, {})

    assert any("z_fail" in e for e in result["errors"])
    assert any("a_fail" in e for e in result["errors"])
    assert "composite" in result
    assert result["errors"] == sorted(result["errors"])


def test_parallel_handles_stale_cache_fallback(monkeypatch):
    """StaleCacheFallback is recorded as a warning, not an error; stale series is scored."""
    stale_series = _dated_series(90.0)

    def _fake_fetch(key, cfg, env, manual):
        if key == "stale_ind":
            raise StaleCacheFallback(stale_series, "stale_ind", "network timeout")
        return 50.0, _dated_series(50.0)

    monkeypatch.setattr("src.scoring._fetch_indicator", _fake_fetch)

    weights = _make_weights([("stale_ind", 0.5), ("ok_ind", 0.5)])

    result = compute_composite(weights, {"MAX_FETCH_WORKERS": "8"}, {})

    assert not any("stale_ind" in e for e in result["errors"])
    assert any("STALE CACHE:" in w for w in result["warnings"])

    # stale_series has iloc[-1]=90; (series<90).mean()*100 = 89.0 → score=89.0
    stale_score = result["buckets"]["test_bucket"]["indicators"]["stale_ind"]["score"]
    assert stale_score != 50.0
    assert stale_score > 80.0
