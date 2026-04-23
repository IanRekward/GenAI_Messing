"""Tests for src/scoring.py composite calculation logic."""
from __future__ import annotations

import pandas as pd
import pytest

from src.scoring import compute_composite


def _make_weights(indicator_defs: list[dict]) -> dict:
    """Build a minimal weights dict with one bucket and given indicators."""
    indicators = {}
    for d in indicator_defs:
        indicators[d["key"]] = {
            "label": d.get("label", d["key"]),
            "weight": d["weight"],
            "invert": d.get("invert", False),
            "unit": d.get("unit", ""),
            "manual": d.get("manual", True),
        }
    return {
        "buckets": {
            "test_bucket": {
                "label": "Test Bucket",
                "weight": 1.0,
                "indicators": indicators,
            }
        }
    }


@pytest.fixture
def mock_fetch(monkeypatch):
    """Patch _fetch_indicator to return controlled (raw, series) pairs."""
    values = {}

    def _fake_fetch(key, cfg, env, manual):
        if key in values:
            raw, pct = values[key]
            # Return a known-percentile series: current value at known position
            series = pd.Series([float(i) for i in range(1, 101)])
            series.iloc[-1] = raw
            return raw, series
        return float(manual.get(key, 50.0)), None

    monkeypatch.setattr("src.scoring._fetch_indicator", _fake_fetch)
    return values


def test_composite_weighted_average(monkeypatch):
    """Weighted average: 0.6*score_a + 0.4*score_b."""
    def _mock(key, cfg, env, manual):
        s = pd.Series(range(1, 101), dtype=float)
        s.iloc[-1] = 80.0 if key == "a" else 20.0
        return s.iloc[-1], s

    monkeypatch.setattr("src.scoring._fetch_indicator", _mock)

    weights = _make_weights([
        {"key": "a", "weight": 0.6, "manual": False},
        {"key": "b", "weight": 0.4, "manual": False},
    ])
    result = compute_composite(weights, {"HISTORY_YEARS": "10"}, {})
    # a: (series < 80).mean() = 79/100 = 79.0; b: 19/100 = 19.0
    # composite = 79.0*0.6 + 19.0*0.4 = 47.4 + 7.6 = 55.0
    assert result["composite"] == 55.0


def test_error_defaults_to_50_and_continues(mock_fetch, monkeypatch):
    """If one indicator raises, it gets score=50, error logged, run continues."""
    def _failing_fetch(key, cfg, env, manual):
        if key == "bad":
            raise RuntimeError("fetch failed")
        # ok: current=5, below all others → percentile=0 → score=0
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
        s.iloc[-1] = 5.0
        return 5.0, s

    monkeypatch.setattr("src.scoring._fetch_indicator", _failing_fetch)

    weights = _make_weights([
        {"key": "bad", "weight": 0.5, "manual": True},
        {"key": "ok", "weight": 0.5, "manual": True},
    ])
    result = compute_composite(weights, {"HISTORY_YEARS": "10"}, {})

    # Run should complete
    assert "composite" in result
    # Error should be recorded
    assert any("bad" in e for e in result["errors"])
    # bad → error → score=50.0; ok → (series < 5).mean()=0 on [10..100] → score=0.0
    # composite = (50.0*0.5 + 0.0*0.5) = 25.0
    assert result["composite"] == 25.0


def test_invert_flag(mock_fetch, monkeypatch):
    """invert=True: an indicator at the 80th percentile should score 20."""
    def _fixed_fetch(key, cfg, env, manual):
        s = pd.Series(range(1, 101), dtype=float)
        s.iloc[-1] = 80.0  # compute_percentile uses iloc[-1] as current
        return 80.0, s

    monkeypatch.setattr("src.scoring._fetch_indicator", _fixed_fetch)

    weights = _make_weights([{"key": "inv", "weight": 1.0, "invert": True, "manual": False}])
    result = compute_composite(weights, {"HISTORY_YEARS": "10"}, {})

    score = result["buckets"]["test_bucket"]["indicators"]["inv"]["score"]
    # series [1..100] with iloc[-1]=80; (series < 80).mean() = 79/100 = 79.0
    # inverted: 100 - 79 = 21.0
    assert score == 21.0
