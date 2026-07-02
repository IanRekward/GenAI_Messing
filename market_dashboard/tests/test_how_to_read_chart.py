"""Tests for the per-indicator 'How to read this chart' drill-down block."""
from __future__ import annotations

import pandas as pd

from src.indicator_detail import build_indicator_detail, _fmt_thr


def _series(n: int = 200) -> dict:
    dates = pd.date_range("2015-01-01", periods=n, freq="B").strftime("%Y-%m-%d").tolist()
    values = [20.0 + (i % 10) for i in range(n)]
    return {"dates": dates, "values": values}


def _ind(label: str = "VIX", manual: bool = False, series: bool = True) -> dict:
    d = {"label": label, "raw": 22.0, "percentile": 60, "band": "yellow", "unit": ""}
    if manual:
        d["manual"] = True
    if series:
        d["_series"] = _series()
    return d


def test_normal_indicator_reads_higher_is_stress_with_real_thresholds():
    thr = {"direction": "high", "yellow": 20.0, "orange": 28.0, "red": 35.0}
    html = build_indicator_detail("vix", _ind("VIX"), thr)
    assert "How to read this chart" in html
    assert "higher = more stress" in html
    assert "rises above" in html
    assert "yellow (20)" in html
    assert "red (35)" in html


def test_inverted_indicator_reads_lower_is_stress_with_minus_sign():
    thr = {"direction": "low", "yellow": 0.1, "orange": -0.25, "red": -0.75}
    html = build_indicator_detail("yield_curve", _ind("Yield Curve (10y-3m)"), thr)
    assert "lower = more stress" in html
    assert "falls below" in html
    assert "orange (−0.25)" in html  # proper Unicode minus


def test_no_threshold_falls_back_to_percentile_and_invert_flag():
    # yield_curve is invert=True in weights.yaml → lower = more stress even w/o levels
    html = build_indicator_detail("yield_curve", _ind("Yield Curve"), None)
    assert "no fixed alert levels" in html
    assert "lower = more stress" in html


def test_normal_no_threshold_reads_higher_is_stress():
    html = build_indicator_detail("vix", _ind("VIX"), None)
    assert "no fixed alert levels" in html
    assert "higher = more stress" in html


def test_manual_indicator_has_no_how_to_read_block():
    html = build_indicator_detail("repo_stress", _ind("Repo Stress", manual=True, series=False), None)
    assert "How to read this chart" not in html


def test_yaml_override_replaces_generated_text(monkeypatch):
    import src.indicator_detail as m
    monkeypatch.setattr(m, "_EXPLAINERS", {"vix": {"how_to_read": "Bespoke chart guidance."}})
    thr = {"direction": "high", "yellow": 20.0, "orange": 28.0, "red": 35.0}
    html = build_indicator_detail("vix", _ind("VIX"), thr)
    assert "Bespoke chart guidance." in html
    assert "higher = more stress" not in html


def test_fmt_thr_uses_unicode_minus():
    assert _fmt_thr(-0.25) == "−0.25"
    assert _fmt_thr(20.0) == "20"
    assert _fmt_thr(0.0021) == "0.0021"
