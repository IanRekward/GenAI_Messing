"""
Evaluation module — computes all performance metrics for the backtest.

Takes:
  - signal_df  : output of backtest.run_backtest() — indexed by date, has 'composite' column
  - target_df  : forward outcome series (SPX drawdown, HY widening, etc.)

Returns a nested dict of metrics covering:
  - Spearman IC + Pearson (continuous → continuous)
  - ROC-AUC, PR-AUC (continuous → binary event)
  - Precision, Recall, F1, F0.5 (band → binary event)
  - EW-IC with 5-yr half-life + equal-weighted
  - Block bootstrap 95% CIs on all correlations
  - Regime stratification (VIX terciles)
  - Per-year IC stability
  - Benchmark comparisons: VIX alone, HY OAS alone, NFCI, yield curve, 3-factor

See BACKTEST_DESIGN.md §4 for the statistical approach.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    fbeta_score,
)


# ---------------------------------------------------------------------------
# Target construction
# ---------------------------------------------------------------------------

def build_forward_drawdown(spx: pd.Series, horizon_days: int) -> pd.Series:
    """
    For each date T, compute the maximum drawdown of SPX over the next
    horizon_days calendar days.

    Returns a Series indexed like spx with values in [0, 1] (positive = loss).
    """
    results = {}
    for i in range(len(spx)):
        t = spx.index[i]
        end_date = t + pd.Timedelta(days=horizon_days)
        window = spx.loc[t:end_date]
        if len(window) < 2:
            results[t] = np.nan
            continue
        peak = window.iloc[0]
        trough = window.min()
        results[t] = float((peak - trough) / peak) if peak > 0 else np.nan
    return pd.Series(results)


def build_forward_hy_widening(hy_oas: pd.Series, horizon_days: int) -> pd.Series:
    """
    For each date T, compute HY OAS change (end - start) over next horizon_days.
    Positive = widening = stress.
    """
    results = {}
    for i in range(len(hy_oas)):
        t = hy_oas.index[i]
        end_date = t + pd.Timedelta(days=horizon_days)
        future = hy_oas.loc[t:end_date]
        if len(future) < 2:
            results[t] = np.nan
            continue
        results[t] = float(future.iloc[-1] - future.iloc[0])
    return pd.Series(results)


def build_stress_index(vix: pd.Series, hy_oas: pd.Series, nfci: pd.Series,
                       horizon_days: int) -> pd.Series:
    """
    Multi-asset realized stress index: equal-weighted z-score of forward average
    of (VIX, HY OAS, NFCI), each standardised over the full series.
    """
    def _forward_mean(s: pd.Series, h: int) -> pd.Series:
        out = {}
        for t in s.index:
            future = s.loc[t: t + pd.Timedelta(days=h)]
            out[t] = float(future.mean()) if len(future) > 0 else np.nan
        return pd.Series(out)

    vix_fwd  = _forward_mean(vix,    horizon_days)
    hy_fwd   = _forward_mean(hy_oas, horizon_days)
    nfci_fwd = _forward_mean(nfci,   horizon_days)

    def _zscore(s: pd.Series) -> pd.Series:
        return (s - s.mean()) / s.std()

    combined = pd.concat([_zscore(vix_fwd), _zscore(hy_fwd), _zscore(nfci_fwd)], axis=1)
    return combined.mean(axis=1)


def build_binary_events(spx: pd.Series, hy_oas: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Build binary event columns:
      major_drawdown  : SPX max drawdown > 10% in next 90 days
      moderate_drawdown: SPX max drawdown > 5% in next 30 days
      credit_stress   : HY OAS widens > 150 bps in next 60 days (if hy_oas provided)
    """
    cols: dict = {}
    dd90 = build_forward_drawdown(spx, 90)
    dd30 = build_forward_drawdown(spx, 30)
    cols["major_drawdown"]    = (dd90 > 0.10).astype(int)
    cols["moderate_drawdown"] = (dd30 > 0.05).astype(int)
    if hy_oas is not None:
        hy60 = build_forward_hy_widening(hy_oas, 60)
        cols["credit_stress"] = (hy60 > 1.50).astype(int)
    return pd.DataFrame(cols)


# ---------------------------------------------------------------------------
# IC helpers
# ---------------------------------------------------------------------------

def spearman_ic(signal: pd.Series, target: pd.Series) -> float:
    """Spearman rank correlation between signal and target (aligned)."""
    common = signal.dropna().index.intersection(target.dropna().index)
    if len(common) < 10:
        return np.nan
    return float(stats.spearmanr(signal.loc[common], target.loc[common]).statistic)


def pearson_ic(signal: pd.Series, target: pd.Series) -> float:
    common = signal.dropna().index.intersection(target.dropna().index)
    if len(common) < 10:
        return np.nan
    return float(stats.pearsonr(signal.loc[common], target.loc[common]).statistic)


def rolling_composite_ic(
    history: pd.DataFrame,
    spx: pd.Series,
    window_days: int = 252,
    horizon_days: int = 21,
) -> dict:
    """Spearman IC of composite vs forward SPX drawdown over the last window_days of history.

    Returns {"ic": float|None, "n_obs": int, "horizon_days": int, "window_days": int}.
    ic is None when fewer than 30 aligned non-NaN pairs are available.
    """
    df = history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["_date"] = df["timestamp"].dt.normalize()
    df = df.sort_values("timestamp").drop_duplicates(subset="_date", keep="last")
    df = df.set_index("_date")["composite"].rename("composite")

    spx_norm = spx.copy()
    spx_norm.index = pd.to_datetime(spx_norm.index).normalize()
    spx_aligned = spx_norm.reindex(df.index, method="ffill")

    target = build_forward_drawdown(spx_aligned.dropna(), horizon_days)
    target = target.reindex(df.index)

    composite_slice = df.tail(window_days)
    target_slice = target.reindex(composite_slice.index)

    valid = composite_slice.notna() & target_slice.notna()
    composite_valid = composite_slice[valid]
    target_valid = target_slice[valid]

    n_obs = int(valid.sum())
    if n_obs < 30:
        return {"ic": None, "n_obs": n_obs, "horizon_days": horizon_days, "window_days": window_days}

    ic = spearman_ic(composite_valid, target_valid)
    return {"ic": float(ic) if not np.isnan(ic) else None, "n_obs": n_obs,
            "horizon_days": horizon_days, "window_days": window_days}


def ew_ic(signal: pd.Series, target: pd.Series, halflife_days: int = 5 * 252) -> float:
    """
    Exponentially-weighted IC with the given half-life (in days).
    Weights are computed relative to the most recent common observation.
    """
    common = signal.dropna().index.intersection(target.dropna().index)
    if len(common) < 10:
        return np.nan
    sig = signal.loc[common].sort_index()
    tgt = target.loc[common].sort_index()
    # Weight = exp(-lambda * age_in_days), where lambda = ln(2) / halflife
    ages = np.array((sig.index[-1] - sig.index).days, dtype=float)
    lam = np.log(2) / halflife_days
    weights = np.exp(-lam * ages)
    weights /= weights.sum()
    # Weighted rank correlation: convert to weighted percentile ranks then correlate
    sig_ranks = sig.rank(pct=True)
    tgt_ranks = tgt.rank(pct=True)
    sig_dm = sig_ranks - (weights * sig_ranks).sum()
    tgt_dm = tgt_ranks - (weights * tgt_ranks).sum()
    cov  = (weights * sig_dm * tgt_dm).sum()
    var1 = (weights * sig_dm ** 2).sum()
    var2 = (weights * tgt_dm ** 2).sum()
    if var1 == 0 or var2 == 0:
        return np.nan
    return float(cov / np.sqrt(var1 * var2))


# ---------------------------------------------------------------------------
# Block bootstrap
# ---------------------------------------------------------------------------

def block_bootstrap_ci(
    signal: pd.Series,
    target: pd.Series,
    metric_fn,
    block_size: int = 63,   # ~1 quarter of business days
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Block bootstrap confidence interval for any metric_fn(signal, target) -> float.
    Preserves time-series autocorrelation by resampling contiguous blocks.

    Returns (lower_bound, upper_bound).
    """
    rng = np.random.default_rng(seed)
    common = signal.dropna().index.intersection(target.dropna().index)
    if len(common) < block_size * 2:
        return np.nan, np.nan

    sig = signal.loc[common].values
    tgt = target.loc[common].values
    n = len(sig)
    n_blocks = int(np.ceil(n / block_size))

    boot_stats = []
    for _ in range(n_bootstrap):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        s_s = pd.Series(sig[idx])
        s_t = pd.Series(tgt[idx])
        try:
            val = metric_fn(s_s, s_t)
            if not np.isnan(val):
                boot_stats.append(val)
        except Exception:
            pass

    if len(boot_stats) < 10:
        return np.nan, np.nan

    alpha = (1 - ci_level) / 2
    return float(np.quantile(boot_stats, alpha)), float(np.quantile(boot_stats, 1 - alpha))


# ---------------------------------------------------------------------------
# Classifier metrics
# ---------------------------------------------------------------------------

def band_to_numeric(band_series: pd.Series) -> pd.Series:
    """Convert green/yellow/orange/red band to 0/1/2/3 numeric."""
    _map = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
    return band_series.map(_map)


def threshold_signal(composite: pd.Series, threshold: float = 50.0) -> pd.Series:
    """Binary signal: 1 if composite >= threshold, else 0."""
    return (composite >= threshold).astype(int)


def classifier_metrics(
    signal_binary: pd.Series,
    events: pd.Series,
    beta: float = 1.0,
) -> dict:
    """
    Compute precision, recall, F-beta, and confusion matrix.
    signal_binary: 0/1 predicted positives
    events:        0/1 true positives
    beta:          F-score beta (1.0 = F1, 0.5 = F0.5 precision-weighted)
    """
    common = signal_binary.dropna().index.intersection(events.dropna().index)
    if len(common) < 10:
        return {}
    s = signal_binary.loc[common].values.astype(int)
    e = events.loc[common].values.astype(int)
    return {
        "precision": float(precision_score(e, s, zero_division=0)),
        "recall":    float(recall_score(e, s, zero_division=0)),
        f"f{beta:.1f}": float(fbeta_score(e, s, beta=beta, zero_division=0)),
        "base_rate": float(e.mean()),
        "signal_rate": float(s.mean()),
        "n_obs": int(len(common)),
    }


def roc_pr_metrics(composite: pd.Series, events: pd.Series) -> dict:
    """ROC-AUC and PR-AUC for continuous composite signal vs binary events."""
    common = composite.dropna().index.intersection(events.dropna().index)
    if len(common) < 10 or events.loc[common].sum() < 2:
        return {}
    s = composite.loc[common].values
    e = events.loc[common].values.astype(int)
    return {
        "roc_auc": float(roc_auc_score(e, s)),
        "pr_auc":  float(average_precision_score(e, s)),
        "lift_top_decile": _lift_top_decile(s, e),
    }


def _lift_top_decile(signal: np.ndarray, events: np.ndarray) -> float:
    """Crisis rate in top-10% signal vs overall base rate."""
    threshold = np.percentile(signal, 90)
    top_decile = events[signal >= threshold]
    base_rate = events.mean()
    if base_rate == 0:
        return np.nan
    return float(top_decile.mean() / base_rate)


# ---------------------------------------------------------------------------
# Regime stratification
# ---------------------------------------------------------------------------

def regime_ic(
    signal: pd.Series,
    target: pd.Series,
    vix: pd.Series,
) -> dict[str, dict]:
    """
    Compute IC per VIX tercile regime.
    Returns dict with keys 'calm', 'normal', 'stress'.
    """
    common = signal.dropna().index.intersection(target.dropna().index).intersection(vix.dropna().index)
    vix_aligned = vix.loc[common]
    q33, q66 = vix_aligned.quantile([1/3, 2/3])

    regimes = {
        "calm":   common[vix_aligned <= q33],
        "normal": common[(vix_aligned > q33) & (vix_aligned <= q66)],
        "stress": common[vix_aligned > q66],
    }

    results = {}
    for name, idx in regimes.items():
        ic = spearman_ic(signal.loc[idx], target.loc[idx])
        lo, hi = block_bootstrap_ci(signal.loc[idx], target.loc[idx], spearman_ic)
        results[name] = {"n": len(idx), "ic": ic, "ci_lo": lo, "ci_hi": hi}

    return results


# ---------------------------------------------------------------------------
# Per-year IC stability
# ---------------------------------------------------------------------------

def per_year_ic(signal: pd.Series, target: pd.Series) -> pd.DataFrame:
    """Compute Spearman IC for each calendar year. Returns DataFrame indexed by year."""
    common = signal.dropna().index.intersection(target.dropna().index)
    sig = signal.loc[common].dropna()
    tgt = target.loc[common].dropna()
    # Drop any NaT entries that may have crept in via reindex
    sig = sig[sig.index.notna()]
    tgt = tgt[tgt.index.notna()]
    if len(sig) < 10:
        return pd.DataFrame(columns=["ic", "n"])

    rows = []
    for year in range(int(sig.index.year.min()), int(sig.index.year.max()) + 1):
        mask = sig.index.year == year
        ic = spearman_ic(sig[mask], tgt[mask])
        rows.append({"year": year, "ic": ic, "n": int(mask.sum())})

    return pd.DataFrame(rows).set_index("year")


# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------

_HORIZONS = {
    "1d":  1,
    "1w":  7,
    "1m":  30,
    "3m":  90,
    "6m":  182,
}


def run_full_evaluation(
    signal_df: pd.DataFrame,
    spx: pd.Series,
    hy_oas: Optional[pd.Series],
    nfci: Optional[pd.Series],
    vix: Optional[pd.Series],
) -> dict:
    """
    Run the complete evaluation suite.

    Parameters
    ----------
    signal_df  : backtest output from backtest.run_backtest()
    spx        : S&P 500 price series (full history)
    hy_oas     : HY OAS series (may be None/short if restricted by FRED)
    nfci       : NFCI series
    vix        : VIX price series

    Returns
    -------
    Nested dict with structure:
      results["continuous"][horizon][target_name][metric_name] = value
      results["classifier"][horizon][event_name][metric_name] = value
      results["benchmarks"][signal_name][horizon][target_name]["ic"] = value
      results["regime"][horizon][target_name][regime_name] = {...}
      results["per_year"][horizon][target_name] = DataFrame
    """
    composite = signal_df["composite"].dropna()
    results: dict = {
        "continuous":  {},
        "classifier":  {},
        "benchmarks":  {},
        "regime":      {},
        "per_year":    {},
    }

    # ------------------------------------------------------------------
    # Build benchmark signals
    # ------------------------------------------------------------------
    benchmarks: dict[str, pd.Series] = {"composite": composite}

    if vix is not None:
        # VIX as percentile rank over 10-year rolling window (same methodology)
        vix_pct = vix.rolling(window=252 * 10, min_periods=252).rank(pct=True) * 100
        benchmarks["vix"] = vix_pct.reindex(composite.index, method="ffill")

    if hy_oas is not None and len(hy_oas) > 50:
        hy_pct = hy_oas.rolling(window=252 * 10, min_periods=252).rank(pct=True) * 100
        benchmarks["hy_oas"] = hy_pct.reindex(composite.index, method="ffill")

    if nfci is not None:
        nfci_pct = nfci.rolling(window=252 * 10, min_periods=252).rank(pct=True) * 100
        benchmarks["nfci"] = nfci_pct.reindex(composite.index, method="ffill")

    # 3-factor equal-weighted: VIX + HY OAS + yield curve
    _factors = []
    yc_col = f"rates_curve__yield_curve__pct"
    if yc_col in signal_df.columns:
        yc_pct = signal_df[yc_col].reindex(composite.index)
        # Yield curve is inverted in the model — high pct = inverted = stress
        _factors.append(yc_pct)
    if "vix" in benchmarks:
        _factors.append(benchmarks["vix"])
    if "hy_oas" in benchmarks:
        _factors.append(benchmarks["hy_oas"])
    if len(_factors) >= 2:
        benchmarks["3factor"] = pd.concat(_factors, axis=1).mean(axis=1)

    # ------------------------------------------------------------------
    # Iterate horizons
    # ------------------------------------------------------------------
    for horizon_label, horizon_days in _HORIZONS.items():
        results["continuous"][horizon_label] = {}
        results["classifier"][horizon_label] = {}
        results["regime"][horizon_label] = {}
        results["per_year"][horizon_label] = {}

        # Continuous targets
        targets_cont: dict[str, pd.Series] = {}

        spx_dd = build_forward_drawdown(spx.reindex(composite.index, method="ffill"), horizon_days)
        targets_cont["spx_drawdown"] = spx_dd

        if hy_oas is not None and len(hy_oas) > 50:
            hy_widen = build_forward_hy_widening(
                hy_oas.reindex(composite.index, method="ffill"), horizon_days
            )
            targets_cont["hy_widening"] = hy_widen

        if (hy_oas is not None and len(hy_oas) > 50
                and nfci is not None and vix is not None):
            stress_idx = build_stress_index(
                vix.reindex(composite.index, method="ffill"),
                hy_oas.reindex(composite.index, method="ffill"),
                nfci.reindex(composite.index, method="ffill"),
                horizon_days,
            )
            targets_cont["stress_index"] = stress_idx

        # Binary events (built once per script, reuse across horizons where applicable)
        spx_aligned = spx.reindex(composite.index, method="ffill")
        hy_aligned  = hy_oas.reindex(composite.index, method="ffill") if hy_oas is not None and len(hy_oas) > 50 else None
        events_df   = build_binary_events(spx_aligned, hy_aligned)

        # Continuous evaluation
        for tname, target in targets_cont.items():
            row = {}
            ic = spearman_ic(composite, target)
            pc = pearson_ic(composite, target)
            ew = ew_ic(composite, target)
            ew_equal = spearman_ic(composite, target)   # equal-weighted = plain spearman
            lo, hi = block_bootstrap_ci(composite, target, spearman_ic)
            row = {
                "spearman_ic": ic,
                "pearson_ic":  pc,
                "ew_ic_5yr":   ew,
                "ew_ic_equal": ew_equal,
                "ci_lo":       lo,
                "ci_hi":       hi,
                "n_obs":       int(composite.dropna().index.intersection(target.dropna().index).__len__()),
            }

            # ROC / PR
            for ename, events in events_df.items():
                auc_metrics = roc_pr_metrics(composite, events)
                row[f"roc_auc_{ename}"]   = auc_metrics.get("roc_auc")
                row[f"pr_auc_{ename}"]    = auc_metrics.get("pr_auc")
                row[f"lift10_{ename}"]    = auc_metrics.get("lift_top_decile")

            results["continuous"][horizon_label][tname] = row

            # Per-year IC stability
            results["per_year"][horizon_label][tname] = per_year_ic(composite, target)

            # Regime IC
            if vix is not None:
                results["regime"][horizon_label][tname] = regime_ic(
                    composite, target, vix.reindex(composite.index, method="ffill")
                )

        # Classifier evaluation (against binary events)
        for threshold in [50.0, 60.0, 70.0]:
            sig_bin = threshold_signal(composite, threshold)
            for ename, events in events_df.items():
                key = f"thresh_{int(threshold)}_{ename}"
                results["classifier"][horizon_label][key] = classifier_metrics(sig_bin, events)
                results["classifier"][horizon_label][key]["f0.5"] = (
                    classifier_metrics(sig_bin, events, beta=0.5).get("f0.5")
                )

        # Benchmark comparisons
        for bname, bsig in benchmarks.items():
            if bname not in results["benchmarks"]:
                results["benchmarks"][bname] = {}
            results["benchmarks"][bname][horizon_label] = {}
            for tname, target in targets_cont.items():
                ic = spearman_ic(bsig, target)
                lo, hi = block_bootstrap_ci(bsig, target, spearman_ic)
                results["benchmarks"][bname][horizon_label][tname] = {
                    "ic": ic, "ci_lo": lo, "ci_hi": hi
                }

    return results


# ---------------------------------------------------------------------------
# Summary table helpers
# ---------------------------------------------------------------------------

def headline_table(results: dict) -> pd.DataFrame:
    """
    Build the headline metrics table (BACKTEST_DESIGN.md §7a):
    rows = (target, horizon), columns = (composite IC, VIX IC, 3-factor IC, p-value proxy).
    """
    rows = []
    for horizon_label in _HORIZONS:
        for tname in results["continuous"].get(horizon_label, {}):
            cont = results["continuous"][horizon_label][tname]
            bench = results["benchmarks"]
            row = {
                "horizon":      horizon_label,
                "target":       tname,
                "composite_ic": cont.get("spearman_ic"),
                "ci_lo":        cont.get("ci_lo"),
                "ci_hi":        cont.get("ci_hi"),
                "vix_ic":       bench.get("vix", {}).get(horizon_label, {}).get(tname, {}).get("ic"),
                "3factor_ic":   bench.get("3factor", {}).get(horizon_label, {}).get(tname, {}).get("ic"),
                "n_obs":        cont.get("n_obs"),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def indicator_ic_table(signal_df: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    """
    Compute Spearman IC for every individual indicator score column vs one target.
    Returns DataFrame ranked by IC descending.
    """
    score_cols = [c for c in signal_df.columns if c.endswith("__score")]
    rows = []
    for col in score_cols:
        ic = spearman_ic(signal_df[col].dropna(), target)
        rows.append({"indicator": col.replace("__score", ""), "ic": ic})
    return pd.DataFrame(rows).sort_values("ic", ascending=False).reset_index(drop=True)
