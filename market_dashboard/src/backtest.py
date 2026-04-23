"""
Point-in-time backtesting engine.

At each date T, the composite score is computed using only data from the
10-year window [T - 10yr, T].  No lookahead bias.

Two standard runs (see BACKTEST_DESIGN.md §11 Q5):
  Full model   : 2018-01-01 → today (all indicators including SOFR + global spillover)
  Subset model : 2000-01-01 → 2017-12-31 (pre-SOFR indicators only)

Output DataFrames are saved to output/backtest_full.csv and output/backtest_subset.csv.
"""
from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import yaml

from src import indicators as ind
from src import fetch as _live_fetch

# ---------------------------------------------------------------------------
# Backtest-specific cache
# Separate from the live cache so 26-year fetches don't overwrite live 10-year data.
# Cache TTL for backtest data: 7 days (historical data doesn't change often).
# ---------------------------------------------------------------------------

_BT_CACHE_DIR = Path("data/cache/backtest")
_BT_CACHE_TTL_HOURS = 168   # 7 days


def _bt_cache_path(kind: str, key: str) -> Path:
    _BT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _BT_CACHE_DIR / f"{kind}_{key}_{FETCH_YEARS}y.json"


def _bt_cache_valid(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _BT_CACHE_TTL_HOURS * 3600


def _bt_read_cache(path: Path) -> pd.Series:
    with open(path) as f:
        d = json.load(f)
    return pd.Series(d["values"], index=pd.to_datetime(d["dates"]))


def _bt_write_cache(path: Path, series: pd.Series) -> None:
    with open(path, "w") as f:
        json.dump(
            {
                "dates": [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [float(v) for v in series.values],
            },
            f,
        )


def _bt_fred(series_id: str, env: dict) -> pd.Series:
    cpath = _bt_cache_path("fred", series_id)
    if _bt_cache_valid(cpath):
        return _bt_read_cache(cpath)

    api_key = env.get("FRED_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("FRED_API_KEY not configured in .env")

    from datetime import datetime, timedelta
    start = (datetime.today() - timedelta(days=FETCH_YEARS * 365 + 60)).strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
        "limit": 10000,
    }
    resp = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=30)
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
    _bt_write_cache(cpath, series)
    return series


def _bt_yf(ticker: str, env: dict) -> pd.Series:
    safe = ticker.replace("^", "X").replace("=", "_")
    cpath = _bt_cache_path("yf", safe)
    if _bt_cache_valid(cpath):
        return _bt_read_cache(cpath)

    from datetime import datetime, timedelta
    start = (datetime.today() - timedelta(days=FETCH_YEARS * 365 + 60)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"Yahoo Finance returned no data for {ticker}")
    series = df["Close"].squeeze().dropna()
    series.index = pd.to_datetime(series.index)
    _bt_write_cache(cpath, series)
    return series


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_YEARS = 10
FETCH_YEARS = 26        # fetch enough history so the earliest backtest dates have a full window

FULL_START   = "2018-01-01"
SUBSET_START = "2000-01-01"
SUBSET_END   = "2017-12-31"

# Earliest date each derived series becomes usable (need enough prior data for vol/YoY windows)
_AVAIL: dict[str, str] = {
    "sofr_spread": "2018-04-03",    # SOFR launched April 2018
    "eem_vol":     "2004-04-01",    # EEM listed 2003; need 1yr price history for 21-day rolling vol
    "usd_index":   "2006-01-04",    # FRED DTWEXBGS starts Jan 2006
    "euro_hy_oas": "1998-01-02",    # ICE BofA Euro HY OAS from 1997/98
    "em_corp_oas": "1998-01-02",    # ICE BofA EM Corp OAS from 1997/98
    "breakeven_5y":"2003-01-03",    # T5YIE starts Jan 2003
}

# Manual indicators: always 0 in historical backtest (no historical series)
_MANUAL = {"repo_stress", "aaii_bull_bear", "iran_trigger"}

# Map from indicator key → derived series key in the fetched dict
_IND_TO_SERIES: dict[str, str] = {
    "vix":          "vix_price",
    "sp500_1m_vol": "sp500_1m_vol",
    "hy_oas":       "hy_oas",
    "ig_oas":       "ig_oas",
    "yield_curve":  "yield_curve",
    "ten_year":     "tnx_price",
    "nfci":         "nfci",
    "stlfsi":       "stlfsi",
    "breakeven_5y": "breakeven_5y",
    "cpi_yoy":      "cpi_yoy",
    "sofr_spread":  "sofr_spread",
    "wti_crude":    "wti_price",
    "oil_vol":      "oil_vol",
    "jobless_claims": "jobless_claims",
    "unemployment": "unemployment",
    "usd_index":    "usd_index",
    "euro_hy_oas":  "euro_hy_oas",
    "em_corp_oas":  "em_corp_oas",
    "eem_vol":      "eem_vol",
}


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_raw(env: dict) -> dict[str, pd.Series]:
    """
    Fetch all base-level raw series using the backtest cache (26-year horizon,
    separate from the 10-year live cache).
    """
    out: dict[str, pd.Series] = {}

    def _fred(key: str, series_id: str) -> None:
        try:
            out[key] = _bt_fred(series_id, env)
        except Exception as exc:
            warnings.warn(f"backtest: could not fetch {key} ({series_id}): {exc}")

    def _yf(key: str, ticker: str) -> None:
        try:
            out[key] = _bt_yf(ticker, env)
        except Exception as exc:
            warnings.warn(f"backtest: could not fetch {key} ({ticker}): {exc}")

    # Note: ICE BofA series on FRED (BAML*) are subject to licensing restrictions.
    # The FRED API may return only ~3 years of history for these series regardless
    # of the requested observation_start.  The backtest engine handles this gracefully
    # by skipping unavailable indicators and re-normalising bucket weights.
    _yf("vix_price",       "^VIX")
    _yf("sp500_price",     "^GSPC")
    _fred("hy_oas",        "BAMLH0A0HYM2")
    _fred("ig_oas",        "BAMLC0A4CBBB")
    _fred("yield_curve",   "T10Y2Y")
    _yf("tnx_price",       "^TNX")
    _fred("nfci",          "NFCI")
    _fred("stlfsi",        "STLFSI4")
    _fred("breakeven_5y",  "T5YIE")
    _fred("cpi",           "CPIAUCSL")
    _fred("sofr",          "SOFR")
    _fred("effr",          "DFF")
    _yf("wti_price",       "CL=F")
    _fred("jobless_claims","IC4WSA")
    _fred("unemployment",  "UNRATE")
    _fred("usd_index",     "DTWEXBGS")
    _fred("euro_hy_oas",   "BAMLHE00EHYIOAS")
    _fred("em_corp_oas",   "BAMLEMCBPIOAS")
    _yf("eem_price",       "EEM")

    return out


def _build_derived(raw: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """
    Build derived series (realized vol, YoY pct change, SOFR spread) from raw.
    These are computed over the full history so the inner 10-year slice sees
    correctly-derived values without repeating the derivation at every date.
    """
    d = dict(raw)

    if "sp500_price" in raw:
        d["sp500_1m_vol"] = ind.realized_vol_series(raw["sp500_price"])

    if "wti_price" in raw:
        d["oil_vol"] = ind.realized_vol_series(raw["wti_price"])

    if "eem_price" in raw:
        d["eem_vol"] = ind.realized_vol_series(raw["eem_price"])

    if "cpi" in raw:
        d["cpi_yoy"] = ind.yoy_series(raw["cpi"])

    if "sofr" in raw and "effr" in raw:
        combined = pd.concat([raw["sofr"].rename("sofr"), raw["effr"].rename("effr")], axis=1)
        combined = combined.ffill().dropna()
        d["sofr_spread"] = (combined["sofr"] - combined["effr"]) * 100

    # vix_price is already the VIX level; no derivation needed
    d["vix_price"] = raw.get("vix_price", pd.Series(dtype=float))

    return d


# ---------------------------------------------------------------------------
# Point-in-time scoring helpers
# ---------------------------------------------------------------------------

def point_in_time_percentile(series: pd.Series) -> float:
    """Percentile rank (0–100) of the last value using only that series slice."""
    if len(series) < 10:
        return 50.0
    current = series.iloc[-1]
    return float((series < current).mean() * 100)


def point_in_time_zscore(series: pd.Series) -> float:
    """Z-score of the last value in the series slice."""
    if len(series) < 10:
        return 0.0
    std = series.std()
    if std == 0:
        return 0.0
    return float((series.iloc[-1] - series.mean()) / std)


def _indicator_pit(
    ikey: str,
    icfg: dict,
    derived: dict[str, pd.Series],
    date: pd.Timestamp,
    window_start: pd.Timestamp,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Return (raw_value, percentile, zscore) for one indicator at date T.
    Returns (None, None, None) when the indicator is unavailable at T.
    """
    if icfg.get("manual") or ikey in _MANUAL:
        # Manual indicators are always calm (0) in historical backtest
        return 0.0, 50.0, 0.0

    avail = _AVAIL.get(ikey)
    if avail and date < pd.Timestamp(avail):
        return None, None, None

    skey = _IND_TO_SERIES.get(ikey)
    if skey is None or skey not in derived:
        return None, None, None

    full_s = derived[skey]
    if full_s is None or len(full_s) == 0:
        return None, None, None

    # Slice to point-in-time window [T-10yr, T]
    slice_s = full_s.loc[window_start:date].dropna()
    if len(slice_s) < 10:
        return None, None, None

    raw = float(slice_s.iloc[-1])
    scale = float(icfg.get("scale", 1.0))
    if scale != 1.0:
        raw = raw * scale
        slice_s = slice_s * scale

    pct = point_in_time_percentile(slice_s)
    zscore = point_in_time_zscore(slice_s)

    return raw, pct, zscore


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_backtest(
    weights: dict,
    env: dict,
    start_date: str,
    end_date: str,
    freq: str = "B",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Compute the composite stress score at every date in [start_date, end_date].

    Parameters
    ----------
    weights   : loaded weights.yaml dict
    env       : environment dict (API keys, settings)
    start_date: ISO date string "YYYY-MM-DD"
    end_date  : ISO date string "YYYY-MM-DD"
    freq      : pandas date frequency (default "B" = business daily)
    verbose   : print progress

    Returns
    -------
    pd.DataFrame indexed by date with columns:
        composite, bucket_<name> (one per bucket),
        <bucket>__<indicator>__raw / __pct / __score
    """
    if verbose:
        print(f"  Fetching all raw series (this may use cache)...")

    raw = _fetch_raw(env)
    derived = _build_derived(raw)

    dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    records = []

    if verbose:
        print(f"  Running point-in-time scoring over {len(dates)} dates ({start_date} to {end_date})...")

    for i, date in enumerate(dates):
        if verbose and i % 500 == 0 and i > 0:
            print(f"    {i}/{len(dates)} ({date.date()})")

        window_start = date - pd.DateOffset(years=WINDOW_YEARS)
        row: dict = {"date": date}

        bucket_wsum = 0.0
        bucket_wused = 0.0

        for bkey, bcfg in weights["buckets"].items():
            b_weight = float(bcfg["weight"])
            ind_wsum = 0.0
            ind_wused = 0.0

            for ikey, icfg in bcfg["indicators"].items():
                i_weight = float(icfg["weight"])
                invert   = bool(icfg.get("invert", False))

                raw_val, pct, zscore = _indicator_pit(ikey, icfg, derived, date, window_start)

                if pct is None:
                    continue

                score = ind.percentile_to_score(pct, invert)
                row[f"{bkey}__{ikey}__raw"]   = round(raw_val, 4)
                row[f"{bkey}__{ikey}__pct"]   = round(pct, 1)
                row[f"{bkey}__{ikey}__score"] = round(score, 1)

                ind_wsum  += score * i_weight
                ind_wused += i_weight

            if ind_wused > 0:
                b_score = ind_wsum / ind_wused
                row[f"bucket_{bkey}"] = round(b_score, 1)
                bucket_wsum  += b_score * b_weight
                bucket_wused += b_weight
            else:
                row[f"bucket_{bkey}"] = np.nan

        composite = round(bucket_wsum / bucket_wused, 1) if bucket_wused > 0 else np.nan
        row["composite"] = composite
        records.append(row)

    df = pd.DataFrame(records).set_index("date")
    return df


# ---------------------------------------------------------------------------
# Entry point: run both standard backtests
# ---------------------------------------------------------------------------

def run_standard_backtests(weights: dict, env: dict, output_dir: str = "output") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the full-model (2018+) and subset-model (2000–2017) backtests and
    save results to output/backtest_full.csv and output/backtest_subset.csv.

    Returns (df_full, df_subset).
    """
    Path(output_dir).mkdir(exist_ok=True)

    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    print("=== Backtest Phase 1: Full model (2018 → present) ===")
    df_full = run_backtest(weights, env, FULL_START, today, freq="B")
    full_path = os.path.join(output_dir, "backtest_full.csv")
    df_full.to_csv(full_path)
    print(f"  Saved {len(df_full)} rows → {full_path}")

    print("=== Backtest Phase 1: Subset model (2000 → 2017) ===")
    df_subset = run_backtest(weights, env, SUBSET_START, SUBSET_END, freq="B")
    subset_path = os.path.join(output_dir, "backtest_subset.csv")
    df_subset.to_csv(subset_path)
    print(f"  Saved {len(df_subset)} rows → {subset_path}")

    return df_full, df_subset


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")

    from dotenv import load_dotenv

    load_dotenv()
    _env = dict(os.environ)

    _weights = yaml.safe_load(open("config/weights.yaml"))
    run_standard_backtests(_weights, _env)
