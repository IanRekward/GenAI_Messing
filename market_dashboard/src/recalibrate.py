"""
Phase 5 — Recalibration script.

Reads backtest CSVs, computes per-indicator IC for both periods
(pre-2016 from subset model, post-2016 from full model), applies the Q4 2x2
matrix, and proposes (or applies) weight updates to config/weights.yaml.

2x2 matrix (BACKTEST_DESIGN.md §11 Q4):
  Historical strong (>=0.10) + Recent strong   → keep at current weight
  Historical strong           + Recent weak     → reduce to 0.25x (regime change)
  Historical weak             + Recent strong   → keep at current weight (new signal)
  Historical weak             + Recent weak     → drop entirely (set to 0)

Usage:
    python -m src.recalibrate              # preview only
    python -m src.recalibrate --apply      # write updated weights.yaml
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, ".")

_STRONG_IC = 0.10        # threshold for "strong" in 2x2 matrix
_REDUCE_FACTOR = 0.25    # multiplier when historical strong + recent weak
_SPLIT_DATE = "2016-01-01"


def _indicator_ic_series(df: pd.DataFrame, spx: pd.Series, horizon_days: int = 30) -> pd.Series:
    """
    For each indicator score column in df, compute Spearman IC vs forward SPX drawdown.
    Returns a Series keyed by indicator column name.
    """
    from scipy import stats as _stats

    # Build forward drawdown for each date in df
    spx_aligned = spx.reindex(df.index, method="ffill")
    dd = {}
    for t in df.index:
        end = t + pd.Timedelta(days=horizon_days)
        future = spx_aligned.loc[t:end]
        if len(future) < 2:
            dd[t] = np.nan
            continue
        p, tr = future.iloc[0], future.min()
        dd[t] = (p - tr) / p if p > 0 else np.nan
    fwd = pd.Series(dd)

    score_cols = [c for c in df.columns if c.endswith("__score")]
    results = {}
    for col in score_cols:
        sig = df[col].dropna()
        common = sig.index.intersection(fwd.dropna().index)
        if len(common) < 20:
            results[col] = np.nan
            continue
        r, _ = _stats.spearmanr(sig.loc[common].values, fwd.loc[common].values)
        results[col] = float(r)

    return pd.Series(results)


def _patch_weights_file(path: str, updates: dict[tuple[str, str], float]) -> None:
    """
    Edit weights.yaml in-place, replacing only indicator weight values.
    Preserves all comments, blank lines, and non-weight fields.

    Identifies each indicator by tracking bucket/indicator context via
    indentation and key names, then replaces the immediately-following
    'weight:' line value.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    out = []
    current_bucket: str | None = None
    current_indicator: str | None = None
    pending_weight_replace: float | None = None   # write this value on the next 'weight:' line

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Detect context from indentation + key structure (no value on same line, ends with ':')
        if stripped.endswith(":\n") and ":" not in stripped[:-2]:
            key = stripped[:-2].strip()
            if indent == 2:               # top-level bucket key
                current_bucket = key
                current_indicator = None
                pending_weight_replace = None
            elif indent == 6:             # indicator key (6 spaces under bucket.indicators)
                current_indicator = key
                # Check if this (bucket, indicator) has an update
                update = updates.get((current_bucket, current_indicator))
                pending_weight_replace = update   # may be None if no change needed

        # Replace the weight line if we're waiting for one
        if pending_weight_replace is not None and stripped.startswith("weight:"):
            # Build replacement, preserving the leading whitespace
            ws = " " * indent
            out.append(f"{ws}weight: {pending_weight_replace}\n")
            pending_weight_replace = None
            continue

        out.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def run_recalibration(
    full_csv: str = "output/backtest_full.csv",
    subset_csv: str = "output/backtest_subset.csv",
    weights_path: str = "config/weights.yaml",
    apply: bool = False,
) -> pd.DataFrame:
    """
    Compute IC for each indicator in both periods, apply the 2x2 matrix,
    and return a DataFrame summarising the proposed changes.

    If apply=True, write the updated weights back to weights_path.
    """
    # Load backtest data
    if not Path(full_csv).exists() or not Path(subset_csv).exists():
        raise FileNotFoundError(
            f"Backtest CSVs not found. Run backtest first:\n"
            f"  python -m src.backtest\n"
            f"Expected: {full_csv}, {subset_csv}"
        )

    df_full   = pd.read_csv(full_csv,   index_col=0, parse_dates=True)
    df_subset = pd.read_csv(subset_csv, index_col=0, parse_dates=True)

    # Load SPX from backtest cache
    from src.backtest import _bt_yf
    import os
    from dotenv import load_dotenv
    load_dotenv()
    env = dict(os.environ)

    spx = _bt_yf("^GSPC", env)

    # Recent = post-2016 (full model), Historical = pre-2016 (subset model)
    split = pd.Timestamp(_SPLIT_DATE)
    df_recent = df_full[df_full.index >= split]
    df_hist   = df_subset[df_subset.index <  split]

    print("Computing indicator IC (recent, post-2016)...")
    ic_recent = _indicator_ic_series(df_recent, spx)

    print("Computing indicator IC (historical, pre-2016)...")
    ic_hist   = _indicator_ic_series(df_hist, spx)

    # Load current weights
    weights = yaml.safe_load(open(weights_path))

    # Build summary table and proposed new weights
    rows = []
    for bkey, bcfg in weights["buckets"].items():
        for ikey, icfg in bcfg["indicators"].items():
            col = f"{bkey}__{ikey}__score"
            hist_ic   = ic_hist.get(col, np.nan)
            recent_ic = ic_recent.get(col, np.nan)
            cur_w = float(icfg["weight"])

            # Classify
            hist_strong   = (not np.isnan(hist_ic))   and hist_ic   >= _STRONG_IC
            recent_strong = (not np.isnan(recent_ic)) and recent_ic >= _STRONG_IC

            if hist_strong and recent_strong:
                action = "keep"
                new_w  = cur_w
            elif hist_strong and not recent_strong:
                action = "reduce"
                new_w  = round(cur_w * _REDUCE_FACTOR, 4)
            elif not hist_strong and recent_strong:
                action = "keep (new signal)"
                new_w  = cur_w
            else:
                action = "drop"
                new_w  = 0.0

            # If data wasn't available for a period, don't penalize the indicator
            if np.isnan(hist_ic):
                action = "keep (no hist data)"
                new_w  = cur_w
            if np.isnan(recent_ic):
                action = "keep (no recent data)"
                new_w  = cur_w

            rows.append({
                "bucket":    bkey,
                "indicator": ikey,
                "hist_ic":   round(hist_ic,   4) if not np.isnan(hist_ic)   else None,
                "recent_ic": round(recent_ic, 4) if not np.isnan(recent_ic) else None,
                "current_weight": cur_w,
                "proposed_weight": new_w,
                "action":    action,
            })

    df_summary = pd.DataFrame(rows)

    # Re-normalise within each bucket so weights still sum to 1.0
    updated_weights = copy.deepcopy(weights)
    for bkey, bcfg in updated_weights["buckets"].items():
        bucket_rows = df_summary[df_summary["bucket"] == bkey]
        total = bucket_rows["proposed_weight"].sum()
        if total <= 0:
            print(f"  Warning: all indicators dropped in bucket '{bkey}'. Keeping originals.")
            continue
        for ikey in bcfg["indicators"]:
            mask = (df_summary["bucket"] == bkey) & (df_summary["indicator"] == ikey)
            raw_w = df_summary.loc[mask, "proposed_weight"].values[0]
            norm_w = round(raw_w / total, 4) if total > 0 else 0.0
            df_summary.loc[mask, "normalised_weight"] = norm_w
            if apply:
                bcfg["indicators"][ikey]["weight"] = norm_w

    # Print summary
    print("\n=== Recalibration Summary ===\n")
    print(df_summary.to_string(index=False))
    print(f"\nIndicators to drop:  {(df_summary['action']=='drop').sum()}")
    print(f"Indicators to reduce: {(df_summary['action']=='reduce').sum()}")
    print(f"Indicators to keep:  {(df_summary['action'].str.startswith('keep')).sum()}")

    if apply:
        # Build map of (bucket, indicator) -> new normalised weight (plain Python float)
        weight_updates: dict[tuple[str, str], float] = {}
        for _, row in df_summary.iterrows():
            nw = row.get("normalised_weight")
            if nw is not None and not (isinstance(nw, float) and np.isnan(nw)):
                weight_updates[(row["bucket"], row["indicator"])] = float(round(float(nw), 4))

        _patch_weights_file(weights_path, weight_updates)
        print(f"\nWeights patched in-place in {weights_path} (comments preserved).")
        print("Re-run the dashboard to use the new weights.")
    else:
        print("\nPreview only.  Run with --apply to write updated weights.yaml.")

    return df_summary


_MULT_CLIP_LOW  = 0.3
_MULT_CLIP_HIGH = 2.0
_REGIME_MIN_DAYS    = 30   # below this, force multiplier to 1.0 (insufficient data)
_REGIME_SHRINK_DAYS = 50   # below this, shrink toward 1.0 (Bayesian-style)


def propose_regime_weights(
    full_csv: str = "output/backtest_full.csv",
    weights_path: str = "config/weights.yaml",
) -> None:
    """
    Compute per-regime per-bucket IC from the backtest CSV and print a
    proposed regime_weights: YAML block to stdout.

    Does NOT write to weights.yaml — that's a manual review step.
    Requires the backtest CSV to have a 'regime' column (Brief 10B backtest run).
    """
    from src.evaluation import per_regime_bucket_ic
    from src.backtest import _bt_yf
    import os
    from dotenv import load_dotenv

    if not Path(full_csv).exists():
        print(
            f"ERROR: {full_csv} not found. Run backtest first:\n  python -m src.backtest",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(full_csv, index_col=0, parse_dates=True)
    if "regime" not in df.columns:
        print(
            "ERROR: backtest CSV has no 'regime' column.\n"
            "Re-run: python -m src.backtest  (requires Brief 10B upgrade)",
            file=sys.stderr,
        )
        sys.exit(1)

    load_dotenv()
    env = dict(os.environ)
    spx = _bt_yf("^GSPC", env)

    print("Computing per-regime bucket IC...")
    ic_df = per_regime_bucket_ic(df, spx, horizon_days=21)

    print("\nPer-regime per-bucket Spearman IC:\n")
    print(ic_df.to_string())

    regime_counts = df["regime"].value_counts()

    multipliers: dict[str, dict[str, float]] = {}
    for regime in ["low", "mid", "high"]:
        multipliers[regime] = {}
        n_days = int(regime_counts.get(regime, 0))
        for bucket in ic_df.index:
            ic_val = ic_df.loc[bucket, regime]
            if np.isnan(ic_val) or n_days < _REGIME_MIN_DAYS:
                multipliers[regime][bucket] = 1.0
                continue
            mean_ic = ic_df.loc[bucket].dropna().mean()
            if np.isnan(mean_ic) or abs(mean_ic) < 1e-6:
                multipliers[regime][bucket] = 1.0
                continue
            raw_mult = float(np.clip(ic_val / mean_ic, _MULT_CLIP_LOW, _MULT_CLIP_HIGH))
            if n_days < _REGIME_SHRINK_DAYS:
                w = n_days / _REGIME_SHRINK_DAYS
                raw_mult = w * raw_mult + (1.0 - w) * 1.0
            multipliers[regime][bucket] = round(raw_mult, 2)

    block = {
        "regime_weights": {
            "enabled": False,
            "classifier": {
                "type": "vix_tercile",
                "smoothing_days": 5,
                "hysteresis_vix": 1.0,
            },
            "multipliers": {
                r: {k: float(v) for k, v in multipliers[r].items()}
                for r in ["low", "mid", "high"]
            },
        }
    }

    print("\n\n# === Proposed regime_weights block (paste into config/weights.yaml) ===")
    print("# Review carefully before accepting. Set enabled: true in Brief 10C after review.")
    print("# Re-run `python -m src.recalibrate --regime` to regenerate.\n")
    print(yaml.dump(block, default_flow_style=False, sort_keys=False))
    print("# weights.yaml was NOT modified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recalibrate indicator weights from backtest IC")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true",
                       help="Write updated weights to config/weights.yaml")
    group.add_argument("--regime", action="store_true",
                       help="Propose regime_weights: block (preview only, no file writes)")
    args = parser.parse_args()
    if args.regime:
        propose_regime_weights()
    else:
        run_recalibration(apply=args.apply)
