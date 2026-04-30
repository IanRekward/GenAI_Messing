"""
Statistical transformations: z-score, percentile rank, realized volatility, YoY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_zscore(series: pd.Series) -> float:
    if len(series) < 10:
        return 0.0
    std = series.std()
    if std == 0:
        return 0.0
    return float((series.iloc[-1] - series.mean()) / std)


def compute_percentile(series: pd.Series) -> float:
    """Percentile rank (0–100) of the latest value vs the full series."""
    if len(series) < 10:
        return 50.0
    current = series.iloc[-1]
    return round(float((series < current).mean() * 100), 1)


def percentile_to_score(percentile: float, invert: bool = False) -> float:
    """Map a percentile rank to a 0–100 stress score."""
    score = 100.0 - percentile if invert else percentile
    return round(score, 1)


def realized_vol_series(price_series: pd.Series, window: int = 21) -> pd.Series:
    """Rolling annualized realized volatility (%) from log returns."""
    log_rets = np.log(price_series / price_series.shift(1))
    return (log_rets.rolling(window).std() * np.sqrt(252) * 100).dropna()


def yoy_series(level_series: pd.Series) -> pd.Series:
    """Year-over-year % change, using pandas 12-period pct_change on a monthly series."""
    return (level_series.pct_change(12) * 100).dropna()


BAND_THRESHOLDS: dict[str, int] = {"yellow": 30, "orange": 50, "red": 70}


def band_from_score(score: float) -> str:
    """Map a 0–100 stress score to a band label (green/yellow/orange/red)."""
    if score >= 70:
        return "red"
    if score >= 50:
        return "orange"
    if score >= 30:
        return "yellow"
    return "green"
