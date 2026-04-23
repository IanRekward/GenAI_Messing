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
import yaml
import yfinance as yf

DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
MANUAL_FILE = DATA_DIR / "manual_overrides.json"

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

_RETRY_DELAYS = [1, 4, 16]  # seconds between attempts 1→2, 2→3, 3→4


class StaleCacheFallback(RuntimeError):
    """Raised when live fetch failed on all retries but stale cache is available."""

    def __init__(self, series: "pd.Series", source_id: str, original_error: str):
        self.series = series
        super().__init__(
            f"live fetch failed ({original_error}); using stale cache for {source_id}"
        )


def _retry_get(url: str, params: dict, timeout: int) -> "requests.Response":
    """GET with exponential backoff: up to 4 attempts (1s / 4s / 16s delays)."""
    last_exc: Exception | None = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
    raise last_exc  # type: ignore[misc]

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
    try:
        resp = _retry_get(FRED_BASE, params, timeout=20)
    except Exception as exc:
        if cpath.exists():
            raise StaleCacheFallback(_read_cache(cpath), series_id, str(exc))
        raise

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


def load_cadence_config(path: str = "config/series_cadence.yaml") -> dict:
    """Load per-indicator staleness thresholds. Returns empty dict if file missing."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def check_series_staleness(key: str, series: pd.Series | None, cadence_cfg: dict) -> str | None:
    """
    Returns a warning string if the series' last observation is older than the
    configured max gap for its cadence, else None. Skips keys not in the config.
    """
    if series is None or series.empty:
        return None
    indicator_cadences = cadence_cfg.get("indicators", {})
    cadence = indicator_cadences.get(key)
    if cadence is None:
        return None
    max_gap = cadence_cfg.get("thresholds", {}).get(cadence)
    if max_gap is None:
        return None
    last_date = pd.to_datetime(series.index[-1]).normalize()
    today = pd.Timestamp.today().normalize()
    gap_days = (today - last_date).days
    if gap_days > max_gap:
        return (
            f"STALE: {key} — last observation {gap_days}d ago "
            f"(expected ≤{max_gap}d for {cadence} series)"
        )
    return None


def fetch_yfinance_series(ticker: str, env: dict, years: int = 10) -> pd.Series:
    """Return a pandas Series of daily close prices from Yahoo Finance."""
    cache_hours = float(env.get("CACHE_HOURS", 12))
    safe = ticker.replace("^", "X").replace("=", "_")
    cpath = _cache_path(f"yf_{safe}")
    if _cache_valid(cpath, cache_hours):
        return _read_cache(cpath)

    start = (datetime.today() - timedelta(days=years * 365 + 60)).strftime("%Y-%m-%d")
    last_exc: Exception | None = None
    raw_df = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            raw_df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
            if not raw_df.empty:
                break
            raise RuntimeError(f"Yahoo Finance returned empty data for {ticker}")
        except Exception as exc:
            last_exc = exc
            raw_df = None
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])

    if raw_df is None or raw_df.empty:
        exc_msg = str(last_exc) if last_exc else f"no data for {ticker}"
        if cpath.exists():
            raise StaleCacheFallback(_read_cache(cpath), ticker, exc_msg)
        raise last_exc or RuntimeError(f"Yahoo Finance returned no data for {ticker}")

    series = raw_df["Close"].squeeze().dropna()
    series.index = pd.to_datetime(series.index)
    _write_cache(cpath, series)
    return series
