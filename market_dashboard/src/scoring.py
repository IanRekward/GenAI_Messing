"""
Composite scoring: orchestrates data fetching, indicator calculations, and bucket weighting.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

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


def _handler_cnn_fear_greed(key: str, cfg: dict, env: dict, manual: dict, years: int):
    try:
        s = fetch.fetch_cnn_fear_greed(env)
        return float(s.iloc[-1]), s
    except StaleCacheFallback:
        raise
    except Exception as cnn_exc:
        try:
            s = fetch.fetch_fred_series("UMCSENT", env, years)
            return float(s.iloc[-1]), s
        except Exception:
            raise cnn_exc


def _handler_sofr_spread(key: str, cfg: dict, env: dict, manual: dict, years: int):
    sofr = fetch.fetch_fred_series("SOFR", env, years)
    effr = fetch.fetch_fred_series("DFF", env, years)
    combined = pd.concat([sofr.rename("sofr"), effr.rename("effr")], axis=1)
    combined = combined.ffill().dropna()
    spread = (combined["sofr"] - combined["effr"]) * 100  # pct → bps
    return float(spread.iloc[-1]), spread


def _handler_treasury_auction_stress(key: str, cfg: dict, env: dict, manual: dict, years: int):
    r10 = fetch.fetch_treasury_auction_results("Note", "10-Year", env)
    r30 = fetch.fetch_treasury_auction_results("Bond", "30-Year", env)
    raw_val, series = _compute_auction_stress(r10, r30)
    return raw_val, series


def _handler_sector_breadth(key: str, cfg: dict, env: dict, manual: dict, years: int):
    return _compute_sector_breadth(env, years)


def _handler_spx_200dma_distance(key: str, cfg: dict, env: dict, manual: dict, years: int):
    return _compute_spx_200dma_distance(env, years)


def _handler_vix_term_structure(key: str, cfg: dict, env: dict, manual: dict, years: int):
    import yfinance as yf
    vix = yf.download("^VIX", period=f"{years}y", progress=False, auto_adjust=True)
    vix3m = yf.download("^VIX3M", period=f"{years}y", progress=False, auto_adjust=True)

    close_vix = vix["Close"].squeeze()
    close_vix3m = vix3m["Close"].squeeze()

    combined = pd.concat([close_vix.rename("vix"), close_vix3m.rename("vix3m")], axis=1)
    combined = combined.ffill().dropna()
    ratio = combined["vix"] / combined["vix3m"]
    return float(ratio.iloc[-1]), ratio


# Registry of computed handlers — keyed by handler name in weights.yaml source.handler.
# config.py validates against this at startup.
COMPUTED_HANDLERS: dict = {
    "cnn_fear_greed":          _handler_cnn_fear_greed,
    "sofr_spread":             _handler_sofr_spread,
    "treasury_auction_stress": _handler_treasury_auction_stress,
    "sector_breadth":          _handler_sector_breadth,
    "spx_200dma_distance":     _handler_spx_200dma_distance,
    "vix_term_structure":      _handler_vix_term_structure,
}

_TRANSFORMS = {
    "realized_vol_series": ind.realized_vol_series,
    "yoy_series":          ind.yoy_series,
}


def _fetch_indicator(key: str, cfg: dict, env: dict, manual: dict) -> tuple[float, pd.Series | None]:
    """
    Return (current_raw_value, history_series) for one indicator.
    Dispatches based on cfg["source"]["type"] from weights.yaml.
    history_series may be None for manual indicators.
    """
    from src.config import ConfigError
    years = int(env.get("HISTORY_YEARS", 10))
    src = cfg.get("source", {})
    stype = src.get("type")

    if stype == "manual" or cfg.get("manual"):
        return float(manual.get(key, 0)), None

    if stype == "computed":
        handler_name = src.get("handler", key)
        handler = COMPUTED_HANDLERS.get(handler_name)
        if handler is None:
            raise ConfigError(f"No computed handler registered for '{handler_name}'")
        return handler(key, cfg, env, manual, years)

    if stype == "yfinance":
        ticker = src["ticker"]
        s = fetch.fetch_yfinance_series(ticker, env, years)
        transform = src.get("transform")
        if transform:
            s = _TRANSFORMS[transform](s)
        return float(s.iloc[-1]), s

    if stype == "fred":
        series_id = src["series_id"]
        s = fetch.fetch_fred_series(series_id, env, years)
        scale = float(cfg.get("scale", 1.0))
        if scale != 1.0:
            s = s * scale
        transform = src.get("transform")
        if transform:
            s = _TRANSFORMS[transform](s)
        return float(s.iloc[-1]), s

    # Fallback for old-format configs without source field (should not occur post-Brief 1)
    raise ConfigError(
        f"Indicator '{key}' has no valid source type (got '{stype}'). "
        f"Add a source: field to config/weights.yaml."
    )


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


_SECTOR_ETFS = [
    "XLY", "XLC", "XLK", "XLE", "XLV",
    "XLI", "XLF", "XLB", "XLRE", "XLU", "XLP",
]


def _compute_sector_breadth(env: dict, years: int) -> tuple[float, pd.Series]:
    """
    Percentage of S&P 500 sector ETFs trading below their 200-day MA.
    0% = all above MA (calm); 100% = all below MA (market-wide downtrend).
    Raises RuntimeError if fewer than 5 sectors are available.
    """
    sector_data: dict[str, pd.Series] = {}
    for ticker in _SECTOR_ETFS:
        try:
            sector_data[ticker] = fetch.fetch_yfinance_series(ticker, env, years)
        except Exception:
            continue

    if len(sector_data) < 5:
        raise RuntimeError(
            f"sector_breadth: only {len(sector_data)}/{len(_SECTOR_ETFS)} sectors available"
        )

    df = pd.DataFrame(sector_data).dropna(how="all")
    ma200 = df.rolling(200).mean()
    below_ma = (df < ma200).fillna(False)
    n_avail = (~df.isna()).sum(axis=1).clip(lower=1)
    ratio = (below_ma.sum(axis=1) / n_avail * 100).dropna()

    return float(ratio.iloc[-1]), ratio


def _compute_spx_200dma_distance(env: dict, years: int) -> tuple[float, pd.Series]:
    """
    SPX % distance from its 200-day MA. Negative = below MA = stress.
    Uses the already-cached ^GSPC series from sp500_1m_vol.
    """
    s = fetch.fetch_yfinance_series("^GSPC", env, years)
    ma200 = s.rolling(200).mean().dropna()
    s_aligned = s.reindex(ma200.index)
    distance_pct = ((s_aligned - ma200) / ma200 * 100).dropna()
    return float(distance_pct.iloc[-1]), distance_pct


def _band_from_score(score: float) -> str:
    if score >= 70:
        return "red"
    if score >= 50:
        return "orange"
    if score >= 30:
        return "yellow"
    return "green"


def _load_prev_regime() -> str | None:
    """Read the previous VIX regime from alert_state.json for hysteresis."""
    import json
    state_file = Path("data") / "alert_state.json"
    try:
        if state_file.exists():
            with open(state_file) as f:
                return json.load(f).get("regime_previous")
    except Exception:
        pass
    return None


def compute_composite(weights: dict, env: dict, manual: dict) -> dict:
    """
    Fetch all data, score every indicator, aggregate into buckets and composite.
    Returns the full scoring dict (bands are placeholder 'green' until triggers.py runs).
    """
    cadence_cfg = fetch.load_cadence_config()
    bucket_results: dict = {}
    errors: list[str] = []
    stale_indicators: list[str] = []
    _vix_series_for_regime: pd.Series | None = None

    short_years = int(env.get("HISTORY_YEARS_SHORT", 3))
    short_cutoff = pd.Timestamp.now() - pd.DateOffset(years=short_years)

    for bkey, bcfg in weights["buckets"].items():
        bucket_weight = float(bcfg["weight"])
        ind_results: dict = {}
        weighted_sum = 0.0
        weighted_sum_short = 0.0
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
                    "percentile_short": None,
                    "score": score,
                    "score_short": score,
                    "band": "green",
                    "unit": icfg.get("unit", ""),
                    "manual": bool(icfg.get("manual", False)),
                    "invert": invert,
                    "error": str(exc),
                }
                weighted_sum += score * iweight
                weighted_sum_short += score * iweight
                weight_used += iweight
                continue

            if bkey == "equity_volatility" and ikey == "vix" and series is not None:
                _vix_series_for_regime = series

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

            # Short-window (regime-aware) percentile
            pct_short = pct  # fall back to 10yr if insufficient short-window data
            if series is not None and not series.empty and isinstance(series.index, pd.DatetimeIndex):
                s_short = series.loc[series.index >= short_cutoff]
                if len(s_short) >= 10:
                    pct_short = ind.compute_percentile(s_short)

            score = ind.percentile_to_score(pct, invert)
            score_short = ind.percentile_to_score(pct_short, invert)

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
                "percentile_short": round(pct_short, 1),
                "score": score,
                "score_short": score_short,
                "band": "green",
                "unit": icfg.get("unit", ""),
                "manual": bool(icfg.get("manual", False)),
                "invert": invert,
                "_series": series_data,
            }

            weighted_sum += score * iweight
            weighted_sum_short += score_short * iweight
            weight_used += iweight

        bucket_score = weighted_sum / weight_used if weight_used > 0 else 50.0
        bucket_score_short = weighted_sum_short / weight_used if weight_used > 0 else 50.0
        bucket_results[bkey] = {
            "label": bcfg["label"],
            "weight": bucket_weight,
            "score": round(bucket_score, 1),
            "score_short": round(bucket_score_short, 1),
            "band": "green",
            "indicators": ind_results,
        }

    total_weight = sum(b["weight"] for b in bucket_results.values())
    composite = (
        sum(b["score"] * b["weight"] for b in bucket_results.values()) / total_weight
        if total_weight > 0
        else 50.0
    )
    composite_short = (
        sum(b["score_short"] * b["weight"] for b in bucket_results.values()) / total_weight
        if total_weight > 0
        else 50.0
    )

    # VIX regime classification (Brief 10A — read-only, no scoring change)
    from src.history import classify_vix_regime
    regime_info: dict = {}
    if _vix_series_for_regime is not None:
        try:
            prev_regime = _load_prev_regime()
            regime_info = classify_vix_regime(_vix_series_for_regime, prev_regime)
        except Exception as exc:
            errors.append(f"vix_regime: {exc}")

    result = {
        "composite": round(composite, 1),
        "composite_band": _band_from_score(composite),
        "composite_short": round(composite_short, 1),
        "composite_short_band": _band_from_score(composite_short),
        "history_years_short": short_years,
        "red_count": 0,
        "orange_count": 0,
        "yellow_count": 0,
        "run_timestamp": datetime.now().isoformat(),
        "buckets": bucket_results,
        "errors": errors,
        "stale_indicators": stale_indicators,
    }
    result.update(regime_info)
    return result
