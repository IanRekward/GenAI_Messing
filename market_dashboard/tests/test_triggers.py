"""Tests for src/triggers.py band evaluation and composite band logic."""
from __future__ import annotations

import pytest

from src.triggers import annotate_results


def _make_scoring(indicators: dict, composite: float = 40.0) -> dict:
    """Build a minimal scoring dict for annotation tests."""
    return {
        "composite": composite,
        "composite_band": "green",
        "red_count": 0,
        "orange_count": 0,
        "yellow_count": 0,
        "buckets": {
            "test_bucket": {
                "label": "Test",
                "weight": 1.0,
                "score": composite,
                "band": "green",
                "indicators": indicators,
            }
        },
        "errors": [],
    }


def _make_thresholds(ikey: str, direction: str = "high",
                     yellow: float = 20, orange: float = 30, red: float = 40) -> dict:
    return {"indicators": {ikey: {"direction": direction,
                                  "yellow": yellow, "orange": orange, "red": red}}}


def test_high_direction_red():
    scoring = _make_scoring({"vix": {"raw": 45.0, "score": 80, "band": "green",
                                     "label": "VIX", "unit": "", "manual": False, "invert": False}})
    result = annotate_results(scoring, _make_thresholds("vix"))
    assert result["buckets"]["test_bucket"]["indicators"]["vix"]["band"] == "red"
    assert result["red_count"] == 1


def test_high_direction_orange():
    scoring = _make_scoring({"vix": {"raw": 32.0, "score": 60, "band": "green",
                                     "label": "VIX", "unit": "", "manual": False, "invert": False}})
    result = annotate_results(scoring, _make_thresholds("vix"))
    assert result["buckets"]["test_bucket"]["indicators"]["vix"]["band"] == "orange"


def test_high_direction_yellow():
    scoring = _make_scoring({"vix": {"raw": 22.0, "score": 40, "band": "green",
                                     "label": "VIX", "unit": "", "manual": False, "invert": False}})
    result = annotate_results(scoring, _make_thresholds("vix"))
    assert result["buckets"]["test_bucket"]["indicators"]["vix"]["band"] == "yellow"


def test_low_direction_red():
    """Low direction (yield curve): raw below red threshold → red."""
    scoring = _make_scoring({"yield_curve": {"raw": -0.5, "score": 80, "band": "green",
                                              "label": "10Y-2Y", "unit": "%",
                                              "manual": False, "invert": True}})
    thr = {"indicators": {"yield_curve": {"direction": "low",
                                          "yellow": 0.0, "orange": -0.25, "red": -0.5}}}
    result = annotate_results(scoring, thr)
    assert result["buckets"]["test_bucket"]["indicators"]["yield_curve"]["band"] == "red"


def test_none_raw_returns_green():
    """raw=None must produce band='green', not a crash."""
    scoring = _make_scoring({"vix": {"raw": None, "score": 50, "band": "green",
                                     "label": "VIX", "unit": "", "manual": False, "invert": False}})
    result = annotate_results(scoring, _make_thresholds("vix"))
    assert result["buckets"]["test_bucket"]["indicators"]["vix"]["band"] == "green"


def test_composite_band_three_reds():
    """3+ red indicators → composite band = red regardless of composite score."""
    inds = {
        f"ind_{i}": {"raw": 99.0, "score": 80, "band": "green",
                     "label": f"Ind {i}", "unit": "", "manual": False, "invert": False}
        for i in range(3)
    }
    thr = {"indicators": {f"ind_{i}": {"direction": "high",
                                        "yellow": 10, "orange": 20, "red": 50}
                          for i in range(3)}}
    scoring = _make_scoring(inds, composite=35.0)
    result = annotate_results(scoring, thr)
    assert result["composite_band"] == "red"


def test_composite_band_high_score():
    """composite score >= 70 → red band even with no individual red triggers."""
    scoring = _make_scoring({"ind": {"raw": 5.0, "score": 80, "band": "green",
                                     "label": "X", "unit": "", "manual": False, "invert": False}},
                            composite=75.0)
    result = annotate_results(scoring, {"indicators": {}})
    assert result["composite_band"] == "red"


def test_composite_band_green():
    """Low composite score with no triggers → green."""
    scoring = _make_scoring({"ind": {"raw": 5.0, "score": 10, "band": "green",
                                     "label": "X", "unit": "", "manual": False, "invert": False}},
                            composite=20.0)
    result = annotate_results(scoring, {"indicators": {}})
    assert result["composite_band"] == "green"
