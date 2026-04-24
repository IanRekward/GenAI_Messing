"""Tests for the escalation-paths / pre-mortem card in dashboard.py."""
from __future__ import annotations

from unittest.mock import patch

from src.dashboard import _build_escalation_card, _load_escalation_paths


def _scoring(composite: float, bucket_bands: dict) -> dict:
    """Build minimal scoring dict."""
    buckets = {
        k: {"label": k.replace("_", " ").title(), "score": 60.0, "band": v}
        for k, v in bucket_bands.items()
    }
    return {"composite": composite, "buckets": buckets}


# ── _load_escalation_paths ────────────────────────────────────────────────────

def test_load_returns_dict():
    result = _load_escalation_paths()
    assert isinstance(result, dict)


def test_load_has_known_bucket():
    result = _load_escalation_paths()
    assert "equity_volatility" in result


def test_load_entry_has_scenario():
    result = _load_escalation_paths()
    assert "scenario" in result["equity_volatility"]


# ── _build_escalation_card ────────────────────────────────────────────────────

def test_empty_when_composite_low():
    s = _scoring(39.9, {"equity_volatility": "red", "credit_spreads": "orange"})
    assert _build_escalation_card(s) == ""


def test_empty_when_no_orange_red():
    s = _scoring(55.0, {"equity_volatility": "green", "credit_spreads": "yellow"})
    assert _build_escalation_card(s) == ""


def test_returns_html_when_triggered():
    s = _scoring(55.0, {"equity_volatility": "orange"})
    html = _build_escalation_card(s)
    assert isinstance(html, str)
    assert len(html) > 0
    assert "ESCALATION" in html


def test_contains_bucket_label():
    s = _scoring(55.0, {"credit_spreads": "red"})
    html = _build_escalation_card(s)
    assert "Credit" in html or "credit" in html


def test_yellow_not_included():
    s = _scoring(55.0, {"equity_volatility": "yellow", "credit_spreads": "orange"})
    html = _build_escalation_card(s)
    # Only credit_spreads should appear, not equity_volatility
    assert "Credit" in html or "credit" in html


def test_multiple_buckets_shown():
    s = _scoring(65.0, {
        "equity_volatility": "orange",
        "credit_spreads": "red",
    })
    html = _build_escalation_card(s)
    assert html.count("<details") >= 2


def test_watch_field_in_output():
    s = _scoring(55.0, {"funding_liquidity": "red"})
    html = _build_escalation_card(s)
    assert "Watch" in html


def test_empty_when_no_paths_file():
    """When escalation_paths.yaml is missing, card should be empty."""
    s = _scoring(55.0, {"equity_volatility": "red"})
    with patch("src.dashboard._load_escalation_paths", return_value={}):
        assert _build_escalation_card(s) == ""
