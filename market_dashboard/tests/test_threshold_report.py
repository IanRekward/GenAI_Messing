"""Tests for src/threshold_report.py (B1 artifact — report-only, applies nothing)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.threshold_report import (
    _firing_rates,
    _load_raws,
    _propose,
    build_report,
    composite_cutoff_proposal,
)


def _bt_csv(tmp_path, n=500):
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "date": dates,
        "equity_volatility__vix__raw": rng.uniform(10, 40, n),
        "sentiment__cnn_fear_greed__raw": [0.0] * n,
        "sentiment__iran_trigger__raw": [0.0] * n,
        "composite": rng.uniform(20, 60, n),
    })
    p = tmp_path / "backtest_full.csv"
    df.to_csv(p, index=False)
    return p


def test_load_raws_excludes_placeholder_and_manual(tmp_path):
    raws = _load_raws(_bt_csv(tmp_path), None)
    assert "vix" in raws
    assert "cnn_fear_greed" not in raws  # backtest stores a 0.0 placeholder
    assert "iran_trigger" not in raws


def test_load_raws_cnn_from_cache(tmp_path):
    cache = tmp_path / "cnn.json"
    cache.write_text(json.dumps({
        "dates": ["2026-01-02", "2026-01-03"], "values": [40.0, 22.0],
    }))
    raws = _load_raws(_bt_csv(tmp_path), cache)
    assert len(raws["cnn_fear_greed"]) == 2


def test_firing_rates_direction_low():
    s = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    thr = {"direction": "low", "yellow": 45, "orange": 35, "red": 25}
    rates = _firing_rates(s, thr)
    assert rates["red"] == 20.0     # 10, 20
    assert rates["orange"] == 10.0  # 30
    assert rates["yellow"] == 10.0  # 40
    assert rates["green"] == 60.0


def test_propose_hits_target_quantiles():
    s = pd.Series(range(1, 101), dtype=float)
    hi = _propose(s, "high")
    assert hi["red"] == pytest.approx(s.quantile(0.95))
    lo = _propose(s, "low")
    assert lo["red"] == pytest.approx(s.quantile(0.05))
    # applying the proposal reproduces the target rate
    thr = {"direction": "high", **hi}
    assert _firing_rates(s, thr)["red"] <= 6.0


def test_build_report_flags_hot_and_dead_thresholds(tmp_path):
    n = 400
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    raws = {
        "hot": pd.Series(np.linspace(0, 100, n), index=dates),
        "dead": pd.Series(np.linspace(0, 100, n), index=dates),
    }
    thresholds = {
        "hot": {"direction": "high", "yellow": 10, "orange": 20, "red": 30},
        "dead": {"direction": "high", "yellow": 90, "orange": 95, "red": 200},
    }
    report, proposed = build_report(thresholds, raws, live_start="2021-06-01")
    assert "RED TOO HOT" in report
    assert "red never fired" in report
    # ceiling semantics: only the too-hot indicator gets a proposal; the
    # conservative/dead one is flagged for judgment, never auto-tightened
    assert set(proposed) == {"hot"}
    assert proposed["hot"]["red"] > proposed["hot"]["orange"] > proposed["hot"]["yellow"]
    assert "| keep |" in report


def test_composite_cutoffs_monotonic(tmp_path):
    cuts = composite_cutoff_proposal(_bt_csv(tmp_path))
    assert cuts["yellow"] < cuts["orange"] < cuts["red"]
