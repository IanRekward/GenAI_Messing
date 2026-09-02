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


def _ind(raw: float) -> dict:
    return {"raw": raw, "score": 80, "band": "green",
            "label": "X", "unit": "", "manual": False, "invert": False}


def _thr(keys) -> dict:
    return {"indicators": {k: {"direction": "high",
                               "yellow": 10, "orange": 20, "red": 50} for k in keys}}


def _multi_bucket_scoring(bucket_inds: dict, composite: float) -> dict:
    return {
        "composite": composite,
        "composite_band": "green",
        "red_count": 0, "orange_count": 0, "yellow_count": 0,
        "buckets": {
            bk: {"label": bk, "weight": 0.5, "score": composite, "band": "green",
                 "indicators": inds}
            for bk, inds in bucket_inds.items()
        },
        "errors": [],
    }


def test_reds_in_one_bucket_do_not_escalate():
    """The 2026 pinned-commodity case: any number of reds confined to ONE
    bucket leaves the headline at the composite's own score band (D1)."""
    scoring = _multi_bucket_scoring(
        {"commodities": {"crack": _ind(99.0), "copper": _ind(99.0), "wti": _ind(99.0)},
         "credit": {"hy": _ind(5.0)}},
        composite=39.0,
    )
    result = annotate_results(scoring, _thr(["crack", "copper", "wti", "hy"]))
    assert result["red_count"] == 3
    assert result["composite_band"] == "green"


def test_reds_in_two_buckets_escalate_one_level():
    """Breadth confirmation: reds in >=2 distinct buckets lift the headline
    by exactly one level (the 08-31 shape: composite ~39 + broad reds -> yellow
    under the 57/65/72 cutoffs, not the old count-based red)."""
    scoring = _multi_bucket_scoring(
        {"commodities": {"crack": _ind(99.0)},
         "equity_volatility": {"vix": _ind(99.0)}},
        composite=39.0,
    )
    result = annotate_results(scoring, _thr(["crack", "vix"]))
    assert result["composite_band"] == "yellow"


def test_breadth_escalation_caps_at_red():
    scoring = _multi_bucket_scoring(
        {"a": {"i1": _ind(99.0)}, "b": {"i2": _ind(99.0)}},
        composite=72.0,
    )
    result = annotate_results(scoring, _thr(["i1", "i2"]))
    assert result["composite_band"] == "red"


def test_orange_score_with_breadth_reaches_red():
    """COVID-shape: composite in orange territory + broad reds -> red
    (COVID peaked at 71 — orange by score, red via breadth)."""
    scoring = _multi_bucket_scoring(
        {"a": {"i1": _ind(99.0)}, "b": {"i2": _ind(99.0)}},
        composite=66.0,
    )
    result = annotate_results(scoring, _thr(["i1", "i2"]))
    assert result["composite_band"] == "red"


def test_composite_band_high_score():
    """composite score >= 72 → red band even with no individual red triggers."""
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
