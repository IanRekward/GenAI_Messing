"""Tests for src/history.py — momentum, trend SVG, and helpers."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

import tempfile
import os

from src.history import compute_composite_momentum, log_run


def _make_history(scores: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    """Build a minimal history DataFrame with one row per day."""
    dates = pd.date_range(start, periods=len(scores), freq="D")
    return pd.DataFrame({
        "timestamp": dates,
        "composite": scores,
        "composite_band": ["green"] * len(scores),
    })


def test_momentum_insufficient_rows():
    h = _make_history([50.0])
    m = compute_composite_momentum(h)
    assert m["velocity_7d"] is None
    assert m["regime"] == "insufficient"


def test_momentum_empty_history():
    m = compute_composite_momentum(pd.DataFrame())
    assert m["velocity_7d"] is None
    assert m["regime"] == "insufficient"


def test_momentum_flat():
    h = _make_history([50.0] * 30)
    m = compute_composite_momentum(h)
    assert m["velocity_7d"] == 0.0
    assert m["regime"] == "flat"


def test_momentum_rising():
    # +2 pts/day for 35 days → velocity_7d ≈ +14, velocity_30d ≈ +60
    scores = [40.0 + i * 2 for i in range(35)]
    h = _make_history(scores)
    m = compute_composite_momentum(h)
    assert m["velocity_7d"] == pytest.approx(14.0, abs=0.5)
    assert m["velocity_30d"] is not None
    assert m["velocity_30d"] > 50
    assert m["regime"] in ("accelerating_up", "decelerating_up")


def test_momentum_falling():
    scores = [80.0 - i * 2 for i in range(30)]
    h = _make_history(scores)
    m = compute_composite_momentum(h)
    assert m["velocity_7d"] is not None
    assert m["velocity_7d"] < -3
    assert "down" in m["regime"]


def test_log_run_writes_composite_regime_weighted(tmp_path, monkeypatch):
    """Regression: composite_regime_weighted must appear in history.csv (Brief 10C gap)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "weights.yaml").write_text("buckets: {}")
    scoring = {
        "run_timestamp": "2026-05-20T12:00:00",
        "composite": 45.0,
        "composite_band": "yellow",
        "red_count": 1,
        "orange_count": 3,
        "yellow_count": 4,
        "buckets": {},
        "regime": "mid",
        "composite_naive": 44.5,
        "composite_regime_weighted": 46.2,
    }
    log_run(scoring)
    df = pd.read_csv(tmp_path / "data" / "history.csv")
    assert "composite_regime_weighted" in df.columns
    assert df["composite_regime_weighted"].iloc[0] == pytest.approx(46.2)


def test_momentum_dedupes_multiple_runs_per_day():
    """Multiple rows with same date → keep the last one."""
    today = pd.Timestamp("2026-04-01")
    df = pd.DataFrame({
        "timestamp": [today, today + pd.Timedelta(hours=1),
                      today - pd.Timedelta(days=7)],
        "composite": [60.0, 65.0, 50.0],  # two today (65 is later)
        "composite_band": ["orange", "orange", "yellow"],
    })
    m = compute_composite_momentum(df)
    # velocity_7d = 65 - 50 = +15
    assert m["velocity_7d"] == pytest.approx(15.0, abs=0.5)
