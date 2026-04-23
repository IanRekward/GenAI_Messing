"""Tests for news-to-trigger cross-reference (Brief 9)."""
from __future__ import annotations

from src.news import filter_headlines_for_triggers


def test_filter_matches_triggered_keywords():
    headlines = [
        "VIX spikes to 30 as recession fears mount",
        "Oil prices fall on OPEC supply increase",
        "Tech stocks gain on earnings beat",
        "High yield spreads widen amid credit concerns",
    ]
    result = filter_headlines_for_triggers(headlines, {"vix", "hy_oas"})
    assert any("VIX" in h for h in result)
    assert any("yield" in h.lower() for h in result)
    # Unrelated headline should not appear
    assert not any("Tech stocks" in h for h in result)


def test_filter_empty_triggered_keys_returns_empty():
    headlines = ["VIX spikes", "Bond yields rise"]
    assert filter_headlines_for_triggers(headlines, set()) == []


def test_filter_no_matching_headlines():
    headlines = ["Local sports team wins championship", "Weather forecast: sunny"]
    result = filter_headlines_for_triggers(headlines, {"vix", "yield_curve"})
    assert result == []


def test_filter_unknown_indicator_key_ignored():
    headlines = ["VIX spikes"]
    result = filter_headlines_for_triggers(headlines, {"nonexistent_indicator"})
    assert result == []


def test_filter_case_insensitive():
    headlines = ["INFLATION hits 40-year high", "CPI report released"]
    result = filter_headlines_for_triggers(headlines, {"cpi_yoy"})
    assert len(result) == 2
