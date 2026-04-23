"""
Data fetching: FRED, Yahoo Finance, and manual overrides.
All series are cached locally in data/cache/ as JSON.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
MANUAL_FILE = DATA_DIR / "manual_overrides.json"

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

MANUAL_DEFAULTS: dict = {
    "repo_stress": 0,       # 0=calm 1=elevated 2=crisis 3=extreme
    "aaii_bull_bear": 10.0, # % bulls minus % bears; update weekly from aaii.com
    "iran_trigger": 0,      # 0=calm 1=elevated 2=crisis
}


def load_manual_overrides() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MANUAL_FILE.exists():
        with open(MANUAL_FILE, "w") as f:
            json.dump(MANUAL_DEFAULTS, f, indent=2)
        return dict(MANUAL_DEFAULTS)
    with open(MANUAL_FILE) as f:
        saved = json.load(f)
    result = dict(MANUAL_DEFAULTS)
    result.update(saved)
    return result


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _cache_valid(path: Path, cache_hours: float) -> bool:
    if cache_hours <= 0 or not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < cache_hours * 3600


def _read_cache(path: Path) -> pd.Series:
    with open(path) as f:
        d = json.load(f)
    return pd.Series(d["values"], index=pd.to_datetime(d["dates"]))


def _write_cache(path: Path, series: pd.Series) -> None:
    with open(path, "w") as f:
        json.dump(
            {
                "dates": [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [float(v) for v in series.values],
            },
            f,
        )


def fetch_fred_series(series_id: str, env: dict, years: int = 10) -> pd.Series:
    """Return a pandas Series of FRED observations indexed by date."""
    cache_hours = float(env.get("CACHE_HOURS", 12))
    cpath = _cache_path(f"fred_{series_id}")
    if _cache_valid(cpath, cache_hours):
        return _read_cache(cpath)

    api_key = env.get("FRED_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("FRED_API_KEY not configured in .env")

    start = (datetime.today() - timedelta(days=years * 365 + 60)).strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
        "limit": 10000,
    }
    resp = requests.get(FRED_BASE, params=params, timeout=20)
    resp.raise_for_status()

    obs = resp.json().get("observations", [])
    dates, values = [], []
    for o in obs:
        if o["value"] != ".":
            dates.append(o["date"])
            values.append(float(o["value"]))

    if not dates:
        raise RuntimeError(f"FRED returned no data for {series_id}")

    series = pd.Series(values, index=pd.to_datetime(dates))
    _write_cache(cpath, series)
    return series


def fetch_yfinance_series(ticker: str, env: dict, years: int = 10) -> pd.Series:
    """Return a pandas Series of daily close prices from Yahoo Finance."""
    cache_hours = float(env.get("CACHE_HOURS", 12))
    safe = ticker.replace("^", "X").replace("=", "_")
    cpath = _cache_path(f"yf_{safe}")
    if _cache_valid(cpath, cache_hours):
        return _read_cache(cpath)

    start = (datetime.today() - timedelta(days=years * 365 + 60)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"Yahoo Finance returned no data for {ticker}")

    series = df["Close"].squeeze().dropna()
    series.index = pd.to_datetime(series.index)
    _write_cache(cpath, series)
    return series
