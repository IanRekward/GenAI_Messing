"""Tests for src/calendar.py — upcoming events fetching and filtering."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.calendar import (
    _fomc_events,
    _ism_dates,
    _is_in_scope_auction,
    _fetch_treasury_upcoming,
    fetch_upcoming_events,
)


# ── _fomc_events ─────────────────────────────────────────────────────────────

def test_fomc_includes_date_within_window():
    # April 29, 2026 is in _FOMC_DATES; use a window that includes it
    end = date(2026, 5, 1)
    with patch("src.calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 23)
        mock_date.fromisoformat = date.fromisoformat
        events = _fomc_events(end)
    assert any(e["label"] == "FOMC Decision" and e["date"] == "2026-04-29" for e in events)


def test_fomc_excludes_past_dates():
    # Window starts today; no FOMC should be in the past
    end = date(2026, 4, 28)
    with patch("src.calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)  # after the Apr 29 meeting
        mock_date.fromisoformat = date.fromisoformat
        events = _fomc_events(end)
    assert not any(e["date"] == "2026-04-29" for e in events)


def test_fomc_type_tag():
    end = date(2026, 6, 30)
    with patch("src.calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.fromisoformat = date.fromisoformat
        events = _fomc_events(end)
    assert all(e["type"] == "fomc" for e in events)


# ── _ism_dates ────────────────────────────────────────────────────────────────

def test_ism_returns_mfg_and_services():
    # Freeze "today" to month-start so the current month's Mfg date is still upcoming.
    end = date(2026, 6, 30)
    events = _ism_dates(end, today=date(2026, 6, 1))
    labels = [e["label"] for e in events]
    assert "ISM Mfg PMI" in labels
    assert "ISM Services PMI" in labels


def test_ism_mfg_is_first_weekday():
    end = date(2026, 6, 30)
    events = _ism_dates(end, today=date(2026, 6, 1))
    mfg = [e for e in events if e["label"] == "ISM Mfg PMI"]
    assert mfg, "Expected at least one ISM Mfg PMI event"
    for ev in mfg:
        d = date.fromisoformat(ev["date"])
        assert d.weekday() < 5  # is a weekday


def test_ism_type_tag():
    end = date(2026, 6, 30)
    events = _ism_dates(end)
    assert all(e["type"] == "economic" for e in events)


# ── _is_in_scope_auction ──────────────────────────────────────────────────────

def test_auction_scope_10y_note():
    assert _is_in_scope_auction("Note", "10-Year") is True


def test_auction_scope_30y_bond():
    assert _is_in_scope_auction("Bond", "30-Year") is True


def test_auction_scope_tips():
    assert _is_in_scope_auction("TIPS", "10-Year") is True
    assert _is_in_scope_auction("TIPS", "5-Year TIPS") is True


def test_auction_scope_rejects_bills():
    assert _is_in_scope_auction("Bill", "13-Week") is False
    assert _is_in_scope_auction("Bill", "52-Week") is False


def test_auction_scope_rejects_frn():
    assert _is_in_scope_auction("FRN", "2-Year") is False


def test_auction_scope_rejects_out_of_scope_note_terms():
    # 3-Year note is not in scope per the project spec
    assert _is_in_scope_auction("Note", "3-Year") is False


# ── _fetch_treasury_upcoming ──────────────────────────────────────────────────

def _mock_td_response(auctions: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = auctions
    return mock_resp


def test_treasury_upcoming_filters_by_date():
    today = date(2026, 4, 23)
    auctions = [
        {"type": "Note", "term": "10-Year", "auctionDate": "2026-04-30"},  # in window
        {"type": "Note", "term": "10-Year", "auctionDate": "2026-05-30"},  # out of window
        {"type": "Bill", "term": "13-Week", "auctionDate": "2026-04-25"},  # filtered out
    ]
    with patch("src.calendar.date") as mock_date, \
         patch("src.calendar.requests.get", return_value=_mock_td_response(auctions)):
        mock_date.today.return_value = today
        mock_date.fromisoformat = date.fromisoformat
        end = today + timedelta(days=14)
        events = _fetch_treasury_upcoming(end)
    assert len(events) == 1
    assert events[0]["date"] == "2026-04-30"
    assert events[0]["type"] == "auction"


def test_treasury_upcoming_graceful_on_error():
    with patch("src.calendar.requests.get", side_effect=Exception("network error")):
        events = _fetch_treasury_upcoming(date(2026, 5, 7))
    assert events == []


# ── fetch_upcoming_events integration ────────────────────────────────────────

def test_fetch_upcoming_events_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "")
    monkeypatch.chdir(tmp_path)
    # Patch FOMC/ISM helpers to return known events; skip live fetches
    fomc_ev = [{"date": "2026-04-29", "label": "FOMC Decision", "type": "fomc"}]
    ism_ev  = [{"date": "2026-05-01", "label": "ISM Mfg PMI",  "type": "economic"}]

    with patch("src.calendar._fomc_events", return_value=fomc_ev), \
         patch("src.calendar._ism_dates",   return_value=ism_ev), \
         patch("src.calendar._fetch_fred_releases", return_value=[]), \
         patch("src.calendar._fetch_treasury_upcoming", return_value=[]), \
         patch("src.calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 23)
        mock_date.fromisoformat = date.fromisoformat
        events = fetch_upcoming_events({"CACHE_HOURS": "0"}, days=14)

    assert isinstance(events, list)
    for ev in events:
        assert "date" in ev
        assert "label" in ev
        assert "type" in ev


def test_fetch_upcoming_events_deduplication_by_sort(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev1 = {"date": "2026-05-01", "label": "NFP", "type": "economic"}
    ev2 = {"date": "2026-04-29", "label": "FOMC Decision", "type": "fomc"}

    with patch("src.calendar._fomc_events", return_value=[ev2]), \
         patch("src.calendar._ism_dates",   return_value=[]), \
         patch("src.calendar._fetch_fred_releases", return_value=[ev1]), \
         patch("src.calendar._fetch_treasury_upcoming", return_value=[]), \
         patch("src.calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 23)
        mock_date.fromisoformat = date.fromisoformat
        events = fetch_upcoming_events({"CACHE_HOURS": "0"}, days=14)

    dates = [e["date"] for e in events]
    assert dates == sorted(dates)  # should be sorted ascending by date
