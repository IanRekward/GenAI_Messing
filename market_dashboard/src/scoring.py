"""
Composite scoring: orchestrates data fetching, indicator calculations, and bucket weighting.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import yaml

from src import fetch, indicators as ind
from src.fetch import StaleCacheFallback


def load_weights(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_thresholds(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _fetch_indicator(key: str, cfg: dict, env: dict, manual: dict) -> tuple[float, pd.Series | None]:
    """
    Return (current_raw_value, history_series) for one indicator.
    history_series may be None for manual indicators or when not computable.
    """
    years = int(env.get("HISTORY_YEARS", 10))

    if key == "cnn_fear_greed":
        try:
            s = fetch.fetch_cnn_fear_greed(env)
            return float(s.iloc[-1]), s
        except StaleCacheFallback:
            raise  # caller scores stale data and logs a warning
        except Exception as cnn_exc:
            # CNN unavailable with no local cache — try FRED UMCSENT as fallback
            try:
                s = fetch.fetch_fred_series("UMCSENT", env, years)
                return float(s.iloc[-1]), s
            except Exception:
                raise cnn_exc  # both failed; caller will default to 50.0

    if cfg.get("manual"):
        return float(manual.get(key, 0)), None

    if key == "vix":
        s = fetch.fetch_yfinance_series("^VIX", env, years)
        return float(s.iloc[-1]), s

    if key == "sp500_1m_vol":
        s = fetch.fetch_yfinance_series("^GSPC", env, years)
        vol_s = ind.realized_vol_series(s)
        return float(vol_s.iloc[-1]), vol_s

    if key == "hy_oas":
        s = fetch.fetch_fred_series("BAMLH0A0HYM2", env, years)
        return float(s.iloc[-1]), s

    if key == "ig_oas":
        s = fetch.fetch_fred_series("BAMLC0A4CBBB", env, years)
        return float(s.iloc[-1]), s

    if key == "yield_curve":
        s = fetch.fetch_fred_series("T10Y2Y", env, years)
        return float(s.iloc[-1]), s

    if key == "ten_year":
        s = fetch.fetch_yfinance_series("^TNX", env, years)
        return float(s.iloc[-1]), s

    if key == "move_index":
        s = fetch.fetch_yfinance_series("^MOVE", env, years)
        return float(s.iloc[-1]), s

    if key == "nfci":
        s = fetch.fetch_fred_series("NFCI", env, years)
        return float(s.iloc[-1]), s

    if key == "stlfsi":
        s = fetch.fetch_fred_series("STLFSI4", env, years)
        return float(s.iloc[-1]), s

    if key == "breakeven_5y":
        s = fetch.fetch_fred_series("T5YIE", env, years)
        return float(s.iloc[-1]), s

    if key == "cpi_yoy":
        s = fetch.fetch_fred_series("CPIAUCSL", env, years)
        yoy_s = ind.yoy_series(s)
        return float(yoy_s.iloc[-1]), yoy_s

    if key == "sofr_spread":
        sofr = fetch.fetch_fred_series("SOFR", env, years)
        effr = fetch.fetch_fred_series("DFF", env, years)
        combined = pd.concat([sofr.rename("sofr"), effr.rename("effr")], axis=1)
        combined = combined.ffill().dropna()
        spread = (combined["sofr"] - combined["effr"]) * 100  # pct → bps
        return float(spread.iloc[-1]), spread

    if key == "wti_crude":
        s = fetch.fetch_yfinance_series("CL=F", env, years)
        return float(s.iloc[-1]), s

    if key == "oil_vol":
        s = fetch.fetch_yfinance_series("CL=F", env, years)
        vol_s = ind.realized_vol_series(s)
        return float(vol_s.iloc[-1]), vol_s

    if key == "jobless_claims":
        s = fetch.fetch_fred_series("IC4WSA", env, years)
        scale = float(cfg.get("scale", 1.0))
        s = s * scale
        return float(s.iloc[-1]), s

    if key == "unemployment":
        s = fetch.fetch_fred_series("UNRATE", env, years)
        return float(s.iloc[-1]), s

    if key == "usd_index":
        s = fetch.fetch_fred_series("DTWEXBGS", env, years)
        return float(s.iloc[-1]), s

    if key == "euro_hy_oas":
        s = fetch.fetch_fred_series("BAMLHE00EHYIOAS", env, years)
        return float(s.iloc[-1]), s

    if key == "em_corp_oas":
        s = fetch.fetch_fred_series("BAMLEMCBPIOAS", env, years)
        return float(s.iloc[-1]), s

    if key == "eem_vol":
        s = fetch.fetch_yfinance_series("EEM", env, years)
        vol_s = ind.realized_vol_series(s)
        return float(vol_s.iloc[-1]), vol_s

    if key == "treasury_auction_stress":
        r10 = fetch.fetch_treasury_auction_results("Note", "10-Year", env)
        r30 = fetch.fetch_treasury_auction_results("Bond", "30-Year", env)
        raw_val, series = _compute_auction_stress(r10, r30)
        return raw_val, series

    raise ValueError(f"Unknown indicator key: {key}")


def _zscore_list(values: list[float]) -> list[float]:
    """Return z-scores for a list of floats; returns zeros if std is near zero."""
    arr = np.array(values, dtype=float)
    mu, sigma = arr.mean(), arr.std()
    if sigma < 1e-10:
        return [0.0] * len(values)
    return list((arr - mu) / sigma)


def _compute_auction_stress(
    r10: list[dict], r30: list[dict]
) -> tuple[float, pd.Series]:
    """
    Build a composite auction stress time series from 10Y Note + 30Y Bond results.

    Stress score per auction = -(0.4*z_b2c + 0.4*z_indirect) + 0.2*z_dealer
    (low bid-to-cover, low indirect bidder, high dealer takedown → high stress)

    Returns (latest_stress_zscore, pd.Series indexed by auction date).
    """

    def _stress_series(results: list[dict]) -> pd.Series:
        if len(results) < fetch._AUCTION_MIN_COUNT:
            return pd.Series(dtype=float)
        dates = pd.to_datetime([r["date"] for r in results])
        z_b2c  = _zscore_list([r["bid_to_cover"]  for r in results])
        z_ind  = _zscore_list([r["indirect_pct"]  for r in results])
        z_dlr  = _zscore_list([r["dealer_pct"]    for r in results])
        stress = [-0.4 * b - 0.4 * i + 0.2 * d
                  for b, i, d in zip(z_b2c, z_ind, z_dlr)]
        return pd.Series(stress, index=dates)

    s10 = _stress_series(r10)
    s30 = _stress_series(r30)

    if s10.empty and s30.empty:
        raise RuntimeError("treasury_auction_stress: insufficient data from TreasuryDirect")

    # Interleave both series; on same date, take mean
    combined = (
        pd.concat([s10, s30])
        .groupby(level=0)
        .mean()
        .sort_index()
    )
    return float(combined.iloc[-1]), combined


def _band_from_score(score: float) -> str:
    if score >= 70:
        return "red"
    if score >= 50:
        return "orange"
    if score >= 30:
        return "yellow"
    return "green"


def compute_composite(weights: dict, env: dict, manual: dict) -> dict:
    """
    Fetch all data, score every indicator, aggregate into buckets and composite.
    Returns the full scoring dict (bands are placeholder 'green' until triggers.py runs).
    """
    cadence_cfg = fetch.load_cadence_config()
    bucket_results: dict = {}
    errors: list[str] = []
    stale_indicators: list[str] = []

    for bkey, bcfg in weights["buckets"].items():
        bucket_weight = float(bcfg["weight"])
        ind_results: dict = {}
        weighted_sum = 0.0
        weight_used = 0.0

        for ikey, icfg in bcfg["indicators"].items():
            iweight = float(icfg["weight"])
            invert = bool(icfg.get("invert", False))

            stale_cache_msg: str | None = None
            try:
                raw, series = _fetch_indicator(ikey, icfg, env, manual)
            except StaleCacheFallback as stale:
                raw, series = float(stale.series.iloc[-1]), stale.series
                stale_cache_msg = f"STALE CACHE: {ikey} — {stale}"
                errors.append(stale_cache_msg)
            except Exception as exc:
                errors.append(f"{ikey}: {exc}")
                score = 50.0
                ind_results[ikey] = {
                    "label": icfg["label"],
                    "raw": None,
                    "zscore": None,
                    "percentile": None,
                    "score": score,
                    "band": "green",
                    "unit": icfg.get("unit", ""),
                    "manual": bool(icfg.get("manual", False)),
                    "invert": invert,
                    "error": str(exc),
                }
                weighted_sum += score * iweight
                weight_used += iweight
                continue

            # Success path (live or stale-cache fallback)
            if not stale_cache_msg:
                staleness_warning = fetch.check_series_staleness(ikey, series, cadence_cfg)
                if staleness_warning:
                    errors.append(staleness_warning)
                    stale_indicators.append(ikey)

            if series is not None and len(series) >= 10:
                pct = ind.compute_percentile(series)
                zscore = ind.compute_zscore(series)
            else:
                pct = 50.0
                zscore = 0.0

            score = ind.percentile_to_score(pct, invert)
            series_data = None
            if series is not None and not series.empty and isinstance(series.index, pd.DatetimeIndex):
                series_data = {
                    "dates": [d.strftime("%Y-%m-%d") for d in series.index],
                    "values": [float(v) for v in series.values],
                }
            ind_results[ikey] = {
                "label": icfg["label"],
                "raw": round(raw, 4) if raw == raw else None,  # nan check
                "zscore": round(zscore, 2),
                "percentile": round(pct, 1),
                "score": score,
                "band": "green",
                "unit": icfg.get("unit", ""),
                "manual": bool(icfg.get("manual", False)),
                "invert": invert,
                "_series": series_data,
            }

            weighted_sum += score * iweight
            weight_used += iweight

        bucket_score = weighted_sum / weight_used if weight_used > 0 else 50.0
        bucket_results[bkey] = {
            "label": bcfg["label"],
            "weight": bucket_weight,
            "score": round(bucket_score, 1),
            "band": "green",
            "indicators": ind_results,
        }

    total_weight = sum(b["weight"] for b in bucket_results.values())
    composite = (
        sum(b["score"] * b["weight"] for b in bucket_results.values()) / total_weight
        if total_weight > 0
        else 50.0
    )

    return {
        "composite": round(composite, 1),
        "composite_band": _band_from_score(composite),
        "red_count": 0,
        "orange_count": 0,
        "yellow_count": 0,
        "run_timestamp": datetime.now().isoformat(),
        "buckets": bucket_results,
        "errors": errors,
        "stale_indicators": stale_indicators,
    }
