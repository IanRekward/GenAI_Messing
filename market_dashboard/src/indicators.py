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


def median_deviation_series(s: pd.Series, window: int = 756, min_periods: int = 252) -> pd.Series:
    """Deviation from the trailing ~3-year rolling median (point-in-time).

    The cure for structural-level-shift indicators (crack spread, copper/gold,
    EM vol): a regime change washes out of the median within the window, so
    only genuine dislocations vs the indicator's own recent norm fire —
    absolute-level thresholds stayed pinned red for months (D2, 2026-09-02).
    """
    eff_min = min(min_periods, max(5, len(s) // 2))
    return (s - s.rolling(window, min_periods=eff_min).median()).dropna()


def realized_vol_series(price_series: pd.Series, window: int = 21) -> pd.Series:
    """Rolling annualized realized volatility (%) from log returns."""
    log_rets = np.log(price_series / price_series.shift(1))
    return (log_rets.rolling(window).std() * np.sqrt(252) * 100).dropna()


def yoy_series(level_series: pd.Series) -> pd.Series:
    """Year-over-year % change, using pandas 12-period pct_change on a monthly series."""
    return (level_series.pct_change(12) * 100).dropna()


BAND_THRESHOLDS: dict[str, int] = {"yellow": 30, "orange": 50, "red": 70}
BAND_ORDER: dict[str, int] = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

BAND_COLOR = {"green": "#22cc44", "yellow": "#ffcc00", "orange": "#ff8800", "red": "#ff4444"}
BAND_BG = {"green": "#0d2e14", "yellow": "#2e2800", "orange": "#2e1600", "red": "#2e0d0d"}


# Composite score-band cutoffs, calibrated to base-rate ceilings on the 8.7y
# backtest distribution (D2, 2026-09-02): yellow+ fires 32.8%, orange+ 17.3%,
# red 6.4% of days. Episodes: 2022 peak 78 / SVB 73 = red; COVID peak 71 =
# orange, escalated to red by the breadth rule; Aug-2024 spike 68 = orange.
# The founding 30/50/70 were never derived; the composite's structural floor
# (~36) made green unreachable and yellow permanent.
COMPOSITE_CUTOFFS = {"yellow": 57.0, "orange": 65.0, "red": 72.0}


def band_from_score(score: float) -> str:
    """Map a 0–100 composite stress score to a band label."""
    if score >= COMPOSITE_CUTOFFS["red"]:
        return "red"
    if score >= COMPOSITE_CUTOFFS["orange"]:
        return "orange"
    if score >= COMPOSITE_CUTOFFS["yellow"]:
        return "yellow"
    return "green"
