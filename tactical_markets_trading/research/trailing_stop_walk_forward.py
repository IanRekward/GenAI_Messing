"""Sensitivity + walk-forward for the trailing-stop leveraged-trend strategy.

Question: are the 200-day MA + 10% trailing-stop parameters that produced 20% CAGR
robust, or did I get lucky? If nearby parameters perform similarly, robust. If
performance collapses one click in any direction, overfit.

Method:
  1. Grid: MA window in {50, 100, 150, 200, 250} × stop_pct in {0.05, 0.075, 0.10, 0.125, 0.15, 0.20}.
     30 combinations of the trailing-stop strategy on synthetic 3× QQQ (full 1999+ window).
  2. Compute full-window metrics for each combo.
  3. Walk-forward hold-out: TRAIN = 1999-2012, TEST = 2013-2026. Pick top-5 by Sharpe
     from TRAIN, see how they do on TEST. If TRAIN-best params survive on TEST,
     we have OOS evidence the strategy isn't overfit.
  4. Verify the synthetic matches real TQQQ where they overlap (2010-2026).

Output:
  research/data/trailing_stop_sensitivity.csv
  research/data/trailing_stop_walk_forward_report.md
"""
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from multi_strategy_extended import (
    ALL_TICKERS,
    INITIAL_NAV,
    TRADING_DAYS_PER_YEAR,
    add_synthetic_cash,
    add_synthetic_leveraged_to_prices,
    fetch_prices,
    metrics,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "data"

MA_WINDOWS = [50, 100, 150, 200, 250]
STOP_PCTS = [0.05, 0.075, 0.10, 0.125, 0.15, 0.20]

TRAIN_END = "2012-12-31"
TEST_START = "2013-01-01"


def run_trailing_stop(prices: pd.DataFrame, lev_ticker: str, cash_ticker: str,
                       ma_window: int, stop_pct: float) -> pd.Series:
    """Generic leveraged-trend + trailing-stop runner. Used by both research and (eventually) prod."""
    if lev_ticker not in prices.columns or cash_ticker not in prices.columns or "SPY" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    lev = prices[lev_ticker].dropna()
    cash = prices[cash_ticker].dropna()
    common = spy.index.intersection(lev.index).intersection(cash.index)
    spy, lev, cash = spy.loc[common], lev.loc[common], cash.loc[common]

    ma = spy.rolling(ma_window).mean()
    trend_on = (spy > ma).shift(1).fillna(False).astype(bool)
    lev_ret = lev.pct_change().fillna(0)
    cash_ret = cash.pct_change().fillna(0)

    holding = pd.Series(False, index=common)
    in_pos = False
    pos_peak = 0.0
    stopped_out = False
    for i in range(len(common)):
        price = lev.iloc[i]
        if in_pos:
            if price > pos_peak:
                pos_peak = price
            if price <= pos_peak * (1 - stop_pct):
                in_pos = False
                stopped_out = True
            elif not trend_on.iloc[i]:
                in_pos = False
        else:
            if trend_on.iloc[i] and not stopped_out:
                in_pos = True
                pos_peak = price
            elif stopped_out and not trend_on.iloc[i]:
                stopped_out = False
        holding.iloc[i] = in_pos
    daily_ret = lev_ret.where(holding, cash_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def run_grid(prices: pd.DataFrame, lev_ticker: str, cash_ticker: str,
              start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Run the full MA x stop grid on the given window."""
    rows = []
    sliced = prices.copy()
    if start:
        sliced = sliced.loc[start:]
    if end:
        sliced = sliced.loc[:end]
    for ma_w, stop_p in product(MA_WINDOWS, STOP_PCTS):
        nav = run_trailing_stop(sliced, lev_ticker, cash_ticker, ma_w, stop_p)
        if nav.empty:
            continue
        m = metrics(nav)
        rows.append({
            "ma_window": ma_w,
            "stop_pct": stop_p,
            **m,
        })
    return pd.DataFrame(rows)


def verify_synth_matches_real(prices: pd.DataFrame) -> dict:
    """Run identical strategy on SYNTH_3X_QQQ and TQQQ during their overlap (2010+).
    If results are similar, the synthetic is faithful; if not, the synthetic understates
    or overstates something important."""
    real_tqqq_start = prices["TQQQ"].dropna().index[0].strftime("%Y-%m-%d")
    print(f"  TQQQ available from {real_tqqq_start}")
    synth_nav = run_trailing_stop(prices, "SYNTH_3X_QQQ", "BIL_EXTENDED", 200, 0.10).loc[real_tqqq_start:]
    real_nav = run_trailing_stop(prices, "TQQQ", "BIL_EXTENDED", 200, 0.10).loc[real_tqqq_start:]
    common = synth_nav.index.intersection(real_nav.index)
    synth_nav = synth_nav.loc[common]
    real_nav = real_nav.loc[common]
    if len(common) < 100:
        return {"status": "insufficient overlap"}
    # Rebase both to 100 at start of overlap for clean comparison
    synth_rebased = synth_nav / synth_nav.iloc[0] * 100
    real_rebased = real_nav / real_nav.iloc[0] * 100
    return {
        "overlap_start": str(common[0].date()),
        "overlap_end": str(common[-1].date()),
        "overlap_days": len(common),
        "synth_metrics": metrics(synth_rebased),
        "real_metrics": metrics(real_rebased),
        "final_nav_diff_pct": round((real_rebased.iloc[-1] / synth_rebased.iloc[-1] - 1) * 100, 2),
    }


def write_report(full_df: pd.DataFrame, train_df: pd.DataFrame, test_results: pd.DataFrame,
                  verify: dict, output_path: Path) -> None:
    lines = [
        "# Trailing-Stop Strategy — Walk-Forward + Sensitivity Report",
        "",
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Question",
        "",
        "The strategy `synth_3x_qqq_trend_trailing_stop_10pct` earned 19.87% CAGR / Sharpe 0.96 / -32% MaxDD over 1999-2026. Were the 200-day MA + 10% trailing-stop parameters lucky picks, or robust across nearby choices?",
        "",
        "## Method",
        "",
        "1. **Sensitivity grid** — 5 MA windows × 6 stop percentages = 30 parameter combos run on synthetic 3× QQQ, full window (1999-2026).",
        "2. **Walk-forward hold-out** — TRAIN = 1999 to 2012; TEST = 2013 to 2026. Identify top-5 by Sharpe on TRAIN. Apply each to TEST without re-tuning.",
        "3. **Synthetic-vs-real verification** — Same strategy applied to SYNTH_3X_QQQ and real TQQQ during their 2010+ overlap. If results match, the synthetic is faithful.",
        "",
        "## Full-window sensitivity",
        "",
        "Each cell is the trailing-stop strategy run on synthetic 3× QQQ for the full 27-year window.",
        "",
    ]
    # Pivot: rows = ma_window, cols = stop_pct, values = CAGR
    pivot_cagr = full_df.pivot(index="ma_window", columns="stop_pct", values="cagr_pct")
    pivot_sharpe = full_df.pivot(index="ma_window", columns="stop_pct", values="sharpe")
    pivot_dd = full_df.pivot(index="ma_window", columns="stop_pct", values="max_drawdown_pct")
    lines.append("### CAGR (%) by (ma_window x stop_pct)")
    lines.append("")
    lines.append(pivot_cagr.to_markdown())
    lines.append("")
    lines.append("### Sharpe by (ma_window x stop_pct)")
    lines.append("")
    lines.append(pivot_sharpe.to_markdown())
    lines.append("")
    lines.append("### Max Drawdown (%) by (ma_window x stop_pct)")
    lines.append("")
    lines.append(pivot_dd.to_markdown())
    lines.append("")
    lines.append("### Top 10 by Sharpe (full window)")
    lines.append("")
    lines.append(full_df.nlargest(10, "sharpe").to_markdown(index=False))
    lines.append("")

    lines.append("## Walk-forward TRAIN -> TEST")
    lines.append("")
    lines.append(f"TRAIN: 1999-2012, TEST: 2013-2026. Top-5 by Sharpe on TRAIN, then applied to TEST.")
    lines.append("")
    lines.append("### TRAIN-top-5 (in-sample best)")
    lines.append("")
    top5_train = train_df.nlargest(5, "sharpe")
    lines.append(top5_train.to_markdown(index=False))
    lines.append("")
    lines.append("### Same params on TEST (out-of-sample)")
    lines.append("")
    lines.append(test_results.to_markdown(index=False))
    lines.append("")

    # Verdict
    best_train_sharpe = top5_train["sharpe"].max()
    best_test_sharpe = test_results["sharpe"].max()
    best_test_cagr = test_results["cagr_pct"].max()
    sharpe_retention = best_test_sharpe / best_train_sharpe if best_train_sharpe > 0 else 0

    lines.append("## Verdict")
    lines.append("")
    if sharpe_retention >= 0.7:
        lines.append(f"**Params are robust.** Best Sharpe on TRAIN: {best_train_sharpe:.2f}. Best Sharpe on TEST: {best_test_sharpe:.2f}. Retention: {sharpe_retention*100:.0f}%. Best CAGR on TEST: {best_test_cagr:.2f}%. The 200d MA + 10% stop combo (or nearby) survived out-of-sample — defensible to proceed.")
    elif sharpe_retention >= 0.5:
        lines.append(f"**Params are partially robust.** Sharpe retention {sharpe_retention*100:.0f}% means params degrade out-of-sample but don't collapse. Some overfit risk. Proceed with caution; expect realized performance to be 30-50% worse than backtest.")
    else:
        lines.append(f"**Params are overfit.** Sharpe collapsed from {best_train_sharpe:.2f} on TRAIN to {best_test_sharpe:.2f} on TEST (retention {sharpe_retention*100:.0f}%). The 200d MA + 10% stop result was lucky. Do NOT proceed with this strategy as-is — re-tune on TRAIN and re-test, or pick a different approach.")
    lines.append("")

    lines.append("## Synthetic-vs-real verification")
    lines.append("")
    if "status" in verify and verify["status"] == "insufficient overlap":
        lines.append("Insufficient overlap to verify.")
    else:
        lines.append(f"Overlap: {verify['overlap_start']} to {verify['overlap_end']} ({verify['overlap_days']} days)")
        lines.append("")
        lines.append("| metric | synthetic | real TQQQ |")
        lines.append("|---|---:|---:|")
        for k in ["cagr_pct", "sharpe", "max_drawdown_pct", "vol_pct"]:
            sv = verify["synth_metrics"].get(k, "?")
            rv = verify["real_metrics"].get(k, "?")
            lines.append(f"| {k} | {sv} | {rv} |")
        lines.append("")
        diff = verify["final_nav_diff_pct"]
        if abs(diff) < 10:
            lines.append(f"Final-NAV difference: {diff:+.2f}%. **Synthetic faithfully tracks real TQQQ.** The 1999-2009 synthetic backtest can be trusted.")
        elif abs(diff) < 25:
            lines.append(f"Final-NAV difference: {diff:+.2f}%. **Synthetic moderately tracks real TQQQ.** Some tracking error; results may overstate or understate by ~20%.")
        else:
            lines.append(f"Final-NAV difference: {diff:+.2f}%. **Synthetic does NOT track real TQQQ well.** Pre-2010 backtest is unreliable. Need to recalibrate synthetic or restrict to real-data window.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = fetch_prices(ALL_TICKERS)
    prices = add_synthetic_leveraged_to_prices(prices)
    prices = add_synthetic_cash(prices)

    print("=== Full-window sensitivity grid (30 combos) ===")
    t0 = time.time()
    full_df = run_grid(prices, "SYNTH_3X_QQQ", "BIL_EXTENDED")
    full_df.to_csv(OUTPUT_DIR / "trailing_stop_sensitivity.csv", index=False)
    print(f"  Done in {time.time() - t0:.0f}s. Top by Sharpe:")
    print(full_df.nlargest(5, "sharpe").to_string(index=False))
    print()

    print("=== TRAIN grid (1999-2012) ===")
    t0 = time.time()
    train_df = run_grid(prices, "SYNTH_3X_QQQ", "BIL_EXTENDED", end=TRAIN_END)
    print(f"  Done in {time.time() - t0:.0f}s. Top-5 by Sharpe on TRAIN:")
    print(train_df.nlargest(5, "sharpe").to_string(index=False))
    print()

    print("=== Applying TRAIN-top-5 to TEST (2013-2026) ===")
    top5 = train_df.nlargest(5, "sharpe")
    test_rows = []
    for _, r in top5.iterrows():
        ma_w, stop_p = int(r["ma_window"]), float(r["stop_pct"])
        nav = run_trailing_stop(prices.loc[TEST_START:], "SYNTH_3X_QQQ", "BIL_EXTENDED", ma_w, stop_p)
        m = metrics(nav)
        test_rows.append({
            "ma_window": ma_w,
            "stop_pct": stop_p,
            **m,
            "train_sharpe": r["sharpe"],
            "train_cagr_pct": r["cagr_pct"],
        })
    test_df = pd.DataFrame(test_rows)
    print(test_df.to_string(index=False))
    print()

    print("=== Synth vs real TQQQ verification ===")
    verify = verify_synth_matches_real(prices)
    print(f"  {verify}")
    print()

    write_report(full_df, train_df, test_df, verify, OUTPUT_DIR / "trailing_stop_walk_forward_report.md")
    print(f"Report: {OUTPUT_DIR / 'trailing_stop_walk_forward_report.md'}")


if __name__ == "__main__":
    main()
