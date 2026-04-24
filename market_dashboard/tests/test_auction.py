"""Tests for treasury auction stress scoring."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from src.scoring import _zscore_list, _compute_auction_stress
from src.fetch import fetch_treasury_auction_results


# ── _zscore_list ──────────────────────────────────────────────────────────────

def test_zscore_list_basic():
    z = _zscore_list([1.0, 2.0, 3.0, 4.0, 5.0])
    assert abs(np.mean(z)) < 1e-9   # mean ≈ 0
    assert abs(np.std(z) - 1.0) < 1e-6  # std ≈ 1


def test_zscore_list_constant():
    z = _zscore_list([2.5, 2.5, 2.5])
    assert z == [0.0, 0.0, 0.0]


def test_zscore_list_length_preserved():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert len(_zscore_list(vals)) == 4


# ── _compute_auction_stress ───────────────────────────────────────────────────

def _make_results(n: int, b2c_base: float = 2.5, ind_base: float = 70.0,
                  dlr_base: float = 15.0) -> list[dict]:
    """Build n synthetic auction result dicts with slight variation."""
    results = []
    for i in range(n):
        results.append({
            "date": f"2025-{(i % 12 + 1):02d}-15",
            "bid_to_cover": b2c_base + i * 0.01,
            "indirect_pct": ind_base - i * 0.1,
            "dealer_pct": dlr_base + i * 0.05,
        })
    return results


def test_compute_auction_stress_returns_series():
    r10 = _make_results(8)
    r30 = _make_results(8, b2c_base=2.3)
    raw, series = _compute_auction_stress(r10, r30)
    assert isinstance(series, pd.Series)
    assert len(series) > 0
    assert isinstance(raw, float)


def test_compute_auction_stress_high_stress_scenario():
    # Weak auction: low b2c, low indirect, high dealer
    r10_weak = _make_results(8, b2c_base=1.8, ind_base=55.0, dlr_base=30.0)
    # Strong historical baseline for comparison
    r10_strong = _make_results(8, b2c_base=2.7, ind_base=75.0, dlr_base=10.0)
    # Combine to create a series where the last entry is from the weak auction
    mixed = r10_strong[:-1] + [r10_weak[-1]]

    raw_weak, _ = _compute_auction_stress(mixed, [])
    raw_strong, _ = _compute_auction_stress(r10_strong, [])
    # Weak final auction should yield higher stress (higher z-score)
    assert raw_weak > raw_strong


def test_compute_auction_stress_insufficient_data_raises():
    with pytest.raises(RuntimeError, match="insufficient data"):
        _compute_auction_stress([], [])


def test_compute_auction_stress_one_series_ok():
    # If 30Y has no data but 10Y does, still works
    r10 = _make_results(8)
    raw, series = _compute_auction_stress(r10, [])
    assert len(series) > 0


def test_compute_auction_stress_series_sorted():
    r10 = _make_results(8)
    r30 = _make_results(6, b2c_base=2.3)
    _, series = _compute_auction_stress(r10, r30)
    assert list(series.index) == sorted(series.index)


# ── fetch_treasury_auction_results ────────────────────────────────────────────

def _td_response(items: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = items
    return mock


def test_fetch_auction_results_filters_by_term(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw_items = [
        {"term": "10-Year", "auctionDate": "2026-03-12",
         "bidToCoverRatio": "2.5", "indirectBidderPercent": "70", "primaryDealerPercent": "12"},
        {"term": "2-Year", "auctionDate": "2026-03-10",   # different term → filtered
         "bidToCoverRatio": "2.7", "indirectBidderPercent": "65", "primaryDealerPercent": "10"},
    ]
    with patch("src.fetch.requests.get", return_value=_td_response(raw_items)):
        results = fetch_treasury_auction_results("Note", "10-Year", {"CACHE_HOURS": "0"})
    assert len(results) == 1
    assert results[0]["date"] == "2026-03-12"


def test_fetch_auction_results_parses_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw_items = [
        {"term": "30-Year", "auctionDate": "2026-02-13",
         "bidToCoverRatio": "2.37", "indirectBidderPercent": "68.2",
         "primaryDealerPercent": "14.5"},
    ]
    with patch("src.fetch.requests.get", return_value=_td_response(raw_items)):
        results = fetch_treasury_auction_results("Bond", "30-Year", {"CACHE_HOURS": "0"})
    assert results[0]["bid_to_cover"] == pytest.approx(2.37)
    assert results[0]["indirect_pct"] == pytest.approx(68.2)
    assert results[0]["dealer_pct"] == pytest.approx(14.5)


def test_fetch_auction_results_skips_zero_b2c(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw_items = [
        {"term": "10-Year", "auctionDate": "2026-03-12",
         "bidToCoverRatio": "0", "indirectBidderPercent": "70", "primaryDealerPercent": "12"},
    ]
    with patch("src.fetch.requests.get", return_value=_td_response(raw_items)):
        results = fetch_treasury_auction_results("Note", "10-Year", {"CACHE_HOURS": "0"})
    assert results == []


def test_fetch_auction_results_graceful_on_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("src.fetch.requests.get", side_effect=Exception("network error")):
        results = fetch_treasury_auction_results("Note", "10-Year", {"CACHE_HOURS": "0"})
    assert results == []


def test_fetch_auction_results_handles_alternate_field_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Some TD API versions use 'securityTerm' and 'indirectBidderAccepted'
    raw_items = [
        {"securityTerm": "10-Year", "auctionDate": "2026-03-12",
         "bidToCoverRatio": "2.6", "indirectBidderAccepted": "72.0",
         "primaryDealerPercent": "11.0"},
    ]
    with patch("src.fetch.requests.get", return_value=_td_response(raw_items)):
        results = fetch_treasury_auction_results("Note", "10-Year", {"CACHE_HOURS": "0"})
    # term lookup uses 'term' first, then 'securityTerm'
    assert len(results) == 1
    assert results[0]["indirect_pct"] == pytest.approx(72.0)
