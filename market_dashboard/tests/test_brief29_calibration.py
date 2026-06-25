"""Brief 29 — honest calibration card: adequacy gate, proven-skill line, IC summary."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.evaluation import rolling_composite_ic, ic_summary_dict
from src import dashboard


def _make_spx(n: int, start: str = "2023-01-01") -> pd.Series:
    rng = np.random.default_rng(7)
    prices = np.cumsum(rng.standard_normal(n)) + 4500
    return pd.Series(prices, index=pd.date_range(start, periods=n, freq="B"))


def _make_history(n: int, start: str = "2023-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(3)
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({"timestamp": dates, "composite": rng.uniform(35, 55, n)})


# ── adequacy gate ──────────────────────────────────────────────────────────

def test_adequacy_building_for_small_live_history():
    """~50 obs (one calm regime) must route to 'building', never a hard verdict."""
    n = 75  # ~54 aligned obs after the 21d forward window drops the tail
    result = rolling_composite_ic(_make_history(n), _make_spx(n), horizon_days=21)
    assert 30 <= result["n_obs"] < 90
    assert result["adequacy"] == "building"


def test_adequacy_ok_past_threshold():
    n = 130  # ~109 aligned obs ≥ 90
    result = rolling_composite_ic(_make_history(n), _make_spx(n), horizon_days=21)
    assert result["n_obs"] >= 90
    assert result["adequacy"] == "ok"


def test_adequacy_insufficient_below_30():
    result = rolling_composite_ic(_make_history(10), _make_spx(10), horizon_days=21)
    assert result["ic"] is None
    assert result["adequacy"] == "insufficient"


# ── IC summary serialization ───────────────────────────────────────────────

def test_ic_summary_dict_both_targets():
    results = {"continuous": {
        "1w": {"spx_drawdown": {"spearman_ic": 0.150}, "stress_index": {"spearman_ic": 0.759}},
        "1m": {"spx_drawdown": {"spearman_ic": 0.115}, "stress_index": {"spearman_ic": 0.704}},
        "3m": {"spx_drawdown": {"spearman_ic": -0.019}, "stress_index": {"spearman_ic": 0.540}},
        "6m": {"spx_drawdown": {"spearman_ic": -0.126}, "stress_index": {"spearman_ic": 0.390}},
    }}
    out = ic_summary_dict(results, n_obs=2167, generated="2026-06-25T07:30:00")
    assert out["n_obs"] == 2167
    assert out["generated"] == "2026-06-25T07:30:00"
    assert out["composite_vs_spx_drawdown"]["1w"] == 0.15
    assert out["composite_vs_stress_index"]["1m"] == 0.704
    json.loads(json.dumps(out))  # must be JSON-serializable


def test_ic_summary_dict_omits_absent_stress_index():
    results = {"continuous": {
        "1w": {"spx_drawdown": {"spearman_ic": 0.150}},
        "1m": {"spx_drawdown": {"spearman_ic": 0.115}},
    }}
    out = ic_summary_dict(results, n_obs=2000, generated="x")
    assert "composite_vs_spx_drawdown" in out
    assert "composite_vs_stress_index" not in out


# ── card rendering ─────────────────────────────────────────────────────────

def _render_card(monkeypatch, tmp_path, ic_result, summary=None):
    monkeypatch.setattr("src.dashboard.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("src.fetch.fetch_yfinance_series", lambda *a, **k: _make_spx(120))
    monkeypatch.setattr("src.evaluation.rolling_composite_ic", lambda *a, **k: ic_result)
    if summary is not None:
        (tmp_path / "backtest_ic_summary.json").write_text(json.dumps(summary))
    return dashboard._build_signal_quality_card(_make_history(120), {}, None)


def test_card_building_history_suppresses_false_verdict(monkeypatch, tmp_path):
    ic_result = {"ic": -0.02, "n_obs": 54, "adequacy": "building",
                 "horizon_days": 21, "window_days": 252}
    html = _render_card(monkeypatch, tmp_path, ic_result)
    assert "BUILDING HISTORY" in html
    assert "54/90 obs" in html
    assert "MISCALIBRATED" not in html  # the false red verdict is gone


def test_card_ok_low_ic_still_shows_miscalibrated(monkeypatch, tmp_path):
    ic_result = {"ic": -0.02, "n_obs": 120, "adequacy": "ok",
                 "horizon_days": 21, "window_days": 252}
    html = _render_card(monkeypatch, tmp_path, ic_result)
    assert "MISCALIBRATED" in html
    assert "BUILDING HISTORY" not in html


def test_card_ok_high_ic_shows_tracking(monkeypatch, tmp_path):
    ic_result = {"ic": 0.22, "n_obs": 120, "adequacy": "ok",
                 "horizon_days": 21, "window_days": 252}
    html = _render_card(monkeypatch, tmp_path, ic_result)
    assert "TRACKING" in html


def test_card_proven_skill_line_present_when_summary_exists(monkeypatch, tmp_path):
    summary = {"generated": "x", "n_obs": 2167,
               "composite_vs_spx_drawdown": {"1w": 0.15, "1m": 0.115},
               "composite_vs_stress_index": {"1m": 0.70}}
    ic_result = {"ic": -0.02, "n_obs": 54, "adequacy": "building",
                 "horizon_days": 21, "window_days": 252}
    html = _render_card(monkeypatch, tmp_path, ic_result, summary=summary)
    assert "Proven skill:" in html
    assert "0.15 IC @ 1wk vs drawdown" in html
    assert "0.70 @ 1m vs realized stress" in html


def test_card_proven_skill_line_omitted_when_summary_absent(monkeypatch, tmp_path):
    ic_result = {"ic": -0.02, "n_obs": 54, "adequacy": "building",
                 "horizon_days": 21, "window_days": 252}
    html = _render_card(monkeypatch, tmp_path, ic_result)
    assert "Proven skill:" not in html
