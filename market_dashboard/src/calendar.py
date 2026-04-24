"""
Economic calendar: upcoming macro releases, Treasury auctions, FOMC, and ISM PMI.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"

_FRED_RELEASE_URL = "https://api.stlouisfed.org/fred/release/dates"
_TD_ANNOUNCED_URL = "https://www.treasurydirect.gov/TA_WS/securities/announced"

# IN scope per project spec (todos 40)
_FRED_RELEASES: dict[int, str] = {
    9:  "Jobless Claims",
    10: "CPI",
    31: "PPI",
    50: "NFP",
    53: "GDP",
    54: "PCE",
    56: "Retail Sales",
}

# 2025–2026 FOMC statement dates (rate decision day)
_FOMC_DATES: list[str] = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Note/Bond terms in scope; TIPS always included; T-bills always excluded
_NOTE_BOND_TERMS = {"2-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"}


def _cache_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "calendar_events.json"


def _cache_valid(hours: float) -> bool:
    if hours <= 0:
        return False
    p = _cache_path()
    return p.exists() and (time.time() - p.stat().st_mtime) < hours * 3600


def _read_cache() -> list[dict]:
    with open(_cache_path()) as f:
        return json.load(f).get("events", [])


def _write_cache(events: list[dict]) -> None:
    with open(_cache_path(), "w") as f:
        json.dump({"events": events}, f)


def _fomc_events(end: date) -> list[dict]:
    today = date.today()
    return [
        {"date": d, "label": "FOMC Decision", "type": "fomc"}
        for d in _FOMC_DATES
        if today <= date.fromisoformat(d) <= end
    ]


def _ism_dates(end: date) -> list[dict]:
    """Approximate ISM PMI dates: Mfg on 1st weekday, Services on 3rd weekday of month."""
    today = date.today()
    events: list[dict] = []
    for m_offset in range(3):
        m = (today.month - 1 + m_offset) % 12 + 1
        y = today.year + (today.month - 1 + m_offset) // 12

        # First weekday = approx ISM Manufacturing PMI
        d = date(y, m, 1)
        while d.weekday() >= 5:
            d += timedelta(1)
        if today <= d <= end:
            events.append({"date": d.isoformat(), "label": "ISM Mfg PMI", "type": "economic"})

        # Third weekday = approx ISM Services PMI
        count, d3 = 0, date(y, m, 1)
        while count < 3:
            if d3.weekday() < 5:
                count += 1
            if count < 3:
                d3 += timedelta(1)
        if today <= d3 <= end:
            events.append({"date": d3.isoformat(), "label": "ISM Services PMI", "type": "economic"})
    return events


def _fetch_fred_releases(api_key: str, end: date) -> list[dict]:
    if not api_key or api_key.startswith("your_"):
        return []
    today_str = date.today().isoformat()
    end_str = end.isoformat()
    events: list[dict] = []
    for release_id, label in _FRED_RELEASES.items():
        try:
            resp = requests.get(
                _FRED_RELEASE_URL,
                params={
                    "release_id": release_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "realtime_start": today_str,
                    "realtime_end": end_str,
                    "include_release_dates_with_no_data": "true",
                    "sort_order": "asc",
                    "limit": 5,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for rd in resp.json().get("release_dates", []):
                d = rd.get("date", "")
                if d:
                    events.append({"date": d, "label": label, "type": "economic"})
        except Exception:
            continue
    return events


def _is_in_scope_auction(sec_type: str, term: str) -> bool:
    if sec_type == "TIPS":
        return True
    if sec_type in ("Note", "Bond"):
        return term in _NOTE_BOND_TERMS
    return False


def _fetch_treasury_upcoming(end: date) -> list[dict]:
    today = date.today()
    try:
        resp = requests.get(_TD_ANNOUNCED_URL, params={"format": "json"}, timeout=15)
        resp.raise_for_status()
        securities = resp.json()
        if not isinstance(securities, list):
            return []
    except Exception:
        return []

    events: list[dict] = []
    for sec in securities:
        sec_type = sec.get("type") or sec.get("securityType", "")
        term = sec.get("term") or sec.get("securityTerm", "")
        auction_date = sec.get("auctionDate", "")
        if not (auction_date and sec_type and term):
            continue
        try:
            d = date.fromisoformat(auction_date[:10])
        except ValueError:
            continue
        if not (today <= d <= end):
            continue
        if not _is_in_scope_auction(sec_type, term):
            continue
        events.append({
            "date": d.isoformat(),
            "label": f"{term} {sec_type} Auction",
            "type": "auction",
        })
    return events


def fetch_upcoming_events(env: dict, days: int = 14) -> list[dict]:
    """
    Return upcoming macro events for the next `days` calendar days.
    Each event: {"date": "YYYY-MM-DD", "label": str, "type": "economic"|"fomc"|"auction"}
    Results are cached for CACHE_HOURS (default 12h).
    """
    cache_hours = float(env.get("CACHE_HOURS", 12))
    today = date.today()
    end = today + timedelta(days=days)

    if _cache_valid(cache_hours):
        cached = _read_cache()
        today_str, end_str = today.isoformat(), end.isoformat()
        return [e for e in cached if today_str <= e["date"] <= end_str]

    # Fetch with a 30-day window so the cache is useful for subsequent runs
    fetch_end = today + timedelta(days=30)
    api_key = env.get("FRED_API_KEY", "")

    events: list[dict] = []
    events.extend(_fetch_fred_releases(api_key, fetch_end))
    events.extend(_fetch_treasury_upcoming(fetch_end))
    events.extend(_fomc_events(fetch_end))
    events.extend(_ism_dates(fetch_end))
    events.sort(key=lambda e: e["date"])

    _write_cache(events)

    today_str, end_str = today.isoformat(), end.isoformat()
    return [e for e in events if today_str <= e["date"] <= end_str]
